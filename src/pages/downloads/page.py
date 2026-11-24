import asyncio
from gettext import gettext as _
from pathlib import Path

from gi.repository import Adw, Gio, GLib, GObject, Gtk

from ...components.file_grid import file_icon
from ...integrations import models
from ...integrations.nuvio import isVideo
from ...performance import timed

FILE_ATTRIBUTES = "standard::display-name,standard::type,standard::icon,standard::is-hidden"
BATCH_SIZE = 200
RELOAD_DELAY_MS = 300
FOLDER_EVENTS = (
    Gio.FileMonitorEvent.CREATED,
    Gio.FileMonitorEvent.DELETED,
    Gio.FileMonitorEvent.MOVED_IN,
    Gio.FileMonitorEvent.MOVED_OUT,
    Gio.FileMonitorEvent.RENAMED,
)


class FolderEntry(GObject.Object):
    __gtype_name__ = "ChelseaFolderEntry"

    def __init__(self, name: str, file: Gio.File, icon: Gio.Icon, is_folder: bool = False, download=None):
        super().__init__()
        self.name = name
        self.file = file
        self.icon = icon
        self.is_folder = is_folder
        self.download = download


def status_text(item) -> str:
    if item.state == "failed":
        return _("Failed")
    text = GLib.format_size(item.downloaded)
    if item.size:
        text = _("{done} of {total}").format(done=text, total=GLib.format_size(item.size))
    if item.state == "paused":
        text = _("Paused · {}").format(text)
    return text


def show_download(cell, item):
    if item.state == "done":
        cell.show_status()
    else:
        cell.show_status(status_text(item), item.progress)


@Gtk.Template(resource_path='/io/github/riyaniii/Chelsea/pages/downloads/page.ui')
class DownloadsPage(Adw.Bin):
    __gtype_name__ = "ChelseaDownloadsPage"

    path_bar = Gtk.Template.Child()
    history = Gtk.Template.Child()
    stack = Gtk.Template.Child()
    empty_page = Gtk.Template.Child()
    file_grid = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.downloads = Gio.Application.get_default().downloads
        self.root = Gio.File.new_for_path(str(self.downloads.folder()))
        self.folder = self.root
        self.store = Gio.ListStore(item_type=FolderEntry)
        self.file_grid.set_files(self.store, self.bind_cell)
        self.monitor = None
        self.load_task = None
        self.reload_source = 0
        self.downloads.store.connect("items-changed", lambda *args: self.schedule_reload())
        self.connect("map", lambda page: self.show_folder(self.folder))
        self.history.reset(self.root)
        self.history.listen_to_mouse(self)
        self.add_actions()

    def add_actions(self):
        self.actions = Gio.SimpleActionGroup()
        for name, callback in (("open", self.open_selected), ("pause", self.pause_selected),
                               ("resume", self.resume_selected), ("trash", self.trash_selected)):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda action, value, callback=callback: callback())
            self.actions.add_action(action)
        open_in_files = Gio.SimpleAction.new("open-in-files", None)
        open_in_files.connect("activate", lambda action, value: self.launch(self.folder))
        self.actions.add_action(open_in_files)
        self.insert_action_group("downloads", self.actions)

        folder_menu = Gio.Menu()
        folder_menu.append(_("Open in Files"), "downloads.open-in-files")
        self.path_bar.set_menu(folder_menu)

        menu = Gio.Menu()
        menu.append(_("Open"), "downloads.open")
        menu.append(_("Pause"), "downloads.pause")
        menu.append(_("Resume"), "downloads.resume")
        trash_section = Gio.Menu()
        trash_section.append(_("Move to Trash"), "downloads.trash")
        menu.append_section(None, trash_section)
        self.file_grid.set_menu(menu)

        shortcuts = Gtk.ShortcutController()
        shortcuts.add_shortcut(Gtk.Shortcut.new(Gtk.ShortcutTrigger.parse_string("Delete"),
                                                Gtk.NamedAction.new("downloads.trash")))
        self.add_controller(shortcuts)

    def open_folder(self, folder: Gio.File):
        self.history.visit(folder)
        self.show_folder(folder)

    def show_folder(self, folder: Gio.File):
        self.folder = folder
        inside = self.root.get_relative_path(folder)
        names = [_("Downloads")] + (inside.split("/") if inside else [])
        self.path_bar.set_folders(names, "folder-download-symbolic")
        if self.monitor is not None:
            self.monitor.cancel()
        try:
            folder.make_directory_with_parents(None)
        except GLib.Error:
            pass
        self.monitor = folder.monitor_directory(Gio.FileMonitorFlags.WATCH_MOVES, None)
        self.monitor.connect("changed", self.on_folder_changed)
        self.reload()

    def schedule_reload(self):
        if self.reload_source:
            GLib.source_remove(self.reload_source)
        self.reload_source = GLib.timeout_add(RELOAD_DELAY_MS, self.reload)

    def reload(self):
        self.reload_source = 0
        if self.load_task is not None:
            self.load_task.cancel()
        self.load_task = asyncio.create_task(self.load_entries(self.folder))
        return GLib.SOURCE_REMOVE

    async def load_entries(self, folder: Gio.File):
        downloads = {item.path: item for item in self.downloads.store}
        entries = []
        with timed(f"listing {folder.get_path()}"):
            try:
                enumerator = await folder.enumerate_children_async(
                    FILE_ATTRIBUTES, Gio.FileQueryInfoFlags.NONE, GLib.PRIORITY_DEFAULT)
                while True:
                    infos = await enumerator.next_files_async(BATCH_SIZE, GLib.PRIORITY_DEFAULT)
                    if not infos:
                        break
                    for info in infos:
                        if not info.get_is_hidden():
                            entries.append(self.make_entry(folder, info, downloads))
            except GLib.Error as error:
                print(f"downloads: could not list {folder.get_path()}: {error.message}")
        listed = {entry.file.get_path() for entry in entries}
        for path, item in downloads.items():
            if Path(path).parent == Path(folder.get_path()) and path not in listed:
                name = Path(path).name
                entries.append(FolderEntry(name, Gio.File.new_for_path(path), file_icon(name), download=item))
        entries.sort(key=lambda entry: (not entry.is_folder, entry.name.lower()))
        self.store.splice(0, self.store.get_n_items(), entries)
        self.update_empty_page()

    def make_entry(self, folder: Gio.File, info: Gio.FileInfo, downloads: dict) -> FolderEntry:
        file = folder.get_child(info.get_name())
        is_folder = info.get_file_type() == Gio.FileType.DIRECTORY
        return FolderEntry(info.get_display_name(), file, info.get_icon(), is_folder,
                           downloads.get(file.get_path()))

    def update_empty_page(self):
        if self.store.get_n_items():
            self.stack.set_visible_child_name("files")
            return
        if self.folder.equal(self.root):
            self.empty_page.set_title(_("No Downloads"))
            self.empty_page.set_description(_("Use the menu next to a stream to save it for offline viewing"))
        else:
            self.empty_page.set_title(_("Folder Is Empty"))
            self.empty_page.set_description("")
        self.stack.set_visible_child_name("empty")

    def bind_cell(self, cell, entry):
        cell.show_file(entry.name, entry.icon)
        if entry.download is not None:
            show_download(cell, entry.download)
            cell.watch(entry.download, "notify", lambda item, pspec: show_download(cell, item))

    def open_entry(self, entry):
        if entry.is_folder:
            self.open_folder(entry.file)
        elif entry.download is not None and entry.download.state != "done":
            if entry.download.state in ("paused", "failed"):
                self.downloads.start(entry.download)
        elif isVideo(entry.name):
            self.play(entry.file)
        else:
            self.launch(entry.file)

    def launch(self, file: Gio.File):
        def done(launcher, result):
            try:
                launcher.launch_finish(result)
            except GLib.Error as error:
                print(f"downloads: could not open {file.get_path()}: {error.message}")
                Gio.Application.get_default().activate_action(
                    "show_toast", GLib.Variant("s", _("Could not open {}").format(file.get_basename())))

        Gtk.FileLauncher(file=file).launch(self.get_root(), None, done)

    def play(self, file: Gio.File):
        name = Path(file.get_path()).stem
        meta = models.Meta()
        meta.update_data(id=file.get_uri(), type="other", name=name)
        stream = models.Stream(name=name, url=file.get_path())
        from ..player import PlayerPage
        self.get_root().main_nav_view.push(PlayerPage(meta, None, file.get_uri(), stream))

    def selected_downloads(self, *states) -> list:
        entries = self.file_grid.selected_items()
        return [entry.download for entry in entries if entry.download is not None and entry.download.state in states]

    def open_selected(self):
        entries = self.file_grid.selected_items()
        if len(entries) == 1:
            self.open_entry(entries[0])

    def pause_selected(self):
        for item in self.selected_downloads("downloading"):
            self.downloads.pause(item)

    def resume_selected(self):
        for item in self.selected_downloads("paused", "failed"):
            self.downloads.start(item)

    def trash_selected(self):
        entries = self.file_grid.selected_items()
        for entry in entries:
            if entry.download is not None:
                self.downloads.remove(entry.download, delete_file=False)
            entry.file.trash_async(GLib.PRIORITY_DEFAULT, None, self.on_trashed, entry)

    def on_trashed(self, file, result, entry):
        try:
            file.trash_finish(result)
        except GLib.Error as error:
            if not error.matches(Gio.io_error_quark(), Gio.IOErrorEnum.NOT_FOUND):
                Gio.Application.get_default().activate_action(
                    "show_toast", GLib.Variant("s", _("Could not move {} to the trash").format(entry.name)))
                return
        self.schedule_reload()

    @Gtk.Template.Callback()
    def on_file_activated(self, grid, entry):
        self.open_entry(entry)

    @Gtk.Template.Callback()
    def on_menu_opening(self, grid):
        entries = self.file_grid.selected_items()
        self.actions.lookup_action("open").set_enabled(len(entries) == 1)
        self.actions.lookup_action("pause").set_enabled(bool(self.selected_downloads("downloading")))
        self.actions.lookup_action("resume").set_enabled(bool(self.selected_downloads("paused", "failed")))

    def on_folder_changed(self, monitor, file, other_file, event):
        if event in FOLDER_EVENTS:
            self.schedule_reload()

    @Gtk.Template.Callback()
    def on_folder_selected(self, path_bar, depth):
        folder = self.root
        inside = self.root.get_relative_path(self.folder)
        for name in (inside.split("/") if inside else [])[:depth]:
            folder = folder.get_child(name)
        self.open_folder(folder)

    @Gtk.Template.Callback()
    def on_location_chosen(self, history, folder):
        self.show_folder(folder)

import asyncio
from gettext import gettext as _

from gi.repository import Adw, Gio, GObject, Gtk

from ..integrations.nuvio import isVideo, magnetUri
from .file_grid import file_icon
from .link_dialog import play_link


class TorrentEntry(GObject.Object):
    __gtype_name__ = "ChelseaTorrentEntry"

    def __init__(self, name: str, file=None):
        super().__init__()
        self.name = name
        self.file = file
        self.is_folder = file is None


def split_path(path: str) -> tuple:
    return tuple(part for part in path.split("/") if part)


def folder_entries(files: list, folder: tuple) -> list:
    folders = []
    items = []
    for item in files:
        parts = split_path(item.path)
        if parts[:len(folder)] != folder or len(parts) <= len(folder):
            continue
        rest = parts[len(folder):]
        if len(rest) > 1:
            if rest[0] not in folders:
                folders.append(rest[0])
        else:
            items.append(TorrentEntry(rest[0], item))
    folders.sort(key=str.lower)
    items.sort(key=lambda entry: entry.name.lower())
    return [TorrentEntry(name) for name in folders] + items


@Gtk.Template(resource_path='/io/github/riyaniii/Chelsea/components/magnet_dialog.ui')
class MagnetDialog(Adw.Dialog):
    __gtype_name__ = "ChelseaMagnetDialog"

    path_bar = Gtk.Template.Child()
    history = Gtk.Template.Child()
    stack = Gtk.Template.Child()
    file_grid = Gtk.Template.Child()
    error_page = Gtk.Template.Child()

    def __init__(self, link, **kwargs):
        super().__init__(**kwargs)
        self.app = Gio.Application.get_default()
        self.link = link
        self.files = []
        self.base = ()
        self.folder = ()
        self.store = Gio.ListStore(item_type=TorrentEntry)
        self.file_grid.set_files(self.store, self.bind_cell)
        self.set_title(link.name or _("Magnet Link"))
        self.path_bar.set_folders([self.get_title()], "folder-symbolic")
        self.history.listen_to_mouse(self)
        self.task = asyncio.create_task(self.load())

    async def load(self):
        engine = self.app.engine
        link = self.link
        try:
            if not self.app.start_engine():
                raise RuntimeError(engine.error)
            torrent_id = await engine.addTorrent(magnetUri(link.info_hash, link.trackers, link.name))
            await engine.waitForMetadata(torrent_id)
            self.files = engine.getFiles(torrent_id)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self.error_page.set_description(str(error))
            self.stack.set_visible_child_name("error")
            return
        entries = folder_entries(self.files, self.base)
        while len(entries) == 1 and entries[0].is_folder:
            self.base = self.base + (entries[0].name,)
            entries = folder_entries(self.files, self.base)
        if not link.name and self.base:
            self.set_title(self.base[-1])
        self.history.reset(self.base)
        self.show_folder(self.base)
        self.stack.set_visible_child_name("files")

    def open_folder(self, folder: tuple):
        self.history.visit(folder)
        self.show_folder(folder)

    def show_folder(self, folder: tuple):
        self.folder = folder
        self.store.splice(0, self.store.get_n_items(), folder_entries(self.files, folder))
        inside = folder[len(self.base):]
        self.path_bar.set_folders([self.get_title()] + list(inside), "folder-symbolic")

    def bind_cell(self, cell, entry):
        cell.show_file(entry.name, file_icon(entry.name, entry.is_folder))

    @Gtk.Template.Callback()
    def on_file_activated(self, grid, entry):
        if entry.is_folder:
            self.open_folder(self.folder + (entry.name,))
        elif isVideo(entry.file.path):
            self.close()
            play_link(self.link, entry.file)

    @Gtk.Template.Callback()
    def on_folder_selected(self, path_bar, depth):
        self.open_folder(self.base + self.folder[len(self.base):][:depth])

    @Gtk.Template.Callback()
    def on_location_chosen(self, history, folder):
        self.show_folder(folder)

    @Gtk.Template.Callback()
    def on_closed(self, dialog):
        if not self.task.done():
            self.task.cancel()

from gettext import gettext as _
from pathlib import Path

from gi.repository import Adw, Gio, GLib, Gtk

from ...integrations import models

from .row import DownloadRow


@Gtk.Template(resource_path='/io/github/riyaniii/Chelsea/pages/downloads/page.ui')
class DownloadsPage(Adw.Bin):
    __gtype_name__ = "ChelseaDownloadsPage"

    stack = Gtk.Template.Child()
    list = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.downloads = Gio.Application.get_default().downloads
        self.list.set_model(Gtk.NoSelection(model=self.downloads.store))
        self.downloads.store.connect("items-changed", lambda *args: self.update_state())
        self.update_state()

    def update_state(self):
        self.stack.set_visible_child_name("list" if self.downloads.store.get_n_items() else "empty")

    def toggle(self, item):
        if item.state == "downloading":
            self.downloads.pause(item)
        elif item.state == "done":
            self.play(item)
        else:
            self.downloads.start(item)

    def play(self, item):
        file = Gio.File.new_for_path(item.path)
        name = Path(item.path).stem
        meta = models.Meta()
        meta.update_data(id=file.get_uri(), type="other", name=name)
        stream = models.Stream(name=name, url=item.path)
        from ..player import PlayerPage
        self.get_root().main_nav_view.push(PlayerPage(meta, None, file.get_uri(), stream))

    def open_folder(self, folder: Path):
        def done(launcher, result):
            try:
                launcher.launch_finish(result)
            except GLib.Error as error:
                print(f"downloads: could not open {folder}: {error.message}")
                Gio.Application.get_default().activate_action(
                    "show_toast", GLib.Variant("s", _("Could not open the downloads folder")))

        Gtk.FileLauncher(file=Gio.File.new_for_path(str(folder))).launch(self.get_root(), None, done)

    def remove(self, item):
        if item.state == "done":
            self.downloads.remove(item, delete_file=False)
            return
        dialog = Adw.AlertDialog(heading=_("Remove Download?"),
                                 body=_("The unfinished file is deleted."))
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("remove", _("Remove"))
        dialog.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", lambda d, response: response == "remove"
                       and self.downloads.remove(item, delete_file=True))
        dialog.present(self.get_root())

    @Gtk.Template.Callback()
    def on_setup(self, factory, list_item):
        list_item.set_child(DownloadRow(self))

    @Gtk.Template.Callback()
    def on_bind(self, factory, list_item):
        list_item.get_child().model = list_item.get_item()

    @Gtk.Template.Callback()
    def on_unbind(self, factory, list_item):
        list_item.get_child().model = None

    @Gtk.Template.Callback()
    def on_open_folder_clicked(self, button):
        folder = self.downloads.folder()
        folder.mkdir(parents=True, exist_ok=True)
        self.open_folder(folder)

    @Gtk.Template.Callback()
    def on_clear_clicked(self, button):
        self.downloads.clear_finished()

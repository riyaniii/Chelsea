from gettext import gettext as _
from pathlib import Path

from gi.repository import GLib, GObject, Gtk

from ...integrations import models


@Gtk.Template(resource_path='/io/github/riyaniii/Chelsea/pages/downloads/row.ui')
class DownloadRow(Gtk.Box):
    __gtype_name__ = "ChelseaDownloadRow"

    model = GObject.Property(type=models.Download)

    def __init__(self, page, **kwargs):
        super().__init__(**kwargs)
        self.page = page

    @Gtk.Template.Callback()
    def name_text(self, obj, path):
        return Path(path).name if path else ""

    @Gtk.Template.Callback()
    def size_text(self, obj, state, downloaded, size):
        if state == "done":
            return GLib.format_size(size or downloaded)
        if state == "failed":
            return _("Failed")
        text = GLib.format_size(downloaded)
        if size:
            text = _("{done} of {total}").format(done=text, total=GLib.format_size(size))
        return text

    @Gtk.Template.Callback()
    def unfinished(self, obj, state):
        return state != "done"

    @Gtk.Template.Callback()
    def toggle_icon(self, obj, state):
        if state == "downloading":
            return "cine-playback-pause-symbolic"
        if state == "failed":
            return "view-refresh-symbolic"
        return "cine-playback-start-symbolic"

    @Gtk.Template.Callback()
    def toggle_tooltip(self, obj, state):
        return {"downloading": _("Pause"), "done": _("Play"), "failed": _("Retry")}.get(state, _("Resume"))

    @Gtk.Template.Callback()
    def on_toggle_clicked(self, button):
        self.page.toggle(self.model)

    @Gtk.Template.Callback()
    def on_remove_clicked(self, button):
        self.page.remove(self.model)

from gettext import gettext as _

from gi.repository import Gio, GLib, Gtk

from ..downloads import default_folder


def folder_label(settings) -> str:
    return settings.get_string("download-folder") or str(default_folder())


def choose_folder(parent, settings, row):
    def chosen(dialog, result):
        try:
            folder = dialog.select_folder_finish(result)
        except GLib.Error:
            return
        settings.set_string("download-folder", folder.get_path())
        row.set_subtitle(folder_label(settings))

    Gtk.FileDialog(title=_("Download Location")).select_folder(parent, None, chosen)

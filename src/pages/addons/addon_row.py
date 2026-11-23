import asyncio

from gi.repository import Adw, GObject, Gtk

from ...integrations import models


@Gtk.Template(resource_path='/io/github/riyaniii/Chelsea/pages/addons/addon_row.ui')
class AddonRow(Gtk.Box):
    __gtype_name__ = "ChelseaAddonRow"

    model = GObject.Property(type=models.Addon)

    def __init__(self, page, **kwargs):
        super().__init__(**kwargs)
        self.page = page
        self.task = None

    @Gtk.Template.Callback()
    def action_page(self, obj, busy, installed, is_protected):
        if busy:
            return "busy"
        if not installed:
            return "install"
        return "required" if is_protected else "remove"

    @Gtk.Template.Callback()
    def on_configure_clicked(self, button):
        self.page.configure(self.model)

    @Gtk.Template.Callback()
    def on_action_clicked(self, button):
        addon = self.model
        if addon.installed:
            asyncio.create_task(self.page.remove(addon))
        elif addon.configuration_required:
            self.page.configure(addon)
        else:
            asyncio.create_task(self.page.install(addon.transport_url, addon))

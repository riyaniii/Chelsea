import asyncio
from gettext import gettext as _

from gi.repository import Adw, Gio, GLib, Gtk

from ...components import links
from ...components.link_dialog import LinkDialog
from ...integrations import models
from ...integrations.endpoints import addonBase, isAddonLink
from .addon_row import AddonRow


@Gtk.Template(resource_path='/io/github/riyaniii/Chelsea/pages/addons/page.ui')
class AddonsPage(Adw.Bin):
    __gtype_name__ = "ChelseaAddonsPage"

    search_entry = Gtk.Template.Child()
    stack = Gtk.Template.Child()
    scroller = Gtk.Template.Child()
    list = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        app = Gio.Application.get_default()
        self.integration = app.integration
        self.images = app.images
        self.catalog = Gio.ListStore(item_type=models.Addon)
        self.catalog_task = None

        self.filter = Gtk.CustomFilter.new(self.matches)
        self.available_filter = Gtk.CustomFilter.new(lambda addon: not addon.installed and self.matches(addon))
        self.sections = [
            (_("Installed"), Gtk.FilterListModel(model=self.integration.addons, filter=self.filter)),
            (_("Discover Addons"), Gtk.FilterListModel(model=self.catalog, filter=self.available_filter)),
        ]
        models_store = Gio.ListStore(item_type=Gio.ListModel)
        for title, model in self.sections:
            models_store.append(model)
        self.list.set_model(Gtk.NoSelection(model=Gtk.FlattenListModel(model=models_store)))

        self.integration.connect("notify::addons-revision", lambda *args: self.sync_installed())
        self.connect("map", self.on_map)

    def on_map(self, widget):
        GLib.idle_add(self.scroll_to_top)
        if self.catalog_task is None and not self.catalog.get_n_items():
            self.catalog_task = asyncio.create_task(self.load_catalog())

    def scroll_to_top(self):
        self.scroller.get_vadjustment().set_value(0)
        return GLib.SOURCE_REMOVE

    def show_link(self, url: str):
        LinkDialog(links.Link("addon", url)).present(self.get_root())

    async def load_catalog(self):
        try:
            addons = await self.integration.getAddonCatalog()
        except Exception as error:
            self.toast(_("Could not load the addon catalog"))
            print(f"addon catalog: {error}")
            self.catalog_task = None
            return
        self.catalog.splice(0, 0, addons)
        self.sync_installed()
        GLib.idle_add(self.scroll_to_top)

    def sync_installed(self):
        installed = {addon.transport_url for addon in self.integration.addons}
        for addon in self.catalog:
            addon.installed = addon.transport_url in installed
        self.refilter()

    def refilter(self):
        self.filter.changed(Gtk.FilterChange.DIFFERENT)
        self.available_filter.changed(Gtk.FilterChange.DIFFERENT)

    def matches(self, addon):
        text = self.search_entry.get_text().strip()
        if not text:
            return True
        query = text.lower()
        return query in addon.name.lower() or query in (addon.description or "").lower()

    def toast(self, message: str):
        Gio.Application.get_default().activate_action("show_toast", GLib.Variant("s", message))


    async def install(self, transport_url: str, addon=None):
        if addon is not None:
            addon.busy = True
        try:
            installed = await self.integration.installAddon(transport_url)
        except Exception as error:
            self.toast(_("Could not install the addon: {}").format(error))
            return False
        finally:
            if addon is not None:
                addon.busy = False
        self.sync_installed()
        self.toast(_("Installed {}").format(installed.name))
        return True

    async def remove(self, addon):
        addon.busy = True
        try:
            await self.integration.removeAddon(addon)
        except Exception as error:
            self.toast(_("Could not remove the addon: {}").format(error))
            return
        finally:
            addon.busy = False
        self.sync_installed()
        self.toast(_("Removed {}").format(addon.name))

    def configure(self, addon):
        uri = addonBase(addon.transport_url) + "/configure"
        Gio.Application.get_default().activate_action("open_uri", GLib.Variant("s", uri))


    def section_title(self, position: int) -> str:
        for title, model in self.sections:
            count = model.get_n_items()
            if position < count:
                return title
            position -= count
        return ""

    @Gtk.Template.Callback()
    def on_setup(self, factory, list_item):
        list_item.set_activatable(True)
        list_item.set_child(AddonRow(self))

    @Gtk.Template.Callback()
    def on_bind(self, factory, list_item):
        row = list_item.get_child()
        row.model = list_item.get_item()
        row.task = self.images.startThumbnail(row.model, "logo", "paintable")

    @Gtk.Template.Callback()
    def on_unbind(self, factory, list_item):
        row = list_item.get_child()
        self.images.stopThumbnail(row.model, row.task)
        row.task = None
        row.model = None

    @Gtk.Template.Callback()
    def on_activate(self, listview, position):
        addon = listview.get_model().get_item(position)
        if addon.configurable:
            self.configure(addon)

    @Gtk.Template.Callback()
    def on_header_setup(self, factory, header):
        header.set_child(Gtk.Label(xalign=0, css_classes=["title-4"],
                                   margin_top=18, margin_bottom=6, margin_start=6))

    @Gtk.Template.Callback()
    def on_header_bind(self, factory, header):
        header.get_child().set_label(self.section_title(header.get_start()))

    @Gtk.Template.Callback()
    def on_search_changed(self, entry):
        text = entry.get_text().strip()
        if isAddonLink(text):
            entry.set_text("")
            self.show_link(text)
            return
        self.refilter()

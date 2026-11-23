import asyncio
from gettext import gettext as _

from gi.repository import Adw, Gio, Gtk

from ...components import Grid
from ...components.formats import type_title
from ...integrations import models

ALL_GENRES = _("All Genres")


def string_list(items: list[str]) -> Gtk.StringList:
    return Gtk.StringList.new(items)


@Gtk.Template(resource_path='/io/github/riyaniii/Chelsea/pages/discover/page.ui')
class DiscoverPage(Adw.Bin):
    __gtype_name__ = "ChelseaDiscoverPage"

    stack = Gtk.Template.Child()
    empty_page = Gtk.Template.Child()
    type_dropdown = Gtk.Template.Child()
    catalog_dropdown = Gtk.Template.Child()
    genre_dropdown = Gtk.Template.Child()
    grid = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.integration = Gio.Application.get_default().integration
        self.store = Gio.ListStore(item_type=models.Meta)
        self.grid.bind_model(self.store)
        self.types = []
        self.catalogs = []
        self.genres = []
        self.seen = set()
        self.updating = False
        self.load_task = None
        self.exhausted = False

        self.integration.connect("notify::addons-revision", lambda *args: self.refresh_types())
        self.integration.connect("notify::ready", lambda *args: self.refresh_types())
        self.refresh_types()

    @property
    def catalog(self) -> models.Catalog | None:
        index = self.catalog_dropdown.get_selected()
        if 0 <= index < len(self.catalogs):
            return self.catalogs[index]
        return None

    @property
    def genre(self) -> str:
        index = self.genre_dropdown.get_selected()
        if 0 <= index < len(self.genres):
            return self.genres[index]
        return ""

    def refresh_types(self):
        if not self.integration.ready:
            return
        self.updating = True
        self.types = self.integration.catalogTypes()
        self.type_dropdown.set_model(string_list([type_title(item) for item in self.types]))
        self.type_dropdown.set_selected(0)
        self.updating = False
        self.refresh_catalogs()

    def refresh_catalogs(self):
        index = self.type_dropdown.get_selected()
        meta_type = self.types[index] if 0 <= index < len(self.types) else None
        self.updating = True
        self.catalogs = [catalog for catalog in self.integration.browseCatalogs() if catalog.type == meta_type]
        labels = [f"{catalog.title} ({catalog.source_name})" for catalog in self.catalogs]
        self.catalog_dropdown.set_model(string_list(labels))
        self.catalog_dropdown.set_selected(0)
        self.updating = False
        self.refresh_genres()

    def refresh_genres(self):
        catalog = self.catalog
        self.updating = True
        genres = list(catalog.genres or []) if catalog else []
        self.genres = genres if catalog and catalog.genre_required else [""] + genres
        labels = [genre or ALL_GENRES for genre in self.genres]
        self.genre_dropdown.set_model(string_list(labels))
        self.genre_dropdown.set_selected(0)
        self.genre_dropdown.set_visible(len(self.genres) > 1)
        self.updating = False
        self.reload()

    def select_catalog(self, key: str):
        for catalog in self.integration.browseCatalogs():
            if catalog.key != key:
                continue
            if catalog.type in self.types:
                self.updating = True
                self.type_dropdown.set_selected(self.types.index(catalog.type))
                self.updating = False
                self.refresh_catalogs()
            for index, item in enumerate(self.catalogs):
                if item.key == key:
                    self.catalog_dropdown.set_selected(index)
            return

    def reload(self):
        if self.load_task:
            self.load_task.cancel()
        self.store.remove_all()
        self.seen.clear()
        self.exhausted = False
        self.grid.scroll_to_top()
        if self.catalog is None:
            self.empty_page.set_description(_("Install an addon that provides catalogs"))
            self.stack.set_visible_child_name("empty")
            return
        self.stack.set_visible_child_name("loading")
        self.load_task = asyncio.create_task(self.load_page())

    async def load_page(self):
        catalog = self.catalog
        try:
            metas = await self.integration.getCatalog(catalog, skip=self.store.get_n_items(), genre=self.genre)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            print(f"discover: {error}")
            metas = []
            if self.store.get_n_items() == 0:
                self.empty_page.set_description(_("Could not load this catalog"))
        finally:
            self.load_task = None

        fresh = [meta for meta in metas if meta.id not in self.seen]
        self.seen.update(meta.id for meta in fresh)
        self.store.splice(self.store.get_n_items(), 0, fresh)
        if not fresh or not catalog.pageable:
            self.exhausted = True
        if self.store.get_n_items():
            self.stack.set_visible_child_name("grid")
        else:
            self.stack.set_visible_child_name("empty")

    @Gtk.Template.Callback()
    def on_type_changed(self, dropdown, pspec):
        if not self.updating:
            self.refresh_catalogs()

    @Gtk.Template.Callback()
    def on_catalog_changed(self, dropdown, pspec):
        if not self.updating:
            self.refresh_genres()

    @Gtk.Template.Callback()
    def on_genre_changed(self, dropdown, pspec):
        if not self.updating:
            self.reload()

    @Gtk.Template.Callback()
    def on_load_more(self, grid):
        if self.load_task is None and not self.exhausted and self.catalog is not None:
            self.load_task = asyncio.create_task(self.load_page())

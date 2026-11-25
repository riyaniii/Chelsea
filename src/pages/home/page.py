import asyncio
from gettext import gettext as _

from gi.repository import Adw, Gio, GLib, Gtk

from ...components import Hero, Row
from ...components.cards import open_meta
from ...components.formats import catalog_title
from ...integrations import models

MAX_CONCURRENT = 4
CAROUSEL_SIZE = 6
CAROUSEL_INTERVAL_S = 8
CAROUSEL_HEIGHT = 320
ROW_LIMIT = 20


@Gtk.Template(resource_path='/io/github/riyaniii/Chelsea/pages/home/page.ui')
class HomePage(Adw.Bin):
    __gtype_name__ = "ChelseaHomePage"

    stack = Gtk.Template.Child()
    rows_box = Gtk.Template.Child()
    carousel_revealer = Gtk.Template.Child()
    carousel = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.integration = Gio.Application.get_default().integration
        self.continue_row = Row(_("Continue Watching"), get_meta=lambda item: item.meta,
                                    item_type=models.LibraryItem)
        self.rows = []
        self.load_task = None
        self.waiting_rows = []
        self.limiter = asyncio.Semaphore(MAX_CONCURRENT)
        GLib.timeout_add_seconds(CAROUSEL_INTERVAL_S, self.advance_carousel)

        self.integration.connect("notify::addons-revision", lambda *args: self.reload())
        self.integration.connect("notify::library-revision", lambda *args: self.update_continue())
        self.integration.connect("notify::ready", lambda *args: self.reload())
        self.reload()

    def update_continue(self):
        items = self.integration.continueWatching()
        self.continue_row.set_items(items)
        self.continue_row.set_visible(bool(items))

    def advance_carousel(self):
        pages = self.carousel.get_n_pages()
        if pages > 1 and self.get_mapped():
            index = (round(self.carousel.get_position()) + 1) % pages
            self.carousel.scroll_to(self.carousel.get_nth_page(index), True)
        return GLib.SOURCE_CONTINUE

    def sync_carousel(self, metas: list):
        while self.carousel.get_n_pages():
            page = self.carousel.get_nth_page(0)
            page.cancel()
            self.carousel.remove(page)
        for meta in metas[:CAROUSEL_SIZE]:
            self.carousel.append(self.make_hero(meta))
        self.carousel_revealer.set_reveal_child(self.carousel.get_n_pages() > 0)

    def make_hero(self, meta):
        hero = Hero(model=meta, min_height=CAROUSEL_HEIGHT, description_lines=2, compact=True)
        hero.connect("play", lambda hero: Gio.Application.get_default().activate_action(
            "play_meta", GLib.Variant("(ss)", (meta.type, meta.id))))
        hero.connect("activated", lambda hero: open_meta(meta))
        return hero

    def reload(self):
        if not self.integration.ready:
            self.stack.set_visible_child_name("loading")
            return
        if self.load_task:
            self.load_task.cancel()
        self.waiting_rows = []

        for row in [self.continue_row] + self.rows:
            if row.get_parent() is not None:
                self.rows_box.remove(row)

        self.rows_box.append(self.continue_row)
        self.update_continue()

        catalogs = self.integration.boardCatalogs()
        self.rows = []
        for catalog in catalogs:
            row = Row(catalog_title(catalog), show_all=True)
            row.catalog = catalog
            row.set_loading()
            row.connect("see-all", self.on_see_all)
            self.rows_box.append(row)
            self.rows.append(row)

        has_content = bool(catalogs) or self.continue_row.get_visible()
        self.stack.set_visible_child_name("home" if has_content else "empty")
        self.load_task = asyncio.create_task(self.load_rows(list(self.rows)))

    async def load_rows(self, rows):
        await asyncio.gather(*(self.load_row(row, index == 0) for index, row in enumerate(rows)))

    async def load_row(self, row, featured: bool):
        async with self.limiter:
            try:
                metas = await self.integration.getCatalog(row.catalog)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                row.set_error(_("Could not load this catalog"))
                print(f"catalog {row.catalog.key} failed: {error}")
                return
        self.waiting_rows.append((row, metas, featured))
        if len(self.waiting_rows) == 1:
            GLib.idle_add(self.show_next_row)

    def show_next_row(self):
        if not self.waiting_rows:
            return GLib.SOURCE_REMOVE
        row, metas, featured = self.waiting_rows.pop(0)
        row.set_items(metas[:ROW_LIMIT])
        if featured:
            self.sync_carousel([meta for meta in metas if meta.description])
        return GLib.SOURCE_CONTINUE if self.waiting_rows else GLib.SOURCE_REMOVE

    def on_see_all(self, row):
        Gio.Application.get_default().activate_action("show_catalog", GLib.Variant("s", row.catalog.key))

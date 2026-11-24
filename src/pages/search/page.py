import asyncio

from gi.repository import Adw, Gio, Gtk

from ...components import Row, links
from ...components.formats import catalog_title
from ...components.link_dialog import dialog_for


@Gtk.Template(resource_path='/io/github/riyaniii/Chelsea/pages/search/page.ui')
class SearchPage(Adw.Bin):
    __gtype_name__ = "ChelseaSearchPage"

    entry = Gtk.Template.Child()
    stack = Gtk.Template.Child()
    rows_box = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.integration = Gio.Application.get_default().integration
        self.task = None
        self.query = ""

    def focus_entry(self):
        self.entry.grab_focus()

    def search_for(self, text: str):
        self.entry.set_text(text)
        self.entry.grab_focus()

    def clear_rows(self):
        child = self.rows_box.get_first_child()
        while child is not None:
            self.rows_box.remove(child)
            child = self.rows_box.get_first_child()

    def start_search(self, query: str):
        query = query.strip()
        if query == self.query:
            return
        self.query = query
        if self.task:
            self.task.cancel()
            self.task = None
        self.clear_rows()
        if not query:
            self.stack.set_visible_child_name("start")
            return
        link = links.parse(query)
        if link is not None:
            self.query = ""
            self.entry.set_text("")
            self.stack.set_visible_child_name("start")
            dialog_for(link).present(self.get_root())
            return

        rows = []
        for catalog in self.integration.searchCatalogs():
            row = Row(catalog_title(catalog))
            row.catalog = catalog
            row.set_loading()
            self.rows_box.append(row)
            rows.append(row)
        self.stack.set_visible_child_name("results" if rows else "none")
        self.task = asyncio.create_task(self.search(query, rows))

    async def search(self, query: str, rows: list):
        async def fill(row):
            try:
                metas = await self.integration.search(row.catalog, query)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                print(f"search in {row.catalog.key} failed: {error}")
                metas = []
            row.set_items(metas)
            row.set_visible(bool(metas))

        await asyncio.gather(*(fill(row) for row in rows))
        if not any(row.get_visible() for row in rows):
            self.stack.set_visible_child_name("none")


    @Gtk.Template.Callback()
    def on_search_changed(self, entry):
        self.start_search(entry.get_text())

    @Gtk.Template.Callback()
    def on_search_activate(self, entry):
        self.start_search(entry.get_text())

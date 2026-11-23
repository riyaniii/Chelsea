import asyncio
import os
from gettext import gettext as _

from gi.repository import Adw, Gio, GLib, Gtk

from ...components import Row, links
from ...components.formats import catalog_title
from ...integrations import models
from ...integrations.nuvio import isVideo, magnetUri


def size_text(size: int) -> str:
    return GLib.format_size(size)


def file_row(item) -> Gtk.ListBoxRow:
    box = Gtk.Box(spacing=12, margin_top=12, margin_bottom=12, margin_start=8, margin_end=8)
    box.append(Gtk.Image(icon_name="video-x-generic-symbolic", pixel_size=24))
    labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True, valign=Gtk.Align.CENTER)
    labels.append(Gtk.Label(label=os.path.basename(item.path), xalign=0, ellipsize=3))
    labels.append(Gtk.Label(label=size_text(item.size), xalign=0, css_classes=["dimmed"]))
    box.append(labels)
    box.append(Gtk.Image(icon_name="media-playback-start-symbolic", css_classes=["dimmed"]))
    row = Gtk.ListBoxRow(child=box)
    row.file = item
    return row


@Gtk.Template(resource_path='/io/github/riyaniii/Chelsea/pages/search/page.ui')
class SearchPage(Adw.Bin):
    __gtype_name__ = "ChelseaSearchPage"

    entry = Gtk.Template.Child()
    link_page = Gtk.Template.Child()
    link_button = Gtk.Template.Child()
    link_spinner = Gtk.Template.Child()
    files_list = Gtk.Template.Child()
    stack = Gtk.Template.Child()
    rows_box = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.integration = Gio.Application.get_default().integration
        self.task = None
        self.query = ""
        self.link = None

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
        self.link = None
        if not query:
            self.stack.set_visible_child_name("start")
            return
        link = links.parse(query)
        if link is not None:
            self.show_link(link)
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


    def show_link(self, link):
        self.link = link
        self.files_list.remove_all()
        self.files_list.set_visible(False)
        self.link_spinner.set_visible(False)
        self.link_button.set_visible(True)
        self.link_button.set_sensitive(True)
        self.link_page.set_description(link.name or link.url)
        if link.kind == "url":
            self.link_page.set_icon_name("network-wireless-symbolic")
            self.link_page.set_title(_("Video Link"))
            self.link_button.set_label(_("Play"))
        elif link.kind == "addon":
            self.link_page.set_icon_name("application-x-addon-symbolic")
            self.link_page.set_title(_("Addon Link"))
            self.link_button.set_label(_("Open in Addons"))
        else:
            self.link_page.set_icon_name("chain-link-symbolic")
            self.link_page.set_title(link.name or _("Magnet Link"))
            self.link_page.set_description(_("Fetching the torrent's files…"))
            self.link_button.set_visible(False)
            self.link_spinner.set_visible(True)
            self.task = asyncio.create_task(self.load_torrent(link))
        self.stack.set_visible_child_name("link")

    async def load_torrent(self, link):
        app = Gio.Application.get_default()
        engine = app.engine
        try:
            if not app.start_engine():
                raise RuntimeError(engine.error)
            torrent_id = await engine.addTorrent(magnetUri(link.info_hash, link.trackers, link.name))
            await engine.waitForMetadata(torrent_id)
            files = engine.getFiles(torrent_id)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self.link_page.set_description(_("Could not read this torrent: {}").format(error))
            self.link_spinner.set_visible(False)
            return
        videos = [item for item in files if isVideo(item.path)] or files
        videos.sort(key=lambda item: item.path.lower())
        for item in videos:
            self.files_list.append(file_row(item))
        self.link_spinner.set_visible(False)
        self.files_list.set_visible(True)
        self.link_page.set_description(_("Choose a file to play"))

    def play_link(self, link, file=None):
        name = link.name or link.url
        if file is not None:
            name = os.path.basename(file.path)
        meta = models.Meta()
        meta.update_data(id=link.url, type="other", name=name)
        stream = models.Stream(name=name)
        if link.kind == "magnet":
            stream.update_data(info_hash=link.info_hash, trackers=link.trackers,
                               file_index=file.index if file is not None else -1,
                               filename=os.path.basename(file.path) if file is not None else "")
        else:
            stream.url = link.url
        from ..player import PlayerPage
        self.get_root().main_nav_view.push(PlayerPage(meta, None, link.url, stream))

    def activate_link(self):
        link = self.link
        if link is None:
            return
        if link.kind == "url":
            self.play_link(link)
        elif link.kind == "addon":
            app = Gio.Application.get_default()
            app.activate_action("open_addons_page", None)
            self.get_root().addons_page.show_link(link.url)
        else:
            first = self.files_list.get_row_at_index(0)
            if first is not None:
                self.play_link(link, first.file)

    @Gtk.Template.Callback()
    def on_link_clicked(self, button):
        self.activate_link()

    @Gtk.Template.Callback()
    def on_file_activated(self, listbox, row):
        self.play_link(self.link, row.file)

    @Gtk.Template.Callback()
    def on_search_changed(self, entry):
        self.start_search(entry.get_text())

    @Gtk.Template.Callback()
    def on_search_activate(self, entry):
        if self.link is not None:
            self.activate_link()
        else:
            self.start_search(entry.get_text())

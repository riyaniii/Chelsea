import asyncio
from gettext import gettext as _
from pathlib import Path

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from ...integrations import models
from ...integrations.nuvio import magnetUri
from .stream_card import StreamCard

STREAMS_PER_FRAME = 20
FRAME_TIME_S = 0.016


@Gtk.Template(resource_path='/io/github/riyaniii/Chelsea/pages/details/streams_view.ui')
class StreamsView(Adw.Bin):
    __gtype_name__ = "ChelseaStreamsView"

    switcher_scroller = Gtk.Template.Child()
    source_switcher = Gtk.Template.Child()
    stack = Gtk.Template.Child()
    list = Gtk.Template.Child()

    def __init__(self, meta: models.Meta, video: models.Video | None = None, **kwargs):
        super().__init__(**kwargs)
        self.meta = meta
        self.video = video
        self.video_id = video.id if video is not None else (meta.default_video_id or meta.id)
        self.integration = Gio.Application.get_default().integration
        self.group_by_source = Gio.Application.get_default().settings.get_boolean("group-streams")
        self.sources = []

        self.store = Gio.ListStore(item_type=models.Stream)
        self.filter = Gtk.CustomFilter.new(self.filter_func)
        self.model = Gtk.NoSelection(model=Gtk.FilterListModel(model=self.store, filter=self.filter))
        self.list.set_model(self.model)
        self.task = asyncio.create_task(self.load())

    def cancel(self):
        if self.task:
            self.task.cancel()
            self.task = None

    def do_unrealize(self):
        self.cancel()
        Adw.Bin.do_unrealize(self)

    async def load(self):
        try:
            async for source, streams in self.integration.iterStreams(self.meta.type, self.video_id):
                if not streams:
                    continue
                self.add_source(source)
                self.stack.set_visible_child_name("streams")
                for start in range(0, len(streams), STREAMS_PER_FRAME):
                    self.store.splice(self.store.get_n_items(), 0, streams[start:start + STREAMS_PER_FRAME])
                    await asyncio.sleep(FRAME_TIME_S)
        finally:
            self.task = None
        if not self.store.get_n_items():
            self.stack.set_visible_child_name("empty")

    def add_source(self, source):
        if source.id in self.sources:
            return
        self.sources.append(source.id)
        self.source_switcher.add(Adw.Toggle(name=source.id, label=source.name))
        if len(self.sources) == 1:
            self.source_switcher.set_active_name(source.id)
        self.switcher_scroller.set_visible(self.group_by_source and len(self.sources) > 1)

    def filter_func(self, stream):
        if not self.group_by_source:
            return True
        active = self.source_switcher.get_active_name()
        return not active or stream.source_id == active

    def stream_link(self, stream: models.Stream) -> str:
        if stream.is_torrent:
            return magnetUri(stream.info_hash, stream.trackers)
        return stream.url or stream.external_url

    def on_stream_action(self, name: str, stream: models.Stream):
        app = Gio.Application.get_default()
        if name == "play-from-start":
            self.play(stream, from_start=True)
        elif name == "download":
            if stream.is_external:
                app.activate_action("show_toast", GLib.Variant("s", _("This stream can't be downloaded")))
                return
            self.download(stream)
        elif name == "copy-link":
            Gdk.Display.get_default().get_clipboard().set(self.stream_link(stream))
            app.activate_action("show_toast", GLib.Variant("s", _("Link copied")))
        elif name == "open-external":
            app.activate_action("open_uri", GLib.Variant("s", self.stream_link(stream)))

    def download(self, stream: models.Stream):
        app = Gio.Application.get_default()
        if not app.settings.get_boolean("ask-download-location"):
            item = app.downloads.add(self.meta, self.video, stream)
            app.activate_action("show_toast", GLib.Variant("s", _("Downloading {}").format(Path(item.path).name)))
            return
        suggested = app.downloads.suggested_path(self.meta, self.video, stream)
        dialog = Gtk.FileDialog(title=_("Save Download"), initial_name=suggested.name)
        dialog.save(self.get_root(), None, self.on_save_chosen, stream)

    def on_save_chosen(self, dialog, result, stream):
        try:
            file = dialog.save_finish(result)
        except GLib.Error:
            return
        app = Gio.Application.get_default()
        item = app.downloads.add(self.meta, self.video, stream, Path(file.get_path()))
        app.activate_action("show_toast", GLib.Variant("s", _("Downloading {}").format(Path(item.path).name)))

    def play(self, stream: models.Stream, from_start: bool = False):
        app = Gio.Application.get_default()
        if stream.is_external:
            uri = stream.external_url or f"https://www.youtube.com/watch?v={stream.yt_id}"
            app.activate_action("open_uri", GLib.Variant("s", uri))
            return
        from ..player import PlayerPage
        self.get_root().main_nav_view.push(
            PlayerPage(self.meta, self.video, self.video_id, stream, from_start=from_start))

    @Gtk.Template.Callback()
    def on_setup(self, factory, list_item):
        list_item.set_activatable(True)
        list_item.set_child(StreamCard(self))

    @Gtk.Template.Callback()
    def on_bind(self, factory, list_item):
        list_item.get_child().stream = list_item.get_item()

    @Gtk.Template.Callback()
    def on_unbind(self, factory, list_item):
        list_item.get_child().stream = None

    @Gtk.Template.Callback()
    def on_source_changed(self, switcher, pspec):
        self.filter.changed(Gtk.FilterChange.DIFFERENT)

    @Gtk.Template.Callback()
    def on_activate(self, listview, position):
        self.play(self.model.get_item(position))

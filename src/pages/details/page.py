import asyncio
from gettext import gettext as _

from gi.repository import Adw, Gio, GLib, GObject, Gtk

from ...components import Hero
from ...components.formats import episode_code
from ...integrations import models
from .panel import EpisodesPanel


@Gtk.Template(resource_path='/io/github/riyaniii/Chelsea/pages/details/page.ui')
class DetailsPage(Adw.NavigationPage):
    __gtype_name__ = "ChelseaDetailsPage"

    meta = GObject.Property(type=models.Meta)
    play_label = GObject.Property(type=str, default=_("Play"))
    panel_title = GObject.Property(type=str, default=_("Streams"))

    split_view = Gtk.Template.Child()
    panel = Gtk.Template.Child()
    stack = Gtk.Template.Child()
    error_page = Gtk.Template.Child()
    hero = Gtk.Template.Child()

    def __init__(self, meta: models.Meta, play: bool = False, **kwargs):
        super().__init__(meta=meta, **kwargs)
        self.integration = Gio.Application.get_default().integration
        self.play_when_loaded = play
        self.task = None
        self.library_handler = self.integration.connect(
            "notify::library-revision", lambda *args: self.update_play_label())
        self.connect("unrealize", lambda page: self.cleanup())
        close = Gio.SimpleAction.new("close", None)
        close.connect("activate", lambda action, value: self.split_view.set_show_sidebar(False))
        group = Gio.SimpleActionGroup()
        group.add_action(close)
        self.insert_action_group("panel", group)
        self.load()

    def cleanup(self):
        if self.task:
            self.task.cancel()
        self.hero.cancel()
        if self.library_handler:
            self.integration.disconnect(self.library_handler)
            self.library_handler = 0

    def load(self):
        self.stack.set_visible_child_name("content" if self.meta.initialized else "loading")
        self.task = asyncio.create_task(self.fetch())

    async def fetch(self):
        try:
            await self.integration.getMeta(self.meta.type, self.meta.id)
        except Exception as error:
            print(f"details: {error}")
            self.error_page.set_description(str(error))
            self.stack.set_visible_child_name("error")
            return
        self.hero.load_images()
        self.panel.set_meta(self.meta)
        self.panel_title = _("Episodes") if self.meta.is_series else _("Streams")
        self.update_play_label()
        self.stack.set_visible_child_name("content")
        if self.play_when_loaded:
            self.play_when_loaded = False
            self.on_play(self.hero)

    def resume_target(self):
        item = self.integration.libraryItem(self.meta.id)
        if self.meta.is_series:
            if item and item.video_id:
                video = self.integration.getModel('Video', item.video_id)
                if video is not None:
                    return video, item.time_offset > 0
            regular = [video for video in self.meta.videos if video.season > 0] or list(self.meta.videos)
            return (regular[0] if regular else None), False
        return None, bool(item and item.time_offset > 0)

    def update_play_label(self):
        video, resume = self.resume_target()
        if video is not None:
            code = episode_code(video)
            self.play_label = _("Resume {}").format(code) if resume else _("Play {}").format(code)
        else:
            self.play_label = _("Resume") if resume else _("Play")

    @Gtk.Template.Callback()
    def on_play(self, hero):
        video, resume = self.resume_target()
        if self.meta.is_series and video is None:
            return
        self.panel.show_streams(video)
        self.split_view.set_show_sidebar(True)

    @Gtk.Template.Callback()
    def on_retry_clicked(self, button):
        self.load()

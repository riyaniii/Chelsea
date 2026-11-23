from gettext import gettext as _

from gi.repository import Adw, Gio, Gtk

from ...integrations import models
from .episode_row import EpisodeRow
from .streams_view import StreamsView


def streams_page(meta: models.Meta, video: models.Video | None, root: bool) -> Adw.NavigationPage:
    title = (video.title or _("Episode {}").format(video.episode)) if video is not None else _("Streams")
    header = Adw.HeaderBar(show_back_button=not root)
    toolbar = Adw.ToolbarView()
    toolbar.add_top_bar(header)
    toolbar.set_content(StreamsView(meta, video))
    return Adw.NavigationPage(title=title, tag="streams", child=toolbar)


@Gtk.Template(resource_path='/io/github/riyaniii/Chelsea/pages/details/panel.ui')
class EpisodesPanel(Adw.Bin):
    __gtype_name__ = "ChelseaEpisodesPanel"

    nav = Gtk.Template.Child()
    episodes_page = Gtk.Template.Child()
    season_dropdown = Gtk.Template.Child()
    episodes_stack = Gtk.Template.Child()
    episode_list = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.integration = Gio.Application.get_default().integration
        self.meta = None
        self.seasons = []

    def set_meta(self, meta: models.Meta):
        self.meta = meta
        if meta.is_series:
            self.fill_seasons()
            self.nav.replace([self.episodes_page])
        else:
            self.nav.replace([streams_page(meta, None, root=True)])

    def fill_seasons(self):
        videos = list(self.meta.videos)
        self.seasons = sorted({video.season for video in videos}, key=lambda season: (season == 0, season))
        labels = [_("Specials") if season == 0 else _("Season {}").format(season) for season in self.seasons]
        self.season_dropdown.set_model(Gtk.StringList.new(labels))
        self.season_dropdown.set_visible(len(self.seasons) > 1)

        item = self.integration.libraryItem(self.meta.id)
        current = self.integration.getModel('Video', item.video_id) if item and item.video_id else None
        season = current.season if current is not None else (self.seasons[0] if self.seasons else 0)
        self.season_dropdown.set_selected(self.seasons.index(season) if season in self.seasons else 0)
        self.fill_episodes()

    def fill_episodes(self):
        self.episode_list.remove_all()
        index = self.season_dropdown.get_selected()
        if not (0 <= index < len(self.seasons)):
            self.episodes_stack.set_visible_child_name("empty")
            return
        season = self.seasons[index]
        for video in self.meta.videos:
            if video.season == season:
                self.episode_list.append(EpisodeRow(video))
        self.episodes_stack.set_visible_child_name("list")

    def show_streams(self, video: models.Video | None):
        if self.meta is None or not self.meta.is_series:
            return
        self.nav.pop_to_tag("episodes")
        if video is not None:
            self.nav.push(streams_page(self.meta, video, root=False))

    @Gtk.Template.Callback()
    def on_season_changed(self, dropdown, pspec):
        if self.meta is not None:
            self.fill_episodes()

    @Gtk.Template.Callback()
    def on_episode_activated(self, listbox, row):
        self.show_streams(row.video)

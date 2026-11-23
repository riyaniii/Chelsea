from gettext import gettext as _

from gi.repository import Gio, GObject, Gtk

from ...components.formats import release_date
from ...integrations import models


@Gtk.Template(resource_path='/io/github/riyaniii/Chelsea/pages/details/episode_row.ui')
class EpisodeRow(Gtk.ListBoxRow):
    __gtype_name__ = "ChelseaEpisodeRow"

    video = GObject.Property(type=models.Video)

    def __init__(self, video: models.Video, **kwargs):
        super().__init__(video=video, **kwargs)
        self.images = Gio.Application.get_default().images
        self.task = self.images.startThumbnail(video, "thumbnail", "paintable")
        self.loaded = True

    def do_unrealize(self):
        if self.loaded:
            self.images.stopThumbnail(self.video, self.task)
            self.task = None
            self.loaded = False
        Gtk.ListBoxRow.do_unrealize(self)

    @Gtk.Template.Callback()
    def title_text(self, obj, episode, title):
        if episode:
            return f"{episode}. {title or _('Episode {}').format(episode)}"
        return title

    @Gtk.Template.Callback()
    def date_text(self, obj, released):
        return release_date(released)

    @Gtk.Template.Callback()
    def has_text(self, obj, text):
        return bool(text)

    @Gtk.Template.Callback()
    def row_opacity(self, obj, watched):
        return 0.55 if watched else 1.0

    @Gtk.Template.Callback()
    def image_page(self, obj, paintable):
        return "image" if paintable is not None else "empty"

    @Gtk.Template.Callback()
    def has_progress(self, obj, progress):
        return progress > 0.0

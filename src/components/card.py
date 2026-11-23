from gi.repository import GObject, Gtk

from ..integrations import models

POSTER_RATIOS = {
    "poster": 0.667,
    "square": 1.0,
    "landscape": 1.778,
}


@Gtk.Template(resource_path='/io/github/riyaniii/Chelsea/components/card.ui')
class Card(Gtk.Box):
    __gtype_name__ = "ChelseaCard"

    model = GObject.Property(type=models.Meta)
    show_title = GObject.Property(type=bool, default=True)

    def __init__(self, model=None, **kwargs):
        super().__init__(**kwargs)
        self.task = None
        if model is not None:
            self.model = model

    @Gtk.Template.Callback()
    def poster_ratio(self, obj, shape):
        return POSTER_RATIOS.get(shape or "poster", POSTER_RATIOS["poster"])

    @Gtk.Template.Callback()
    def image_page(self, obj, paintable):
        return "image" if paintable is not None else "empty"

    @Gtk.Template.Callback()
    def has_progress(self, obj, progress):
        return progress > 0.0

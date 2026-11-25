from gettext import gettext as _

from gi.repository import Gdk, Gio, GLib, GObject, Gtk

from ..integrations import models


MAX_PEOPLE = 6
LOGO_MAX_WIDTH = 280
LOGO_MAX_HEIGHT = 90


class HeroLogo(Gtk.Widget):
    __gtype_name__ = "ChelseaHeroLogo"

    paintable = GObject.Property(type=Gdk.Paintable)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.connect("notify::paintable", lambda *args: self.queue_resize())

    def logo_size(self):
        ratio = self.paintable.get_intrinsic_aspect_ratio() if self.paintable is not None else 0
        if ratio <= 0:
            return 0, 0
        height = LOGO_MAX_HEIGHT
        width = height * ratio
        if width > LOGO_MAX_WIDTH:
            width = LOGO_MAX_WIDTH
            height = width / ratio
        return round(width), round(height)

    def do_get_request_mode(self):
        return Gtk.SizeRequestMode.CONSTANT_SIZE

    def do_measure(self, orientation, for_size):
        width, height = self.logo_size()
        size = width if orientation == Gtk.Orientation.HORIZONTAL else height
        return 0, size, -1, -1

    def do_snapshot(self, snapshot):
        if self.paintable is not None:
            self.paintable.snapshot(snapshot, self.get_width(), self.get_height())


@Gtk.Template(resource_path='/io/github/riyaniii/Chelsea/components/hero.ui')
class Hero(Gtk.Overlay):
    __gtype_name__ = "ChelseaHero"

    model = GObject.Property(type=models.Meta)
    play_label = GObject.Property(type=str, default=_("Play"))
    min_height = GObject.Property(type=int, default=420)
    description_lines = GObject.Property(type=int, default=3)
    compact = GObject.Property(type=bool, default=False)
    show_people = GObject.Property(type=bool, default=False)

    __gsignals__ = {
        "play": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "activated": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.integration = Gio.Application.get_default().integration
        self.images = Gio.Application.get_default().images
        self.tasks = []
        self.connect("notify::model", lambda *args: self.load_images())
        self.load_images()

    def load_images(self):
        previous = self.tasks
        self.tasks = []
        if self.model is not None:
            for url_property, target in (("background", "background_paintable"), ("logo", "logo_paintable")):
                task = self.images.startThumbnail(self.model, url_property, target, priority=True)
                self.tasks.append((self.model, target, task))
        for model, target, task in previous:
            self.images.stopThumbnail(model, task, target)

    def cancel(self):
        for model, target, task in self.tasks:
            self.images.stopThumbnail(model, task, target)
        self.tasks = []

    @Gtk.Template.Callback()
    def on_hero_clicked(self, gesture, n_press, x, y):
        self.emit("activated")

    @Gtk.Template.Callback()
    def image_page(self, obj, paintable):
        return "image" if paintable is not None else "empty"

    @Gtk.Template.Callback()
    def title_page(self, obj, logo):
        return "logo" if logo is not None else "title"

    @Gtk.Template.Callback()
    def people_visible(self, obj, show, cast, directors):
        return show and bool(cast or directors)

    @Gtk.Template.Callback()
    def people_text(self, obj, show, cast, directors):
        if not show:
            return ""
        lines = []
        if directors:
            names = GLib.markup_escape_text(", ".join(directors[:MAX_PEOPLE]))
            lines.append(f"<b>{GLib.markup_escape_text(_('Director'))}</b>  {names}")
        if cast:
            names = GLib.markup_escape_text(", ".join(cast[:MAX_PEOPLE]))
            lines.append(f"<b>{GLib.markup_escape_text(_('Cast'))}</b>  {names}")
        return "\n".join(lines)

    @Gtk.Template.Callback()
    def on_play_clicked(self, button):
        self.emit("play")

    @Gtk.Template.Callback()
    def on_library_clicked(self, button):
        self.integration.runInBackground(self.integration.setInLibrary(self.model, not self.model.in_library))

    @Gtk.Template.Callback()
    def on_trailer_clicked(self, button):
        trailer = self.model.trailer
        uri = trailer if "://" in trailer else f"https://www.youtube.com/watch?v={trailer}"
        Gio.Application.get_default().activate_action("open_uri", GLib.Variant("s", uri))

    @Gtk.Template.Callback()
    def trailer_visible(self, obj, compact, trailer):
        return not compact and bool(trailer)

    @Gtk.Template.Callback()
    def has_text(self, obj, text):
        return bool(text)

    @Gtk.Template.Callback()
    def info_text(self, obj, release, runtime, rating, genres):
        parts = [release, runtime]
        if rating:
            parts.append("★ " + rating)
        parts.extend((genres or [])[:3])
        return "  ·  ".join(part for part in parts if part)

    @Gtk.Template.Callback()
    def library_icon(self, obj, in_library):
        return "heart-filled-symbolic" if in_library else "heart-outline-thick-symbolic"

    @Gtk.Template.Callback()
    def library_label(self, obj, in_library):
        return _("In Library") if in_library else _("Add to Library")

    @Gtk.Template.Callback()
    def library_tooltip(self, obj, in_library):
        return _("Remove from your library") if in_library else _("Save to your library")

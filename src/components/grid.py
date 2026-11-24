from gi.repository import Adw, GObject, Gtk

from .cards import open_meta, card_factory, same

GRID_POSTER_WIDTH = 150


@Gtk.Template(resource_path='/io/github/riyaniii/Chelsea/components/grid.ui')
class Grid(Adw.BreakpointBin):
    __gtype_name__ = "ChelseaGrid"

    scroller = Gtk.Template.Child()
    grid = Gtk.Template.Child()

    __gsignals__ = {
        "load-more": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.get_meta = same
        self.model = None

    def bind_model(self, model, get_meta=same):
        self.get_meta = get_meta
        self.model = model
        self.grid.set_factory(card_factory(get_meta, poster_width=GRID_POSTER_WIDTH))
        self.grid.set_model(Gtk.NoSelection(model=model))

    def scroll_to_top(self):
        self.scroller.get_vadjustment().set_value(0)

    @Gtk.Template.Callback()
    def on_edge_reached(self, scroller, position):
        if position == Gtk.PositionType.BOTTOM:
            self.emit("load-more")

    @Gtk.Template.Callback()
    def on_activate(self, view, position):
        open_meta(self.get_meta(self.model.get_item(position)))

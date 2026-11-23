from gi.repository import Gio, GObject, Gtk

from ..integrations import models
from .cards import open_meta, card_factory, same


@Gtk.Template(resource_path='/io/github/riyaniii/Chelsea/components/row.ui')
class Row(Gtk.Box):
    __gtype_name__ = "ChelseaRow"

    title = GObject.Property(type=str, default="")
    show_all = GObject.Property(type=bool, default=False)

    stack = Gtk.Template.Child()
    scroller = Gtk.Template.Child()
    list = Gtk.Template.Child()
    empty_label = Gtk.Template.Child()

    __gsignals__ = {
        "see-all": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, title: str = "", get_meta=same, item_type=models.Meta, **kwargs):
        super().__init__(title=title, **kwargs)
        self.get_meta = get_meta
        self.store = Gio.ListStore(item_type=item_type)
        self.list.set_model(Gtk.NoSelection(model=self.store))
        self.list.set_factory(card_factory(get_meta))
        self.task = None

    def set_loading(self):
        self.stack.set_visible_child_name("loading")

    def set_items(self, items: list):
        self.store.splice(0, self.store.get_n_items(), items)
        self.stack.set_visible_child_name("items" if items else "empty")
        self.set_visible(bool(items))

    def set_error(self, message: str):
        self.empty_label.set_label(message)
        self.set_visible(False)

    @Gtk.Template.Callback()
    def on_see_all_clicked(self, button):
        self.emit("see-all")

    @Gtk.Template.Callback()
    def on_activate(self, view, position):
        open_meta(self.get_meta(self.store.get_item(position)))

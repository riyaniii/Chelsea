from gi.repository import Gtk, Pango


def label_factory(ellipsize: bool) -> Gtk.SignalListItemFactory:
    factory = Gtk.SignalListItemFactory()
    mode = Pango.EllipsizeMode.END if ellipsize else Pango.EllipsizeMode.NONE
    factory.connect("setup", lambda factory, item: item.set_child(Gtk.Label(xalign=0, ellipsize=mode)))
    factory.connect("bind", lambda factory, item: item.get_child().set_label(item.get_item().get_string()))
    return factory


def make_shrinkable(*dropdowns):
    for dropdown in dropdowns:
        dropdown.set_factory(label_factory(ellipsize=True))
        dropdown.set_list_factory(label_factory(ellipsize=False))

from gi.repository import Gio, GLib, Gtk

from .card import Card


def same(item):
    return item


def open_meta(meta):
    if meta is not None:
        Gio.Application.get_default().activate_action(
            "show_meta", GLib.Variant("(ss)", (meta.type, meta.id)))


def card_factory(get_meta=same, landscape: bool = False) -> Gtk.SignalListItemFactory:
    images = Gio.Application.get_default().images
    factory = Gtk.SignalListItemFactory()

    def on_setup(factory, list_item):
        list_item.set_child(Card())

    def on_bind(factory, list_item):
        card = list_item.get_child()
        meta = get_meta(list_item.get_item())
        card.model = meta
        card.task = images.startThumbnail(meta) if meta is not None else None

    def on_unbind(factory, list_item):
        card = list_item.get_child()
        if card.model is not None:
            images.stopThumbnail(card.model, card.task)
        card.task = None
        card.model = None

    factory.connect("setup", on_setup)
    factory.connect("bind", on_bind)
    factory.connect("unbind", on_unbind)
    return factory

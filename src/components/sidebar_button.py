from gettext import gettext as _

from gi.repository import Adw, GObject, Gtk


class SidebarButton(Gtk.ToggleButton):
    __gtype_name__ = "ChelseaSidebarButton"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_icon_name("sidebar-show-symbolic")
        self.set_tooltip_text(_("Toggle Sidebar"))
        self.set_visible(False)
        self.bindings = []
        self.connect("notify::root", lambda *args: self.attach())

    def attach(self):
        for binding in self.bindings:
            binding.unbind()
        self.bindings = []
        split_view = self.get_ancestor(Adw.OverlaySplitView)
        if split_view is None:
            return
        flags = GObject.BindingFlags.SYNC_CREATE
        self.bindings = [
            split_view.bind_property("collapsed", self, "visible", flags),
            split_view.bind_property("show-sidebar", self, "active", flags | GObject.BindingFlags.BIDIRECTIONAL),
        ]

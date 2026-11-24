from gettext import gettext as _

from gi.repository import Gdk, GObject, Gtk, Pango

MINIMUM_CHARS = 7


def bold_label(name: str, current: bool) -> Gtk.Label:
    label = Gtk.Label(label=name, single_line_mode=True)
    attributes = Pango.AttrList()
    attributes.insert(Pango.attr_weight_new(Pango.Weight.BOLD))
    label.set_attributes(attributes)
    minimum = MINIMUM_CHARS * 4 if current else MINIMUM_CHARS
    if len(name) > minimum * 1.5:
        label.set_width_chars(minimum)
        label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
    return label


class PathBar(Gtk.Box):
    __gtype_name__ = "ChelseaPathBar"

    __gsignals__ = {
        "folder-selected": (GObject.SignalFlags.RUN_FIRST, None, (int,)),
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.add_css_class("linked")
        self.add_css_class("path-bar")

        self.scroller = Gtk.ScrolledWindow(hexpand=True, hscrollbar_policy=Gtk.PolicyType.EXTERNAL,
                                           vscrollbar_policy=Gtk.PolicyType.NEVER)
        self.scroller.get_hadjustment().connect("changed", lambda adjustment: self.reveal_current())
        wheel = Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.VERTICAL)
        wheel.connect("scroll", self.on_scroll)
        self.scroller.add_controller(wheel)
        self.append(self.scroller)

        self.buttons = Gtk.Box()
        self.scroller.set_child(self.buttons)

        self.menu_button = Gtk.MenuButton(icon_name="view-more-symbolic", css_classes=["flat"],
                                          tooltip_text=_("Current Folder Menu"), visible=False)
        self.append(self.menu_button)

    def set_menu(self, menu):
        self.menu_button.set_menu_model(menu)
        self.menu_button.set_visible(menu is not None)

    def set_folders(self, names: list, root_icon: str):
        while self.buttons.get_first_child() is not None:
            self.buttons.remove(self.buttons.get_first_child())
        last = len(names) - 1
        for depth, name in enumerate(names):
            self.buttons.append(self.make_container(name, depth, depth == last, root_icon))

    def make_container(self, name: str, depth: int, current: bool, root_icon: str) -> Gtk.Box:
        button = Gtk.Button(focus_on_click=False, tooltip_text=name, css_classes=["path-button"])
        label = bold_label(name, current)
        if depth == 0:
            container = Gtk.Box(spacing=6)
            content = Gtk.Box(spacing=6)
            image = Gtk.Image(icon_name=root_icon)
            content.append(image)
        else:
            container = Gtk.Box()
            container.append(Gtk.Label(label="/", css_classes=["dimmed"]))
            content = Gtk.Box(spacing=2)
            image = None
        content.append(label)
        button.set_child(content)
        container.append(button)
        if current:
            button.add_css_class("current-dir")
            button.set_hexpand(True)
            label.set_halign(Gtk.Align.START)
        else:
            label.add_css_class("dimmed")
            if image is not None:
                image.add_css_class("dimmed")
            button.connect("clicked", lambda button: self.emit("folder-selected", depth))
        return container

    def reveal_current(self):
        last = self.buttons.get_last_child()
        if last is not None:
            self.scroller.get_child().scroll_to(last, None)

    def on_scroll(self, controller, dx, dy):
        if dy == 0:
            return Gdk.EVENT_PROPAGATE
        adjustment = self.scroller.get_hadjustment()
        adjustment.set_value(adjustment.get_value() + dy * adjustment.get_step_increment())
        return Gdk.EVENT_STOP

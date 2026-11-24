from gettext import gettext as _

from gi.repository import GObject, Gtk

MOUSE_BACK_BUTTON = 8
MOUSE_FORWARD_BUTTON = 9


class HistoryControls(Gtk.Box):
    __gtype_name__ = "ChelseaHistoryControls"

    __gsignals__ = {
        "location-chosen": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_spacing(6)
        self.back_list = []
        self.forward_list = []
        self.current = None

        self.back_button = Gtk.Button(icon_name="go-previous-symbolic", tooltip_text=_("Back"),
                                      valign=Gtk.Align.CENTER, sensitive=False)
        self.back_button.connect("clicked", lambda button: self.go_back())
        self.append(self.back_button)

        self.forward_button = Gtk.Button(icon_name="go-next-symbolic", tooltip_text=_("Forward"),
                                         valign=Gtk.Align.CENTER, sensitive=False)
        self.forward_button.connect("clicked", lambda button: self.go_forward())
        self.append(self.forward_button)

    def visit(self, location):
        if self.current is not None:
            self.back_list.append(self.current)
        self.forward_list = []
        self.current = location
        self.update_buttons()

    def reset(self, location):
        self.back_list = []
        self.forward_list = []
        self.current = location
        self.update_buttons()

    def go_back(self):
        if not self.back_list:
            return
        self.forward_list.append(self.current)
        self.current = self.back_list.pop()
        self.update_buttons()
        self.emit("location-chosen", self.current)

    def go_forward(self):
        if not self.forward_list:
            return
        self.back_list.append(self.current)
        self.current = self.forward_list.pop()
        self.update_buttons()
        self.emit("location-chosen", self.current)

    def update_buttons(self):
        self.back_button.set_sensitive(bool(self.back_list))
        self.forward_button.set_sensitive(bool(self.forward_list))

    def listen_to_mouse(self, widget: Gtk.Widget):
        clicks = Gtk.GestureClick(button=0)
        clicks.connect("pressed", self.on_mouse_pressed)
        widget.add_controller(clicks)

    def on_mouse_pressed(self, gesture, presses, x, y):
        button = gesture.get_current_button()
        if button == MOUSE_BACK_BUTTON:
            self.go_back()
        elif button == MOUSE_FORWARD_BUTTON:
            self.go_forward()
        else:
            return
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)

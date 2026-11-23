from gi.repository import Gtk


@Gtk.Template(resource_path='/io/github/riyaniii/Chelsea/pages/player/options.ui')
class OptionsButton(Gtk.MenuButton):
    __gtype_name__ = "ChelseaOptionsButton"

    sub_delay_reset_btn = Gtk.Template.Child()
    audio_delay_reset_btn = Gtk.Template.Child()
    speed_reset_btn = Gtk.Template.Child()
    sub_delay_spin = Gtk.Template.Child()
    audio_delay_spin = Gtk.Template.Child()
    speed_spin = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.video = None
        self.connect("realize", self.on_realize)
        self.connect("notify::active", self.on_active_changed)

    def controls(self):
        return [
            ("sub-delay", self.sub_delay_spin, self.sub_delay_reset_btn, 0.0),
            ("audio-delay", self.audio_delay_spin, self.audio_delay_reset_btn, 0.0),
            ("speed", self.speed_spin, self.speed_reset_btn, 1.0),
        ]

    def on_realize(self, button):
        for name, spin, reset_button, default in self.controls():
            text = spin.get_first_child()
            down = text.get_next_sibling()
            up = down.get_next_sibling()
            text.set_alignment(1.0)
            down.set_css_classes(["button"])
            up.set_css_classes(["button"])
            down.set_margin_start(8)
            down.set_margin_end(8)
            down.set_size_request(50, -1)
            up.set_size_request(50, -1)

    def set_enabled(self, button: Gtk.Button, enabled: bool):
        button.set_can_target(enabled)
        button.set_can_focus(enabled)
        button.set_opacity(1 if enabled else 0.4)

    def on_active_changed(self, button, pspec):
        if not self.get_active() or self.video is None:
            return
        for name, spin, reset_button, default in self.controls():
            value = self.video.get(name, default)
            if spin.get_value() != value:
                spin.set_value(value)
            self.set_enabled(reset_button, abs(value - default) > 0.001)

    def spin_changed(self, name: str, spin: Gtk.SpinButton, reset_button: Gtk.Button, default: float):
        if self.video is None:
            return
        value = round(spin.get_value(), 4)
        self.video.set(name, value)
        self.set_enabled(reset_button, abs(value - default) > 0.001)

    @Gtk.Template.Callback()
    def on_reset_all(self, button):
        for name, spin, reset_button, default in self.controls():
            spin.set_value(default)

    @Gtk.Template.Callback()
    def on_sub_delay_changed(self, spin):
        self.spin_changed("sub-delay", spin, self.sub_delay_reset_btn, 0.0)

    @Gtk.Template.Callback()
    def on_audio_delay_changed(self, spin):
        self.spin_changed("audio-delay", spin, self.audio_delay_reset_btn, 0.0)

    @Gtk.Template.Callback()
    def on_speed_changed(self, spin):
        self.spin_changed("speed", spin, self.speed_reset_btn, 1.0)

    @Gtk.Template.Callback()
    def on_sub_delay_reset(self, button):
        self.sub_delay_spin.set_value(0)

    @Gtk.Template.Callback()
    def on_audio_delay_reset(self, button):
        self.audio_delay_spin.set_value(0)

    @Gtk.Template.Callback()
    def on_speed_reset(self, button):
        self.speed_spin.set_value(1)

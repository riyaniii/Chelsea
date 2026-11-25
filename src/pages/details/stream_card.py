from gi.repository import Gio, GObject, Gtk

from ...integrations import models

ACTIONS = ("play-from-start", "download", "copy-link", "open-external")


@Gtk.Template(resource_path='/io/github/riyaniii/Chelsea/pages/details/stream_card.ui')
class StreamCard(Gtk.Box):
    __gtype_name__ = "ChelseaStreamCard"

    stream = GObject.Property(type=models.Stream)

    more_button = Gtk.Template.Child()
    stream_menu = Gtk.Template.Child()

    def __init__(self, view, **kwargs):
        super().__init__(**kwargs)
        self.more_button.set_create_popup_func(self.on_create_popup)
        group = Gio.SimpleActionGroup()
        for name in ACTIONS:
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda action, value, name=name: view.on_stream_action(name, self.stream))
            group.add_action(action)
        self.insert_action_group("stream", group)

    def on_create_popup(self, button):
        button.set_menu_model(self.stream_menu)

    @Gtk.Template.Callback()
    def name_text(self, obj, name, source_name):
        return (name or source_name or "").replace("\n", " · ")

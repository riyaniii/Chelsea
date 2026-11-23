import asyncio

from gi.repository import Adw, GLib, Gtk

from .. import actions
from ..pages.profiles import ProfilesPage
from .main_view import ChelseaMainView

VIEW_PARTS = (
    "main_stack",
    "main_nav_view",
    "toast_overlay",
    "home_page",
    "discover_page",
    "library_page",
    "search_page",
    "addons_page",
)


@Gtk.Template(resource_path='/io/github/riyaniii/Chelsea/components/window.ui')
class ChelseaWindow(Adw.ApplicationWindow):
    __gtype_name__ = 'ChelseaWindow'

    main_bin = Gtk.Template.Child()
    window_stack = Gtk.Template.Child()
    window_toasts = Gtk.Template.Child()
    profiles_page = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.main_view = ChelseaMainView()
        for name in VIEW_PARTS:
            setattr(self, name, getattr(self.main_view, name))
        self.main_bin.set_child(self.main_view)
        self.add_actions()

    def show_profiles(self):
        if self.main_nav_view.get_visible_page().get_tag() != "main":
            self.main_nav_view.pop_to_tag("main")
        self.window_stack.set_visible_child_name("profiles")

    def show_main(self):
        self.window_stack.set_visible_child_name("main")

    def toast(self, message: str):
        self.window_toasts.add_toast(Adw.Toast(title=message, timeout=4, use_markup=False))

    @Gtk.Template.Callback()
    def on_profile_chosen(self, page, profile):
        self.get_application().select_profile(profile)

    @Gtk.Template.Callback()
    def on_add_profile(self, page):
        from ..pages.setup import SetupDialog
        SetupDialog(login_only=True).present(self)

    def add_actions(self):
        self.create_action(actions.show_meta, parameter_type="(ss)")
        self.create_action(actions.play_meta, parameter_type="(ss)")
        self.create_action(actions.show_catalog)
        self.create_action(actions.switch_page)
        self.create_action(actions.show_toast)
        self.create_action(actions.open_uri)
        self.create_action(actions.open_link)
        self.create_action(actions.open_search_page, ['<control>f', '<control>k', '<alt>2'], parameter_type=None)
        self.create_action(actions.open_home_page, ['<alt>1'], parameter_type=None)
        self.create_action(actions.open_discover_page, ['<alt>4'], parameter_type=None)
        self.create_action(actions.open_library_page, ['<control>l', '<alt>3'], parameter_type=None)
        self.create_action(actions.open_addons_page, ['<alt>6'], parameter_type=None)
        self.create_action(actions.open_downloads_page, ['<alt>5'], parameter_type=None)
        self.create_action(actions.sign_in, parameter_type=None)
        self.create_action(actions.switch_profile, parameter_type=None)

    def create_action(self, callback: callable, shortcuts: list | None = None, parameter_type: str = "s"):
        shortcuts = shortcuts or []

        def call_action(action, variant):
            app = self.get_application()
            if variant is None:
                result = callback(app)
            else:
                value = variant.unpack()
                result = callback(app, *value) if isinstance(value, tuple) else callback(app, value)
            if asyncio.iscoroutine(result):
                task = asyncio.create_task(result)
                task.add_done_callback(
                    lambda t: not t.cancelled() and t.exception()
                    and print(f"Action '{callback.__name__}' failed:", t.exception())
                )

        self.get_application().create_action(
            name=callback.__name__,
            callback=call_action,
            shortcuts=shortcuts,
            parameter_type=GLib.VariantType.new(parameter_type) if parameter_type else None
        )

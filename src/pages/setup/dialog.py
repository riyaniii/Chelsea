import asyncio
from gettext import gettext as _

from gi.repository import Adw, Gio, Gtk

from ... import profiles
from ...components.download_location import choose_folder, folder_label
from ...integrations import IntegrationError, LoginFailed
from ...languages import setup_language_row

PROFILES = ("soft", "balanced", "fast")


@Gtk.Template(resource_path='/io/github/riyaniii/Chelsea/pages/setup/dialog.ui')
class SetupDialog(Adw.Dialog):
    __gtype_name__ = 'ChelseaSetupDialog'

    toast_overlay = Gtk.Template.Child()
    stack = Gtk.Template.Child()
    navigation = Gtk.Template.Child()
    login_page = Gtk.Template.Child()
    tour_page = Gtk.Template.Child()
    email_row = Gtk.Template.Child()
    password_row = Gtk.Template.Child()
    login_error_label = Gtk.Template.Child()
    carousel = Gtk.Template.Child()
    back_button = Gtk.Template.Child()
    next_button = Gtk.Template.Child()
    profile_row = Gtk.Template.Child()
    cache_row = Gtk.Template.Child()
    upload_row = Gtk.Template.Child()
    hwdec_row = Gtk.Template.Child()
    audio_language_row = Gtk.Template.Child()
    subtitle_language_row = Gtk.Template.Child()
    download_folder_row = Gtk.Template.Child()
    ask_location_row = Gtk.Template.Child()

    def __init__(self, login_only: bool = False, email: str = ""):
        super().__init__()
        self.app = Gio.Application.get_default()
        self.settings = self.app.settings
        self.integration = self.app.integration
        self.login_only = login_only
        self.current = 0
        self.profile = None
        self.email_row.set_text(email)

        self.set_can_close(login_only or self.settings.get_boolean('welcome-shown'))
        self.settings.bind('torrent-cache-size', self.cache_row, 'value', Gio.SettingsBindFlags.DEFAULT)
        self.settings.bind('torrent-upload', self.upload_row, 'active', Gio.SettingsBindFlags.DEFAULT)
        self.settings.bind('hardware-decoding', self.hwdec_row, 'active', Gio.SettingsBindFlags.DEFAULT)
        setup_language_row(self.audio_language_row, self.settings, 'audio-language')
        setup_language_row(self.subtitle_language_row, self.settings, 'subtitle-language')
        self.settings.bind('ask-download-location', self.ask_location_row, 'active', Gio.SettingsBindFlags.DEFAULT)
        self.download_folder_row.set_subtitle(folder_label(self.settings))
        profile = self.settings.get_string('torrent-profile')
        self.profile_row.set_selected(PROFILES.index(profile) if profile in PROFILES else 1)
        self.profile_row.connect('notify::selected', lambda row, pspec: self.settings.set_string(
            'torrent-profile', PROFILES[row.get_selected()]))

        if login_only:
            self.show_login()
            if email:
                self.password_row.grab_focus()

    def show_toast(self, message: str):
        self.toast_overlay.add_toast(Adw.Toast(title=message, timeout=6))

    def show_login(self, error: str | None = None):
        self.login_error_label.set_label(error or "")
        self.login_error_label.set_visible(bool(error))
        if self.login_only:
            self.navigation.replace([self.login_page])
        elif self.navigation.get_visible_page() != self.login_page:
            self.navigation.push(self.login_page)
        self.email_row.grab_focus()

    @Gtk.Template.Callback()
    def on_sign_in_activated(self, row):
        self.show_login()

    @Gtk.Template.Callback()
    def on_download_folder_activated(self, row):
        choose_folder(self.get_root(), self.settings, row)

    @Gtk.Template.Callback()
    def on_guest_activated(self, row):
        self.profile = profiles.ensure_guest(self.settings)
        self.start_tour()

    @Gtk.Template.Callback()
    def on_sign_in(self, *args):
        email = self.email_row.get_text().strip()
        password = self.password_row.get_text()
        if not email:
            self.email_row.grab_focus()
            return
        if not password:
            self.password_row.grab_focus()
            return
        self.stack.set_visible_child_name("busy")
        asyncio.create_task(self.try_sign_in(email, password))

    async def try_sign_in(self, email: str, password: str):
        try:
            auth_key, user = await self.integration.authenticate(email, password)
        except LoginFailed as error:
            self.stack.set_visible_child_name("pages")
            self.show_login(str(error))
            return
        except IntegrationError as error:
            self.stack.set_visible_child_name("pages")
            self.show_toast(str(error))
            return
        except Exception as error:
            print(f'[chelsea] sign in raised: {error!r}')
            self.stack.set_visible_child_name("pages")
            self.show_toast(_("Could not sign in: {}").format(error))
            return

        self.profile = self.app.add_account(email, auth_key, user)
        if self.login_only or self.settings.get_boolean('welcome-shown'):
            self.finish()
            return
        self.start_tour()

    def finish(self):
        profile = self.profile or profiles.ensure_guest(self.settings)
        self.force_close()
        self.app.select_profile(profile)

    def start_tour(self):
        self.stack.set_visible_child_name("pages")
        self.navigation.replace([self.tour_page])
        self.update_nav()

    def update_nav(self):
        last = self.carousel.get_n_pages() - 1
        self.back_button.set_opacity(1 if self.current > 0 else 0)
        self.back_button.set_sensitive(self.current > 0)
        self.next_button.set_label(_('Get Started') if self.current >= last else _('Next'))

    def go_to(self, index: int):
        self.carousel.scroll_to(self.carousel.get_nth_page(index), True)

    @Gtk.Template.Callback()
    def on_position_changed(self, carousel, pspec):
        self.current = round(carousel.get_position())
        self.update_nav()

    @Gtk.Template.Callback()
    def on_back(self, button):
        if self.current > 0:
            self.go_to(self.current - 1)

    @Gtk.Template.Callback()
    def on_next(self, button):
        if self.current >= self.carousel.get_n_pages() - 1:
            self.settings.set_boolean('welcome-shown', True)
            self.finish()
        else:
            self.go_to(self.current + 1)

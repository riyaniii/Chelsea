import asyncio
import os
import platform
import sys
import time

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.events import GLibEventLoopPolicy

asyncio.set_event_loop_policy(GLibEventLoopPolicy())

from gettext import gettext as _

from gi.repository import Adw, Gio, GLib, Gtk

from .constants import APPLICATION_ID, DONATE_URL, NAME, RESOURCE_PATH, WEBSITE
from .integrations import Images, Nuvio, Stremio
from . import profiles
from .integrations import LoginFailed
from .mpris import MPRIS
from .passwords import Secrets

METAINFO_PATH = f'{RESOURCE_PATH}/{APPLICATION_ID}.metainfo.xml'
SHUTDOWN_TIMEOUT = 5
REFRESH_INTERVAL = 120
REFRESH_MIN_GAP = 30


def run_until_done(coro, timeout: float) -> None:
    task = asyncio.ensure_future(coro)
    context = GLib.MainContext.default()
    deadline = time.monotonic() + timeout
    while not task.done() and time.monotonic() < deadline:
        if not context.iteration(False):
            time.sleep(0.01)
    if not task.done():
        task.cancel()


class ChelseaApplication(Adw.Application):

    def __init__(self, version: str) -> None:
        super().__init__(application_id=APPLICATION_ID,
                         flags=Gio.ApplicationFlags.HANDLES_OPEN,
                         resource_base_path=RESOURCE_PATH)
        self.version = version
        self.settings = Gio.Settings(schema_id=APPLICATION_ID)
        self.images = Images()
        self.secrets = Secrets('stremio')
        self.stremio = Stremio(self.images, self.settings, self.secrets)
        self.integration = self.stremio
        self.engine = Nuvio()
        self.window = None
        self.player_page = None
        self.pending_link = ''
        self.last_refresh = 0.0
        from .downloads import Downloads
        self.downloads = Downloads(self.settings, self.engine, self.start_engine)
        self.mpris = MPRIS(self)

        self.create_action('quit', lambda *args: self.quit(), ['<control>q'])
        self.create_action('preferences', self.on_preferences_action, ['<control>comma'])
        self.create_action('shortcuts', self.on_shortcuts_action,
                           ['<control>question', '<control>slash'])
        self.create_action('about', self.on_about_action)
        self.create_action('donate', self.on_donate_action)

    def select_profile(self, profile: dict) -> None:
        self.settings.set_string('last-profile', profile['id'])
        self.integration.useProfile(profile)
        self.last_refresh = time.monotonic()
        if self.window is not None:
            self.window.show_main()
        asyncio.create_task(self.start_integration(profile))
        self.remind_to_donate()

    async def start_integration(self, profile: dict) -> None:
        try:
            await self.integration.start()
        except LoginFailed as error:
            if self.window is not None:
                self.window.show_profiles()
                self.window.toast(str(error))
                from .pages.setup import SetupDialog
                SetupDialog(login_only=True, email=profile.get('email', '')).present(self.window)
        except Exception as error:
            print(f'[chelsea] starting {self.integration.display_name} failed: {error}')
            self.integration.ready = True
        self.open_pending_link()

    def add_account(self, email: str, auth_key: str, user: dict) -> dict:
        self.secrets.save(email, auth_key)
        user = user or {}
        return profiles.add_account(self.settings, email, user.get('fullname') or '', user.get('avatar') or '')


    def watch_window(self, window):
        window.connect('notify::is-active', self.on_window_active)
        GLib.timeout_add_seconds(REFRESH_INTERVAL, self.on_refresh_tick)

    def on_window_active(self, window, pspec):
        if window.is_active():
            self.refresh_soon()

    def on_refresh_tick(self):
        if self.window is not None and self.window.is_active():
            self.refresh_soon()
        return GLib.SOURCE_CONTINUE

    def refresh_soon(self):
        now = time.monotonic()
        if not self.integration.ready or now - self.last_refresh < REFRESH_MIN_GAP:
            return
        self.last_refresh = now
        self.integration.runInBackground(self.integration.refresh())

    def start_engine(self) -> bool:
        if self.engine.available:
            return True
        return self.engine.start(
            profile=self.settings.get_string('torrent-profile'),
            disk_cache_bytes=self.settings.get_int('torrent-cache-size') * 1024 ** 3,
            upload=self.settings.get_boolean('torrent-upload'),
        )

    def do_activate(self) -> None:
        if self.window is not None:
            self.window.present()
            return
        window = self.open_window()
        window.show_profiles()
        if not self.settings.get_boolean('welcome-shown'):
            from .pages.setup import SetupDialog
            SetupDialog().present(window)

    def do_open(self, files, n_files, hint) -> None:
        self.do_activate()
        for file in files:
            self.pending_link = file.get_uri()
        self.open_pending_link()

    def open_pending_link(self) -> None:
        if not self.pending_link or self.window is None:
            return
        if self.window.window_stack.get_visible_child_name() != 'main' or not self.integration.ready:
            return
        link, self.pending_link = self.pending_link, ''
        self.activate_action('open_link', GLib.Variant('s', link))

    def open_window(self):
        from .components.window import ChelseaWindow
        if self.window is None:
            self.window = ChelseaWindow(application=self)
            self.window.connect('close-request', self.on_window_closed)
            self.watch_window(self.window)
        self.window.present()
        return self.window

    def on_window_closed(self, window) -> bool:
        self.window = None
        return False

    def do_shutdown(self) -> None:
        run_until_done(self.integration.close(), SHUTDOWN_TIMEOUT)
        run_until_done(self.images.close(), SHUTDOWN_TIMEOUT)
        run_until_done(self.downloads.close(), SHUTDOWN_TIMEOUT)
        self.engine.stop()
        Adw.Application.do_shutdown(self)

    def debug_info(self) -> str:
        lines = [
            f'{NAME}: {self.version}',
            f'Integration: {self.integration.display_name}',
            f'Signed in: {"yes" if self.integration.signed_in else "no"}',
            f'Addons: {", ".join(addon.name for addon in self.integration.addons)}',
            f'Nuvio engine: {self.engine.version() or "not started"}',
            f'Platform: {platform.platform()}',
            f'Python: {platform.python_version()}',
            f'GTK: {Gtk.get_major_version()}.{Gtk.get_minor_version()}.{Gtk.get_micro_version()}',
            f'Libadwaita: {Adw.get_major_version()}.{Adw.get_minor_version()}.{Adw.get_micro_version()}',
        ]
        if os.path.exists('/.flatpak-info'):
            lines.append('Flatpak: yes')
        return '\n'.join(lines)

    def on_about_action(self, *args) -> None:
        dialog = Adw.AboutDialog.new_from_appdata(METAINFO_PATH, self.version)
        dialog.set_version(self.version)
        dialog.set_developer_name('Riyan Parvez')
        dialog.set_website(WEBSITE)
        dialog.set_issue_url(f'{WEBSITE}/issues')
        dialog.set_developers([f'Riyan Parvez {WEBSITE}'])
        dialog.set_designers([f'Riyan Parvez {WEBSITE}'])
        dialog.set_translator_credits(_('translator-credits'))
        dialog.set_copyright('© 2026 Riyan Parvez')
        dialog.set_debug_info(self.debug_info())
        dialog.set_debug_info_filename('chelsea-debug-info.txt')
        dialog.add_link(_('Buy Me a Coffee'), DONATE_URL)
        dialog.add_other_app('io.github.riyaniii.Kaori', 'Kaori', _('Read and discover comics.'))
        dialog.add_acknowledgement_section(_('Built With'), [
            'Stremio https://www.stremio.com',
            'Nuvio Engine https://github.com/NuvioMedia/nuvio-engine',
            'mpv https://mpv.io',
            'Cine https://github.com/diegopvlk/Cine',
            'GTK https://gtk.org',
            'Libadwaita https://gnome.pages.gitlab.gnome.org/libadwaita/',
            'Blueprint https://gnome.pages.gitlab.gnome.org/blueprint-compiler/',
        ])
        dialog.add_legal_section('Nuvio Engine', '© Nuvio contributors', Gtk.License.GPL_3_0, None)
        dialog.add_legal_section('Cine', '© Diego Povliuk. The player design is based on Cine.',
                                 Gtk.License.GPL_3_0, None)
        dialog.add_legal_section('mpv', '© mpv contributors', Gtk.License.LGPL_2_1, None)
        dialog.add_legal_section(
            _('Icons'),
            _('Some icons come from the GNOME Icon Development Kit'),
            Gtk.License.CUSTOM,
            _('These icons are dedicated to the public domain (CC0 1.0).'),
        )
        dialog.present(self.props.active_window)

    def on_donate_action(self, *args) -> None:
        from .components.donate import DonateDialog
        if self.window:
            DonateDialog().present(self.window)

    def remind_to_donate(self) -> None:
        from .components.donate import reminder_due
        if self.settings.get_boolean('welcome-shown') and reminder_due(self.settings):
            GLib.timeout_add_seconds(3, self.show_donate_reminder)

    def show_donate_reminder(self) -> bool:
        if self.window and self.window.get_visible_dialog() is None:
            self.on_donate_action()
        return GLib.SOURCE_REMOVE

    def on_preferences_action(self, *args) -> None:
        from .pages.preferences import PreferencesDialog
        if self.window:
            PreferencesDialog().present(self.window)

    def on_shortcuts_action(self, *args) -> None:
        from .components import build_shortcuts
        build_shortcuts().present(self.props.active_window)

    def create_action(self, name, callback, shortcuts=None, parameter_type=None) -> None:
        action = Gio.SimpleAction.new(name, parameter_type)
        action.connect('activate', callback)
        self.add_action(action)
        if shortcuts:
            self.set_accels_for_action(f'app.{name}', shortcuts)


def main(version: str) -> int:
    return ChelseaApplication(version).run(sys.argv)

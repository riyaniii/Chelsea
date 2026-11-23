import asyncio
from gettext import gettext as _

from gi.repository import Adw, Gio, GLib, GObject, Gtk

from ...components.avatars import load_avatar
from ...components.download_location import choose_folder, folder_label


PROFILES = ("soft", "balanced", "fast")


@Gtk.Template(resource_path='/io/github/riyaniii/Chelsea/pages/preferences/dialog.ui')
class PreferencesDialog(Adw.PreferencesDialog):
    __gtype_name__ = "ChelseaPreferencesDialog"

    account_avatar = Gtk.Template.Child()
    account_name = Gtk.Template.Child()
    account_detail = Gtk.Template.Child()
    sign_in_button = Gtk.Template.Child()
    sign_out_button = Gtk.Template.Child()
    hwdec_row = Gtk.Template.Child()
    download_folder_row = Gtk.Template.Child()
    ask_location_row = Gtk.Template.Child()
    audio_language_row = Gtk.Template.Child()
    subtitle_language_row = Gtk.Template.Child()
    profile_row = Gtk.Template.Child()
    cache_row = Gtk.Template.Child()
    upload_row = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        app = Gio.Application.get_default()
        self.settings = app.settings
        self.integration = app.integration
        self.engine = app.engine

        self.settings.bind("hardware-decoding", self.hwdec_row, "active", Gio.SettingsBindFlags.DEFAULT)
        self.settings.bind("torrent-cache-size", self.cache_row, "value", Gio.SettingsBindFlags.DEFAULT)
        self.settings.bind("torrent-upload", self.upload_row, "active", Gio.SettingsBindFlags.DEFAULT)
        self.settings.bind("ask-download-location", self.ask_location_row, "active", Gio.SettingsBindFlags.DEFAULT)
        self.download_folder_row.set_subtitle(folder_label(self.settings))
        self.audio_language_row.set_text(self.settings.get_string("audio-language"))
        self.subtitle_language_row.set_text(self.settings.get_string("subtitle-language"))

        profile = self.settings.get_string("torrent-profile")
        self.profile_row.set_selected(PROFILES.index(profile) if profile in PROFILES else 1)
        self.profile_row.connect("notify::selected", self.on_profile_changed)

        self.account_handler = self.integration.connect("notify::signed-in", lambda *args: self.update_account())
        self.connect("closed", lambda *args: self.integration.disconnect(self.account_handler))
        self.update_account()

    def update_account(self):
        profile = self.integration.profile or {}
        is_account = profile.get("kind") == "stremio"
        self.account_name.set_label(profile.get("name", ""))
        self.account_detail.set_label(profile.get("email") if is_account else _("Guest profile on this computer"))
        self.account_avatar.set_text(profile.get("name", ""))
        load_avatar(self.account_avatar, self.integration.avatar_url)
        self.sign_in_button.set_visible(not is_account)
        self.sign_out_button.set_visible(is_account)

    def on_profile_changed(self, row, pspec):
        self.settings.set_string("torrent-profile", PROFILES[row.get_selected()])

    @Gtk.Template.Callback()
    def on_audio_language_applied(self, row):
        self.settings.set_string("audio-language", row.get_text().strip())

    @Gtk.Template.Callback()
    def on_subtitle_language_applied(self, row):
        self.settings.set_string("subtitle-language", row.get_text().strip())

    @Gtk.Template.Callback()
    def on_sign_in_activated(self, button):
        from ..setup import SetupDialog
        SetupDialog(login_only=True).present(self)

    @Gtk.Template.Callback()
    def on_sign_out_activated(self, button):
        asyncio.create_task(self.sign_out())

    async def sign_out(self):
        from ... import profiles
        app = Gio.Application.get_default()
        profile = self.integration.profile
        await self.integration.logOut()
        profiles.remove_profile(self.settings, app.secrets, profile["id"])
        self.close()
        app.activate_action("switch_profile", None)

    @Gtk.Template.Callback()
    def on_switch_activated(self, button):
        self.close()
        Gio.Application.get_default().activate_action("switch_profile", None)

    @Gtk.Template.Callback()
    def on_download_folder_activated(self, row):
        choose_folder(self.get_root(), self.settings, row)

    @Gtk.Template.Callback()
    def on_clear_cache_activated(self, row):
        if self.engine.available:
            self.engine.reclaimDiskCache(0)
        self.add_toast(Adw.Toast(title=_("Torrent cache cleared")))

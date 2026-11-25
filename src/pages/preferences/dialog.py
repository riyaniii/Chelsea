import asyncio
from gettext import gettext as _

from gi.repository import Adw, Gio, Gtk

from ... import profiles
from ...components.avatars import load_avatar
from ...components.download_location import choose_folder, folder_label
from ...gpu import nvidia_available
from ...languages import setup_language_row


PROFILES = ("soft", "balanced", "fast")


@Gtk.Template(resource_path='/io/github/riyaniii/Chelsea/pages/preferences/dialog.ui')
class PreferencesDialog(Adw.PreferencesDialog):
    __gtype_name__ = "ChelseaPreferencesDialog"

    account_avatar = Gtk.Template.Child()
    name_row = Gtk.Template.Child()
    email_row = Gtk.Template.Child()
    sign_in_row = Gtk.Template.Child()
    sign_out_row = Gtk.Template.Child()
    hwdec_row = Gtk.Template.Child()
    discrete_gpu_row = Gtk.Template.Child()
    download_folder_row = Gtk.Template.Child()
    ask_location_row = Gtk.Template.Child()
    audio_language_row = Gtk.Template.Child()
    subtitle_language_row = Gtk.Template.Child()
    hide_subtitles_row = Gtk.Template.Child()
    group_streams_row = Gtk.Template.Child()
    open_last_profile_row = Gtk.Template.Child()
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
        self.settings.bind("prefer-discrete-gpu", self.discrete_gpu_row, "active", Gio.SettingsBindFlags.DEFAULT)
        self.discrete_gpu_row.set_visible(nvidia_available())
        self.settings.bind("torrent-cache-size", self.cache_row, "value", Gio.SettingsBindFlags.DEFAULT)
        self.settings.bind("torrent-upload", self.upload_row, "active", Gio.SettingsBindFlags.DEFAULT)
        self.settings.bind("ask-download-location", self.ask_location_row, "active", Gio.SettingsBindFlags.DEFAULT)
        self.download_folder_row.set_subtitle(folder_label(self.settings))
        setup_language_row(self.audio_language_row, self.settings, "audio-language")
        setup_language_row(self.subtitle_language_row, self.settings, "subtitle-language")
        self.settings.bind("hide-other-subtitles", self.hide_subtitles_row, "active", Gio.SettingsBindFlags.DEFAULT)
        self.settings.bind("group-streams", self.group_streams_row, "active", Gio.SettingsBindFlags.DEFAULT)
        self.settings.bind("open-last-profile", self.open_last_profile_row, "active", Gio.SettingsBindFlags.DEFAULT)

        profile = self.settings.get_string("torrent-profile")
        self.profile_row.set_selected(PROFILES.index(profile) if profile in PROFILES else 1)
        self.profile_row.connect("notify::selected", self.on_profile_changed)

        self.account_handler = self.integration.connect("notify::signed-in", lambda *args: self.update_account())
        self.connect("closed", lambda *args: self.integration.disconnect(self.account_handler))
        self.update_account()

    def update_account(self):
        profile = self.integration.profile or {}
        is_account = profile.get("kind") == profiles.ACCOUNT
        self.name_row.set_text(profile.get("name", ""))
        self.email_row.set_subtitle(profile.get("email", ""))
        self.email_row.set_visible(is_account)
        self.account_avatar.set_text(profile.get("name", ""))
        load_avatar(self.account_avatar, self.integration.avatar_url)
        self.sign_in_row.set_visible(not is_account)
        self.sign_out_row.set_visible(is_account)

    def on_profile_changed(self, row, pspec):
        self.settings.set_string("torrent-profile", PROFILES[row.get_selected()])

    @Gtk.Template.Callback()
    def on_sign_in_activated(self, button):
        from ..setup import SetupDialog
        SetupDialog(login_only=True).present(self)

    @Gtk.Template.Callback()
    def on_sign_out_activated(self, button):
        asyncio.create_task(self.sign_out())

    async def sign_out(self):
        app = Gio.Application.get_default()
        profile = self.integration.profile
        await self.integration.logOut()
        profiles.remove_profile(self.settings, app.secrets, profile["id"])
        self.close()
        app.activate_action("switch_profile", None)

    @Gtk.Template.Callback()
    def on_name_applied(self, row):
        name = row.get_text().strip()
        profile = self.integration.profile
        if not name or profile is None:
            row.set_text(profile.get("name", "") if profile else "")
            return
        profiles.update_profile(self.settings, profile["id"], name=name)
        profile["name"] = name
        self.integration.profile_name = name
        self.account_avatar.set_text(name)

    @Gtk.Template.Callback()
    def on_download_folder_activated(self, row):
        choose_folder(self.get_root(), self.settings, row)

    @Gtk.Template.Callback()
    def on_clear_cache_activated(self, row):
        if self.engine.available:
            self.engine.reclaimDiskCache(0)
        self.add_toast(Adw.Toast(title=_("Torrent cache cleared")))

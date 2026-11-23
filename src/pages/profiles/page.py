from gettext import gettext as _

from gi.repository import Adw, Gio, GObject, Gtk

from ... import profiles
from ...components.avatars import load_avatar

TILE_AVATAR_SIZE = 112


class ProfileTile(Gtk.Button):
    __gtype_name__ = "ChelseaProfileTile"

    def __init__(self, profile: dict | None, manage: bool = False):
        super().__init__(css_classes=["flat", "profile-tile"])
        self.profile = profile
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        overlay = Gtk.Overlay()
        if profile is None:
            avatar = Adw.Avatar(size=TILE_AVATAR_SIZE, icon_name="list-add-symbolic", show_initials=False)
            name = _("Add Profile")
            detail = _("Stremio account")
        else:
            is_guest = profile["kind"] == profiles.GUEST
            avatar = Adw.Avatar(size=TILE_AVATAR_SIZE, text=profile["name"], show_initials=not is_guest,
                                icon_name="avatar-default-symbolic")
            name = profile["name"]
            detail = _("This computer") if is_guest else profile["email"]
            load_avatar(avatar, profile.get("avatar", ""))
        overlay.set_child(avatar)
        if manage and profile is not None and profile["kind"] != profiles.GUEST:
            badge = Gtk.Image(icon_name="user-trash-symbolic", css_classes=["profile-remove"],
                              halign=Gtk.Align.END, valign=Gtk.Align.START)
            overlay.add_overlay(badge)
        box.append(overlay)
        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        labels.append(Gtk.Label(label=name, css_classes=["heading"], ellipsize=3, max_width_chars=16))
        labels.append(Gtk.Label(label=detail, css_classes=["dimmed", "caption"], ellipsize=3, max_width_chars=20))
        box.append(labels)
        self.set_child(box)


@Gtk.Template(resource_path='/io/github/riyaniii/Chelsea/pages/profiles/page.ui')
class ProfilesPage(Gtk.WindowHandle):
    __gtype_name__ = "ChelseaProfilesPage"

    manage_button = Gtk.Template.Child()
    title_label = Gtk.Template.Child()
    profiles_box = Gtk.Template.Child()

    __gsignals__ = {
        "profile-chosen": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        "add-profile": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = Gio.Application.get_default()
        self.settings = self.app.settings
        profiles.ensure_guest(self.settings)
        self.settings.connect("changed::profiles", lambda *args: self.refresh())
        self.refresh()

    def refresh(self):
        manage = self.manage_button.get_active()
        self.title_label.set_label(_("Manage Profiles") if manage else _("Who's Watching?"))
        child = self.profiles_box.get_first_child()
        while child is not None:
            self.profiles_box.remove(child)
            child = self.profiles_box.get_first_child()
        for profile in profiles.load_profiles(self.settings):
            tile = ProfileTile(profile, manage)
            tile.connect("clicked", self.on_tile_clicked)
            self.profiles_box.append(tile)
        if not manage:
            add = ProfileTile(None)
            add.connect("clicked", lambda button: self.emit("add-profile"))
            self.profiles_box.append(add)

    def on_tile_clicked(self, tile):
        profile = tile.profile
        if not self.manage_button.get_active():
            self.emit("profile-chosen", profile)
            return
        if profile["kind"] == profiles.GUEST:
            return
        dialog = Adw.AlertDialog(
            heading=_("Remove {}?").format(profile["name"]),
            body=_("The profile is removed from this computer. Its library stays on the Stremio account."),
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("remove", _("Remove"))
        dialog.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", self.on_remove_response, profile)
        dialog.present(self.get_root())

    def on_remove_response(self, dialog, response, profile):
        if response == "remove":
            profiles.remove_profile(self.settings, self.app.secrets, profile["id"])

    @Gtk.Template.Callback()
    def on_manage_toggled(self, button):
        self.refresh()

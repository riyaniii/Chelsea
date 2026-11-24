import asyncio
import os
from gettext import gettext as _
from urllib.parse import urlparse

from gi.repository import Adw, Gio, GLib, GObject, Gtk

from ..integrations import models
from ..integrations.endpoints import addonBase


def play_link(link, file=None):
    app = Gio.Application.get_default()
    name = link.name or link.url
    if file is not None:
        name = os.path.basename(file.path)
    meta = models.Meta()
    meta.update_data(id=link.url, type="other", name=name)
    stream = models.Stream(name=name)
    if link.kind == "magnet":
        stream.update_data(info_hash=link.info_hash, trackers=link.trackers,
                           file_index=file.index if file is not None else -1,
                           filename=os.path.basename(file.path) if file is not None else "")
    else:
        stream.url = link.url
    from ..pages.player import PlayerPage
    window = app.get_active_window() or app.window
    window.main_nav_view.push(PlayerPage(meta, None, link.url, stream))


def dialog_for(link) -> Adw.Dialog:
    if link.kind == "magnet":
        from .magnet_dialog import MagnetDialog
        return MagnetDialog(link)
    return LinkDialog(link)


@Gtk.Template(resource_path='/io/github/riyaniii/Chelsea/components/link_dialog.ui')
class LinkDialog(Adw.Dialog):
    __gtype_name__ = "ChelseaLinkDialog"

    image = Gtk.Template.Child()
    title_label = Gtk.Template.Child()
    description_label = Gtk.Template.Child()
    stack = Gtk.Template.Child()
    action_button = Gtk.Template.Child()
    error_label = Gtk.Template.Child()

    def __init__(self, link, **kwargs):
        super().__init__(**kwargs)
        self.app = Gio.Application.get_default()
        self.integration = self.app.integration
        self.link = link
        self.addon = None
        self.logo_task = None
        self.task = None
        self.closed = False
        if link.kind == "addon":
            self.show_addon_loading()
            self.task = asyncio.create_task(self.load_addon())
        else:
            self.show_video()

    def set_header(self, title: str, description: str, icon_name: str = ""):
        self.set_title(title)
        self.title_label.set_label(title)
        self.description_label.set_label(description)
        self.description_label.set_visible(bool(description))
        if icon_name:
            self.image.set_from_icon_name(icon_name)

    def show_error(self, message: str):
        self.error_label.set_label(message)
        self.stack.set_visible_child_name("error")

    def toast(self, message: str):
        self.app.activate_action("show_toast", GLib.Variant("s", message))

    def show_video(self):
        host = urlparse(self.link.url).netloc
        self.set_header(self.link.name or _("Video Link"), host, "camera-video-symbolic")
        self.action_button.set_label(_("Play"))
        self.stack.set_visible_child_name("action")

    def show_addon_loading(self):
        self.set_header(_("Addon Link"), self.link.url, "application-x-addon-symbolic")
        self.stack.set_visible_child_name("loading")

    async def load_addon(self):
        try:
            addon = await self.integration.previewAddon(self.link.url)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            print(f"addon link {self.link.url}: {error}")
            self.show_error(_("This link is not a Stremio addon"))
            return
        if self.closed:
            return
        self.addon = addon
        self.set_header(addon.name, addon.description)
        if addon.logo:
            addon.bind_property("paintable", self.image, "paintable", GObject.BindingFlags.SYNC_CREATE)
            self.logo_task = self.app.images.startThumbnail(addon, "logo", "paintable")
        self.update_addon_action()

    def update_addon_action(self):
        addon = self.addon
        self.action_button.set_sensitive(not addon.installed)
        if addon.installed:
            self.action_button.set_label(_("Installed"))
        elif addon.configuration_required:
            self.action_button.set_label(_("Configure"))
        else:
            self.action_button.set_label(_("Install"))
        self.stack.set_visible_child_name("action")

    def configure(self):
        uri = addonBase(self.addon.transport_url) + "/configure"
        self.app.activate_action("open_uri", GLib.Variant("s", uri))

    async def install(self):
        self.stack.set_visible_child_name("loading")
        try:
            installed = await self.integration.installAddon(self.addon.transport_url)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self.toast(_("Could not install the addon: {}").format(error))
            self.update_addon_action()
            return
        self.toast(_("Installed {}").format(installed.name))
        self.close()

    @Gtk.Template.Callback()
    def on_action_clicked(self, button):
        if self.link.kind == "url":
            self.close()
            play_link(self.link)
        elif self.addon is not None:
            if self.addon.configuration_required:
                self.configure()
            else:
                self.task = asyncio.create_task(self.install())

    @Gtk.Template.Callback()
    def on_closed(self, dialog):
        self.closed = True
        if self.addon is not None and self.addon.logo:
            self.app.images.stopThumbnail(self.addon, self.logo_task)
            self.logo_task = None

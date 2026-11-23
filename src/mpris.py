from gi.repository import Gio, GLib

from .constants import APPLICATION_ID, NAME

PLAYER_INTERFACE = "org.mpris.MediaPlayer2.Player"
OBJECT_PATH = "/org/mpris/MediaPlayer2"

INTERFACE_XML = """
<node>
  <interface name='org.mpris.MediaPlayer2'>
    <method name='Raise'/>
    <method name='Quit'/>
    <property name='Identity' type='s' access='read'/>
    <property name='DesktopEntry' type='s' access='read'/>
    <property name='CanQuit' type='b' access='read'/>
    <property name='CanRaise' type='b' access='read'/>
    <property name='HasTrackList' type='b' access='read'/>
    <property name='SupportedUriSchemes' type='as' access='read'/>
    <property name='SupportedMimeTypes' type='as' access='read'/>
  </interface>
  <interface name='org.mpris.MediaPlayer2.Player'>
    <method name='Next'/>
    <method name='Previous'/>
    <method name='Pause'/>
    <method name='PlayPause'/>
    <method name='Stop'/>
    <method name='Play'/>
    <method name='Seek'><arg direction='in' name='Offset' type='x'/></method>
    <method name='SetPosition'>
      <arg direction='in' name='TrackId' type='o'/>
      <arg direction='in' name='Position' type='x'/>
    </method>
    <signal name='Seeked'><arg name='Position' type='x'/></signal>
    <property name='PlaybackStatus' type='s' access='read'/>
    <property name='Metadata' type='a{sv}' access='read'/>
    <property name='Position' type='x' access='read'/>
    <property name='Volume' type='d' access='readwrite'/>
    <property name='CanGoNext' type='b' access='read'/>
    <property name='CanGoPrevious' type='b' access='read'/>
    <property name='CanPlay' type='b' access='read'/>
    <property name='CanPause' type='b' access='read'/>
    <property name='CanSeek' type='b' access='read'/>
    <property name='CanControl' type='b' access='read'/>
  </interface>
</node>
"""

NODE_INFO = Gio.DBusNodeInfo.new_for_xml(INTERFACE_XML)


class MPRIS:
    def __init__(self, app):
        self.app = app
        self.connection = None
        self.name_id = 0
        Gio.bus_get(Gio.BusType.SESSION, None, self.on_bus)


    def on_bus(self, source, result):
        try:
            self.connection = Gio.bus_get_finish(result)
        except GLib.Error as error:
            print(f"mpris: no session bus: {error.message}")
            return
        GLib.idle_add(self.register)

    def register(self):
        try:
            for interface in NODE_INFO.interfaces:
                self.connection.register_object_with_closures2(
                    OBJECT_PATH, interface, self.on_method_call, self.on_get_property, self.on_set_property)
            self.name_id = Gio.bus_own_name_on_connection(
                self.connection, f"org.mpris.MediaPlayer2.{APPLICATION_ID}",
                Gio.BusNameOwnerFlags.NONE, None, None)
        except Exception as error:
            print(f"mpris: registering failed: {error}")
        return GLib.SOURCE_REMOVE


    @property
    def page(self):
        return getattr(self.app, "player_page", None)

    def status(self) -> str:
        page = self.page
        if page is None:
            return "Stopped"
        return "Paused" if page.paused else "Playing"

    def metadata(self) -> GLib.Variant:
        page = self.page
        if page is None:
            return GLib.Variant("a{sv}", {})
        values = {
            "mpris:trackid": GLib.Variant("o", "/org/mpris/MediaPlayer2/Track/0"),
            "mpris:length": GLib.Variant("x", int(page.duration * 1_000_000)),
            "xesam:title": GLib.Variant("s", page.get_title() or NAME),
        }
        if page.video is not None:
            values["xesam:album"] = GLib.Variant("s", page.meta.name)
        return GLib.Variant("a{sv}", values)

    def changed(self, values: dict):
        if self.connection is None:
            return
        self.connection.emit_signal(
            None, OBJECT_PATH, "org.freedesktop.DBus.Properties", "PropertiesChanged",
            GLib.Variant("(sa{sv}as)", (PLAYER_INTERFACE, values, [])))


    def update(self):
        page = self.page
        self.changed({
            "PlaybackStatus": GLib.Variant("s", self.status()),
            "Metadata": self.metadata(),
            "CanGoNext": GLib.Variant("b", bool(page and page.next_btn.get_sensitive())),
            "CanGoPrevious": GLib.Variant("b", bool(page and page.previous_btn.get_sensitive())),
        })

    def seeked(self):
        page = self.page
        if self.connection is None or page is None:
            return
        self.connection.emit_signal(None, OBJECT_PATH, PLAYER_INTERFACE, "Seeked",
                                    GLib.Variant("(x)", (int(page.position * 1_000_000),)))


    def on_method_call(self, connection, sender, path, interface, method, params, invocation):
        invocation.return_value(None)
        GLib.idle_add(self.handle_method, method, params)

    def handle_method(self, method, params):
        page = self.page
        window = self.app.get_active_window()
        if method == "Raise" and window is not None:
            window.present()
        elif method == "Quit":
            self.app.quit()
        elif page is not None:
            if method == "PlayPause":
                page.toggle_pause()
            elif method == "Pause":
                page.video_widget.set("pause", True)
            elif method == "Play":
                page.video_widget.set("pause", False)
            elif method == "Next":
                page.play_episode(1)
            elif method == "Previous":
                page.play_episode(-1)
            elif method == "Stop":
                page.get_root().main_nav_view.pop()
            elif method == "Seek":
                page.seek_relative(params.get_child_value(0).get_int64() / 1_000_000)
                self.seeked()
            elif method == "SetPosition":
                page.video_widget.command("seek", str(params.get_child_value(1).get_int64() / 1_000_000), "absolute")
                self.seeked()
        return GLib.SOURCE_REMOVE

    def on_get_property(self, connection, sender, path, interface, prop):
        page = self.page
        if interface == "org.mpris.MediaPlayer2":
            values = {
                "Identity": GLib.Variant("s", NAME),
                "DesktopEntry": GLib.Variant("s", APPLICATION_ID),
                "CanQuit": GLib.Variant("b", True),
                "CanRaise": GLib.Variant("b", True),
                "HasTrackList": GLib.Variant("b", False),
                "SupportedUriSchemes": GLib.Variant("as", []),
                "SupportedMimeTypes": GLib.Variant("as", []),
            }
            return values.get(prop)
        if prop == "PlaybackStatus":
            return GLib.Variant("s", self.status())
        if prop == "Metadata":
            return self.metadata()
        if prop == "Position":
            return GLib.Variant("x", int((page.position if page else 0) * 1_000_000))
        if prop == "Volume":
            return GLib.Variant("d", (page.volume_scale_adj.get_value() / 100) if page else 1.0)
        if prop == "CanGoNext":
            return GLib.Variant("b", bool(page and page.next_btn.get_sensitive()))
        if prop == "CanGoPrevious":
            return GLib.Variant("b", bool(page and page.previous_btn.get_sensitive()))
        if prop in ("CanPlay", "CanPause", "CanSeek", "CanControl"):
            return GLib.Variant("b", page is not None)
        return None

    def on_set_property(self, connection, sender, path, interface, prop, value):
        page = self.page
        if page is not None and prop == "Volume":
            page.volume_scale_adj.set_value(value.get_double() * 100)
            return True
        return False

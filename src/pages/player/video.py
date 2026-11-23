import ctypes
import locale

from gi.repository import GLib, GObject, Gtk

locale.setlocale(locale.LC_NUMERIC, "C")
import mpv

GL_VIEWPORT = 0x0BA2
GL_FRAMEBUFFER_BINDING = 0x8CA6


def load_gl_function(name: str, restype, argtypes):
    library = ctypes.CDLL("libepoxy.so.0")
    pointer = ctypes.c_void_p.in_dll(library, f"epoxy_{name}")
    return ctypes.CFUNCTYPE(restype, *argtypes)(pointer.value)


def proc_address_loader(context):
    uses_glx = "GLX" in type(context).__name__
    candidates = [("libGL.so.1", "glXGetProcAddressARB")] if uses_glx else []
    candidates += [("libEGL.so.1", "eglGetProcAddress"), ("libGL.so.1", "glXGetProcAddressARB")]
    for library_name, function_name in candidates:
        try:
            function = getattr(ctypes.CDLL(library_name), function_name)
        except (OSError, AttributeError):
            continue
        function.restype = ctypes.c_void_p
        function.argtypes = [ctypes.c_char_p]
        return function
    raise RuntimeError("No OpenGL loader found")


PLAYER_OPTIONS = {
    "vo": "libmpv",
    "config": False,
    "terminal": False,
    "load_scripts": False,
    "input_builtin_bindings": False,
    "input_default_bindings": True,
    "input_vo_keyboard": True,
    "keep_open": True,
    "idle": True,
    "cache": True,
    "demuxer_max_bytes": "150MiB",
    "demuxer_max_back_bytes": "50MiB",
    "volume_max": 150,
    "audio_client_name": "Chelsea",
    "sub_border_size": 2,
    "sub_shadow_offset": 0.6,
    "sub_border_color": "#B6000000",
    "sub_shadow_color": "#97000000",
    "sub_color": "#ebebeb",
    "sub_use_margins": False,
    "sub_font": "Adwaita Sans SemiBold",
    "osd_font": "Adwaita Sans",
    "osd_bold": True,
    "osd_bar": False,
    "osd_blur": 1,
    "osd_border_size": 1.5,
    "osd_shadow_offset": 0.6,
    "osd_border_color": "#BE000000",
    "osd_shadow_color": "#1B000000",
    "osd_margin_x": 66,
    "osd_margin_y": 66,
}


class MpvVideo(Gtk.GLArea):
    __gtype_name__ = "ChelseaMpvVideo"

    __gsignals__ = {
        "property-changed": (GObject.SignalFlags.RUN_FIRST, None, (str, object)),
        "end-file": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "message": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "playback-restart": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    OBSERVED = (
        "time-pos",
        "duration",
        "pause",
        "paused-for-cache",
        "cache-buffering-state",
        "core-idle",
        "track-list",
        "volume",
        "mute",
        "aid",
        "sid",
        "seeking",
        "eof-reached",
        "chapter-list",
        "chapter",
        "vid",
        "fullscreen",
        "sub-visibility",
    )

    def __init__(self, **options):
        super().__init__()
        self.set_has_depth_buffer(False)
        self.set_has_stencil_buffer(False)
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.render_context = None
        self.update_queued = False
        self.gl_get_integerv = None
        self.proc_address = None

        self.player = mpv.MPV(**dict(PLAYER_OPTIONS, **options))
        for name in self.OBSERVED:
            self.player.observe_property(name, self.on_property)
        self.player.register_event_callback(self.on_event)
        for name in ("escape", "next-episode", "previous-episode"):
            self.player.register_message_handler(name, self.message_handler(name))

    def message_handler(self, name: str):
        def handler(*args):
            GLib.idle_add(self.emit_message, name)
        return handler

    def emit_message(self, name):
        if self.player is not None:
            self.emit("message", name)
        return GLib.SOURCE_REMOVE

    def on_property(self, name, value):
        GLib.idle_add(self.emit_property, name, value)

    def emit_property(self, name, value):
        if self.player is not None:
            self.emit("property-changed", name, value)
        return GLib.SOURCE_REMOVE

    def on_event(self, event):
        if event.event_id.value == mpv.MpvEventID.END_FILE:
            reason = getattr(event.data, "reason", None)
            GLib.idle_add(self.emit_end, str(reason))
        elif event.event_id.value == mpv.MpvEventID.PLAYBACK_RESTART:
            GLib.idle_add(self.emit_restart)

    def emit_restart(self):
        if self.player is not None:
            self.emit("playback-restart")
        return GLib.SOURCE_REMOVE

    def emit_end(self, reason):
        if self.player is not None:
            self.emit("end-file", reason)
        return GLib.SOURCE_REMOVE

    def do_realize(self):
        Gtk.GLArea.do_realize(self)
        self.make_current()
        if self.get_error() is not None:
            print(f"player: OpenGL is unavailable: {self.get_error().message}")
            return
        loader = proc_address_loader(self.get_context())

        def get_proc_address(context, name):
            return loader(name) or 0

        self.proc_address = mpv.MpvGlGetProcAddressFn(get_proc_address)
        self.gl_get_integerv = load_gl_function(
            "glGetIntegerv", None, [ctypes.c_uint, ctypes.POINTER(ctypes.c_int)])
        self.render_context = mpv.MpvRenderContext(
            self.player, "opengl", opengl_init_params={"get_proc_address": self.proc_address})
        self.render_context.update_cb = self.on_update

    def do_unrealize(self):
        self.make_current()
        if self.render_context is not None:
            self.render_context.free()
            self.render_context = None
        Gtk.GLArea.do_unrealize(self)

    def on_update(self):
        if not self.update_queued:
            self.update_queued = True
            GLib.idle_add(self.redraw)

    def redraw(self):
        self.update_queued = False
        if self.render_context is not None:
            self.queue_render()
        return GLib.SOURCE_REMOVE

    def do_render(self, context):
        if self.render_context is None:
            return False
        viewport = (ctypes.c_int * 4)()
        framebuffer = ctypes.c_int(0)
        self.gl_get_integerv(GL_VIEWPORT, viewport)
        self.gl_get_integerv(GL_FRAMEBUFFER_BINDING, ctypes.byref(framebuffer))
        width, height = viewport[2], viewport[3]
        if width <= 0 or height <= 0:
            scale = self.get_scale_factor()
            width, height = self.get_width() * scale, self.get_height() * scale
        self.render_context.render(flip_y=True, opengl_fbo={"w": width, "h": height, "fbo": framebuffer.value})
        return True

    def play(self, url: str, start: float = 0.0, headers: dict | None = None):
        if headers:
            self.player.http_header_fields = [f"{key}: {value}" for key, value in headers.items()]
        options = {"start": f"{start:.3f}"} if start > 0 else {}
        self.player.loadfile(url, **options)
        self.player.pause = False

    def add_subtitle(self, url: str, title: str = "", lang: str = "", select: bool = False):
        def done(error, result):
            if error:
                print(f"player: subtitle {url} failed: {error}")

        if self.player is None:
            return
        args = [url, "select" if select else "auto"]
        if title or lang:
            args.append(title or lang)
        if lang:
            args.append(lang)
        try:
            self.player.command_async("sub-add", *args, callback=done)
        except Exception as error:
            print(f"player: subtitle {url} failed: {error}")

    def command(self, *args):
        if self.player is None:
            return
        try:
            self.player.command_async(*args, callback=lambda error, result: error and print(
                f"player: command {args} failed: {error}"))
        except Exception as error:
            print(f"player: command {args} failed: {error}")

    def run(self, *args):
        if self.player is None:
            return
        try:
            self.player.command(*args)
        except Exception as error:
            print(f"player: command {args} failed: {error}")

    def get(self, name: str, default=None):
        if self.player is None:
            return default
        try:
            value = getattr(self.player, name.replace("-", "_"))
        except Exception:
            return default
        return default if value is None else value

    def set(self, name: str, value):
        if self.player is None:
            return
        try:
            setattr(self.player, name.replace("-", "_"), value)
        except Exception as error:
            print(f"player: setting {name} failed: {error}")

    def shutdown(self):
        if self.player is None:
            return
        player, self.player = self.player, None
        if self.get_realized():
            self.make_current()
        if self.render_context is not None:
            self.render_context.free()
            self.render_context = None
        player.terminate()

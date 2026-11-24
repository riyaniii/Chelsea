import ctypes

from gi.repository import GLib, Gtk

from .video import GL_FRAMEBUFFER_BINDING, display_params, load_gl_function, mpv, proc_address_loader

THUMB_OPTIONS = {
    "vo": "libmpv",
    "sub": "no",
    "audio": "no",
    "ao": "null",
    "config": False,
    "terminal": False,
    "load_scripts": False,
    "msg_level": "all=no",
    "vd_lavc_threads": 2,
    "vd_lavc_fast": True,
    "vd_lavc_skiploopfilter": "all",
    "vd_lavc_software_fallback": 1,
    "sws_scaler": "fast-bilinear",
    "demuxer_readahead_secs": 0,
    "demuxer_max_bytes": "128KiB",
    "hr_seek": False,
    "pause": True,
    "really_quiet": True,
    "dither": False,
    "linear_downscaling": False,
    "sigmoid_upscaling": False,
    "hdr_compute_peak": False,
    "allow_delayed_peak_detect": True,
}


class ThumbPreview(Gtk.GLArea):
    __gtype_name__ = "ChelseaThumbPreview"

    def __init__(self, hwdec: str = "no"):
        super().__init__()
        self.set_auto_render(False)
        self.set_has_depth_buffer(False)
        self.set_has_stencil_buffer(False)
        self.render_context = None
        self.proc_address = None
        self.gl_get_integerv = None
        self.time = None
        self.seeking = False

        self.player = mpv.MPV(**THUMB_OPTIONS, hwdec=hwdec)
        self.player.observe_property("seeking", self.on_seeking)

    def on_seeking(self, name, seeking):
        if not seeking:
            GLib.idle_add(self.finish_seek)

    def finish_seek(self):
        self.seeking = False
        self.flush_seek()
        return GLib.SOURCE_REMOVE

    def do_realize(self):
        Gtk.GLArea.do_realize(self)
        self.make_current()
        if self.get_error() is not None:
            return
        loader = proc_address_loader(self.get_context())
        self.proc_address = mpv.MpvGlGetProcAddressFn(lambda context, name: loader(name) or 0)
        self.gl_get_integerv = load_gl_function(
            "glGetIntegerv", None, [ctypes.c_uint, ctypes.POINTER(ctypes.c_int)])
        self.render_context = mpv.MpvRenderContext(
            self.player, "opengl", opengl_init_params={"get_proc_address": self.proc_address},
            **display_params(self))
        self.render_context.update_cb = lambda: GLib.idle_add(self.queue_render, priority=GLib.PRIORITY_HIGH_IDLE)

    def do_unrealize(self):
        self.make_current()
        if self.render_context is not None:
            self.render_context.free()
            self.render_context = None
        Gtk.GLArea.do_unrealize(self)

    def do_render(self, context):
        if self.render_context is None:
            return False
        framebuffer = ctypes.c_int(0)
        self.gl_get_integerv(GL_FRAMEBUFFER_BINDING, ctypes.byref(framebuffer))
        scale = self.get_scale_factor()
        self.render_context.render(flip_y=True, opengl_fbo={
            "w": self.get_width() * scale, "h": self.get_height() * scale, "fbo": framebuffer.value})
        return True

    def load(self, url: str, headers: dict | None = None):
        if self.player is None:
            return
        if headers:
            self.player["http-header-fields"] = [f"{key}: {value}" for key, value in headers.items()]
        try:
            self.player.loadfile(url, "replace")
        except Exception as error:
            print(f"thumbnails: could not open {url}: {error}")

    def seek(self, time: float):
        self.time = time
        self.flush_seek()

    def flush_seek(self):
        if self.player is None or self.seeking or self.time is None:
            return
        time, self.time = self.time, None
        self.seeking = True
        try:
            self.player.command_async("seek", str(time), "absolute+keyframes")
        except Exception:
            self.seeking = False

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

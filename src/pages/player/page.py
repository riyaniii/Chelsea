import asyncio
from gettext import gettext as _

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from ...languages import code_list
from ...components.formats import duration_text, episode_code, rate_text
from ...integrations import EngineError, models
from .bindings import MOUSE_BUTTONS, build_bindings, key_combo, nonrepeatable_keys
from .options import OptionsButton
from .thumbnail import ThumbPreview
from .video import MpvVideo, hwdec_option

HIDE_UI_S = 2
SAVE_INTERVAL_S = 10
STATUS_INTERVAL_MS = 1000
INDICATOR_MS = 385
SPACE_HOLD_MS = 500
MAX_ADDON_SUBTITLES = 60
THUMB_WIDTH = 200
THUMB_SIZE = 168
MAX_VOLUME = 150


def track_label(track: dict) -> str:
    parts = [track.get("title") or "", track.get("lang") or ""]
    label = " · ".join(part for part in parts if part)
    if track.get("codec"):
        label = f"{label} ({track['codec']})" if label else track["codec"]
    return label or _("Track {}").format(track.get("id"))


def click_delay_ms() -> int:
    settings = Gtk.Settings.get_default()
    double_click = settings.props.gtk_double_click_time if settings else 400
    return max(double_click, 200)


@Gtk.Template(resource_path='/io/github/riyaniii/Chelsea/pages/player/page.ui')
class PlayerPage(Adw.NavigationPage):
    __gtype_name__ = "ChelseaPlayerPage"

    window_handle = Gtk.Template.Child()
    video_overlay = Gtk.Template.Child()
    video_bin = Gtk.Template.Child()
    revealer_icon_indicator = Gtk.Template.Child()
    icon_indicator = Gtk.Template.Child()
    status_stack = Gtk.Template.Child()
    status_label = Gtk.Template.Child()
    status_detail = Gtk.Template.Child()
    error_label = Gtk.Template.Child()
    error_detail = Gtk.Template.Child()
    revealer_ui = Gtk.Template.Child()
    headerbar = Gtk.Template.Child()
    title_widget = Gtk.Template.Child()
    controls_box = Gtk.Template.Child()
    controls_separator = Gtk.Template.Child()
    previous_btn = Gtk.Template.Child()
    play_pause_btn = Gtk.Template.Child()
    next_btn = Gtk.Template.Child()
    volume_menu_btn = Gtk.Template.Child()
    mute_toggle_btn = Gtk.Template.Child()
    volume_scale = Gtk.Template.Child()
    volume_scale_adj = Gtk.Template.Child()
    subtitles_menu_btn = Gtk.Template.Child()
    audio_tracks_menu_btn = Gtk.Template.Child()
    video_tracks_menu_btn = Gtk.Template.Child()
    chapters_menu_btn = Gtk.Template.Child()
    options_menu_btn = Gtk.Template.Child()
    fullscreen_btn = Gtk.Template.Child()
    video_progress_adj = Gtk.Template.Child()
    video_progress_scale = Gtk.Template.Child()
    time_elapsed_label = Gtk.Template.Child()
    time_total_label = Gtk.Template.Child()

    def __init__(self, meta: models.Meta, video: models.Video | None, video_id: str,
                 stream: models.Stream, from_start: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.from_start = from_start
        app = Gio.Application.get_default()
        self.app = app
        self.settings = app.settings
        self.integration = app.integration
        self.engine = app.engine
        self.meta = meta
        self.video = video
        self.video_id = video_id
        self.stream = stream
        self.episodes = list(meta.videos) if meta.is_series else []
        self.tracked = not meta.id.startswith(("magnet:", "http://", "https://", "file://"))

        self.position = 0.0
        self.duration = 0.0
        self.failed = False
        self.paused = False
        self.opening = True
        self.waiting_for_cache = False
        self.cache_percent = None
        self.started = False
        self.closed = False
        self.switching = False
        self.stream_id = ""
        self.task = None
        self.hide_source = 0
        self.status_source = 0
        self.save_source = 0
        self.space_source = 0
        self.inhibit_cookie = 0
        self.window = None
        self.window_handlers = []
        self.last_saved = 0.0
        self.last_motion = None
        self.last_progress_motion = None
        self.syncing_volume = False
        self.syncing_progress = False
        self.show_remaining = self.settings.get_boolean("show-remaining")
        self.tracks = []
        self.chapters = []
        self.chapter_start = None
        self.addon_subtitles = []
        self.url = ""
        self.thumb = None
        self.thumb_loaded = True
        self.thumb_width = THUMB_WIDTH
        self.hover_time = 0.0
        self.fine_tuning = False
        self.playing_on_press = False
        self.skip_pause_changes = 0
        self.click_holding = False
        self.space_pressed = False
        self.space_holding = False
        self.normal_speed = 1.0
        self.wheel_y = 0.0
        self.pressed_keys = set()
        self.preferred_subtitles = code_list(self.settings.get_string("subtitle-language"))
        self.hide_other_subtitles = self.settings.get_boolean("hide-other-subtitles")

        hwdec = hwdec_option(self.settings.get_boolean("hardware-decoding"))
        options = {"hwdec": hwdec, "volume": self.settings.get_double("volume")}
        if self.settings.get_string("audio-language"):
            options["alang"] = self.settings.get_string("audio-language")
        if self.settings.get_string("subtitle-language"):
            options["slang"] = self.settings.get_string("subtitle-language")
        self.video_widget = MpvVideo(**options)
        self.video_widget.connect("property-changed", self.on_property_changed)
        self.video_widget.connect("end-file", self.on_end_file)
        self.video_widget.connect("message", self.on_message)
        self.video_widget.connect("playback-restart", self.on_playback_restart)
        self.video_widget.run("load-input-conf", f"memory://{build_bindings()}")
        self.nonrepeat_keys = nonrepeatable_keys(self.video_widget.get("input-bindings", []))
        self.video_bin.set_child(self.video_widget)
        self.options_menu_btn.video = self.video_widget

        self.volume_scale_adj.set_upper(MAX_VOLUME)
        self.volume_scale.add_mark(100.0, Gtk.PositionType.BOTTOM, None)
        self.volume_scale_adj.set_value(self.settings.get_double("volume"))
        self.video_progress_adj.connect("value-changed", self.on_progress_changed)

        self.setup_actions()
        self.setup_controllers()
        self.setup_time_tooltip()

        for button in (self.volume_menu_btn, self.subtitles_menu_btn, self.audio_tracks_menu_btn,
                       self.video_tracks_menu_btn, self.chapters_menu_btn, self.options_menu_btn):
            button.connect("notify::active", self.on_menu_active_changed)

        self.connect("shown", self.on_shown)
        self.connect("hiding", self.on_hiding)
        self.update_titles()
        self.update_track_menus()
        self.update_volume_icon()
        self.set_status(_("Opening Stream"))

    def setup_actions(self):
        self.actions = Gio.SimpleActionGroup()
        for name in ("audio", "subtitle", "video"):
            action = Gio.SimpleAction.new_stateful(name, GLib.VariantType.new("s"), GLib.Variant("s", "auto"))
            action.connect("change-state", self.on_track_selected)
            self.actions.add_action(action)
        addon_subtitle = Gio.SimpleAction.new("addon-subtitle", GLib.VariantType.new("i"))
        addon_subtitle.connect("activate", self.on_addon_subtitle)
        self.actions.add_action(addon_subtitle)
        chapter = Gio.SimpleAction.new_stateful("chapter", GLib.VariantType.new("i"), GLib.Variant("i", 0))
        chapter.connect("change-state", self.on_chapter_selected)
        self.actions.add_action(chapter)
        self.insert_action_group("player", self.actions)

    def setup_controllers(self):
        self.motion_controls = Gtk.EventControllerMotion()
        self.controls_box.add_controller(self.motion_controls)
        self.motion_header = Gtk.EventControllerMotion()
        self.headerbar.add_controller(self.motion_header)
        self.motion_separator = Gtk.EventControllerMotion()
        self.controls_separator.add_controller(self.motion_separator)

        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self.on_motion)
        self.add_controller(motion)

        for number, button in MOUSE_BUTTONS.items():
            click = Gtk.GestureClick(button=number)
            click.connect("pressed", self.on_click_pressed, button)
            click.connect("released", self.on_click_released, button)
            self.video_overlay.add_controller(click)

        long_press = Gtk.GestureLongPress()
        long_press.connect("pressed", self.on_click_hold)
        long_press.connect("end", self.cancel_click_hold)
        long_press.connect("cancelled", self.cancel_click_hold)
        self.window_handle.add_controller(long_press)

        for controller in self.window_handle.observe_controllers():
            if isinstance(controller, Gtk.GestureClick):
                controller.set_propagation_phase(Gtk.PropagationPhase.NONE)
                controller.set_button(9)

        wheel = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        wheel.connect("scroll", self.on_video_scroll)
        self.video_overlay.add_controller(wheel)

        volume_wheel = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        volume_wheel.connect("scroll", self.on_volume_scroll)
        self.volume_scale.add_controller(volume_wheel)

        volume_middle_click = Gtk.GestureClick(button=2)
        volume_middle_click.connect("pressed", lambda *args: self.video_widget.command("cycle", "mute"))
        self.volume_menu_btn.add_controller(volume_middle_click)

        progress_middle_click = Gtk.GestureClick(button=2)
        progress_middle_click.connect("pressed", self.go_to_chapter_start)
        self.video_progress_scale.add_controller(progress_middle_click)

        for controller in self.video_progress_scale.observe_controllers():
            if isinstance(controller, Gtk.GestureDrag):
                controller.connect("drag-begin", self.on_progress_pressed)
                controller.connect("drag-end", self.on_progress_released)
            if isinstance(controller, Gtk.GestureLongPress):
                controller.connect("pressed", lambda *args: setattr(self, "fine_tuning", True))
                controller.connect("end", lambda *args: setattr(self, "fine_tuning", False))

        self.keys = Gtk.EventControllerKey()
        self.keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self.keys.connect("key-pressed", self.on_key_event, "keypress")
        self.keys.connect("key-released", self.on_key_event, "keyup")


    def on_shown(self, page):
        if self.started:
            return
        self.started = True
        self.window = self.get_root()
        self.window.add_controller(self.keys)
        self.window_handlers = [
            self.window.connect("notify::fullscreened", self.on_window_fullscreen_changed),
            self.window.connect("notify::is-active", self.on_window_active_changed),
        ]
        self.save_source = GLib.timeout_add_seconds(SAVE_INTERVAL_S, self.on_save_tick)
        self.status_source = GLib.timeout_add(STATUS_INTERVAL_MS, self.on_status_tick)
        self.task = asyncio.create_task(self.start())
        self.app.player_page = self
        self.app.mpris.update()
        self.set_inhibit(not self.paused)
        self.show_ui()
        self.grab_focus()

    def on_hiding(self, page):
        if self.closed:
            return
        self.closed = True
        self.save_progress()
        if self.app.player_page is self:
            self.app.player_page = None
            self.app.mpris.update()
        if self.window is not None:
            if self.keys.get_widget() is self.window:
                self.window.remove_controller(self.keys)
            for handler in self.window_handlers:
                self.window.disconnect(handler)
            if self.window.is_fullscreen():
                self.window.unfullscreen()
            self.window.set_cursor(None)
        self.set_inhibit(False)
        for name in ("hide_source", "status_source", "save_source", "space_source"):
            source = getattr(self, name)
            if source:
                GLib.source_remove(source)
                setattr(self, name, 0)
        if self.task:
            self.task.cancel()
        self.settings.set_double("volume", self.volume_scale_adj.get_value())
        self.video_widget.shutdown()
        if self.thumb is not None:
            self.thumb.shutdown()
        self.stop_stream()

    def stop_stream(self):
        if self.stream_id:
            self.engine.stopStream(self.stream_id)
            self.stream_id = ""

    def set_inhibit(self, inhibit: bool):
        if inhibit and not self.inhibit_cookie and self.window is not None:
            self.inhibit_cookie = self.app.inhibit(self.window, Gtk.ApplicationInhibitFlags.IDLE, _("Playing video"))
        elif not inhibit and self.inhibit_cookie:
            self.app.uninhibit(self.inhibit_cookie)
            self.inhibit_cookie = 0

    def update_titles(self):
        if self.video is not None:
            title = self.video.title or episode_code(self.video)
        else:
            title = self.meta.name
        self.set_title(title)
        self.title_widget.set_title(title)
        index = self.episode_index()
        self.previous_btn.set_visible(bool(self.episodes))
        self.next_btn.set_visible(bool(self.episodes))
        self.previous_btn.set_sensitive(index is not None and index > 0)
        self.next_btn.set_sensitive(index is not None and index + 1 < len(self.episodes))


    async def start(self):
        try:
            url = await self.resolve_url()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self.set_error(_("Could Not Play This Stream"), str(error))
            return
        start = self.resume_position()
        self.set_status(_("Loading"))
        self.url = url
        self.video_widget.play(url, start=start, headers=self.stream.headers)
        self.thumb_loaded = False
        await self.add_addon_subtitles()

    async def resolve_url(self) -> str:
        stream = self.stream
        if not stream.is_torrent:
            return stream.url
        if not self.app.start_engine():
            raise EngineError(self.engine.error)
        self.set_status(_("Connecting to Peers"))
        file_index = stream.file_index if stream.file_index >= 0 else None
        info = await self.engine.stream(stream.info_hash, file_index, stream.trackers, stream.filename)
        self.stream_id = info["stream_id"]
        return info["url"]

    def resume_position(self) -> float:
        if not self.tracked or self.from_start:
            return 0.0
        item = self.integration.libraryItem(self.meta.id)
        if item and item.video_id == self.video_id and item.time_offset > 0:
            return item.time_offset / 1000
        return 0.0

    async def add_addon_subtitles(self):
        if not self.tracked:
            return
        extra = {}
        if self.stream.filename:
            extra["filename"] = self.stream.filename
        try:
            subtitles = await self.integration.getSubtitles(self.meta.type, self.video_id, **extra)
        except Exception as error:
            print(f"player: subtitles failed: {error}")
            return
        subtitles = [subtitle for subtitle in subtitles if self.shows_subtitle(subtitle.lang)]
        subtitles.sort(key=lambda item: (not self.is_preferred(item.lang), item.lang))
        self.addon_subtitles = subtitles[:MAX_ADDON_SUBTITLES]
        self.update_track_menus()
        if self.addon_subtitles and self.is_preferred(self.addon_subtitles[0].lang):
            has_preferred = any(track.get("type") == "sub" and self.is_preferred(track.get("lang"))
                                for track in self.tracks)
            if not has_preferred:
                self.load_addon_subtitle(0, select=True)

    def is_preferred(self, lang: str | None) -> bool:
        return (lang or "").lower() in self.preferred_subtitles

    def shows_subtitle(self, lang: str | None) -> bool:
        if not self.hide_other_subtitles or not self.preferred_subtitles:
            return True
        return self.is_preferred(lang)

    def load_addon_subtitle(self, index: int, select: bool = True):
        if not (0 <= index < len(self.addon_subtitles)):
            return
        subtitle = self.addon_subtitles[index]
        title = f"{subtitle.lang} · {subtitle.source_name}"
        self.video_widget.add_subtitle(subtitle.url, title, subtitle.lang, select=select)
        self.addon_subtitles[index] = None
        self.update_track_menus()

    def on_addon_subtitle(self, action, value):
        self.load_addon_subtitle(value.get_int32())

    def save_progress(self):
        if not self.tracked:
            return
        if self.duration <= 0 or self.position <= 0 or abs(self.position - self.last_saved) < 1:
            return
        self.last_saved = self.position
        self.integration.runInBackground(
            self.integration.saveProgress(self.meta, self.video_id, self.position, self.duration))

    def on_save_tick(self):
        if not self.paused:
            self.save_progress()
        return GLib.SOURCE_CONTINUE


    def episode_index(self):
        for index, video in enumerate(self.episodes):
            if video.id == self.video_id:
                return index
        return None

    async def pick_stream(self, video: models.Video) -> models.Stream | None:
        fallback = None
        same_source = None
        async for source, streams in self.integration.iterStreams(self.meta.type, video.id):
            for stream in streams:
                if stream.is_external:
                    continue
                if self.stream.binge_group and stream.binge_group == self.stream.binge_group:
                    return stream
                if same_source is None and stream.source_id == self.stream.source_id:
                    same_source = stream
                if fallback is None:
                    fallback = stream
        return same_source or fallback

    async def switch_episode(self, video: models.Video):
        if self.switching:
            return
        self.switching = True
        self.save_progress()
        self.video_widget.command("stop")
        self.stop_stream()
        self.video = video
        self.video_id = video.id
        self.position = self.duration = self.last_saved = 0.0
        self.update_titles()
        self.app.mpris.update()
        self.update_progress(0)
        self.set_status(_("Looking for Streams"))
        try:
            stream = await self.pick_stream(video)
            if stream is None:
                self.set_error(_("No Streams Found"), _("No addon has a stream for this episode"))
                return
            self.stream = stream
            await self.start()
        finally:
            self.switching = False

    def play_episode(self, offset: int):
        index = self.episode_index()
        if index is None or not (0 <= index + offset < len(self.episodes)):
            return
        if self.task:
            self.task.cancel()
        self.task = asyncio.create_task(self.switch_episode(self.episodes[index + offset]))


    def setup_time_tooltip(self):
        self.time_tooltip_label = Gtk.Label(use_markup=True, justify=Gtk.Justification.CENTER)
        self.time_tooltip_label.add_css_class("numeric")

        def layer_and_revealer(child, margin_bottom):
            layer = Gtk.Fixed(valign=Gtk.Align.END, margin_bottom=margin_bottom,
                              can_focus=False, can_target=False)
            revealer = Gtk.Revealer(css_name="time-tooltip", transition_duration=175,
                                    transition_type=Gtk.RevealerTransitionType.CROSSFADE)
            revealer.set_child(child)
            layer.put(revealer, 0, 0)
            self.video_overlay.add_overlay(layer)
            return layer, revealer

        self.label_layer, self.label_revealer = layer_and_revealer(self.time_tooltip_label, 38)
        self.thumb_frame = Gtk.Frame()
        self.thumb_layer, self.thumb_revealer = layer_and_revealer(self.thumb_frame, 72)

        hover = Gtk.EventControllerMotion()
        hover.connect("enter", self.reset_progress_motion)
        hover.connect("motion", self.on_progress_motion)
        hover.connect("leave", self.hide_time_tooltip)
        self.video_progress_scale.add_controller(hover)

    def setup_thumbnails(self):
        if self.closed or not self.url:
            return GLib.SOURCE_REMOVE
        width = self.video_widget.get("width", 1280) or 1280
        height = self.video_widget.get("height", 720) or 720
        if width >= height:
            thumb_width = THUMB_WIDTH
            thumb_height = int(height / width * thumb_width)
            if thumb_height == thumb_width:
                thumb_width = thumb_height = THUMB_SIZE
        else:
            thumb_height = THUMB_SIZE
            thumb_width = int(width / height * thumb_height)
        if self.thumb is None:
            hwdec = hwdec_option(self.settings.get_boolean("hardware-decoding"))
            self.thumb = ThumbPreview(hwdec)
            self.thumb_frame.set_child(self.thumb)
            self.thumb.realize()
        self.thumb_width = thumb_width
        self.thumb.set_size_request(thumb_width, thumb_height)
        self.thumb.load(self.url, self.stream.headers)
        return GLib.SOURCE_REMOVE

    def hide_time_tooltip(self, *args):
        self.label_revealer.set_reveal_child(False)
        self.thumb_revealer.set_reveal_child(False)

    def reset_progress_motion(self, *args):
        self.last_progress_motion = None

    def move_tooltip(self, revealer, layer, x, width):
        position = max(0, min(x - width / 2 + 23, self.get_width() - width))
        layer.move(revealer, position, 0)

    def on_progress_motion(self, controller, x, y):
        if (x, y) == self.last_progress_motion:
            return
        self.last_progress_motion = (x, y)
        if self.fine_tuning:
            self.hide_time_tooltip()
            return
        scale_width = self.video_progress_scale.get_width()
        if scale_width <= 0 or self.duration <= 0:
            return
        self.hover_time = max(0.0, min(1.0, x / scale_width)) * self.duration
        title = None
        self.chapter_start = None
        for chapter in self.chapters:
            if chapter.get("time", 0) <= self.hover_time:
                title = chapter.get("title")
                self.chapter_start = chapter.get("time", 0)
        text = duration_text(self.hover_time)
        if title:
            text = f"{text} ‐ <b>{GLib.markup_escape_text(title)}</b>"
        self.time_tooltip_label.set_markup(text)
        self.label_revealer.set_reveal_child(True)
        label_width = self.label_revealer.get_preferred_size()[1].width
        self.move_tooltip(self.label_revealer, self.label_layer, x, label_width)
        if self.thumb is not None:
            self.thumb_revealer.set_reveal_child(True)
            self.move_tooltip(self.thumb_revealer, self.thumb_layer, x, self.thumb_width + 12)
            self.thumb.seek(self.hover_time)

    def go_to_chapter_start(self, *args):
        if self.chapter_start is not None:
            self.video_widget.command("seek", str(self.chapter_start), "absolute")


    def set_status(self, title: str):
        self.failed = False
        self.opening = True
        self.cache_percent = None
        self.status_label.set_label(title)
        self.update_status()

    def set_error(self, title: str, detail: str):
        self.failed = True
        self.error_label.set_label(title)
        self.error_detail.set_label(detail)
        self.error_detail.set_visible(bool(detail))
        self.update_status()
        self.show_ui(stay=True)

    def update_status(self):
        if self.failed:
            self.status_stack.set_visible_child_name("error")
            self.status_stack.set_visible(True)
            return
        loading = self.opening or self.waiting_for_cache
        self.status_stack.set_visible_child_name("loading")
        self.status_stack.set_visible(loading)
        if loading:
            self.status_detail.set_label(self.status_text())
            self.status_detail.set_visible(bool(self.status_detail.get_label()))

    def status_text(self) -> str:
        parts = []
        if self.stream.is_torrent and self.engine.available:
            parts.append(_("{} peers").format(self.engine.peers))
            parts.append(rate_text(self.engine.download_rate))
        if self.cache_percent is not None:
            parts.append(f"{self.cache_percent}%")
        return " · ".join(parts)

    def on_playback_restart(self, widget):
        if self.opening:
            print(f"player: hwdec {widget.get('hwdec-current', 'unknown') or 'no'}")
        self.opening = False
        self.update_status()

    def on_status_tick(self):
        if self.status_stack.get_visible() and not self.failed:
            self.update_status()
        return GLib.SOURCE_CONTINUE

    def show_icon_indicator(self, icon: str):
        if self.opening:
            return
        self.icon_indicator.set_from_icon_name(icon)
        self.revealer_icon_indicator.set_reveal_child(True)
        GLib.timeout_add(INDICATOR_MS, self.hide_icon_indicator)

    def hide_icon_indicator(self):
        self.revealer_icon_indicator.set_reveal_child(False)
        return GLib.SOURCE_REMOVE

    def show_icon_if_asked(self, icon: str):
        user_data = self.video_widget.get("user-data", {})
        if user_data.get("show-icon") == "yes":
            self.video_widget.run("del", "user-data/show-icon")
            self.show_icon_indicator(icon)


    def update_progress(self, position: float):
        self.syncing_progress = True
        self.video_progress_adj.set_value(position)
        self.syncing_progress = False
        if self.show_remaining:
            remaining = self.duration - position if self.duration > position else 0
            self.time_elapsed_label.set_label(f"-{duration_text(remaining)}")
        else:
            self.time_elapsed_label.set_label(duration_text(position))
        self.time_elapsed_label.set_margin_end(3 if self.show_remaining else 0)

    def update_duration(self, duration: float):
        self.duration = duration
        self.time_total_label.set_label(duration_text(duration))
        can_seek = duration > 0
        self.video_progress_scale.set_can_target(can_seek)
        self.video_progress_scale.set_can_focus(can_seek)
        if not can_seek:
            return
        self.syncing_progress = True
        self.video_progress_adj.set_upper(duration)
        self.syncing_progress = False
        if duration >= 86400:
            width = 10
        elif duration >= 3600:
            width = 7
        elif duration >= 600:
            width = 6
        else:
            width = 5
        self.time_elapsed_label.set_width_chars(width)

    def update_play_pause(self, paused: bool):
        play = "cine-playback-start-symbolic"
        pause = "cine-playback-pause-symbolic"
        self.play_pause_btn.set_icon_name(play if paused else pause)
        self.play_pause_btn.update_property([Gtk.AccessibleProperty.LABEL], [_("Play") if paused else _("Pause")])
        self.show_icon_indicator(pause if paused else play)

    def update_subtitle_icon(self):
        visible = self.video_widget.get("sub-visibility", True)
        selected = self.video_widget.get("sid", False)
        icon = "cine-subtitles-symbolic" if visible and selected else "cine-subtitles-off-symbolic"
        self.subtitles_menu_btn.set_icon_name(icon)
        return icon

    def on_property_changed(self, widget, name, value):
        if name == "time-pos" and value is not None:
            self.position = value
            self.update_progress(value)
        elif name == "duration" and value:
            if not self.thumb_loaded:
                self.thumb_loaded = True
                GLib.timeout_add(500, self.setup_thumbnails)
            self.update_duration(value)
        elif name == "pause":
            self.on_pause_changed(bool(value))
        elif name == "paused-for-cache":
            self.waiting_for_cache = bool(value)
            if self.waiting_for_cache:
                self.status_label.set_label(_("Buffering"))
            self.update_status()
        elif name == "cache-buffering-state":
            self.cache_percent = value
            if self.status_stack.get_visible():
                self.update_status()
        elif name == "track-list":
            self.tracks = value or []
            self.update_track_menus()
        elif name == "chapter-list":
            self.chapters = sorted(value or [], key=lambda chapter: chapter.get("time", 0))
            self.update_chapters_menu()
        elif name == "chapter":
            self.sync_chapter_state()
        elif name in ("aid", "sid", "vid"):
            action = {"aid": "audio", "sid": "subtitle", "vid": "video"}[name]
            self.actions.lookup_action(action).set_state(GLib.Variant("s", str(value) if value else "no"))
            if name == "sid":
                self.update_subtitle_icon()
            elif name == "aid":
                self.audio_tracks_menu_btn.set_icon_name(
                    "cine-audio-symbolic" if value else "cine-audio-off-symbolic")
        elif name == "sub-visibility":
            self.show_icon_if_asked(self.update_subtitle_icon())
        elif name == "volume" and value is not None:
            self.on_volume_property(value)
        elif name == "mute":
            self.mute_toggle_btn.set_active(bool(value))
            self.show_icon_if_asked(self.update_volume_icon())
        elif name == "fullscreen":
            self.sync_fullscreen(bool(value))
        elif name == "eof-reached" and value:
            self.position = self.duration
            self.save_progress()
            index = self.episode_index()
            if index is not None and index + 1 < len(self.episodes):
                self.play_episode(1)
            else:
                self.show_ui(stay=True)

    def on_pause_changed(self, paused: bool):
        if not paused and self.video_widget.get("eof-reached", False):
            self.video_widget.command("seek", "0", "absolute")
            self.skip_pause_changes = 0
        if self.skip_pause_changes > 0:
            self.skip_pause_changes -= 1
            return
        self.paused = paused
        self.app.mpris.update()
        self.set_inhibit(not paused)
        self.update_play_pause(paused)
        if paused:
            self.show_ui(stay=True)
            self.save_progress()
        else:
            self.hide_ui_timeout()

    def on_volume_property(self, value: float):
        volume = int(value)
        self.syncing_volume = True
        self.volume_scale_adj.set_value(volume)
        self.syncing_volume = False
        if volume > 0 and self.video_widget.get("mute", False):
            self.video_widget.set("mute", False)
        self.update_volume_icon()
        self.settings.set_double("volume", volume)
        self.app.mpris.update()

    def on_end_file(self, widget, reason):
        if reason == "4" and not self.switching:
            self.set_error(_("Playback Failed"), _("The stream could not be decoded"))

    def on_message(self, widget, name):
        if name == "next-episode":
            self.play_episode(1)
        elif name == "previous-episode":
            self.play_episode(-1)
        elif name == "escape":
            if self.window is not None and self.window.is_fullscreen():
                self.video_widget.set("fullscreen", False)
            elif self.window is not None:
                self.window.main_nav_view.pop()


    def update_track_menus(self):
        menus = {"audio": Gio.Menu(), "sub": Gio.Menu(), "video": Gio.Menu()}
        menus["sub"].append(_("None"), "player.subtitle::no")
        actions = {"audio": "audio", "sub": "subtitle", "video": "video"}
        counts = {"audio": 0, "sub": 0, "video": 0}
        for track in self.tracks:
            kind = track.get("type")
            if kind not in menus:
                continue
            if kind == "sub" and track.get("lang") and not self.shows_subtitle(track.get("lang")):
                continue
            menus[kind].append(track_label(track), f"player.{actions[kind]}::{track.get('id')}")
            counts[kind] += 1
        addon_section = Gio.Menu()
        for index, subtitle in enumerate(self.addon_subtitles):
            if subtitle is None:
                continue
            item = Gio.MenuItem.new(f"{subtitle.lang or _('Unknown')} · {subtitle.source_name}", None)
            item.set_action_and_target_value("player.addon-subtitle", GLib.Variant("i", index))
            addon_section.append_item(item)
        if addon_section.get_n_items():
            menus["sub"].append_section(_("From Addons"), addon_section)
        self.audio_tracks_menu_btn.set_menu_model(menus["audio"])
        self.subtitles_menu_btn.set_menu_model(menus["sub"])
        self.video_tracks_menu_btn.set_menu_model(menus["video"])
        self.audio_tracks_menu_btn.set_visible(counts["audio"] > 0)
        self.audio_tracks_menu_btn.set_sensitive(counts["audio"] > 1)
        self.video_tracks_menu_btn.set_visible(counts["video"] > 1)

    def update_chapters_menu(self):
        self.video_progress_scale.clear_marks()
        menu = Gio.Menu()
        for index, chapter in enumerate(self.chapters):
            title = chapter.get("title") or _("Chapter {}").format(index + 1)
            item = Gio.MenuItem.new(f"{duration_text(chapter.get('time', 0))}  {title}", None)
            item.set_action_and_target_value("player.chapter", GLib.Variant("i", index))
            menu.append_item(item)
            if chapter.get("time") is not None:
                self.video_progress_scale.add_mark(chapter["time"], Gtk.PositionType.TOP, None)
        self.chapters_menu_btn.set_menu_model(menu)
        self.chapters_menu_btn.set_visible(bool(self.chapters))

    def sync_chapter_state(self):
        chapter = self.video_widget.get("chapter", 0)
        self.actions.lookup_action("chapter").set_state(GLib.Variant("i", max(chapter, 0)))

    def on_chapter_selected(self, action, value):
        index = value.get_int32()
        if 0 <= index < len(self.chapters):
            self.video_widget.command("seek", str(self.chapters[index].get("time", 0)), "absolute")
        action.set_state(value)

    @Gtk.Template.Callback()
    def on_chapters_menu_active(self, button, pspec):
        if button.get_active():
            self.sync_chapter_state()

    def on_track_selected(self, action, value):
        action.set_state(value)
        prop = {"audio": "aid", "subtitle": "sid", "video": "vid"}[action.get_name()]
        if prop == "sid" and value.get_string() != "no":
            self.video_widget.set("sub-visibility", True)
        self.video_widget.set(prop, value.get_string())

    def update_volume_icon(self):
        volume = self.volume_scale_adj.get_value()
        if self.mute_toggle_btn.get_active() or volume == 0:
            icon = "cine-volume-mute-symbolic"
        elif volume < 33:
            icon = "cine-volume-low-symbolic"
        elif volume < 66:
            icon = "cine-volume-mid-symbolic"
        elif volume <= 100.5:
            icon = "cine-volume-max-symbolic"
        else:
            icon = "cine-volume-overamp-symbolic"
        self.volume_menu_btn.set_icon_name(icon)
        return icon


    def show_ui(self, stay: bool = False):
        if self.window is not None:
            self.window.set_cursor(None)
        self.revealer_ui.set_reveal_child(True)
        if stay:
            self.cancel_hide()
        else:
            self.hide_ui_timeout()

    def cancel_hide(self):
        if self.hide_source:
            GLib.source_remove(self.hide_source)
            self.hide_source = 0

    def hide_ui_timeout(self, seconds: int = HIDE_UI_S):
        self.cancel_hide()
        self.hide_source = GLib.timeout_add_seconds(seconds, self.hide_ui)

    def hide_ui(self):
        self.hide_source = 0
        menus = (self.volume_menu_btn, self.subtitles_menu_btn, self.audio_tracks_menu_btn,
                 self.video_tracks_menu_btn, self.chapters_menu_btn, self.options_menu_btn)
        active_or_hover = (
            self.paused
            or self.failed
            or self.motion_controls.props.contains_pointer
            or self.motion_header.props.contains_pointer
            or any(button.get_active() for button in menus)
        )
        if active_or_hover:
            return GLib.SOURCE_REMOVE
        self.revealer_ui.set_reveal_child(False)
        self.hide_time_tooltip()
        if self.window is not None and self.window.is_fullscreen() and self.window.get_visible_dialog() is None:
            self.window.set_cursor(Gdk.Cursor.new_from_name("none"))
        return GLib.SOURCE_REMOVE

    def on_menu_active_changed(self, button, pspec):
        if not button.get_active():
            self.hide_ui_timeout()

    def is_hovering_ui(self):
        hovering = self.motion_controls.props.contains_pointer or self.motion_header.props.contains_pointer
        return hovering and not self.motion_separator.props.contains_pointer

    def on_motion(self, controller, x, y):
        position = (round(x), round(y))
        if self.last_motion != position and not self.click_holding:
            self.last_motion = position
            self.show_ui(stay=self.paused)


    def toggle_pause(self):
        self.video_widget.command("cycle", "pause")

    def toggle_fullscreen(self):
        self.video_widget.command("cycle", "fullscreen")

    def sync_fullscreen(self, fullscreen: bool):
        icon = "cine-view-restore-symbolic" if fullscreen else "cine-view-fullscreen-symbolic"
        self.fullscreen_btn.set_icon_name(icon)
        self.fullscreen_btn.set_tooltip_text(_("Exit Fullscreen") if fullscreen else _("Fullscreen"))
        if self.window is None:
            return
        if fullscreen and not self.window.is_fullscreen():
            self.window.fullscreen()
        elif not fullscreen and self.window.is_fullscreen():
            self.window.unfullscreen()
        self.hide_ui_timeout()

    def on_window_fullscreen_changed(self, window, pspec):
        if self.video_widget.get("fullscreen", False) != window.is_fullscreen():
            self.video_widget.set("fullscreen", window.is_fullscreen())

    def on_window_active_changed(self, window, pspec):
        if not window.is_active():
            self.cancel_click_hold()
            self.set_space_holding(False)

    def seek_relative(self, seconds: float):
        self.video_widget.command("seek", str(seconds), "relative")
        self.show_ui()

    def show_speed_text(self, text: str, duration: str = "1000"):
        self.video_widget.command("show-text", text, duration)

    def start_fast_playback(self):
        self.video_widget.set("pause", False)
        self.normal_speed = self.video_widget.get("speed", 1.0)
        fast = self.normal_speed * 2
        self.video_widget.set("speed", fast)
        self.show_speed_text(f"{fast:g}× ⯈⯈", "100000000")

    def stop_fast_playback(self):
        self.video_widget.set("speed", self.normal_speed)
        self.show_speed_text(f"{self.normal_speed:g}×")


    def on_key_event(self, controller, keyval, keycode, state, kind):
        if self.window is not None and self.window.get_visible_dialog() is not None:
            return Gdk.EVENT_PROPAGATE
        focus = self.window.get_focus() if self.window is not None else None
        if isinstance(focus, Gtk.Text):
            return Gdk.EVENT_PROPAGATE

        name = Gdk.keyval_name(keyval)
        if self.space_holding and kind == "keyup":
            self.set_space_holding(False)

        if name in ("Tab", "ISO_Left_Tab", "Return", "KP_Enter"):
            self.show_ui()
            self.hide_ui_timeout(3)
            self.set_space_holding(False)
            return Gdk.EVENT_PROPAGATE

        accel = Gtk.accelerator_name(keyval, state & Gtk.accelerator_get_default_mod_mask())
        if self.app.get_actions_for_accel(accel):
            self.set_space_holding(False)
            return Gdk.EVENT_PROPAGATE

        combo = key_combo(keyval, state)
        if not combo:
            return Gdk.EVENT_PROPAGATE

        if kind == "keypress":
            if combo in self.nonrepeat_keys and combo in self.pressed_keys:
                return Gdk.EVENT_STOP
            self.pressed_keys.add(combo)
        else:
            self.pressed_keys.discard(combo)

        if combo == "SPACE":
            self.on_space(kind)
            return Gdk.EVENT_STOP

        self.video_widget.command(kind, combo)
        return Gdk.EVENT_STOP

    def on_space(self, kind: str):
        if kind == "keypress":
            if self.space_pressed:
                return
            self.space_pressed = True
            self.space_source = GLib.timeout_add(SPACE_HOLD_MS, self.on_space_held)
            return
        if self.space_source:
            GLib.source_remove(self.space_source)
            self.space_source = 0
        if not self.space_holding:
            self.video_widget.command("keypress", "SPACE")
        self.space_pressed = False
        self.space_holding = False

    def on_space_held(self):
        self.space_source = 0
        self.set_space_holding(True)
        return GLib.SOURCE_REMOVE

    def set_space_holding(self, hold: bool):
        if hold:
            if self.click_holding:
                return
            self.set_can_target(False)
            self.space_holding = True
            self.start_fast_playback()
            return
        self.set_can_target(True)
        if self.space_source:
            GLib.source_remove(self.space_source)
            self.space_source = 0
        if self.space_pressed:
            self.space_pressed = False
            self.stop_fast_playback()


    def on_click_pressed(self, gesture, n_press, x, y, button):
        self.skip_pause_changes = 0
        if button in ("MBTN_BACK", "MBTN_FORWARD"):
            self.video_widget.command("keypress", button)
            return
        self.show_ui()

    def on_click_released(self, gesture, n_press, x, y, button):
        if button in ("MBTN_BACK", "MBTN_FORWARD") or self.is_hovering_ui():
            return
        if self.click_holding:
            return
        if n_press == 2 and button == "MBTN_LEFT":
            self.video_widget.command("keypress", "MBTN_LEFT_DBL")
        elif n_press == 1 and button == "MBTN_RIGHT":
            self.toggle_pause()
        elif n_press == 1 and button == "MBTN_MID":
            self.video_widget.command("keypress", button)

    def on_click_hold(self, gesture, x, y):
        if self.space_holding or self.is_hovering_ui():
            return
        self.click_holding = True
        self.start_fast_playback()

    def cancel_click_hold(self, *args):
        if not self.click_holding:
            return
        self.click_holding = False
        self.stop_fast_playback()

    def on_video_scroll(self, controller, dx, dy):
        self.skip_pause_changes = 0
        event = controller.get_current_event()
        if event.get_modifier_state() & Gdk.ModifierType.SHIFT_MASK:
            return True
        if event.get_unit() == Gdk.ScrollUnit.SURFACE:
            dy *= 0.1
        self.wheel_y += dy
        if abs(self.wheel_y) < 1:
            return True
        going_up = self.wheel_y < 0
        if event.get_relative_direction() == Gdk.ScrollRelativeDirection.INVERTED:
            going_up = not going_up
        self.wheel_y = 0.0
        names = []
        if event.get_modifier_state() & Gdk.ModifierType.CONTROL_MASK:
            names.append("Ctrl")
        if event.get_modifier_state() & Gdk.ModifierType.ALT_MASK:
            names.append("Alt")
        self.video_widget.command("keypress", "+".join(names + ["WHEEL_UP" if going_up else "WHEEL_DOWN"]))
        return True

    def scroll_step(self, controller, dy: float, multiplier: int) -> float:
        event = controller.get_current_event()
        step = dy if event.get_direction() == Gdk.ScrollDirection.SMOOTH else dy * multiplier
        if event.get_relative_direction() == Gdk.ScrollRelativeDirection.INVERTED:
            step = -step
        return step

    def on_volume_scroll(self, controller, dx, dy):
        volume = int(self.volume_scale_adj.get_value() - self.scroll_step(controller, dy, 5))
        self.volume_scale_adj.set_value(max(0, min(volume, MAX_VOLUME)))
        return True


    def on_progress_changed(self, adjustment):
        if self.syncing_progress:
            return
        self.video_widget.command("seek", str(adjustment.get_value()), "absolute")
        self.show_ui(stay=self.paused)

    def on_progress_pressed(self, *args):
        self.playing_on_press = not self.paused
        if self.playing_on_press:
            self.skip_pause_changes += 1
            self.video_widget.command("set", "pause", "yes")

    def on_progress_released(self, *args):
        if self.playing_on_press:
            self.skip_pause_changes += 1
            self.playing_on_press = False
            self.video_widget.command("set", "pause", "no")

    @Gtk.Template.Callback()
    def on_play_clicked(self, button):
        self.toggle_pause()

    @Gtk.Template.Callback()
    def on_previous_clicked(self, button):
        self.play_episode(-1)

    @Gtk.Template.Callback()
    def on_next_clicked(self, button):
        self.play_episode(1)

    @Gtk.Template.Callback()
    def on_fullscreen_clicked(self, button):
        self.toggle_fullscreen()

    @Gtk.Template.Callback()
    def on_toggle_elapsed_remaining(self, button):
        self.show_remaining = not self.show_remaining
        self.settings.set_boolean("show-remaining", self.show_remaining)
        self.update_progress(self.position)

    @Gtk.Template.Callback()
    def on_volume_changed(self, scale):
        if not self.syncing_volume:
            self.video_widget.command("set", "volume", str(scale.get_value()))
        self.update_volume_icon()

    @Gtk.Template.Callback()
    def on_mute_toggled(self, button):
        if bool(self.video_widget.get("mute", False)) != button.get_active():
            self.video_widget.set("mute", button.get_active())
        self.update_volume_icon()

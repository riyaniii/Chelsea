from gettext import gettext as _

from gi.repository import Gdk

MOUSE_BUTTONS = {
    1: "MBTN_LEFT",
    2: "MBTN_MID",
    3: "MBTN_RIGHT",
    8: "MBTN_BACK",
    9: "MBTN_FORWARD",
}

KEY_NAMES = {
    "Escape": "ESC",
    "Return": "ENTER",
    "BackSpace": "BS",
    "Tab": "TAB",
    "ISO_Left_Tab": "TAB",
    "Page_Up": "PGUP",
    "Page_Down": "PGDWN",
    "Left": "LEFT",
    "Right": "RIGHT",
    "Up": "UP",
    "Down": "DOWN",
    "Home": "HOME",
    "End": "END",
    "Insert": "INS",
    "Delete": "DEL",
    "Pause": "PAUSE",
    "Print": "PRINT",
    "Sys_Req": "PRINT",
    "Menu": "MENU",
    "space": "SPACE",
    "KP_Add": "KP_ADD",
    "KP_Subtract": "KP_SUBTRACT",
    "KP_Divide": "KP_DIVIDE",
    "KP_Multiply": "KP_MULTIPLY",
    "KP_1": "KP1",
    "KP_2": "KP2",
    "KP_3": "KP3",
    "KP_4": "KP4",
    "KP_5": "KP5",
    "KP_6": "KP6",
    "KP_7": "KP7",
    "KP_8": "KP8",
    "KP_9": "KP9",
    "KP_0": "KP0",
    "KP_Decimal": "KP_DEC",
    "KP_Delete": "KP_DEL",
    "KP_Separator": "KP_SEPARATOR",
    "KP_Insert": "KP_INS",
    "KP_Enter": "KP_ENTER",
    "KP_End": "KP_END",
    "KP_Down": "KP_DOWN",
    "KP_Page_Down": "KP_PGDWN",
    "KP_Next": "KP_PGDWN",
    "KP_Left": "KP_LEFT",
    "KP_Begin": "KP_BEGIN",
    "KP_Right": "KP_RIGHT",
    "KP_Home": "KP_HOME",
    "KP_Up": "KP_UP",
    "KP_Page_Up": "KP_PGUP",
    "KP_Prior": "KP_PGUP",
    "AudioRaiseVolume": "VOLUME_UP",
    "AudioLowerVolume": "VOLUME_DOWN",
    "AudioMute": "MUTE",
    "AudioPlay": "PLAY",
    "AudioPause": "PAUSE",
    "AudioStop": "STOP",
    "AudioNext": "NEXT",
    "AudioPrev": "PREV",
    "AudioRewind": "PREV",
    "AudioForward": "NEXT",
    "AudioMedia": "MEDIA",
    "AudioMicMute": "MUTE",
    "ZoomIn": "ZOOMIN",
    "ZoomOut": "ZOOMOUT",
}

for number in range(1, 25):
    KEY_NAMES[f"F{number}"] = f"F{number}"


def build_bindings() -> str:
    volume = _("Volume")
    subtitles = _("Subtitles")
    audio = _("Audio")
    sub_delay = _("Subtitle Delay")
    audio_delay = _("Audio Delay")
    speed = _("Speed")
    return f"""\
UP               no-osd add volume 5; show-text "{volume}: ${{volume}}%"
DOWN             no-osd add volume -5; show-text "{volume}: ${{volume}}%"
WHEEL_UP         no-osd add volume 5; show-text "{volume}: ${{volume}}%"
WHEEL_DOWN       no-osd add volume -5; show-text "{volume}: ${{volume}}%"
VOLUME_UP        no-osd add volume 5; show-text "{volume}: ${{volume}}%"
VOLUME_DOWN      no-osd add volume -5; show-text "{volume}: ${{volume}}%"
k                nonrepeatable cycle pause
SPACE            nonrepeatable cycle pause
PLAY             nonrepeatable cycle pause
PAUSE            nonrepeatable cycle pause
c                nonrepeatable no-osd cycle sub-visibility; no-osd set user-data/show-icon "yes"
z                nonrepeatable cycle sub; show-text "{subtitles}: ${{sub}}"
Z                nonrepeatable cycle sub down; show-text "{subtitles}: ${{sub}}"
a                nonrepeatable cycle audio; show-text "{audio}: ${{audio}}"
A                nonrepeatable cycle audio down; show-text "{audio}: ${{audio}}"
j                seek -10; show-text "⯇⯇"
l                seek 10; show-text "⯈⯈"
LEFT             seek -5; show-text "⯇⯇"
RIGHT            seek 5; show-text "⯈⯈"
F11              nonrepeatable cycle fullscreen
f                nonrepeatable cycle fullscreen
ESC              nonrepeatable script-message escape
MBTN_LEFT_DBL    nonrepeatable cycle fullscreen
MBTN_MID         nonrepeatable cycle fullscreen
MBTN_BACK        nonrepeatable script-message previous-episode
MBTN_FORWARD     nonrepeatable script-message next-episode
PREV             nonrepeatable script-message previous-episode
NEXT             nonrepeatable script-message next-episode
p                nonrepeatable script-message previous-episode
n                nonrepeatable script-message next-episode
,                add sub-delay -0.1; show-text "{sub_delay}: ${{sub-delay}}"
.                add sub-delay +0.1; show-text "{sub_delay}: ${{sub-delay}}"
m                nonrepeatable no-osd cycle mute; no-osd set user-data/show-icon "yes"
MUTE             nonrepeatable no-osd cycle mute; no-osd set user-data/show-icon "yes"
ctrl+-           add audio-delay -0.1; show-text "{audio_delay}: ${{audio-delay}}"
ctrl+=           add audio-delay 0.1; show-text "{audio_delay}: ${{audio-delay}}"
ctrl++           add audio-delay 0.1; show-text "{audio_delay}: ${{audio-delay}}"
Ctrl+LEFT        nonrepeatable add chapter -1
Ctrl+RIGHT       nonrepeatable add chapter 1
[                nonrepeatable multiply speed 1/1.1; show-text "{speed}: ${{speed}}×"
]                nonrepeatable multiply speed 1.1; show-text "{speed}: ${{speed}}×"
BS               set speed 1.0; show-text "{speed}: ${{speed}}×"
"""


def modifier_names(state) -> list:
    names = []
    if state & Gdk.ModifierType.CONTROL_MASK:
        names.append("Ctrl")
    if state & Gdk.ModifierType.ALT_MASK:
        names.append("Alt")
    if state & Gdk.ModifierType.SHIFT_MASK:
        names.append("Shift")
    if state & Gdk.ModifierType.META_MASK:
        names.append("Meta")
    return names


def key_combo(keyval, state) -> str:
    gdk_name = Gdk.keyval_name(keyval) or ""
    key = KEY_NAMES.get(gdk_name)
    if key is None:
        character = Gdk.keyval_to_unicode(keyval)
        if not character:
            return ""
        key = chr(character)
    return "+".join(modifier_names(state) + [key])


def nonrepeatable_keys(bindings: list) -> set:
    keys = set()
    for binding in bindings or []:
        key = binding.get("key")
        if key and "nonrepeatable" in binding.get("cmd", ""):
            if len(key) == 1 and key.isalpha() and key.isupper():
                key = f"Shift+{key}"
            keys.add(key)
    return keys


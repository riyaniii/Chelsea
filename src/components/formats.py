from gettext import gettext as _


def duration_text(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        seconds = 0
    seconds = int(seconds)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def rate_text(rate: int) -> str:
    value = float(rate)
    for unit in ("B/s", "KB/s", "MB/s", "GB/s"):
        if value < 1024 or unit == "GB/s":
            return f"{value:.0f} {unit}" if unit == "B/s" else f"{value:.1f} {unit}"
        value /= 1024
    return ""


def episode_code(video) -> str:
    if video is None:
        return ""
    if video.season or video.episode:
        return _("S{season}E{episode}").format(season=video.season, episode=video.episode)
    return video.title


def release_date(value: str) -> str:
    return value[:10] if value else ""


def type_title(meta_type: str) -> str:
    titles = {
        "movie": _("Movies"),
        "series": _("Series"),
        "channel": _("Channels"),
        "tv": _("TV"),
        "anime": _("Anime"),
        "other": _("Other"),
    }
    return titles.get(meta_type, meta_type.replace("_", " ").title())


def catalog_title(catalog) -> str:
    return f"{catalog.title} · {type_title(catalog.type)}"

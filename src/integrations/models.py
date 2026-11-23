import gi
gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, Gio, GObject


class BasicModel(GObject.Object):
    __gtype_name__ = 'ChelseaBasicModel'

    def update_data(self, **kwargs):
        for name, value in kwargs.items():
            if getattr(self, name) != value:
                setattr(self, name, value)


class Video(BasicModel):
    __gtype_name__ = 'ChelseaVideo'
    id = GObject.Property(type=str, default="")
    meta_id = GObject.Property(type=str, default="")
    title = GObject.Property(type=str, default="")
    season = GObject.Property(type=int, default=0)
    episode = GObject.Property(type=int, default=0)
    released = GObject.Property(type=str, default="")
    overview = GObject.Property(type=str, default="")
    thumbnail = GObject.Property(type=str, default="")
    paintable = GObject.Property(type=Gdk.Paintable, default=None)
    progress = GObject.Property(type=float, default=0.0)
    watched = GObject.Property(type=bool, default=False)


class Meta(BasicModel):
    __gtype_name__ = 'ChelseaMeta'
    id = GObject.Property(type=str, default="")
    type = GObject.Property(type=str, default="")
    name = GObject.Property(type=str, default="")
    poster = GObject.Property(type=str, default="")
    poster_shape = GObject.Property(type=str, default="poster")
    background = GObject.Property(type=str, default="")
    logo = GObject.Property(type=str, default="")
    description = GObject.Property(type=str, default="")
    release_info = GObject.Property(type=str, default="")
    released = GObject.Property(type=str, default="")
    runtime = GObject.Property(type=str, default="")
    imdb_rating = GObject.Property(type=str, default="")
    genres = GObject.Property(type=object, default=None)
    cast = GObject.Property(type=object, default=None)
    directors = GObject.Property(type=object, default=None)
    trailer = GObject.Property(type=str, default="")
    default_video_id = GObject.Property(type=str, default="")
    initialized = GObject.Property(type=bool, default=False)
    in_library = GObject.Property(type=bool, default=False)
    progress = GObject.Property(type=float, default=0.0)
    paintable = GObject.Property(type=Gdk.Paintable, default=None)
    background_paintable = GObject.Property(type=Gdk.Paintable, default=None)
    logo_paintable = GObject.Property(type=Gdk.Paintable, default=None)
    videos = GObject.Property(type=Gio.ListStore, default=None)

    def __init__(self):
        super().__init__(videos=Gio.ListStore(item_type=Video))

    @property
    def is_series(self) -> bool:
        return self.videos.get_n_items() > 0 and self.type != "movie"


class Stream(BasicModel):
    __gtype_name__ = 'ChelseaStream'
    name = GObject.Property(type=str, default="")
    title = GObject.Property(type=str, default="")
    description = GObject.Property(type=str, default="")
    url = GObject.Property(type=str, default="")
    info_hash = GObject.Property(type=str, default="")
    file_index = GObject.Property(type=int, default=-1)
    trackers = GObject.Property(type=object, default=None)
    filename = GObject.Property(type=str, default="")
    external_url = GObject.Property(type=str, default="")
    yt_id = GObject.Property(type=str, default="")
    headers = GObject.Property(type=object, default=None)
    binge_group = GObject.Property(type=str, default="")
    not_web_ready = GObject.Property(type=bool, default=False)
    source_id = GObject.Property(type=str, default="")
    source_name = GObject.Property(type=str, default="")

    @property
    def is_torrent(self) -> bool:
        return bool(self.info_hash)

    @property
    def is_external(self) -> bool:
        return not self.url and not self.info_hash and bool(self.external_url or self.yt_id)


class Subtitle(BasicModel):
    __gtype_name__ = 'ChelseaSubtitle'
    id = GObject.Property(type=str, default="")
    url = GObject.Property(type=str, default="")
    lang = GObject.Property(type=str, default="")
    source_name = GObject.Property(type=str, default="")


class Addon(BasicModel):
    __gtype_name__ = 'ChelseaAddon'
    id = GObject.Property(type=str, default="")
    transport_url = GObject.Property(type=str, default="")
    name = GObject.Property(type=str, default="")
    description = GObject.Property(type=str, default="")
    version = GObject.Property(type=str, default="")
    logo = GObject.Property(type=str, default="")
    types = GObject.Property(type=object, default=None)
    catalogs = GObject.Property(type=object, default=None)
    resources = GObject.Property(type=object, default=None)
    id_prefixes = GObject.Property(type=object, default=None)
    configurable = GObject.Property(type=bool, default=False)
    configuration_required = GObject.Property(type=bool, default=False)
    is_official = GObject.Property(type=bool, default=False)
    is_protected = GObject.Property(type=bool, default=False)
    installed = GObject.Property(type=bool, default=False)
    busy = GObject.Property(type=bool, default=False)
    paintable = GObject.Property(type=Gdk.Paintable, default=None)


class Catalog(BasicModel):
    __gtype_name__ = 'ChelseaCatalog'
    source_id = GObject.Property(type=str, default="")
    source_name = GObject.Property(type=str, default="")
    base_url = GObject.Property(type=str, default="")
    type = GObject.Property(type=str, default="")
    id = GObject.Property(type=str, default="")
    name = GObject.Property(type=str, default="")
    genres = GObject.Property(type=object, default=None)
    genre_required = GObject.Property(type=bool, default=False)
    board = GObject.Property(type=bool, default=False)
    searchable = GObject.Property(type=bool, default=False)
    pageable = GObject.Property(type=bool, default=False)

    @property
    def key(self) -> str:
        return f"{self.base_url}|{self.type}|{self.id}"

    @property
    def title(self) -> str:
        return self.name or self.id


class LibraryItem(BasicModel):
    __gtype_name__ = 'ChelseaLibraryItem'
    id = GObject.Property(type=str, default="")
    type = GObject.Property(type=str, default="")
    name = GObject.Property(type=str, default="")
    poster = GObject.Property(type=str, default="")
    removed = GObject.Property(type=bool, default=False)
    temp = GObject.Property(type=bool, default=False)
    added_at = GObject.Property(type=str, default="")
    modified_at = GObject.Property(type=str, default="")
    last_watched = GObject.Property(type=str, default="")
    time_offset = GObject.Property(type=GObject.TYPE_INT64, default=0)
    duration = GObject.Property(type=GObject.TYPE_INT64, default=0)
    video_id = GObject.Property(type=str, default="")
    times_watched = GObject.Property(type=int, default=0)
    meta = GObject.Property(type=Meta)

    @property
    def in_library(self) -> bool:
        return not self.removed and not self.temp

    @property
    def progress(self) -> float:
        if self.duration <= 0:
            return 0.0
        return max(0.0, min(1.0, self.time_offset / self.duration))

    @property
    def in_progress(self) -> bool:
        return (not self.removed or self.temp) and self.time_offset > 0


class Download(BasicModel):
    __gtype_name__ = 'ChelseaDownload'
    id = GObject.Property(type=str, default="")
    path = GObject.Property(type=str, default="")
    url = GObject.Property(type=str, default="")
    info_hash = GObject.Property(type=str, default="")
    file_index = GObject.Property(type=int, default=-1)
    trackers = GObject.Property(type=object, default=None)
    headers = GObject.Property(type=object, default=None)
    state = GObject.Property(type=str, default="downloading")
    size = GObject.Property(type=GObject.TYPE_INT64, default=0)
    downloaded = GObject.Property(type=GObject.TYPE_INT64, default=0)
    progress = GObject.Property(type=float, default=0.0)


class LibraryOptions(GObject.Object):
    __gtype_name__ = 'ChelseaLibraryOptions'
    type = GObject.Property(type=str, default="")
    sort_key = GObject.Property(type=str, default="recent")

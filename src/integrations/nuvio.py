import asyncio
import ctypes
import ctypes.util
import os
from pathlib import Path

from gi.repository import GLib, GObject

API_VERSION = 3
LIBRARY_NAMES = ("libnuvio_engine.so.0", "libnuvio_engine.so", "libnuvio_engine.dylib", "nuvio_engine.dll")
LIBRARY_ENV = "NUVIO_ENGINE_LIBRARY"

POLL_INTERVAL_MS = 100
METADATA_TIMEOUT = 90
STREAM_TIMEOUT = 60
MEMORY_CACHE_BYTES = 256 * 1024 * 1024
DISK_CACHE_BYTES = 4 * 1024 * 1024 * 1024
STREAM_INACTIVITY_MS = 60 * 1000
WARM_TORRENT_MS = 5 * 60 * 1000

STATUS_OK = 0
STATUS_NO_EVENT = 7

UPLOAD_DISABLED = 0
UPLOAD_UNLIMITED = 1
UPLOAD_LIMITED = 2

PROFILES = {"soft": 0, "balanced": 1, "fast": 2}

SOURCE_MAGNET = 0

EVENT_TORRENT_ADDED = 1
EVENT_TORRENT_METADATA_READY = 2
EVENT_TORRENT_ERROR = 3
EVENT_STREAM_PREPARED = 4
EVENT_TORRENT_REMOVED = 5
EVENT_STREAM_STOPPED = 6
EVENT_DISK_CACHE_RECLAIMED = 7

VIDEO_EXTENSIONS = (".mkv", ".mp4", ".avi", ".webm", ".mov", ".m4v", ".ts", ".wmv", ".flv", ".mpg", ".mpeg")


class EngineError(Exception):
    pass


class Config(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("data_directory", ctypes.c_char_p),
        ("cache_directory", ctypes.c_char_p),
        ("memory_cache_capacity_bytes", ctypes.c_uint64),
        ("disk_cache_capacity_bytes", ctypes.c_uint64),
        ("listen_port", ctypes.c_uint16),
        ("reserved_0", ctypes.c_uint16),
        ("upload_mode", ctypes.c_uint32),
        ("upload_limit_bytes_per_second", ctypes.c_uint64),
        ("stream_inactivity_timeout_milliseconds", ctypes.c_uint32),
        ("reserved_1", ctypes.c_uint32),
        ("warm_torrent_timeout_milliseconds", ctypes.c_uint32),
        ("reserved_2", ctypes.c_uint32),
        ("tls_ca_bundle_path", ctypes.c_char_p),
        ("torrent_profile", ctypes.c_uint32),
        ("reserved_3", ctypes.c_uint32),
    ]


class TorrentRequest(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("magnet_uri", ctypes.c_char_p),
        ("source_type", ctypes.c_uint32),
        ("reserved_0", ctypes.c_uint32),
        ("torrent_data", ctypes.POINTER(ctypes.c_uint8)),
        ("torrent_data_size", ctypes.c_size_t),
    ]


class Event(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("type", ctypes.c_uint32),
        ("sequence", ctypes.c_uint64),
        ("request_id", ctypes.c_uint64),
        ("dropped_events", ctypes.c_uint64),
        ("torrent_id", ctypes.c_char * 65),
        ("message", ctypes.c_char * 256),
        ("file_index", ctypes.c_uint32),
        ("reserved_0", ctypes.c_uint32),
        ("file_size", ctypes.c_uint64),
        ("stream_id", ctypes.c_char * 65),
        ("stream_url", ctypes.c_char * 512),
    ]


class StreamRequest(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("torrent_id", ctypes.c_char_p),
        ("file_index", ctypes.c_uint32),
        ("reserved_0", ctypes.c_uint32),
        ("filename_hint", ctypes.c_char_p),
    ]


class File(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("index", ctypes.c_uint32),
        ("offset", ctypes.c_uint64),
        ("size", ctypes.c_uint64),
        ("path_truncated", ctypes.c_uint8),
        ("reserved_0", ctypes.c_uint8 * 7),
        ("path", ctypes.c_char * 1024),
    ]


class Stats(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("active_torrents", ctypes.c_uint32),
        ("active_streams", ctypes.c_uint32),
        ("active_http_requests", ctypes.c_uint32),
        ("connected_peers", ctypes.c_uint32),
        ("connected_seeds", ctypes.c_uint32),
        ("pending_piece_reads", ctypes.c_uint32),
        ("reserved_0", ctypes.c_uint32),
        ("download_rate_bytes_per_second", ctypes.c_uint64),
        ("upload_rate_bytes_per_second", ctypes.c_uint64),
        ("total_payload_download_bytes", ctypes.c_uint64),
        ("total_payload_upload_bytes", ctypes.c_uint64),
        ("memory_cache_capacity_bytes", ctypes.c_uint64),
        ("memory_cache_used_bytes", ctypes.c_uint64),
        ("memory_cache_hits", ctypes.c_uint64),
        ("memory_cache_misses", ctypes.c_uint64),
        ("memory_cache_evictions", ctypes.c_uint64),
        ("memory_cache_entries", ctypes.c_uint64),
        ("warm_torrents", ctypes.c_uint32),
        ("quiesced_torrents", ctypes.c_uint32),
        ("disk_cache_capacity_bytes", ctypes.c_uint64),
        ("disk_cache_used_bytes", ctypes.c_uint64),
        ("disk_cache_protected_bytes", ctypes.c_uint64),
        ("disk_cache_evictions", ctypes.c_uint64),
        ("disk_cache_reclaimed_bytes", ctypes.c_uint64),
        ("disk_cache_over_budget", ctypes.c_uint8),
        ("reserved_1", ctypes.c_uint8 * 7),
        ("known_peers", ctypes.c_uint32),
        ("connect_candidates", ctypes.c_uint32),
        ("interested_peers", ctypes.c_uint32),
        ("unchoked_peers", ctypes.c_uint32),
        ("downloading_peers", ctypes.c_uint32),
        ("snubbed_peers", ctypes.c_uint32),
        ("pending_block_requests", ctypes.c_uint32),
        ("target_block_requests", ctypes.c_uint32),
        ("timed_out_block_requests", ctypes.c_uint32),
        ("connecting_peers", ctypes.c_uint32),
        ("handshaking_peers", ctypes.c_uint32),
        ("target_piece_peers", ctypes.c_uint32),
        ("target_piece_unchoked_peers", ctypes.c_uint32),
        ("target_piece_downloading_peers", ctypes.c_uint32),
        ("off_target_downloading_peers", ctypes.c_uint32),
        ("tracker_reply_events", ctypes.c_uint32),
        ("tracker_error_events", ctypes.c_uint32),
        ("dht_reply_events", ctypes.c_uint32),
        ("reserved_2", ctypes.c_uint32),
        ("tracker_peers_returned", ctypes.c_uint64),
        ("dht_peers_returned", ctypes.c_uint64),
        ("peer_connect_events", ctypes.c_uint64),
        ("peer_disconnect_events", ctypes.c_uint64),
        ("peer_disconnect_timeouts", ctypes.c_uint64),
        ("peer_disconnect_connect_failures", ctypes.c_uint64),
        ("peer_disconnect_redundant", ctypes.c_uint64),
        ("peer_disconnect_turnover", ctypes.c_uint64),
        ("peer_disconnect_other", ctypes.c_uint64),
        ("torrent_finished_events", ctypes.c_uint64),
    ]


class StreamStats(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("file_index", ctypes.c_uint32),
        ("file_size", ctypes.c_uint64),
        ("contiguous_ready_bytes", ctypes.c_uint64),
        ("verified_file_bytes", ctypes.c_uint64),
        ("delivered_bytes", ctypes.c_uint64),
        ("active_demands", ctypes.c_uint32),
        ("scheduled_pieces", ctypes.c_uint32),
        ("blocking_pieces", ctypes.c_uint32),
        ("primary_blocking_piece", ctypes.c_uint32),
        ("secondary_blocking_piece", ctypes.c_uint32),
        ("last_ready_piece", ctypes.c_uint32),
        ("primary_demand_start", ctypes.c_uint64),
        ("primary_demand_end", ctypes.c_uint64),
        ("secondary_demand_start", ctypes.c_uint64),
        ("secondary_demand_end", ctypes.c_uint64),
        ("schedule_revision", ctypes.c_uint64),
    ]


SIGNATURES = {
    "nuvio_engine_api_version": ([], ctypes.c_uint32),
    "nuvio_engine_version_string": ([], ctypes.c_char_p),
    "nuvio_engine_protocol_backend_version": ([], ctypes.c_char_p),
    "nuvio_engine_status_message": ([ctypes.c_uint32], ctypes.c_char_p),
    "nuvio_engine_config_init_sized": ([ctypes.POINTER(Config), ctypes.c_uint32], None),
    "nuvio_engine_torrent_request_init_sized": ([ctypes.POINTER(TorrentRequest), ctypes.c_uint32], None),
    "nuvio_engine_event_init_sized": ([ctypes.POINTER(Event), ctypes.c_uint32], None),
    "nuvio_engine_file_init_sized": ([ctypes.POINTER(File), ctypes.c_uint32], None),
    "nuvio_engine_stream_request_init_sized": ([ctypes.POINTER(StreamRequest), ctypes.c_uint32], None),
    "nuvio_engine_stats_init_sized": ([ctypes.POINTER(Stats), ctypes.c_uint32], None),
    "nuvio_engine_stream_stats_init_sized": ([ctypes.POINTER(StreamStats), ctypes.c_uint32], None),
    "nuvio_engine_create": ([ctypes.POINTER(Config), ctypes.POINTER(ctypes.c_void_p)], ctypes.c_uint32),
    "nuvio_engine_destroy": ([ctypes.c_void_p], None),
    "nuvio_engine_add_torrent": (
        [ctypes.c_void_p, ctypes.POINTER(TorrentRequest), ctypes.POINTER(ctypes.c_uint64)], ctypes.c_uint32),
    "nuvio_engine_poll_event": ([ctypes.c_void_p, ctypes.POINTER(Event)], ctypes.c_uint32),
    "nuvio_engine_get_file_count": (
        [ctypes.c_void_p, ctypes.c_char_p, ctypes.POINTER(ctypes.c_size_t)], ctypes.c_uint32),
    "nuvio_engine_get_file": (
        [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t, ctypes.POINTER(File)], ctypes.c_uint32),
    "nuvio_engine_prepare_stream": (
        [ctypes.c_void_p, ctypes.POINTER(StreamRequest), ctypes.POINTER(ctypes.c_uint64)], ctypes.c_uint32),
    "nuvio_engine_remove_torrent": (
        [ctypes.c_void_p, ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint64)], ctypes.c_uint32),
    "nuvio_engine_stop_stream": (
        [ctypes.c_void_p, ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint64)], ctypes.c_uint32),
    "nuvio_engine_get_stats": ([ctypes.c_void_p, ctypes.POINTER(Stats)], ctypes.c_uint32),
    "nuvio_engine_get_stream_stats": (
        [ctypes.c_void_p, ctypes.c_char_p, ctypes.POINTER(StreamStats)], ctypes.c_uint32),
    "nuvio_engine_reclaim_disk_cache": (
        [ctypes.c_void_p, ctypes.c_uint64, ctypes.POINTER(ctypes.c_uint64)], ctypes.c_uint32),
}


def loadLibrary() -> ctypes.CDLL:
    candidates = []
    if os.environ.get(LIBRARY_ENV):
        candidates.append(os.environ[LIBRARY_ENV])
    candidates.extend(LIBRARY_NAMES)
    found = ctypes.util.find_library("nuvio_engine")
    if found:
        candidates.append(found)

    errors = []
    for name in candidates:
        try:
            lib = ctypes.CDLL(name)
            break
        except OSError as error:
            errors.append(str(error))
    else:
        raise EngineError("Could not load the Nuvio engine: " + "; ".join(errors))

    for name, (argtypes, restype) in SIGNATURES.items():
        function = getattr(lib, name)
        function.argtypes = argtypes
        function.restype = restype

    if lib.nuvio_engine_api_version() != API_VERSION:
        raise EngineError(f"Nuvio engine API version {lib.nuvio_engine_api_version()} is not supported")
    return lib


def text(value: bytes) -> str:
    return value.decode("utf-8", "replace")


def isVideo(path: str) -> bool:
    return path.lower().endswith(VIDEO_EXTENSIONS)


def magnetUri(info_hash: str, trackers: list | None = None, name: str = "") -> str:
    uri = f"magnet:?xt=urn:btih:{info_hash}"
    if name:
        uri += "&dn=" + GLib.Uri.escape_string(name, None, False)
    for tracker in trackers or []:
        if tracker.startswith("tracker:"):
            tracker = tracker[len("tracker:"):]
        elif tracker.startswith("dht:"):
            continue
        uri += "&tr=" + GLib.Uri.escape_string(tracker, None, False)
    return uri


class TorrentFile(GObject.Object):
    __gtype_name__ = "ChelseaTorrentFile"
    index = GObject.Property(type=int, default=0)
    path = GObject.Property(type=str, default="")
    size = GObject.Property(type=GObject.TYPE_UINT64, default=0)


class Nuvio(GObject.Object):
    __gtype_name__ = "ChelseaIntegrationNuvio"

    available = GObject.Property(type=bool, default=False)
    download_rate = GObject.Property(type=GObject.TYPE_UINT64, default=0)
    upload_rate = GObject.Property(type=GObject.TYPE_UINT64, default=0)
    peers = GObject.Property(type=int, default=0)

    def __init__(self):
        super().__init__()
        self.lib = None
        self.engine = ctypes.c_void_p()
        self.poll_source = 0
        self.requests = {}
        self.metadata = {}
        self.torrents = {}
        self.streams = {}
        self.error = ""

    def start(self, data_dir: str | None = None, profile: str = "balanced",
              disk_cache_bytes: int = DISK_CACHE_BYTES, upload: bool = True) -> bool:
        if self.available:
            return True
        base = Path(data_dir or GLib.get_user_cache_dir()) / "chelsea" / "torrents"
        data = base / "data"
        cache = base / "cache"
        data.mkdir(parents=True, exist_ok=True)
        cache.mkdir(parents=True, exist_ok=True)
        try:
            self.lib = loadLibrary()
            config = Config()
            self.lib.nuvio_engine_config_init_sized(ctypes.byref(config), ctypes.sizeof(Config))
            self.config_paths = (str(data).encode(), str(cache).encode())
            config.data_directory = self.config_paths[0]
            config.cache_directory = self.config_paths[1]
            config.memory_cache_capacity_bytes = MEMORY_CACHE_BYTES
            config.disk_cache_capacity_bytes = disk_cache_bytes
            config.upload_mode = UPLOAD_UNLIMITED if upload else UPLOAD_DISABLED
            config.stream_inactivity_timeout_milliseconds = STREAM_INACTIVITY_MS
            config.warm_torrent_timeout_milliseconds = WARM_TORRENT_MS
            config.torrent_profile = PROFILES.get(profile, PROFILES["balanced"])
            self.check(self.lib.nuvio_engine_create(ctypes.byref(config), ctypes.byref(self.engine)))
        except EngineError as error:
            self.error = str(error)
            print(error)
            return False
        self.poll_source = GLib.timeout_add(POLL_INTERVAL_MS, self.poll)
        self.available = True
        return True

    def stop(self):
        if self.poll_source:
            GLib.source_remove(self.poll_source)
            self.poll_source = 0
        if self.engine:
            self.lib.nuvio_engine_destroy(self.engine)
            self.engine = ctypes.c_void_p()
        for future in list(self.requests.values()) + list(self.metadata.values()):
            if not future.done():
                future.cancel()
        self.requests.clear()
        self.metadata.clear()
        self.torrents.clear()
        self.streams.clear()
        self.available = False

    def version(self) -> str:
        if self.lib is None:
            return ""
        return text(self.lib.nuvio_engine_version_string())

    def check(self, status: int):
        if status != STATUS_OK:
            message = text(self.lib.nuvio_engine_status_message(status)) if self.lib else str(status)
            raise EngineError(message)

    def requireEngine(self):
        if not self.available:
            raise EngineError(self.error or "The torrent engine is not running")

    def waitRequest(self, request_id: int) -> asyncio.Future:
        future = asyncio.get_running_loop().create_future()
        self.requests[request_id] = future
        return future

    def waitMetadata(self, torrent_id: str) -> asyncio.Future:
        future = self.metadata.get(torrent_id)
        if future is None:
            future = asyncio.get_event_loop().create_future()
            self.metadata[torrent_id] = future
        return future

    def poll(self) -> bool:
        if not self.engine:
            return GLib.SOURCE_REMOVE
        while True:
            event = Event()
            self.lib.nuvio_engine_event_init_sized(ctypes.byref(event), ctypes.sizeof(Event))
            status = self.lib.nuvio_engine_poll_event(self.engine, ctypes.byref(event))
            if status == STATUS_NO_EVENT:
                break
            if status != STATUS_OK:
                print("nuvio poll failed:", text(self.lib.nuvio_engine_status_message(status)))
                break
            self.dispatch(event)
        self.refreshStats()
        return GLib.SOURCE_CONTINUE

    def dispatch(self, event: Event):
        torrent_id = text(event.torrent_id)
        message = text(event.message)
        request = self.requests.pop(event.request_id, None)

        if event.type == EVENT_TORRENT_METADATA_READY:
            self.resolve(self.waitMetadata(torrent_id), torrent_id)
        elif event.type == EVENT_TORRENT_ERROR:
            error = EngineError(message or "Torrent failed")
            self.reject(request, error)
            self.reject(self.metadata.pop(torrent_id, None), error)
            return
        elif event.type == EVENT_STREAM_PREPARED:
            stream = {
                "torrent_id": torrent_id,
                "stream_id": text(event.stream_id),
                "url": text(event.stream_url),
                "file_index": event.file_index,
                "file_size": event.file_size,
            }
            self.streams[stream["stream_id"]] = stream
            self.resolve(request, stream)
            return
        elif event.type == EVENT_TORRENT_REMOVED:
            self.torrents = {key: value for key, value in self.torrents.items() if value != torrent_id}
            self.metadata.pop(torrent_id, None)
        elif event.type == EVENT_STREAM_STOPPED:
            self.streams.pop(text(event.stream_id), None)

        self.resolve(request, torrent_id)

    @staticmethod
    def resolve(future, value):
        if future is not None and not future.done():
            future.set_result(value)

    @staticmethod
    def reject(future, error):
        if future is not None and not future.done():
            future.set_exception(error)

    def refreshStats(self):
        stats = self.getStats()
        if stats is None:
            return
        if self.download_rate != stats.download_rate_bytes_per_second:
            self.download_rate = stats.download_rate_bytes_per_second
        if self.upload_rate != stats.upload_rate_bytes_per_second:
            self.upload_rate = stats.upload_rate_bytes_per_second
        if self.peers != stats.connected_peers:
            self.peers = stats.connected_peers

    def getStats(self) -> Stats | None:
        if not self.engine:
            return None
        stats = Stats()
        self.lib.nuvio_engine_stats_init_sized(ctypes.byref(stats), ctypes.sizeof(Stats))
        if self.lib.nuvio_engine_get_stats(self.engine, ctypes.byref(stats)) != STATUS_OK:
            return None
        return stats

    def getStreamStats(self, stream_id: str) -> StreamStats | None:
        if not self.engine:
            return None
        stats = StreamStats()
        self.lib.nuvio_engine_stream_stats_init_sized(ctypes.byref(stats), ctypes.sizeof(StreamStats))
        status = self.lib.nuvio_engine_get_stream_stats(self.engine, stream_id.encode(), ctypes.byref(stats))
        if status != STATUS_OK:
            return None
        return stats

    async def addTorrent(self, magnet: str) -> str:
        self.requireEngine()
        known = self.torrents.get(magnet)
        if known:
            return known
        request = TorrentRequest()
        self.lib.nuvio_engine_torrent_request_init_sized(ctypes.byref(request), ctypes.sizeof(TorrentRequest))
        uri = magnet.encode()
        request.magnet_uri = uri
        request.source_type = SOURCE_MAGNET
        request_id = ctypes.c_uint64()
        self.check(self.lib.nuvio_engine_add_torrent(self.engine, ctypes.byref(request), ctypes.byref(request_id)))
        torrent_id = await self.waitRequest(request_id.value)
        self.torrents[magnet] = torrent_id
        return torrent_id

    async def waitForMetadata(self, torrent_id: str, timeout: float = METADATA_TIMEOUT):
        if self.fileCount(torrent_id) is not None:
            return
        await asyncio.wait_for(asyncio.shield(self.waitMetadata(torrent_id)), timeout)

    def fileCount(self, torrent_id: str) -> int | None:
        count = ctypes.c_size_t()
        status = self.lib.nuvio_engine_get_file_count(self.engine, torrent_id.encode(), ctypes.byref(count))
        if status != STATUS_OK:
            return None
        return count.value

    def getFiles(self, torrent_id: str) -> list[TorrentFile]:
        files = []
        for index in range(self.fileCount(torrent_id) or 0):
            item = File()
            self.lib.nuvio_engine_file_init_sized(ctypes.byref(item), ctypes.sizeof(File))
            status = self.lib.nuvio_engine_get_file(self.engine, torrent_id.encode(), index, ctypes.byref(item))
            if status == STATUS_OK:
                files.append(TorrentFile(index=item.index, path=text(item.path), size=item.size))
        return files

    def pickFile(self, torrent_id: str, file_index: int | None, filename: str = "") -> int:
        files = self.getFiles(torrent_id)
        if not files:
            raise EngineError("The torrent has no files")
        if file_index is not None and 0 <= file_index < len(files):
            return file_index
        if filename:
            for item in files:
                if os.path.basename(item.path) == filename:
                    return item.index
        videos = [item for item in files if isVideo(item.path)] or files
        return max(videos, key=lambda item: item.size).index

    async def prepareStream(self, torrent_id: str, file_index: int, filename: str = "") -> dict:
        self.requireEngine()
        request = StreamRequest()
        self.lib.nuvio_engine_stream_request_init_sized(ctypes.byref(request), ctypes.sizeof(StreamRequest))
        encoded_id = torrent_id.encode()
        hint = filename.encode() if filename else None
        request.torrent_id = encoded_id
        request.file_index = file_index
        request.filename_hint = hint
        request_id = ctypes.c_uint64()
        self.check(self.lib.nuvio_engine_prepare_stream(self.engine, ctypes.byref(request), ctypes.byref(request_id)))
        return await asyncio.wait_for(self.waitRequest(request_id.value), STREAM_TIMEOUT)

    async def stream(self, info_hash: str, file_index: int | None = None, trackers: list | None = None,
                     filename: str = "") -> dict:
        torrent_id = await self.addTorrent(magnetUri(info_hash, trackers))
        await self.waitForMetadata(torrent_id)
        index = self.pickFile(torrent_id, file_index, filename)
        return await self.prepareStream(torrent_id, index, filename)

    def stopStream(self, stream_id: str):
        if not self.engine or not stream_id:
            return
        request_id = ctypes.c_uint64()
        self.lib.nuvio_engine_stop_stream(self.engine, stream_id.encode(), ctypes.byref(request_id))

    def removeTorrent(self, torrent_id: str):
        if not self.engine or not torrent_id:
            return
        request_id = ctypes.c_uint64()
        self.lib.nuvio_engine_remove_torrent(self.engine, torrent_id.encode(), ctypes.byref(request_id))

    def reclaimDiskCache(self, target_bytes: int = 0):
        if not self.engine:
            return
        request_id = ctypes.c_uint64()
        self.lib.nuvio_engine_reclaim_disk_cache(self.engine, target_bytes, ctypes.byref(request_id))

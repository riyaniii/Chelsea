import asyncio
import json
import os
import re
import uuid
from pathlib import Path

import httpx
from gi.repository import Gio, GLib, GObject

from .integrations import models
from .integrations.endpoints import HEADERS

CHUNK_SIZE = 256 * 1024
PROGRESS_STEP = 4 * 1024 * 1024
SAVED_FIELDS = ("id", "path", "url", "info_hash", "file_index", "trackers", "headers",
                "state", "size", "downloaded")


def default_folder() -> Path:
    base = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD)
    return Path(base or Path.home() / "Downloads") / "Chelsea"


def safe_name(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', " ", name).strip()
    return name[:180] or "video"


def unique_path(path: Path) -> Path:
    candidate = path
    number = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.stem} ({number}){path.suffix}")
        number += 1
    return candidate


def file_name(meta, video, stream) -> str:
    name = stream.filename
    if not name:
        name = f"{meta.name} {video.title}" if video is not None else meta.name
    name = safe_name(name)
    if "." not in name[-6:]:
        name += ".mp4"
    return name


class Downloads(GObject.Object):
    __gtype_name__ = "ChelseaDownloads"

    active = GObject.Property(type=int, default=0)

    def __init__(self, settings, engine, start_engine):
        super().__init__()
        self.settings = settings
        self.engine = engine
        self.start_engine = start_engine
        self.store = Gio.ListStore(item_type=models.Download)
        self.tasks = {}
        self.http = httpx.AsyncClient(headers=HEADERS, timeout=httpx.Timeout(30, read=None),
                                      follow_redirects=True)
        self.load_history()

    def history_path(self) -> Path:
        return Path(GLib.get_user_data_dir()) / "chelsea" / "downloads.json"

    def load_history(self):
        try:
            entries = json.loads(self.history_path().read_text())
        except (FileNotFoundError, ValueError):
            return
        for entry in entries:
            item = models.Download()
            item.update_data(**{key: value for key, value in entry.items() if key in SAVED_FIELDS})
            if item.state == "downloading":
                item.state = "paused"
            if item.state == "done":
                continue
            if item.size:
                item.progress = item.downloaded / item.size
            self.store.append(item)

    def save_history(self):
        entries = [{key: item.get_property(key) for key in SAVED_FIELDS} for item in self.store]
        path = self.history_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(entries))

    def update_active(self):
        self.active = sum(1 for item in self.store if item.state == "downloading")

    def folder(self) -> Path:
        chosen = self.settings.get_string("download-folder")
        return Path(chosen) if chosen else default_folder()

    def suggested_path(self, meta, video, stream) -> Path:
        return self.folder() / safe_name(meta.name) / file_name(meta, video, stream)

    def add(self, meta, video, stream, path: Path | None = None) -> models.Download:
        path = unique_path(path or self.suggested_path(meta, video, stream))
        path.parent.mkdir(parents=True, exist_ok=True)
        item = models.Download()
        item.update_data(
            id=uuid.uuid4().hex, path=str(path), url=stream.url, info_hash=stream.info_hash,
            file_index=stream.file_index, trackers=stream.trackers or [], headers=stream.headers or {},
        )
        self.store.insert(0, item)
        self.start(item)
        return item

    def start(self, item: models.Download):
        item.state = "downloading"
        self.tasks[item.id] = asyncio.create_task(self.run(item))
        self.update_active()
        self.save_history()

    def pause(self, item: models.Download):
        task = self.tasks.pop(item.id, None)
        if task:
            task.cancel()
        item.state = "paused"
        self.update_active()
        self.save_history()

    def remove(self, item: models.Download, delete_file: bool):
        self.pause(item)
        if delete_file:
            try:
                os.remove(item.path)
            except FileNotFoundError:
                pass
        found, position = self.store.find(item)
        if found:
            self.store.remove(position)
        self.update_active()
        self.save_history()

    def close(self):
        for task in self.tasks.values():
            task.cancel()
        self.save_history()

    async def source_url(self, item: models.Download) -> str:
        if not item.info_hash:
            return item.url
        if not self.start_engine():
            raise RuntimeError(self.engine.error)
        file_index = item.file_index if item.file_index >= 0 else None
        info = await self.engine.stream(item.info_hash, file_index, item.trackers)
        self.match_extension(item, info)
        return info["url"]

    def match_extension(self, item: models.Download, info: dict):
        path = Path(item.path)
        if path.exists():
            return
        for torrent_file in self.engine.getFiles(info["torrent_id"]):
            if torrent_file.index == info["file_index"]:
                suffix = Path(torrent_file.path).suffix
                if suffix and suffix != path.suffix:
                    item.path = str(unique_path(path.with_suffix(suffix)))
                return

    async def run(self, item: models.Download):
        try:
            url = await self.source_url(item)
            await self.fetch(item, url)
            item.update_data(state="done", progress=1.0)
            found, position = self.store.find(item)
            if found:
                self.store.remove(position)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            print(f"download {item.path}: {error}")
            item.state = "failed"
        finally:
            self.tasks.pop(item.id, None)
            self.update_active()
            self.save_history()

    async def fetch(self, item: models.Download, url: str):
        path = Path(item.path)
        offset = path.stat().st_size if path.exists() else 0
        headers = dict(item.headers or {})
        if offset:
            headers["Range"] = f"bytes={offset}-"
        async with self.http.stream("GET", url, headers=headers) as response:
            if response.status_code == 416:
                return
            response.raise_for_status()
            if offset and response.status_code != 206:
                offset = 0
            length = int(response.headers.get("Content-Length") or 0)
            if length:
                item.size = offset + length
            done = offset
            shown = done
            with open(path, "ab" if offset else "wb") as output:
                async for chunk in response.aiter_bytes(CHUNK_SIZE):
                    await asyncio.to_thread(output.write, chunk)
                    done += len(chunk)
                    if done - shown >= PROGRESS_STEP:
                        shown = done
                        item.update_data(downloaded=done, progress=done / item.size if item.size else 0.0)
            item.downloaded = done

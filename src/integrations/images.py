import asyncio
import os
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
from diskcache import Cache
from gi.repository import Gdk, GLib, GObject

from .endpoints import HEADERS

FETCH_CONNECTIONS = 8
IMAGE_TIMEOUT = 15
IMAGE_RETRIES = 1
IMAGE_TTL = 30 * 24 * 60 * 60
CACHE_SIZE_LIMIT = 500 * 1024 * 1024
THUMB_CACHE_ITEMS = 200


class Images:

    def __init__(self, cache_name: str = "chelsea"):
        transport = httpx.AsyncHTTPTransport(
            retries=IMAGE_RETRIES,
            limits=httpx.Limits(max_connections=FETCH_CONNECTIONS),
        )
        self.http = httpx.AsyncClient(
            headers=HEADERS,
            transport=transport,
            timeout=httpx.Timeout(IMAGE_TIMEOUT, pool=None),
            follow_redirects=True,
        )
        self.priority_http = httpx.AsyncClient(
            headers=HEADERS,
            timeout=httpx.Timeout(IMAGE_TIMEOUT, pool=None),
            limits=httpx.Limits(max_connections=4),
            follow_redirects=True,
        )
        cache_folder = Path(GLib.get_user_cache_dir()) / cache_name / "images"
        self.cache = Cache(
            str(cache_folder),
            size_limit=CACHE_SIZE_LIMIT,
            eviction_policy="least-recently-used",
        )
        worker_count = max(2, min(4, os.cpu_count() or 2))
        self.decoder = ThreadPoolExecutor(max_workers=worker_count)
        self.pending = {}
        self.textures = OrderedDict()
        self.users = {}

    def close(self):
        self.decoder.shutdown(wait=False, cancel_futures=True)
        self.cache.close()

    def shared(self, key, factory):
        task = self.pending.get(key)
        if task is None:
            task = asyncio.ensure_future(factory())
            self.pending[key] = task
            task.add_done_callback(lambda done: self.pending.pop(key, None))
        return asyncio.shield(task)

    async def loadBytes(self, url: str, priority: bool = False) -> bytes:
        data = await asyncio.to_thread(self.cache.get, url)
        if data is None:
            client = self.priority_http if priority else self.http
            response = await client.get(url)
            response.raise_for_status()
            data = response.content
            await asyncio.to_thread(self.cache.set, url, data, expire=IMAGE_TTL)
        return data

    @staticmethod
    def decode(raw: bytes) -> Gdk.Paintable:
        return Gdk.Texture.new_from_bytes(GLib.Bytes.new(raw))

    async def getPaintable(self, url: str, priority: bool = False) -> Gdk.Paintable:
        texture = self.cachedTexture(url)
        if texture is not None:
            return texture
        raw = await self.shared(('bytes', url), lambda: self.loadBytes(url, priority))
        loop = asyncio.get_running_loop()
        texture = await loop.run_in_executor(self.decoder, self.decode, raw)
        self.textures[url] = texture
        while len(self.textures) > THUMB_CACHE_ITEMS:
            self.textures.popitem(last=False)
        return texture

    def cachedTexture(self, url: str):
        texture = self.textures.get(url)
        if texture is not None:
            self.textures.move_to_end(url)
        return texture

    async def loadInto(self, item: GObject.Object, url: str, target: str, priority: bool = False):
        try:
            item.set_property(target, await self.getPaintable(url, priority))
        except asyncio.CancelledError:
            raise
        except Exception as error:
            print(f"image failed: {url}: {error}")

    def load(self, item: GObject.Object, url_property: str = "poster", target: str = "paintable",
             priority: bool = False):
        url = item.get_property(url_property)
        if not url or item.get_property(target) is not None:
            return None
        cached = self.cachedTexture(url)
        if cached is not None:
            item.set_property(target, cached)
            return None
        return asyncio.create_task(self.loadInto(item, url, target, priority))

    def startThumbnail(self, item: GObject.Object, url_property: str = "poster", target: str = "paintable",
                       priority: bool = False):
        key = (item, target)
        self.users[key] = self.users.get(key, 0) + 1
        return self.load(item, url_property, target, priority)

    def stopThumbnail(self, item: GObject.Object, task, target: str = "paintable"):
        if task:
            task.cancel()
        key = (item, target)
        count = self.users.get(key, 0) - 1
        if count > 0:
            self.users[key] = count
            return
        self.users.pop(key, None)
        item.set_property(target, None)

import asyncio
import copy
import json
from datetime import datetime, timezone
from gettext import gettext as _
from pathlib import Path
from urllib.parse import quote

import httpx
from gi.repository import Gio, GLib, GObject

from . import models
from .endpoints import *
from .integration import Integration, IntegrationError, LoginFailed

API_TIMEOUT = 20
ADDON_TIMEOUT = 15
STREAM_TIMEOUT = 25
FETCH_CONNECTIONS = 16
LIBRARY_SYNC_INTERVAL = 5 * 60
WATCHED_THRESHOLD = 0.9

MODEL_CLASSES = {
    'Meta': models.Meta,
    'Video': models.Video,
    'Addon': models.Addon,
    'LibraryItem': models.LibraryItem,
}


class ServerUnreachable(IntegrationError):
    pass


def mapped(item: dict, fields: dict) -> dict:
    return {name: item[key] for key, name in fields.items() if item.get(key) is not None}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def asText(value) -> str:
    if value is None:
        return ""
    return str(value)


def extraPath(**extra) -> str:
    parts = [f"{key}={quote(str(value), safe='')}" for key, value in extra.items() if value not in (None, "")]
    return "/" + "&".join(parts) if parts else ""


def resourceMatches(manifest: dict, resource: str, item_type: str, item_id: str) -> bool:
    for entry in manifest.get("resources") or []:
        if isinstance(entry, str):
            name, types, prefixes = entry, manifest.get("types") or [], manifest.get("idPrefixes")
        else:
            name = entry.get("name")
            types = entry.get("types") or manifest.get("types") or []
            prefixes = entry.get("idPrefixes", manifest.get("idPrefixes"))
        if name != resource or item_type not in types:
            continue
        if not prefixes or any(item_id.startswith(prefix) for prefix in prefixes):
            return True
    return False


def videoTitle(video: dict) -> str:
    return video.get("title") or video.get("name") or ""


def profileFolder(profile_id: str) -> Path:
    return Path(GLib.get_user_data_dir()) / "chelsea" / "profiles" / profile_id


class Stremio(Integration):
    __gtype_name__ = 'ChelseaIntegrationStremio'

    name = "stremio"
    display_name = "Stremio"

    def __init__(self, images, settings: Gio.Settings, secrets):
        super().__init__(images)
        self.settings = settings
        self.profile = {}
        self.secrets = secrets
        self.auth_key = ""
        self.user = {}
        self.manifests = {}
        self.library_items = {}
        self.last_addons = None
        self.last_library = None
        self.http = httpx.AsyncClient(
            headers=HEADERS,
            timeout=httpx.Timeout(API_TIMEOUT, pool=None),
            limits=httpx.Limits(max_connections=FETCH_CONNECTIONS),
            follow_redirects=True,
        )


    def useProfile(self, profile: dict):
        self.ready = False
        self.profile = profile
        self.auth_key = ""
        self.user = {}
        self.account_name = profile.get("name", "")
        self.profile_name = profile.get("name", "")
        self.avatar_url = profile.get("avatar", "")
        self.signed_in = False
        self.library_items = {}
        self.last_addons = None
        self.last_library = None
        for (item_type, key), model in self.loaded_models.items():
            if item_type == 'Meta':
                model.update_data(in_library=False, progress=0.0)
        self.replace(self.library, [])
        self.replace(self.addons, [])

    @property
    def is_account(self) -> bool:
        return bool(self.profile and self.profile.get("kind") == "stremio")

    async def start(self):
        if self.is_account:
            email = self.profile["email"]
            self.auth_key = await asyncio.to_thread(self.secrets.load, email)
            if not self.auth_key:
                raise LoginFailed(_("Sign in again to use this profile"))
            try:
                await self.getUser()
            except LoginFailed:
                raise
            except Exception as error:
                print(f"stremio: could not check the login, staying signed in: {error}")
                self.setSignedIn(email)
        await self.refresh()
        self.ready = True

    async def refresh(self):
        await asyncio.gather(self.refreshAddons(), self.refreshLibrary(), return_exceptions=True)

    async def request(self, method: str, payload: dict) -> dict | list:
        try:
            response = await self.http.post(API_URL + method, json=payload)
        except httpx.HTTPError as error:
            raise ServerUnreachable(_("Could not reach Stremio: {}").format(error)) from error
        try:
            data = response.json()
        except ValueError as error:
            raise IntegrationError(_("Stremio sent an invalid response")) from error
        if data.get("error"):
            error = data["error"]
            message = error.get("message") if isinstance(error, dict) else str(error)
            code = error.get("code") if isinstance(error, dict) else None
            if code in (1, 2, 3) or "session" in (message or "").lower():
                raise LoginFailed(message or _("Login failed"))
            raise IntegrationError(message or _("Stremio request failed"))
        return data.get("result")

    async def authed(self, method: str, payload: dict):
        if not self.auth_key:
            raise LoginFailed(_("Not signed in"))
        try:
            return await self.request(method, {"authKey": self.auth_key, **payload})
        except LoginFailed:
            await self.dropLogin()
            raise

    async def fetchJson(self, url: str, timeout: float = ADDON_TIMEOUT) -> dict:
        response = await self.http.get(url, timeout=timeout)
        response.raise_for_status()
        return response.json()


    def setSignedIn(self, email: str):
        self.account_name = email
        self.signed_in = True

    async def getUser(self) -> dict:
        self.user = await self.authed("getUser", {"type": GET_USER}) or {}
        self.setSignedIn(self.user.get("email") or self.profile.get("email", ""))
        self.avatar_url = self.user.get("avatar") or self.profile.get("avatar", "")
        return self.user

    async def authenticate(self, email: str, password: str) -> tuple[str, dict]:
        result = await self.request("login", {
            "type": LOGIN,
            "email": email,
            "password": password,
            "facebook": False,
        })
        if not result or not result.get("authKey"):
            raise LoginFailed(_("The email or password is wrong."))
        return result["authKey"], result.get("user") or {}

    async def logIn(self, email: str, password: str):
        auth_key, user = await self.authenticate(email, password)
        self.secrets.save(email, auth_key)
        return auth_key, user

    async def logOut(self):
        if self.auth_key:
            try:
                await self.request("logout", {"type": LOGOUT, "authKey": self.auth_key})
            except Exception as error:
                print(f"stremio: logout request failed: {error}")
        await self.dropLogin()

    async def dropLogin(self):
        if self.is_account:
            self.secrets.forget(self.profile["email"])
        self.auth_key = ""
        self.user = {}
        self.signed_in = False


    def modelFor(self, item_type: str, item_id) -> GObject.Object:
        key = (item_type, item_id)
        if key not in self.loaded_models:
            self.loaded_models[key] = MODEL_CLASSES[item_type]()
        return self.loaded_models[key]

    def makeMeta(self, item: dict) -> models.Meta:
        meta_type = item.get("type", "")
        model = self.modelFor('Meta', (meta_type, item["id"]))
        self.fillMeta(model, item)
        return model

    def fillMeta(self, model: models.Meta, item: dict):
        values = {name: asText(value) for name, value in mapped(item, META_FIELDS).items()}
        for key, name in META_LIST_FIELDS.items():
            if isinstance(item.get(key), list):
                values[name] = item[key]
        links = item.get("links") or []
        if not values.get("genres"):
            genres = [link.get("name") for link in links if link.get("category") == "Genres"]
            if genres:
                values["genres"] = genres
        trailers = item.get("trailerStreams") or item.get("trailers") or []
        if trailers:
            values["trailer"] = trailers[0].get("ytId") or trailers[0].get("source") or ""
        hints = item.get("behaviorHints") or {}
        if hints.get("defaultVideoId"):
            values["default_video_id"] = hints["defaultVideoId"]
        if not values.get("release_info") and item.get("year"):
            values["release_info"] = asText(item["year"])
        model.update_data(**values)
        library = self.library_items.get(model.id)
        model.update_data(
            in_library=bool(library and library.in_library),
            progress=library.progress if library else 0.0,
        )

    def fillVideos(self, model: models.Meta, videos: list):
        library = self.library_items.get(model.id)
        video_models = []
        for item in videos:
            if not item.get("id"):
                continue
            video = self.modelFor('Video', item["id"])
            values = {name: value for name, value in mapped(item, VIDEO_FIELDS).items()}
            values["title"] = videoTitle(item)
            values["overview"] = item.get("overview") or item.get("description") or ""
            values["season"] = int(values.get("season") or 0)
            values["episode"] = int(values.get("episode") or item.get("number") or 0)
            values["released"] = asText(values.get("released"))
            values["thumbnail"] = asText(values.get("thumbnail"))
            if library and library.video_id == item["id"]:
                values["progress"] = library.progress
            video.update_data(meta_id=model.id, **values)
            video_models.append(video)
        video_models.sort(key=lambda video: (video.season == 0, video.season, video.episode, video.released))
        self.replace(model.videos, video_models)

    def makeAddon(self, transport_url: str, manifest: dict, flags: dict | None = None) -> models.Addon:
        flags = flags or {}
        model = self.modelFor('Addon', transport_url)
        values = mapped(manifest, ADDON_FIELDS)
        hints = manifest.get("behaviorHints") or {}
        model.update_data(
            transport_url=transport_url,
            configurable=bool(hints.get("configurable")),
            configuration_required=bool(hints.get("configurationRequired")),
            is_official=bool(flags.get("official")),
            is_protected=bool(flags.get("protected")) or transport_url in PROTECTED_ADDONS,
            **values,
        )
        return model

    def makeStream(self, item: dict, addon: models.Addon) -> models.Stream:
        stream = models.Stream()
        values = mapped(item, STREAM_FIELDS)
        hints = item.get("behaviorHints") or {}
        values.update(mapped(hints, STREAM_HINT_FIELDS))
        proxy = hints.get("proxyHeaders") or {}
        if proxy.get("request"):
            values["headers"] = proxy["request"]
        if item.get("sources"):
            values["trackers"] = item["sources"]
        if "file_index" in values:
            values["file_index"] = int(values["file_index"])
        if not values.get("title") and values.get("description"):
            values["title"] = values["description"]
        stream.update_data(source_id=addon.id, source_name=addon.name, **values)
        return stream

    def makeLibraryItem(self, raw: dict) -> models.LibraryItem:
        model = self.modelFor('LibraryItem', raw["_id"])
        values = mapped(raw, LIBRARY_FIELDS)
        state = raw.get("state") or {}
        values.update(mapped(state, LIBRARY_STATE_FIELDS))
        for key in ("time_offset", "duration", "times_watched"):
            values[key] = int(values.get(key) or 0)
        for key in ("added_at", "modified_at", "last_watched", "video_id", "poster", "name", "type"):
            values[key] = asText(values.get(key))
        model.raw = raw
        model.update_data(**values)

        meta = self.modelFor('Meta', (model.type, model.id))
        if not meta.initialized:
            meta.update_data(id=model.id, type=model.type, name=model.name, poster=model.poster,
                             poster_shape=raw.get("posterShape") or "poster")
        meta.update_data(in_library=model.in_library, progress=model.progress)
        model.meta = meta
        return model


    def addonList(self) -> list[models.Addon]:
        return list(self.addons)

    def supporting(self, resource: str, item_type: str, item_id: str) -> list[models.Addon]:
        return [addon for addon in self.addons
                if resourceMatches(self.manifests.get(addon.transport_url, {}), resource, item_type, item_id)]

    async def loadManifest(self, transport_url: str) -> dict:
        manifest = await self.fetchJson(manifestUrl(transport_url))
        if not manifest.get("id"):
            raise IntegrationError(_("This is not a Stremio addon"))
        return manifest

    async def refreshAddons(self):
        if self.signed_in:
            try:
                result = await self.authed("addonCollectionGet", {"type": ADDON_COLLECTION_GET, "update": True})
                entries = [(item["transportUrl"], item.get("manifest") or {}, item.get("flags") or {})
                           for item in result.get("addons", [])]
            except LoginFailed:
                entries = await self.localAddonEntries()
        else:
            entries = await self.localAddonEntries()
        if entries == self.last_addons:
            return
        self.last_addons = entries

        addons = []
        for transport_url, manifest, flags in entries:
            if not manifest.get("id"):
                continue
            self.manifests[transport_url] = manifest
            model = self.makeAddon(transport_url, manifest, flags)
            model.installed = True
            addons.append(model)
        self.replace(self.addons, addons)
        self.addons_revision += 1

    async def localAddonEntries(self) -> list:
        urls = await asyncio.to_thread(self.readLocalAddons)

        async def entry(url):
            try:
                manifest = self.manifests.get(url) or await self.loadManifest(url)
                return url, manifest, {"official": url in DEFAULT_ADDONS}
            except Exception as error:
                print(f"stremio: addon {url} failed: {error}")
                return None

        results = await asyncio.gather(*(entry(url) for url in urls))
        return [result for result in results if result]

    async def saveAddons(self, addons: list[models.Addon]):
        if self.signed_in:
            payload = [{
                "transportUrl": addon.transport_url,
                "transportName": "http",
                "manifest": self.manifests[addon.transport_url],
                "flags": {"official": addon.is_official, "protected": addon.is_protected},
            } for addon in addons]
            await self.authed("addonCollectionSet", {"type": ADDON_COLLECTION_SET, "addons": payload})
        else:
            await asyncio.to_thread(self.writeLocalAddons, [addon.transport_url for addon in addons])
        for addon in self.addons:
            addon.installed = False
        for addon in addons:
            addon.installed = True
        self.replace(self.addons, addons)
        self.addons_revision += 1

    async def installAddon(self, transport_url: str) -> models.Addon:
        transport_url = manifestUrl(transport_url)
        manifest = await self.loadManifest(transport_url)
        self.manifests[transport_url] = manifest
        addon = self.makeAddon(transport_url, manifest)
        addons = [item for item in self.addons if item.transport_url != transport_url and item.id != addon.id]
        addons.append(addon)
        await self.saveAddons(addons)
        return addon

    def parseLink(self, uri: str) -> dict | None:
        return parseDeepLink(uri)

    async def previewAddon(self, transport_url: str) -> models.Addon:
        transport_url = manifestUrl(transport_url)
        manifest = await self.loadManifest(transport_url)
        self.manifests[transport_url] = manifest
        addon = self.makeAddon(transport_url, manifest)
        addon.installed = any(item.transport_url == transport_url for item in self.addons)
        return addon

    async def removeAddon(self, addon: models.Addon):
        if addon.is_protected:
            raise IntegrationError(_("This addon can't be removed"))
        await self.saveAddons([item for item in self.addons if item is not addon])

    async def getAddonCatalog(self) -> list[models.Addon]:
        result = await self.fetchJson(ADDON_CATALOG_URL)
        addons = []
        for item in result:
            transport_url = item.get("transportUrl")
            manifest = item.get("manifest") or {}
            if not transport_url or not manifest.get("id"):
                continue
            self.manifests.setdefault(transport_url, manifest)
            addon = self.makeAddon(transport_url, manifest, item.get("flags"))
            addon.installed = any(installed.transport_url == transport_url for installed in self.addons)
            addons.append(addon)
        return addons


    def getCatalogs(self) -> list[models.Catalog]:
        catalogs = []
        for addon in self.addons:
            base = addonBase(addon.transport_url)
            for item in addon.catalogs or []:
                extra = item.get("extra") or []
                names = {entry.get("name") for entry in extra}
                required = {entry.get("name") for entry in extra if entry.get("isRequired")}
                required.update(item.get("extraRequired") or [])
                names.update(item.get("extraSupported") or [])
                genres = []
                for entry in extra:
                    if entry.get("name") == "genre":
                        genres = entry.get("options") or []
                catalogs.append(models.Catalog(
                    source_id=addon.id,
                    source_name=addon.name,
                    base_url=base,
                    type=item.get("type", ""),
                    id=item.get("id", ""),
                    name=item.get("name") or "",
                    genres=genres,
                    genre_required="genre" in required,
                    board=not required,
                    searchable="search" in names,
                    pageable="skip" in names,
                ))
        return catalogs

    async def fetchCatalog(self, catalog: models.Catalog, **extra) -> list[models.Meta]:
        url = f"{catalog.base_url}/catalog/{catalog.type}/{quote(catalog.id, safe='')}{extraPath(**extra)}.json"
        result = await self.fetchJson(url)
        metas = []
        for item in result.get("metas") or []:
            if item.get("id"):
                item.setdefault("type", catalog.type)
                metas.append(self.makeMeta(item))
        return metas

    async def getCatalog(self, catalog: models.Catalog, skip: int = 0, genre: str = "") -> list[models.Meta]:
        if catalog.genre_required and not genre and catalog.genres:
            genre = catalog.genres[0]
        key = ('catalog', catalog.key, skip, genre)
        return await self.shared(key, lambda: self.fetchCatalog(catalog, genre=genre, skip=skip or None))

    async def search(self, catalog: models.Catalog, query: str) -> list[models.Meta]:
        return await self.shared(('search', catalog.key, query),
                                 lambda: self.fetchCatalog(catalog, search=query))

    async def getMeta(self, meta_type: str, meta_id: str, force: bool = False) -> models.Meta:
        model = self.modelFor('Meta', (meta_type, meta_id))
        if model.initialized and not force:
            return model
        return await self.shared(('meta', meta_type, meta_id), lambda: self.fetchMeta(meta_type, meta_id))

    async def fetchMeta(self, meta_type: str, meta_id: str) -> models.Meta:
        model = self.modelFor('Meta', (meta_type, meta_id))
        errors = []
        for addon in self.supporting("meta", meta_type, meta_id):
            url = f"{addonBase(addon.transport_url)}/meta/{meta_type}/{quote(meta_id, safe='')}.json"
            try:
                result = await self.fetchJson(url)
            except Exception as error:
                errors.append(f"{addon.name}: {error}")
                continue
            item = result.get("meta")
            if not item:
                continue
            item.setdefault("id", meta_id)
            item.setdefault("type", meta_type)
            self.fillMeta(model, item)
            self.fillVideos(model, item.get("videos") or [])
            model.initialized = True
            return model
        if model.name:
            model.initialized = True
            return model
        raise IntegrationError(_("No addon could load this title") + (": " + "; ".join(errors) if errors else ""))

    async def iterStreams(self, meta_type: str, video_id: str):
        addons = self.supporting("stream", meta_type, video_id)

        async def fetch(addon):
            url = f"{addonBase(addon.transport_url)}/stream/{meta_type}/{quote(video_id, safe='')}.json"
            try:
                result = await self.fetchJson(url, timeout=STREAM_TIMEOUT)
            except Exception as error:
                print(f"stremio: streams from {addon.name} failed: {error}")
                return addon, []
            return addon, [self.makeStream(item, addon) for item in result.get("streams") or []]

        for future in asyncio.as_completed([fetch(addon) for addon in addons]):
            addon, streams = await future
            yield addon, streams

    async def getSubtitles(self, meta_type: str, video_id: str, **extra) -> list[models.Subtitle]:
        addons = self.supporting("subtitles", meta_type, video_id)

        async def fetch(addon):
            url = (f"{addonBase(addon.transport_url)}/subtitles/{meta_type}/"
                   f"{quote(video_id, safe='')}{extraPath(**extra)}.json")
            try:
                result = await self.fetchJson(url)
            except Exception as error:
                print(f"stremio: subtitles from {addon.name} failed: {error}")
                return []
            return [models.Subtitle(id=asText(item.get("id")), url=item["url"], lang=item.get("lang") or "",
                                    source_name=addon.name)
                    for item in result.get("subtitles") or [] if item.get("url")]

        results = await asyncio.gather(*(fetch(addon) for addon in addons))
        return [subtitle for result in results for subtitle in result]


    async def refreshLibrary(self):
        if self.signed_in:
            raws = await self.authed("datastoreGet", {"collection": LIBRARY_COLLECTION, "ids": [], "all": True})
        else:
            raws = await asyncio.to_thread(self.readLocalLibrary)
        if raws == self.last_library:
            return
        self.last_library = copy.deepcopy(raws)
        items = [self.makeLibraryItem(raw) for raw in raws or [] if raw.get("_id")]
        self.library_items = {item.id: item for item in items}
        self.replace(self.library, items)
        self.library_revision += 1

    def localPath(self, name: str) -> Path:
        return profileFolder(self.profile.get("id", "guest")) / name

    def readLocalAddons(self) -> list:
        try:
            urls = json.loads(self.localPath("addons.json").read_text())
        except FileNotFoundError:
            return list(DEFAULT_ADDONS)
        except Exception as error:
            print(f"stremio: local addons are unreadable: {error}")
            return list(DEFAULT_ADDONS)
        return urls or list(DEFAULT_ADDONS)

    def writeLocalAddons(self, urls: list):
        self.writeJson("addons.json", urls)

    def writeJson(self, name: str, value):
        path = self.localPath(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(value))
        temporary.replace(path)

    def readLocalLibrary(self) -> list:
        path = self.localPath("library.json")
        try:
            return json.loads(path.read_text())
        except FileNotFoundError:
            return []
        except Exception as error:
            print(f"stremio: local library is unreadable: {error}")
            return []

    def writeLocalLibrary(self, raws: list):
        self.writeJson("library.json", raws)

    async def putLibraryItem(self, raw: dict):
        raw["_mtime"] = now()
        item = self.makeLibraryItem(raw)
        if item.id not in self.library_items:
            self.library_items[item.id] = item
            self.library.append(item)
        self.library_revision += 1
        if self.signed_in:
            await self.authed("datastorePut", {"collection": LIBRARY_COLLECTION, "changes": [raw]})
        else:
            raws = [entry.raw for entry in self.library_items.values()]
            await asyncio.to_thread(self.writeLocalLibrary, raws)

    def libraryItem(self, meta_id: str) -> models.LibraryItem | None:
        return self.library_items.get(meta_id)

    def libraryRaw(self, meta: models.Meta) -> dict:
        existing = self.library_items.get(meta.id)
        if existing is not None:
            raw = copy.deepcopy(existing.raw)
        else:
            raw = {
                "_id": meta.id,
                "_ctime": now(),
                "removed": True,
                "temp": True,
                "state": {
                    "lastWatched": None,
                    "timeWatched": 0,
                    "timeOffset": 0,
                    "overallTimeWatched": 0,
                    "timesWatched": 0,
                    "flaggedWatched": 0,
                    "duration": 0,
                    "video_id": None,
                    "watched": None,
                    "noNotif": False,
                },
                "behaviorHints": {"defaultVideoId": meta.default_video_id or None},
            }
        raw.update({
            "name": meta.name,
            "type": meta.type,
            "poster": meta.poster or None,
            "posterShape": meta.poster_shape or "poster",
        })
        return raw

    async def setInLibrary(self, meta: models.Meta, in_library: bool):
        raw = self.libraryRaw(meta)
        raw["removed"] = not in_library
        raw["temp"] = False
        await self.putLibraryItem(raw)

    async def saveProgress(self, meta: models.Meta, video_id: str, position: float, duration: float):
        if duration <= 0:
            return
        raw = self.libraryRaw(meta)
        state = raw.setdefault("state", {})
        previous_offset = int(state.get("timeOffset") or 0)
        position_ms = int(position * 1000)
        duration_ms = int(duration * 1000)
        finished = position / duration >= WATCHED_THRESHOLD

        state["lastWatched"] = now()
        state["duration"] = duration_ms
        state["video_id"] = video_id
        state["timeWatched"] = int(state.get("timeWatched") or 0) + max(0, position_ms - previous_offset)
        state["overallTimeWatched"] = int(state.get("overallTimeWatched") or 0) + max(0, position_ms - previous_offset)
        if finished:
            state["timeOffset"] = 0
            state["timesWatched"] = int(state.get("timesWatched") or 0) + 1
            state["flaggedWatched"] = 1
        else:
            state["timeOffset"] = position_ms
        if raw.get("removed") and not raw.get("temp"):
            raw["temp"] = True
        await self.putLibraryItem(raw)

        video = self.getModel('Video', video_id)
        if video is not None:
            video.update_data(progress=0.0 if finished else position / duration, watched=finished or video.watched)

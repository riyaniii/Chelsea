import asyncio

from gi.repository import Gio, GObject

from . import models

MAX_BOARD_CATALOGS = 12


class IntegrationError(Exception):
    pass


class LoginFailed(IntegrationError):
    pass


def watch(widget, obj: GObject.Object, callback, signal: str = "items-changed"):
    def on_signal(*args):
        callback()

    def on_unrealize(*args):
        if obj.handler_is_connected(handler):
            obj.disconnect(handler)

    handler = obj.connect(signal, on_signal)
    widget.connect("unrealize", on_unrealize)


class Integration(GObject.Object):
    __gtype_name__ = 'ChelseaIntegration'

    name = "integration"
    display_name = "Integration"

    signed_in = GObject.Property(type=bool, default=False)
    account_name = GObject.Property(type=str, default="")
    profile_name = GObject.Property(type=str, default="")
    avatar_url = GObject.Property(type=str, default="")
    ready = GObject.Property(type=bool, default=False)
    library_revision = GObject.Property(type=int, default=0)
    addons_revision = GObject.Property(type=int, default=0)

    def __init__(self, images):
        super().__init__()
        self.images = images
        self.background = set()
        self.pending = {}
        self.loaded_models = {}
        self.addons = Gio.ListStore(item_type=models.Addon)
        self.library = Gio.ListStore(item_type=models.LibraryItem)

    def runInBackground(self, job):
        task = asyncio.create_task(job)
        self.background.add(task)
        task.add_done_callback(self.finishBackgroundTask)
        return task

    def finishBackgroundTask(self, task):
        self.background.discard(task)
        if not task.cancelled() and task.exception():
            print(f"background job failed: {task.exception()!r}")

    def shared(self, key, factory):
        task = self.pending.get(key)
        if task is None:
            task = asyncio.ensure_future(factory())
            self.pending[key] = task
            task.add_done_callback(lambda done: self.pending.pop(key, None))
        return asyncio.shield(task)

    def getModel(self, item_type: str, model_id) -> GObject.Object | None:
        return self.loaded_models.get((item_type, model_id))

    @staticmethod
    def replace(store: Gio.ListStore, items: list):
        store.splice(0, store.get_n_items(), items)

    async def start(self):
        raise NotImplementedError

    async def refresh(self):
        raise NotImplementedError

    def close(self):
        for task in list(self.background):
            task.cancel()

    async def logIn(self, username: str, password: str):
        raise NotImplementedError

    async def logOut(self):
        raise NotImplementedError

    def getCatalogs(self) -> list[models.Catalog]:
        raise NotImplementedError

    def boardCatalogs(self) -> list[models.Catalog]:
        return [catalog for catalog in self.getCatalogs() if catalog.board][:MAX_BOARD_CATALOGS]

    def searchCatalogs(self) -> list[models.Catalog]:
        return [catalog for catalog in self.getCatalogs() if catalog.searchable]

    def browseCatalogs(self) -> list[models.Catalog]:
        return [catalog for catalog in self.getCatalogs() if catalog.board or catalog.genre_required]

    def catalogTypes(self) -> list[str]:
        types = []
        for catalog in self.browseCatalogs():
            if catalog.type not in types:
                types.append(catalog.type)
        return types

    async def getCatalog(self, catalog: models.Catalog, skip: int = 0, genre: str = "") -> list[models.Meta]:
        raise NotImplementedError

    async def search(self, catalog: models.Catalog, query: str) -> list[models.Meta]:
        raise NotImplementedError

    async def getMeta(self, meta_type: str, meta_id: str, force: bool = False) -> models.Meta:
        raise NotImplementedError

    async def iterStreams(self, meta_type: str, video_id: str):
        raise NotImplementedError
        yield []

    async def getSubtitles(self, meta_type: str, video_id: str, **extra) -> list[models.Subtitle]:
        return []

    def libraryItem(self, meta_id: str) -> models.LibraryItem | None:
        raise NotImplementedError

    async def setInLibrary(self, meta: models.Meta, in_library: bool):
        raise NotImplementedError

    async def saveProgress(self, meta: models.Meta, video_id: str, position: float, duration: float):
        raise NotImplementedError

    def continueWatching(self) -> list[models.LibraryItem]:
        items = [item for item in self.library if item.in_progress]
        items.sort(key=lambda item: item.last_watched, reverse=True)
        return items

    def savedItems(self) -> list[models.LibraryItem]:
        return [item for item in self.library if item.in_library]

    async def installAddon(self, transport_url: str) -> models.Addon:
        raise NotImplementedError

    async def previewAddon(self, transport_url: str) -> models.Addon:
        raise NotImplementedError

    async def removeAddon(self, addon: models.Addon):
        raise NotImplementedError

    async def getAddonCatalog(self) -> list[models.Addon]:
        return []

    def parseLink(self, uri: str) -> dict | None:
        return None

from urllib.parse import parse_qs, unquote, urlsplit

USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": USER_AGENT}

API_URL = "https://api.strem.io/api/"
ADDON_CATALOG_URL = "https://api.strem.io/addonscollection.json"

CINEMETA_URL = "https://v3-cinemeta.strem.io/manifest.json"
OPENSUBTITLES_URL = "https://opensubtitles-v3.strem.io/manifest.json"
DEFAULT_ADDONS = (CINEMETA_URL, OPENSUBTITLES_URL)
PROTECTED_ADDONS = (CINEMETA_URL,)

LIBRARY_COLLECTION = "libraryItem"

LOGIN = "Login"
LOGOUT = "Logout"
GET_USER = "GetUser"
ADDON_COLLECTION_GET = "AddonCollectionGet"
ADDON_COLLECTION_SET = "AddonCollectionSet"

META_FIELDS = {
    'id': 'id',
    'type': 'type',
    'name': 'name',
    'poster': 'poster',
    'posterShape': 'poster_shape',
    'background': 'background',
    'logo': 'logo',
    'description': 'description',
    'releaseInfo': 'release_info',
    'released': 'released',
    'runtime': 'runtime',
    'imdbRating': 'imdb_rating',
}

META_LIST_FIELDS = {
    'genres': 'genres',
    'cast': 'cast',
    'director': 'directors',
}

VIDEO_FIELDS = {
    'id': 'id',
    'season': 'season',
    'episode': 'episode',
    'released': 'released',
    'thumbnail': 'thumbnail',
}

STREAM_FIELDS = {
    'name': 'name',
    'title': 'title',
    'description': 'description',
    'url': 'url',
    'infoHash': 'info_hash',
    'fileIdx': 'file_index',
    'externalUrl': 'external_url',
    'ytId': 'yt_id',
}

STREAM_HINT_FIELDS = {
    'filename': 'filename',
    'bingeGroup': 'binge_group',
    'notWebReady': 'not_web_ready',
}

ADDON_FIELDS = {
    'id': 'id',
    'name': 'name',
    'description': 'description',
    'version': 'version',
    'logo': 'logo',
    'types': 'types',
    'catalogs': 'catalogs',
    'resources': 'resources',
    'idPrefixes': 'id_prefixes',
}

LIBRARY_FIELDS = {
    '_id': 'id',
    'type': 'type',
    'name': 'name',
    'poster': 'poster',
    'removed': 'removed',
    'temp': 'temp',
    '_ctime': 'added_at',
    '_mtime': 'modified_at',
}

LIBRARY_STATE_FIELDS = {
    'lastWatched': 'last_watched',
    'timeOffset': 'time_offset',
    'duration': 'duration',
    'video_id': 'video_id',
    'timesWatched': 'times_watched',
}


WEB_HOSTS = ("web.stremio.com", "app.strem.io", "web.strem.io")


def webAddonLink(text: str) -> str:
    parts = urlsplit(text.strip())
    if parts.netloc not in WEB_HOSTS or "?" not in parts.fragment:
        return ""
    query = parse_qs(parts.fragment.split("?", 1)[1])
    return query.get("addon", [""])[0]


def addonBase(transport_url: str) -> str:
    base = webAddonLink(transport_url) or transport_url.strip()
    if base.startswith("stremio://"):
        base = "https://" + base[len("stremio://"):]
    if base.endswith("/manifest.json"):
        base = base[:-len("/manifest.json")]
    return base.rstrip("/")


def manifestUrl(transport_url: str) -> str:
    return addonBase(transport_url) + "/manifest.json"


def isAddonLink(text: str) -> bool:
    text = text.strip()
    if webAddonLink(text):
        return True
    if text.startswith("stremio://"):
        return bool(urlsplit(text).netloc)
    return text.startswith(("http://", "https://")) and text.split("?")[0].endswith("/manifest.json")


def parseDeepLink(uri: str) -> dict | None:
    uri = uri.strip()
    if isAddonLink(uri):
        return {"page": "addon", "url": manifestUrl(uri)}
    parts = urlsplit(uri)
    if parts.scheme == "stremio":
        path, query = parts.path, parts.query
    elif parts.netloc in WEB_HOSTS:
        path, _, query = parts.fragment.partition("?")
    else:
        return None
    pieces = [unquote(piece) for piece in path.split("/") if piece]
    params = parse_qs(query)
    if not pieces:
        return {"page": "home"}
    page = pieces[0]
    if page == "detail" and len(pieces) >= 3:
        return {"page": "details", "type": pieces[1], "id": pieces[2]}
    if page == "search":
        return {"page": "search", "query": params.get("search", [""])[0]}
    if page in ("discover", "library", "addons", "board"):
        return {"page": "home" if page == "board" else page}
    return None

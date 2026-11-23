import base64
import binascii
import os
from urllib.parse import parse_qs, unquote, urlparse

from ..integrations.endpoints import isAddonLink


class Link:
    def __init__(self, kind: str, url: str, info_hash: str = "", name: str = "", trackers=None):
        self.kind = kind
        self.url = url
        self.info_hash = info_hash
        self.name = name
        self.trackers = trackers or []


def info_hash_from(value: str) -> str:
    value = value.strip()
    if len(value) == 40:
        return value.lower()
    if len(value) == 32:
        try:
            return binascii.hexlify(base64.b32decode(value.upper())).decode()
        except (binascii.Error, ValueError):
            return ""
    return ""


def parse(text: str) -> Link | None:
    text = text.strip()
    if not text or " " in text:
        return None
    if text.startswith("magnet:?"):
        params = parse_qs(text[len("magnet:?"):])
        info_hash = ""
        for topic in params.get("xt", []):
            if topic.startswith("urn:btih:"):
                info_hash = info_hash_from(topic[len("urn:btih:"):])
        if not info_hash:
            return None
        trackers = [f"tracker:{tracker}" for tracker in params.get("tr", [])]
        name = params.get("dn", [""])[0]
        return Link("magnet", text, info_hash=info_hash, name=name, trackers=trackers)
    if isAddonLink(text):
        return Link("addon", text)
    if text.startswith(("http://", "https://")):
        path = urlparse(text).path
        name = unquote(os.path.basename(path.rstrip("/"))) or urlparse(text).netloc
        return Link("url", text, name=name)
    return None

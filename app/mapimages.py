"""Vorschaubilder für Maps, die keine feste Bild-URL haben: CS2-Workshop (Steam-API) und Wreckfest-Strecken (Wreckfest-Wiki).

Ergebnisse werden im Volume gespeichert; Fehlschläge werden nach einem Tag erneut versucht.
Abfragen laufen im Hintergrund – die Anzeige nutzt, was schon im Speicher liegt.
"""
import asyncio
import re
import time

import httpx

from . import store

FILE = "mapimages.json"
_cache: dict | None = None
_pending: set[str] = set()


def _load() -> dict:
    global _cache
    if _cache is None:
        _cache = store.load(FILE, {})
    return _cache


def workshop_id(map_name: str | None, ws: dict | None = None) -> str | None:
    if ws and str(ws.get("id") or "").isdigit():
        return str(ws["id"])
    m = re.search(r"workshop/(\d{6,})", map_name or "")
    return m.group(1) if m else None


def _venue(track_label: str) -> str:
    """„Sandstone Raceway – Long (rückwärts)“ -> „Sandstone Raceway“."""
    return re.sub(r"\s*\(rückwärts\)", "", track_label.split(" – ")[0]).strip()


async def _fetch_workshop(wid: str) -> str:
    async with httpx.AsyncClient(timeout=10) as cl:
        r = await cl.post("https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/",
                          data={"itemcount": 1, "publishedfileids[0]": wid})
    d = ((r.json().get("response") or {}).get("publishedfiledetails") or [{}])[0]
    return d.get("preview_url") or ""


async def _fetch_wreckfest(venue: str) -> str:
    async with httpx.AsyncClient(timeout=10, headers={"User-Agent": "Spielservermanager"}) as cl:
        r = await cl.get("https://wreckfest.fandom.com/api.php",
                         params={"action": "query", "titles": venue, "prop": "pageimages", "format": "json",
                                 "pithumbsize": 480, "redirects": 1})
    for p in ((r.json().get("query") or {}).get("pages") or {}).values():
        src = (p.get("thumbnail") or {}).get("source")
        if src:
            return src
    return ""


async def _fetch_wiki(val: str) -> str:
    """Bild einer Wiki-Seite (MediaWiki pageimages): val = "host|Seitentitel"."""
    host, title = val.split("|", 1)
    async with httpx.AsyncClient(timeout=10, headers={"User-Agent": "Spielservermanager"}) as cl:
        r = await cl.get(f"https://{host}/api.php", params={"action": "query", "titles": title, "prop": "pageimages",
                                                          "format": "json", "pithumbsize": 800, "redirects": 1})
    for p in ((r.json().get("query") or {}).get("pages") or {}).values():
        src = (p.get("thumbnail") or {}).get("source")
        if src:
            return src
    return ""


# Spiele ohne Map-Bild: passendes Wiki-Bild statt Logo
WIKI_IMAGES = {"minecraft": "minecraft.wiki|Overworld"}


async def _resolve(key: str) -> None:
    try:
        kind, val = key.split(":", 1)
        url = await (_fetch_workshop(val) if kind == "ws" else _fetch_wiki(val) if kind == "mw" else _fetch_wreckfest(val))
    except (httpx.HTTPError, ValueError, KeyError, IndexError):
        url = ""
    c = _load()
    c[key] = {"url": url, "t": time.time()}
    store.save(FILE, c)
    _pending.discard(key)


def _get(key: str) -> str | None:
    e = _load().get(key)
    if e and (e.get("url") or time.time() - e.get("t", 0) < 86400):
        return e.get("url") or None
    if key not in _pending:
        _pending.add(key)
        try:
            asyncio.get_running_loop().create_task(_resolve(key))
        except RuntimeError:
            _pending.discard(key)
    return None


def _base(map_name: str | None) -> str:
    return (map_name or "").split("/")[-1].replace(".vpk", "").lower()


def remember_workshop_map(map_name: str, ws: dict) -> None:
    """Workshop-Map wurde geladen -> Map-Name dauerhaft mit Vorschaubild/Titel verknüpfen."""
    b = _base(map_name)
    if not b or not ws.get("preview"):
        return
    c = _load()
    key = f"wsname:{b}"
    if (c.get(key) or {}).get("url") != ws["preview"]:
        c[key] = {"url": ws["preview"], "title": ws.get("title") or "", "id": ws.get("id"), "t": time.time()}
        store.save(FILE, c)


def workshop_title(map_name: str | None) -> str | None:
    return ((_load().get(f"wsname:{_base(map_name)}") or {}).get("title")) or None


def image_for(game: str, map_name: str | None, ws: dict | None = None, track_label: str | None = None) -> str | None:
    """Bild-URL, falls bekannt (sonst wird sie im Hintergrund geholt und beim nächsten Mal geliefert)."""
    if game == "cs2":
        if ws and ws.get("preview"):
            return ws["preview"]
        known = _load().get(f"wsname:{_base(map_name)}")
        if known and known.get("url"):
            return known["url"]
        wid = workshop_id(map_name, ws)
        return _get(f"ws:{wid}") if wid else None
    if game == "wreckfest" and track_label:
        return _get(f"wf:{_venue(track_label)}")
    if game in WIKI_IMAGES:
        return _get(f"mw:{WIKI_IMAGES[game]}")
    return None

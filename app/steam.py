"""Steam-Hilfen: Workshop-Suche (ohne API-Key) und SteamID-Auflösung."""
import asyncio
import html
import os
import re
import time

import httpx

COMMUNITY = os.getenv("STEAM_COMMUNITY_URL", "https://steamcommunity.com").rstrip("/")
API = os.getenv("STEAM_API_URL", "https://api.steampowered.com").rstrip("/")
STEAMID64_BASE = 76561197960265728
UA = {"User-Agent": "Mozilla/5.0 (cs2-rcon-web)", "Accept-Language": "de-DE,de;q=0.9,en;q=0.8"}

_cache: dict[str, tuple[float, object]] = {}


class SteamError(Exception):
    pass


def _cached(key, ttl):
    v = _cache.get(key)
    if v and time.time() - v[0] < ttl:
        return v[1]
    return None


def _client():
    return httpx.AsyncClient(timeout=12, headers=UA, follow_redirects=True)


# ---------------------------------------------------------------- Workshop
SORTS = {"relevanz": "textsearch", "trend": "trend", "neu": "mostrecent", "beliebt": "totaluniquesubscribers"}


# Spiele, deren Server Workshop-Maps live laden können: appid, Pflicht-Tag, nur Einträge mit Tag „Map“
WS_GAMES = {"cs2": ("730", "CS2", True), "tf2": ("440", None, False)}


async def workshop_search(query: str = "", sort: str = "", page: int = 1, game: str = "cs2") -> list[dict]:
    query = (query or "").strip()
    sort = SORTS.get(sort) or ("textsearch" if query else "trend")
    appid, tag, only_maps = WS_GAMES.get(game) or WS_GAMES["cs2"]
    params = {
        "appid": appid, "section": "readytouseitems",
        "browsesort": sort, "actualsort": sort, "p": str(max(1, page)), "numperpage": "30",
    }
    if tag:
        params["requiredtags[]"] = tag
    if query:
        params["searchtext"] = query
    if sort == "trend":
        params["days"] = "90"
    key = "search:" + repr(sorted(params.items()))
    if (c := _cached(key, 300)) is not None:
        return c
    try:
        async with _client() as cl:
            r = await cl.get(f"{COMMUNITY}/workshop/browse/", params=params)
            r.raise_for_status()
    except httpx.HTTPError as e:
        raise SteamError(f"Steam Workshop nicht erreichbar ({e.__class__.__name__})") from e
    ids = list(dict.fromkeys(re.findall(r"filedetails/\?id=(\d+)", r.text)))[:30]
    items = await workshop_details(ids)
    maps = [i for i in items if i.get("is_map", True)] if only_maps else items
    _cache[key] = (time.time(), maps)
    return maps


async def workshop_details(ids: list[str]) -> list[dict]:
    ids = [i for i in dict.fromkeys(str(x) for x in ids) if i.isdigit()]
    if not ids:
        return []
    out, missing = {}, []
    for i in ids:
        c = _cached("wd:" + i, 3600)
        if c:
            out[i] = c
        else:
            missing.append(i)
    if missing:
        data = {"itemcount": str(len(missing))}
        for n, i in enumerate(missing):
            data[f"publishedfileids[{n}]"] = i
        try:
            async with _client() as cl:
                r = await cl.post(f"{API}/ISteamRemoteStorage/GetPublishedFileDetails/v1/", data=data)
                r.raise_for_status()
                details = r.json().get("response", {}).get("publishedfiledetails", [])
        except (httpx.HTTPError, ValueError) as e:
            raise SteamError(f"Workshop-Details nicht abrufbar ({e.__class__.__name__})") from e
        for d in details:
            if d.get("result") != 1:
                continue
            tags = [t.get("tag", "") for t in d.get("tags", [])]
            item = {
                "id": str(d.get("publishedfileid")),
                "title": d.get("title") or str(d.get("publishedfileid")),
                "preview": d.get("preview_url") or "",
                "size_mb": round(int(d.get("file_size") or 0) / 1024 / 1024),
                "subscriptions": int(d.get("lifetime_subscriptions") or d.get("subscriptions") or 0),
                "updated": int(d.get("time_updated") or 0),
                "tags": tags,
                "is_map": any(t.lower() == "map" for t in tags) or not tags,
                "app": d.get("consumer_app_id"),
            }
            _cache["wd:" + item["id"]] = (time.time(), item)
            out[item["id"]] = item
    return [out[i] for i in ids if i in out]


def parse_workshop_id(text: str) -> str | None:
    text = (text or "").strip()
    m = re.search(r"[?&]id=(\d+)", text) or re.fullmatch(r"(\d{6,})", text)
    return m.group(1) if m else None


# ---------------------------------------------------------------- SteamIDs
def to_steamid64(text: str) -> str | None:
    """Wandelt SteamID-Formate und Profil-Links (/profiles/) offline um."""
    t = (text or "").strip()
    if m := re.search(r"(7656119\d{10})", t):
        return m.group(1)
    if m := re.fullmatch(r"STEAM_[0-5]:([01]):(\d+)", t, re.I):
        return str(STEAMID64_BASE + int(m.group(2)) * 2 + int(m.group(1)))
    if m := re.fullmatch(r"\[?U:1:(\d+)\]?", t, re.I):
        return str(STEAMID64_BASE + int(m.group(1)))
    return None


def vanity_name(text: str) -> str | None:
    t = (text or "").strip()
    if m := re.search(r"steamcommunity\.com/id/([A-Za-z0-9_\-]+)", t):
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_\-]{2,32}", t):
        return t
    return None


def _xml_tag(xml: str, tag: str) -> str | None:
    m = re.search(rf"<{tag}>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{tag}>", xml, re.S)
    return html.unescape(m.group(1).strip()) if m else None


async def resolve_player(text: str) -> dict:
    """Akzeptiert SteamID64, STEAM_0:x:y, [U:1:z], Profil-Link oder Vanity-Namen."""
    sid = to_steamid64(text)
    async with _client() as cl:
        try:
            if sid:
                r = await cl.get(f"{COMMUNITY}/profiles/{sid}/", params={"xml": "1"})
            else:
                v = vanity_name(text)
                if not v:
                    raise SteamError("Unbekanntes Format – SteamID64, STEAM_0:…, [U:1:…] oder Profil-Link angeben")
                r = await cl.get(f"{COMMUNITY}/id/{v}/", params={"xml": "1"})
            xml = r.text
        except httpx.HTTPError as e:
            if sid:  # offline: SteamID ist trotzdem gültig, nur ohne Namen
                return {"steamid": sid, "name": "", "avatar": "", "offline": True}
            raise SteamError(f"Steam nicht erreichbar ({e.__class__.__name__})") from e
    found = _xml_tag(xml, "steamID64")
    if not found:
        if sid:
            return {"steamid": sid, "name": "", "avatar": "", "offline": True}
        raise SteamError("Steam-Profil nicht gefunden")
    return {"steamid": found, "name": _xml_tag(xml, "steamID") or "",
            "avatar": _xml_tag(xml, "avatarMedium") or "", "offline": False}


def extract_steamids(text: str) -> list[dict]:
    """Sucht SteamIDs (+ Namen in Anführungszeichen) in Konsolenausgaben."""
    found: dict[str, str] = {}
    for line in text.splitlines():
        ids = re.findall(r"7656119\d{10}", line)
        ids += [str(STEAMID64_BASE + int(u)) for u in re.findall(r"\[U:1:(\d+)\]", line)]
        ids += [str(STEAMID64_BASE + int(z) * 2 + int(y)) for y, z in re.findall(r"STEAM_[0-5]:([01]):(\d+)", line)]
        names = re.findall(r"[\"']([^\"']{1,64})[\"']", line)
        for i in ids:
            if i not in found or (not found[i] and names):
                found[i] = names[0] if names else ""
    return [{"steamid": k, "name": v} for k, v in found.items()]


async def gather_limited(coros, limit=5):
    sem = asyncio.Semaphore(limit)

    async def run(c):
        async with sem:
            return await c
    return await asyncio.gather(*(run(c) for c in coros), return_exceptions=True)

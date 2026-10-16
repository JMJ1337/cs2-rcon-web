"""Steam-Depot-ID -> Spiel (App-ID + Name). Ergebnisse werden im Volume gespeichert."""
import asyncio
import time

import httpx

from . import store

FILE = "depots.json"
KNOWN_APPS = [730, 740, 2347770, 440, 232250, 361580, 228380, 892970, 896660, 427520, 526870, 1690800, 4000, 570, 578080,
              252490, 271590, 1172470, 1086940, 381210, 1245620, 359550, 236390, 1938090, 2357570, 1063730]
_map: dict | None = None
_queue: list[str] = []
_apps_checked: dict[int, float] = {}
_running = False


def _load() -> dict:
    global _map
    if _map is None:
        _map = store.load(FILE, {})
    return _map


def lookup(depot: str) -> dict | None:
    e = _load().get(str(depot))
    return e if e and e.get("app") else None


def want(depots) -> None:
    m = _load()
    for d in depots:
        d = str(d)
        e = m.get(d)
        if (e is None or (not e.get("app") and time.time() - e.get("t", 0) > 86400)) and d not in _queue:
            _queue.append(d)


async def _app_info(cl: httpx.AsyncClient, appid: int) -> dict | None:
    try:
        r = await cl.get(f"https://api.steamcmd.net/v1/info/{appid}")
        if r.status_code != 200:
            return None
        j = r.json()
        return (j.get("data") or {}).get(str(appid))
    except (httpx.HTTPError, ValueError):
        return None


async def _store_name(cl: httpx.AsyncClient, appid: int) -> str | None:
    try:
        r = await cl.get("https://store.steampowered.com/api/appdetails", params={"appids": appid, "filters": "basic"})
        d = (r.json() or {}).get(str(appid)) or {}
        return (d.get("data") or {}).get("name") if d.get("success") else None
    except (httpx.HTTPError, ValueError):
        return None


def _remember_app(appid: int, info: dict) -> None:
    """Alle Depots einer App eintragen."""
    m = _load()
    name = ((info.get("common") or {}).get("name")) or f"App {appid}"
    for dk in (info.get("depots") or {}):
        if dk.isdigit():
            m[dk] = {"app": appid, "name": name, "t": time.time()}


async def run() -> None:
    """Warteschlange abarbeiten (im Hintergrund, schonend)."""
    global _running
    if _running or not _queue:
        return
    _running = True
    m = _load()
    try:
        async with httpx.AsyncClient(timeout=10, headers={"User-Agent": "Spielservermanager"}) as cl:
            # bekannte Apps einmal komplett einlesen (z. B. CS2-Depots 2347770…)
            for a in KNOWN_APPS:
                if a in _apps_checked:
                    continue
                _apps_checked[a] = time.time()
                info = await _app_info(cl, a)
                if info:
                    _remember_app(a, info)
                await asyncio.sleep(0.5)
            while _queue:
                d = _queue.pop(0)
                if lookup(d):
                    continue
                dep = int(d)
                found = None
                for cand in range(dep - 1, dep - 8, -1):       # Depots liegen meist knapp über der App-ID
                    if cand in _apps_checked and time.time() - _apps_checked[cand] < 86400:
                        continue
                    _apps_checked[cand] = time.time()
                    info = await _app_info(cl, cand)
                    await asyncio.sleep(0.4)
                    if info:
                        _remember_app(cand, info)
                        if d in (info.get("depots") or {}):
                            found = m.get(d)
                            break
                if not found and not m.get(d, {}).get("app"):
                    # Ersatz ohne steamcmd-API: App-ID = Depot-1 und Name aus dem Store
                    name = await _store_name(cl, dep - 1)
                    m[d] = {"app": dep - 1, "name": name, "t": time.time(), "guess": True} if name else {"app": None, "t": time.time()}
                store.save(FILE, m)
    finally:
        store.save(FILE, m)
        _running = False


def games(depots: dict) -> list[dict]:
    """{depot: [hit, miss]} -> nach Spiel zusammengefasst."""
    want(depots.keys())
    agg: dict = {}
    for d, (h, mi) in depots.items():
        e = lookup(d)
        key = e["app"] if e else f"d{d}"
        g = agg.setdefault(key, {"app": e["app"] if e else None, "name": (e or {}).get("name") or f"Depot {d}",
                                 "hit": 0, "miss": 0, "depots": 0})
        g["hit"] += h; g["miss"] += mi; g["depots"] += 1
    return sorted(agg.values(), key=lambda x: -(x["hit"] + x["miss"]))

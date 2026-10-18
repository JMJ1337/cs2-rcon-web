"""Steam-Depot-ID -> Spiel (App-ID + Name). Ergebnisse werden im Volume gespeichert."""
import asyncio
import re
import time

import httpx

from . import store

FILE = "depots.json"
KNOWN_APPS = [730, 740, 2347770, 440, 232250, 361580, 228380, 892970, 896660, 427520, 526870, 1690800, 4000, 570, 578080,
              252490, 271590, 1172470, 1086940, 381210, 1245620, 359550, 236390, 1938090, 2357570, 1063730, 1422450]
_map: dict | None = None
_queue: list[str] = []
_running = False
# weitere wahrscheinliche Apps (Prefill-Liste, Spielserver) – wird von main gesetzt
extra_apps = lambda: []  # noqa: E731
ICON_DIR = store.DATA_DIR / "icons"
RESOLVER_V = 2                     # neue Suchlogik -> alte Fehlschläge einmal neu versuchen
ICON_ALIAS = {740: 730}            # CS2 Dedicated Server -> Icon von CS2


class _Checked(dict):
    """Welche App-IDs schon abgefragt wurden – im Volume gespeichert, damit nach Neustarts nichts neu geholt wird."""
    def __setitem__(self, k, v):
        super().__setitem__(k, v)
        _load().setdefault("_checked", {})[str(k)] = v


_apps_checked: _Checked = _Checked()


def _load() -> dict:
    global _map
    if _map is None:
        _map = store.load(FILE, {})
        for k, v in (_map.get("_checked") or {}).items():
            if k.isdigit():
                dict.__setitem__(_apps_checked, int(k), v)
    return _map


def depots_of(appid: int) -> list[str]:
    """Alle bekannten Depot-IDs einer App."""
    return [k for k, e in _load().items() if k[:1] != "_" and isinstance(e, dict) and e.get("app") == int(appid)] + [str(appid)]


def lookup(depot: str) -> dict | None:
    e = _load().get(str(depot))
    return e if e and e.get("app") else None


def want(depots) -> None:
    m = _load()
    for d in depots:
        d = str(d)
        if d.startswith("_") or not d.isdigit():
            continue
        e = m.get(d)
        retry = not e or (not e.get("app") and (time.time() - e.get("t", 0) > 86400 or e.get("v", 1) < RESOLVER_V))
        if retry and d not in _queue:
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


async def _store_image(cl: httpx.AsyncClient, appid: int) -> str | None:
    try:
        r = await cl.get("https://store.steampowered.com/api/appdetails", params={"appids": appid, "filters": "basic"})
        d = (r.json() or {}).get(str(appid)) or {}
        data = d.get("data") or {}
        return data.get("capsule_imagev5") or data.get("capsule_image") or data.get("header_image") if d.get("success") else None
    except (httpx.HTTPError, ValueError):
        return None


def _remember_app(appid: int, info: dict) -> None:
    """Alle Depots einer App eintragen."""
    m = _load()
    name = ((info.get("common") or {}).get("name")) or f"App {appid}"
    total = 0
    for dk, dv in (info.get("depots") or {}).items():
        if not dk.isdigit():
            continue
        m[dk] = {"app": appid, "name": name, "t": time.time()}
        cfg = (dv or {}).get("config") or {}
        if (cfg.get("oslist") and "windows" not in cfg["oslist"]) or (cfg.get("language") not in (None, "", "english")):
            continue
        man = ((dv or {}).get("manifests") or {}).get("public") or {}
        try:
            total += int(man.get("download") or man.get("size") or 0)
        except (TypeError, ValueError):
            pass
    if total:
        m.setdefault("_size", {})[str(appid)] = total


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
            try:
                more = [int(a) for a in extra_apps() if str(a).isdigit()]
            except Exception:  # noqa: BLE001
                more = []
            for a in list(dict.fromkeys(KNOWN_APPS + more)):
                if a in _apps_checked and time.time() - _apps_checked[a] < 7 * 86400:
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
                # App-IDs sind meist Vielfache von 10, Depots liegen knapp darüber (1422450 -> 1422451…1422459);
                # manche Depot-IDs sind gleich der App-ID (730, 1422450)
                base10 = dep - dep % 10
                cands = list(dict.fromkeys([dep, base10] + list(range(dep - 1, dep - 10, -1))))
                known = next((e for k, e in m.items() if k[:1] != "_" and isinstance(e, dict) and e.get("app") == base10 and e.get("name")), None)
                if known:                       # Nachbar-Depot derselben App schon bekannt
                    m[d] = {"app": base10, "name": known["name"], "t": time.time(), "guess": True}
                    continue
                for cand in cands:
                    if cand in _apps_checked and time.time() - _apps_checked[cand] < 86400:
                        continue
                    _apps_checked[cand] = time.time()
                    info = await _app_info(cl, cand)
                    await asyncio.sleep(0.4)
                    if info:
                        _remember_app(cand, info)
                        if d in (info.get("depots") or {}) or str(cand) == d:
                            m[d] = {"app": cand, "name": ((info.get("common") or {}).get("name")) or f"App {cand}", "t": time.time()}
                            found = m.get(d)
                            break
                        # Depots nicht öffentlich gelistet (z. B. Deadlock): Zehner-App mit Namen übernehmen
                        nm = (info.get("common") or {}).get("name")
                        if cand == base10 and nm and not [k for k in (info.get("depots") or {}) if k.isdigit()]:
                            m[d] = {"app": cand, "name": nm, "t": time.time(), "guess": True}
                            found = m.get(d)
                            break
                if not found and not m.get(d, {}).get("app"):
                    # Ersatz ohne steamcmd-API: App-ID = Depot-1 und Name aus dem Store
                    hit = None
                    for cand in dict.fromkeys([base10, dep, dep - 1]):
                        name = await _store_name(cl, cand)
                        await asyncio.sleep(0.3)
                        if name:
                            hit = {"app": cand, "name": name, "t": time.time(), "guess": True}
                            break
                    m[d] = hit or {"app": None, "t": time.time(), "v": RESOLVER_V}
                store.save(FILE, m)
    finally:
        store.save(FILE, m)
        _running = False


# Battle.net: CDN-Pfad (…/tpr/<pfad>/…) -> Spiel
BNET_NAMES = {"wow": "World of Warcraft", "hs": "Hearthstone", "sc2": "StarCraft II", "s2": "StarCraft II", "sc1": "StarCraft Remastered",
              "s1": "StarCraft Remastered", "d3": "Diablo III", "fenris": "Diablo IV", "osi": "Diablo II: Resurrected",
              "ovw": "Overwatch 2", "pro": "Overwatch 2", "hero": "Heroes of the Storm", "w3": "Warcraft III: Reforged",
              "war3": "Warcraft III: Reforged", "anbs": "Diablo Immortal", "gryphon": "Warcraft Rumble", "zeus": "CoD: Black Ops Cold War",
              "odin": "CoD: Modern Warfare 2019", "viper": "CoD: Black Ops 4", "auks": "Call of Duty", "nina": "CoD: MW II",
              "pinta": "CoD: MW III", "btlr": "CoD: Black Ops 6", "fore": "CoD: Vanguard", "lazr": "CoD: MW2 Remastered",
              "wlby": "Crash Bandicoot 4", "rtro": "Blizzard Arcade Collection", "scor": "Sea of Thieves", "aqua": "Avowed",
              "catalogs": "Battle.net-Katalog", "bna": "Battle.net-App", "agent": "Battle.net-Agent", "configs": "Battle.net-Konfiguration"}


def _nice(name: str) -> str:
    return re.sub(r"(?<=[a-z])(?=[A-Z0-9])", " ", name).replace("_", " ").strip() or name


def games(depots: dict) -> list[dict]:
    """{depot: [hit, miss]} -> nach Spiel zusammengefasst (Steam-Depots, Epic- und Battle.net-Spiele)."""
    want(depots.keys())
    agg: dict = {}
    for d, (h, mi) in depots.items():
        d = str(d)
        if d.startswith(("epic:", "bnet:")):
            kind, _, code = d.partition(":")
            if kind == "epic":
                name = _nice(code) if not code.startswith("o-") and not re.fullmatch(r"[0-9a-f]{20,}", code) else "Epic-Spiel"
                svc = "epicgames"
            else:
                name, svc = BNET_NAMES.get(code, code.upper()), "blizzard"
            g = agg.setdefault(f"{svc}:{name}", {"app": None, "name": name, "service": svc, "hit": 0, "miss": 0, "depots": 0})
            g["hit"] += h; g["miss"] += mi; g["depots"] += 1
            continue
        e = lookup(d)
        key = e["app"] if e else f"d{d}"
        g = agg.setdefault(key, {"app": e["app"] if e else None, "name": (e or {}).get("name") or f"Depot {d}",
                                 "hit": 0, "miss": 0, "depots": 0})
        g["hit"] += h; g["miss"] += mi; g["depots"] += 1
    return sorted(agg.values(), key=lambda x: -(x["hit"] + x["miss"]))


async def icons(appids: list[int]) -> dict:
    """Echte Spiel-Icons (Steam-Community-Icon) je App-ID, gecacht."""
    m = _load()
    ic = m.setdefault("_icons", {})
    tv = m.setdefault("_icons_v", {})
    todo = [a for a in appids if str(a) not in ic or (not ic[str(a)] and (time.time() - m.get("_icons_t", {}).get(str(a), 0) > 86400
                                                                       or tv.get(str(a), 1) < RESOLVER_V))]
    if todo:
        tt = m.setdefault("_icons_t", {})
        async with httpx.AsyncClient(timeout=8, headers={"User-Agent": "Spielservermanager"}) as cl:
            for a in todo[:20]:
                src = ICON_ALIAS.get(int(a), int(a))
                info = await _app_info(cl, src)
                h = ((info or {}).get("common") or {}).get("icon")
                url = f"https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/apps/{src}/{h}.jpg" if h else ""
                if not url:                    # kein Community-Icon -> Kapselbild aus dem Store
                    url = await _store_image(cl, src) or ""
                ic[str(a)] = url
                tv[str(a)] = RESOLVER_V
                tt[str(a)] = time.time()
                if info:
                    _remember_app(a, info)
        store.save(FILE, m)
    return {str(a): (f"/api/appicon/{a}" if ic.get(str(a)) else "") for a in appids}


async def icon_file(appid: int):
    """Icon einmal von Steam holen und im Volume ablegen – danach nur noch lokal ausliefern."""
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    f = ICON_DIR / f"{int(appid)}.jpg"
    if f.exists() and f.stat().st_size > 0:
        return f
    url = (_load().get("_icons") or {}).get(str(appid))
    if not url:
        await icons([int(appid)])
        url = (_load().get("_icons") or {}).get(str(appid))
    if not url:
        return None
    try:
        async with httpx.AsyncClient(timeout=10, headers={"User-Agent": "Spielservermanager"}) as cl:
            r = await cl.get(url)
        if r.status_code == 200 and (r.content[:3] == b"\xff\xd8\xff" or r.content[:4] == b"\x89PNG"):
            f.write_bytes(r.content)
            return f
    except httpx.HTTPError:
        pass
    return None


def app_size(appid) -> int | None:
    return (_load().get("_size") or {}).get(str(appid))


async def ensure_sizes(appids: list[int]) -> None:
    """Fehlende Spielgrößen nachladen (steamcmd-API)."""
    m = _load()
    todo = [a for a in appids if a and str(a) not in (m.get("_size") or {}) and time.time() - _apps_checked.get(a, 0) > 3600]
    if not todo:
        return
    async with httpx.AsyncClient(timeout=8, headers={"User-Agent": "Spielservermanager"}) as cl:
        for a in todo[:10]:
            _apps_checked[a] = time.time()
            info = await _app_info(cl, a)
            if info:
                _remember_app(a, info)
            await asyncio.sleep(0.3)
    store.save(FILE, m)

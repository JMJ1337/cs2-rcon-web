"""Deathmatch-Bestenliste (CS #1): Kills/Tode/Kopfschüsse je Spieler aus dem Server-Log (logaddress_add_http).

Gezählt wird laufend über alle Maps; „heute“ (seit 6 Uhr) und „gesamt“. Bots zählen nicht.
"""
import time
from datetime import datetime

from . import store
from .matchlog import RE_KILL
from .playerdb import _sid64

FILE = "dm_stats.json"
_cache: dict | None = None
_dirty = {"t": 0.0, "n": 0}


def _load() -> dict:
    global _cache
    if _cache is None:
        _cache = store.load(FILE, {"total": {}, "day": {}, "day_key": "", "since": time.time()})
    return _cache


def _day_key() -> str:
    t = time.time() - 6 * 3600          # Tag wechselt um 6 Uhr (LAN-Nächte zählen zum Vortag)
    return datetime.fromtimestamp(t).strftime("%Y-%m-%d")


def _bump(tab: dict, key: str, name: str, k=0, d=0, hs=0) -> None:
    r = tab.setdefault(key, {"name": name, "kills": 0, "deaths": 0, "hs": 0, "last": 0})
    r["name"] = name or r["name"]
    r["kills"] += k
    r["deaths"] += d
    r["hs"] += hs
    r["last"] = time.time()


def ingest(text: str) -> int:
    db = _load()
    if db.get("day_key") != _day_key():
        db["day"], db["day_key"] = {}, _day_key()
    n = 0
    for line in text.splitlines():
        x = RE_KILL.search(line)
        if not x:
            continue
        aid, vid = x.group("aid"), x.group("vid")
        if aid != "BOT" and aid != vid:
            key = _sid64(aid) or aid
            for tab in (db["total"], db["day"]):
                _bump(tab, key, x.group("a"), k=1, hs=1 if x.group("hs") else 0)
        if vid != "BOT":
            key = _sid64(vid) or vid
            for tab in (db["total"], db["day"]):
                _bump(tab, key, x.group("v"), d=1)
        n += 1
    if n:
        _dirty["n"] += n
        if time.time() - _dirty["t"] > 20:
            store.save(FILE, db)
            _dirty.update(t=time.time(), n=0)
    return n


def board(period: str = "day", n: int = 15, names: dict | None = None) -> list[dict]:
    db = _load()
    if period == "day" and db.get("day_key") != _day_key():
        return []
    tab = db["day" if period == "day" else "total"]
    out = []
    for key, r in tab.items():
        if r["kills"] + r["deaths"] < 5:
            continue
        out.append({"steamid": key if key.isdigit() else None, "name": (names or {}).get(key) or r["name"], "kills": r["kills"],
                    "deaths": r["deaths"], "kd": round(r["kills"] / max(1, r["deaths"]), 2),
                    "hs_pct": round(100 * r["hs"] / r["kills"]) if r["kills"] else 0, "last": r["last"]})
    return sorted(out, key=lambda r: (-r["kills"], -r["kd"]))[:n]


def reset() -> None:
    global _cache
    _cache = {"total": {}, "day": {}, "day_key": _day_key(), "since": time.time()}
    store.save(FILE, _cache)

"""Was liegt (vermutlich) noch im Lancache? – Nachbildung der Verdrängung.

Der Lancache (nginx proxy_cache) löscht, sobald CACHE_DISK_SIZE erreicht ist, die am längsten NICHT MEHR
GENUTZTEN Dateien (LRU) – nicht die ältesten. Gelöscht wird still, ohne Logeintrag. Deshalb wird hier aus
dem Verlauf (pro Stunde, pro Depot: aus dem Cache / aus dem Internet) nachgerechnet:

- aus dem Internet geladen  -> liegt danach im Cache (höchstens Spielgröße)
- aus dem Cache geliefert   -> war im Cache (auch Daten von vor Beginn der Aufzeichnung), zählt als „benutzt“
- Summe > Limit             -> die am längsten unbenutzten Spiele werden verdrängt
- „Downloadgröße“ eines Spiels = größter zusammenhängender Download (Prefill lädt nur Windows/Englisch,
  nicht alle Sprachen/DLCs – die Steam-Gesamtgröße wäre zu groß)
"""
import time

from . import cache_history, cache_stats, depots

BURST_H = 6          # Lücke in Stunden, ab der ein neuer Download-Durchgang beginnt
_cache: dict = {"t": 0.0, "data": None}


def _key(depot: str) -> str:
    d = str(depot)
    if d.startswith(("epic:", "bnet:")):
        return d
    e = depots.lookup(d)
    return str(e["app"]) if e else "d" + d


def model(force: bool = False) -> dict:
    if not force and _cache["data"] is not None and time.time() - _cache["t"] < 300:
        return _cache["data"]
    cache_history.load()
    limit = cache_stats.storage.get("limit")
    stored: dict[str, float] = {}
    last: dict[str, int] = {}
    full: dict[str, float] = {}
    burst: dict[str, list] = {}           # app -> [Start-Stunde, letzte Stunde, Bytes]
    evicted: list[dict] = []
    ev_sum: dict[str, float] = {}
    for hour in sorted(cache_history._h):
        dep = (cache_history._h[hour] or {}).get("dep") or {}
        if not dep:
            continue
        per: dict[str, list] = {}
        for d, (h, m) in dep.items():
            p = per.setdefault(_key(d), [0, 0])
            p[0] += h
            p[1] += m
        for k, (h, m) in per.items():
            size = depots.app_size(int(k)) if k.isdigit() else None
            b = burst.get(k)
            if not b or hour - b[1] > BURST_H:
                b = burst[k] = [hour, hour, 0]
            b[1] = hour
            b[2] += h + m
            full[k] = max(full.get(k, 0), b[2])
            cap = min(size, full[k]) if size else full[k]
            cap = max(cap, b[2])
            stored[k] = min(cap, max(stored.get(k, 0) + m, b[2]))
            last[k] = hour
        if limit:
            total = sum(stored.values())
            if total > limit:
                for k in sorted(stored, key=lambda x: last.get(x, 0)):
                    if total <= limit:
                        break
                    if last.get(k) == hour or stored[k] <= 0:
                        continue
                    take = min(stored[k], total - limit)
                    stored[k] -= take
                    total -= take
                    ev_sum[k] = ev_sum.get(k, 0) + take
                    evicted.append({"t": hour * 3600, "key": k, "bytes": take})
    data = {"stored": stored, "last": {k: v * 3600 for k, v in last.items()}, "full": full, "limit": limit,
            "total": sum(stored.values()), "evicted": evicted[-300:], "evicted_sum": ev_sum}
    _cache.update(t=time.time(), data=data)
    return data


def app_state(appid) -> dict:
    """{stored, ref (Downloadgröße), pct, last, evicted} für eine Steam-App."""
    m = model()
    k = str(appid)
    size = depots.app_size(int(appid)) if k.isdigit() else None
    fu = m["full"].get(k) or 0
    ref = fu if fu and (not size or fu < size) else size
    st = m["stored"].get(k, 0)
    return {"stored": round(st), "ref": ref, "steam_size": size,
            "pct": round(min(100.0, st / ref * 100), 1) if ref else None,
            "last": m["last"].get(k), "evicted": round(m["evicted_sum"].get(k, 0))}


def name_of(key: str) -> str:
    if key.isdigit():
        for d in depots.depots_of(int(key)):
            e = depots.lookup(d)
            if e and e.get("name"):
                return e["name"]
        return f"App {key}"
    g = depots.games({key: [0, 1]})
    return g[0]["name"] if g else key


def evictions(n: int = 30) -> list[dict]:
    """Zuletzt verdrängte Spiele (zusammengefasst je Spiel und Tag)."""
    m = model()
    agg: dict = {}
    for e in m["evicted"]:
        day = int(e["t"] // 86400)
        a = agg.setdefault((day, e["key"]), {"t": e["t"], "key": e["key"], "bytes": 0})
        a["bytes"] += e["bytes"]
        a["t"] = max(a["t"], e["t"])
    out = sorted(agg.values(), key=lambda x: -x["t"])[:n]
    for x in out:
        x["bytes"] = round(x["bytes"])
        x["app"] = int(x["key"]) if x["key"].isdigit() else None
        x["name"] = name_of(x["key"])
    return out

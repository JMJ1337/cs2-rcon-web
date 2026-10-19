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
import re
import time

from . import cache_history, cache_stats, depots

OLD = "_alt"          # Daten von vor Beginn der Aufzeichnung (aus der Messung abgeleitet)
BURST_H = 6          # Lücke in Stunden, ab der ein neuer Download-Durchgang beginnt
_cache: dict = {"t": 0.0, "data": None}


def _key(depot: str) -> str:
    d = str(depot)
    if d.startswith(("epic:", "bnet:")):
        return d
    e = depots.lookup(d)
    return str(e["app"]) if e else "d" + d


def _age_h(txt) -> int | None:
    m = re.fullmatch(r"\s*(\d+)\s*([smhdwMy]?)\s*", str(txt or ""))
    if not m:
        return None
    n, u = int(m.group(1)), m.group(2) or "s"
    return max(1, int(n * {"s": 1 / 3600, "m": 1 / 60, "h": 1, "d": 24, "w": 168, "M": 720, "y": 8760}[u]))


def _sim(limit, max_age_h, offset: float = 0.0, until: int | None = None) -> dict:
    stored: dict[str, float] = {}
    last: dict[str, int] = {}
    hours = sorted(h for h in cache_history._h if (cache_history._h[h] or {}).get("dep"))
    if offset > 0 and hours:
        stored[OLD] = offset              # Daten von vor der Aufzeichnung: am längsten unbenutzt -> fliegen zuerst
        last[OLD] = hours[0] - 1
    # Downloadgröße je Depot = Menge im ERSTEN Durchgang dieses Depots (spätere Wiederholungen,
    # z. B. Prefill lädt dasselbe nochmal aus dem Cache, würden sonst doppelt zählen)
    dfirst: dict[str, float] = {}
    dburst: dict[str, int] = {}
    done: set = set()
    evicted: list[dict] = []
    ev_sum: dict[str, float] = {}

    def drop(k, take, hour, why):
        stored[k] -= take
        ev_sum[k] = ev_sum.get(k, 0) + take
        evicted.append({"t": hour * 3600, "key": k, "bytes": take, "why": why})

    for hour in hours + [int(time.time() // 3600)]:
        if until is not None and hour > until:
            break
        dep = (cache_history._h.get(hour) or {}).get("dep") or {}
        per: dict[str, list] = {}
        for d, (h, m) in dep.items():
            d = str(d)
            if d not in done:
                if d in dburst and hour - dburst[d] > BURST_H:
                    done.add(d)
                else:
                    dfirst[d] = dfirst.get(d, 0) + h + m
                    dburst[d] = hour
            p = per.setdefault(_key(d), [0, 0])
            p[0] += h
            p[1] += m
        for k, (h, m) in per.items():
            size = depots.app_size(int(k)) if k.isdigit() else None
            ref = sum(v for d, v in dfirst.items() if _key(d) == k)
            cap = min(size, ref) if size and ref else (ref or size or float("inf"))
            # aus dem Internet -> liegt jetzt im Cache; aus dem Cache -> war (mindestens so viel) da
            stored[k] = min(cap, max(stored.get(k, 0) + m, min(h + m, cap)))
            last[k] = hour
        if max_age_h:                     # CACHE_MAX_AGE: so lange nicht benutzt -> gelöscht
            for k in [k for k, v in stored.items() if v > 0 and hour - last.get(k, hour) > max_age_h]:
                drop(k, stored[k], hour, "abgelaufen")
        if limit:
            total = sum(stored.values())
            if total > limit:
                for k in sorted(stored, key=lambda x: last.get(x, 0)):
                    if total <= limit:
                        break
                    if last.get(k) == hour or stored[k] <= 0:
                        continue
                    take = min(stored[k], total - limit)
                    drop(k, take, hour, "voll")
                    total -= take
    full: dict[str, float] = {}
    for d, v in dfirst.items():
        full[_key(d)] = full.get(_key(d), 0) + v
    return {"stored": stored, "last": last, "full": full, "evicted": evicted, "evicted_sum": ev_sum}


def model(force: bool = False) -> dict:
    if not force and _cache["data"] is not None and time.time() - _cache["t"] < 300:
        return _cache["data"]
    cache_history.load()
    limit = cache_stats.storage.get("limit")
    max_age_h = _age_h(cache_stats.storage.get("max_age"))
    meas, mt = cache_stats.storage.get("cache_bytes"), cache_stats.storage.get("measured")
    offset = 0.0
    if meas and mt:
        # Abgleich mit der echten Messung: was der Verlauf nicht kennt, ist ältere Daten von vor der Aufzeichnung
        at = _sim(limit, max_age_h, 0.0, int(mt // 3600))
        offset = max(0.0, meas - sum(at["stored"].values()))
    r = _sim(limit, max_age_h, offset)
    data = {"stored": r["stored"], "last": {k: v * 3600 for k, v in r["last"].items()}, "full": r["full"], "limit": limit,
            "max_age": cache_stats.storage.get("max_age"), "total": sum(r["stored"].values()), "offset": offset,
            "measured": meas, "measured_at": mt, "evicted": r["evicted"][-300:], "evicted_sum": r["evicted_sum"]}
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
    if key == OLD:
        return "Ältere Daten (von vor Beginn der Aufzeichnung)"
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
        a = agg.setdefault((day, e["key"], e.get("why")), {"t": e["t"], "key": e["key"], "bytes": 0, "why": e.get("why")})
        a["bytes"] += e["bytes"]
        a["t"] = max(a["t"], e["t"])
    out = sorted(agg.values(), key=lambda x: -x["t"])[:n]
    for x in out:
        x["bytes"] = round(x["bytes"])
        x["app"] = int(x["key"]) if x["key"].isdigit() else None
        x["name"] = name_of(x["key"])
    return out

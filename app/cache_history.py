"""Langzeit-Verlauf des Lancache (Stunden-Buckets, bis zu 1 Jahr, im Volume gespeichert)."""
import time
from collections import defaultdict

from . import store

FILE = "cache_history.json"
KEEP_H = 366 * 24
SVC_CAP = 40     # max. Dienste je Stunde
IP_CAP = 30      # max. Clients je Tag

_h: dict[int, dict] = {}          # Stunde -> {hb, mb, hr, mr, svc:{name:[h,m]}}
_ips: dict[int, dict] = {}        # Tag -> {ip: bytes}
_disk: dict[int, dict] = {}       # Tag -> {used,total}
_ipdep: dict[int, dict] = {}      # Tag -> {ip: {depot/spiel: bytes}}  (was hat welcher Client geladen)
meta = {"watermark": 0.0, "bf_cut": None, "bf_done": False, "bf_pos": 0, "bf_size": 0, "bf_lines": 0,
        "bf_error": None, "since": None}
_loaded = False
_dirty = False
_last_save = 0.0


def load():
    global _loaded
    if _loaded:
        return
    raw = store.load(FILE, {})
    for k, v in (raw.get("hours") or {}).items():
        _h[int(k)] = v
    for k, v in (raw.get("ips") or {}).items():
        _ips[int(k)] = v
    for k, v in (raw.get("disk") or {}).items():
        _disk[int(k)] = v
    for k, v in (raw.get("ipdep") or {}).items():
        _ipdep[int(k)] = v
    meta.update(raw.get("meta") or {})
    _loaded = True


DEP_CAP = 120   # max. Depots je Stunde


def add_depot(ts: float, depot: str, size: int, hit: bool) -> None:
    global _dirty
    hour = int(ts // 3600)
    b = _h.setdefault(hour, {"hb": 0, "mb": 0, "hr": 0, "mr": 0, "svc": {}})
    dep = b.setdefault("dep", {})
    e = dep.get(depot)
    if e is None:
        if len(dep) >= DEP_CAP:
            return
        e = dep[depot] = [0, 0]
    e[0 if hit else 1] += size
    _dirty = True


def add(svc: str, ip: str, ts: float, size: int, hit: bool, depot: str | None = None) -> None:
    global _dirty
    hour = int(ts // 3600)
    if depot:
        add_depot(ts, depot, size, hit)
    b = _h.get(hour)
    if b is None:
        b = _h[hour] = {"hb": 0, "mb": 0, "hr": 0, "mr": 0, "svc": {}}
    if hit:
        b["hb"] += size; b["hr"] += 1
    else:
        b["mb"] += size; b["mr"] += 1
    s = b["svc"].get(svc)
    if s is None:
        if len(b["svc"]) >= SVC_CAP:
            svc = "_other"
        s = b["svc"].setdefault(svc, [0, 0])
    s[0 if hit else 1] += size
    day = hour // 24
    d = _ips.setdefault(day, {})
    if ip in d or len(d) < IP_CAP * 4:
        d[ip] = d.get(ip, 0) + size
    if depot:
        dd = _ipdep.setdefault(day, {}).setdefault(ip, {})
        if depot in dd or len(dd) < 60:
            dd[depot] = dd.get(depot, 0) + size
    if meta["since"] is None or ts < meta["since"]:
        meta["since"] = ts
    _dirty = True


def init():
    load()
    if meta["bf_cut"] is None:
        # erster Start: alles bis zur vollen Stunde holt der Rückimport, ab da zählt live
        meta["bf_cut"] = float(int(time.time() // 3600) * 3600)
        meta["watermark"] = meta["bf_cut"]


def live(svc, ip, ts, size, hit, depot=None):
    """Live-Zeilen nur zählen, wenn sie neuer als der gespeicherte Stand sind (keine Doppelzählung nach Neustart)."""
    init()
    if meta.get("dep_cut") is None:
        meta["dep_cut"] = meta["watermark"]     # ältere Depot-Daten holt der Depot-Rückimport
    if ts <= meta["watermark"]:
        return
    add(svc, ip, ts, size, hit, depot)
    meta["watermark_next"] = max(meta.get("watermark_next") or 0, ts)


def commit_watermark():
    if meta.get("watermark_next"):
        meta["watermark"] = max(meta["watermark"], meta.pop("watermark_next"))


def backfill_line(svc, ip, ts, size, hit, depot=None):
    if meta["bf_cut"] is not None and ts < meta["bf_cut"]:
        add(svc, ip, ts, size, hit, depot)


def depot_backfill_line(ts, depot, size, hit):
    if depot and meta.get("dep_cut") is not None and ts <= meta["dep_cut"]:
        add_depot(ts, depot, size, hit)


def reset_backfill():
    """Unvollständiger Rückimport nach Neustart: alte Stunden verwerfen und neu einlesen."""
    cut = meta["bf_cut"]
    if cut is None:
        return
    for k in [k for k in _h if k * 3600 < cut]:
        del _h[k]
    for k in [k for k in _ips if (k + 1) * 86400 <= cut]:
        del _ips[k]
    meta.update(bf_pos=0, bf_lines=0, bf_error=None, since=None)


def reset_all() -> None:
    """Neuer Cache: gesamten Verlauf verwerfen; nichts Älteres mehr aus dem Log nachimportieren."""
    global _dirty
    load()
    now = float(time.time())
    _h.clear(); _ips.clear(); _disk.clear()
    meta.update(watermark=now, bf_cut=now, bf_done=True, bf_pos=0, bf_size=0, bf_lines=0, bf_error=None, since=now,
                dep_cut=now, dbf_done=True, reset_at=now)
    meta.pop("watermark_next", None)
    _dirty = True
    maybe_save(force=True)


def add_net(rx_bytes: float, tx_bytes: float) -> None:
    """Netzwerk des Lancache-Containers (rx = aus dem Internet geholt, tx = an Clients ausgeliefert)."""
    global _dirty
    load()
    hour = int(time.time() // 3600)
    b = _h.setdefault(hour, {"hb": 0, "mb": 0, "hr": 0, "mr": 0, "svc": {}})
    b["rx"] = b.get("rx", 0) + int(rx_bytes)
    b["tx"] = b.get("tx", 0) + int(tx_bytes)
    _dirty = True


def record_disk(disk):
    if disk:
        _disk[int(time.time() // 86400)] = {"used": disk["used"], "total": disk["total"]}


def prune():
    now_h = int(time.time() // 3600)
    for k in [k for k in _h if k < now_h - KEEP_H]:
        del _h[k]
    for k in [k for k in _ips if k < (now_h - KEEP_H) // 24]:
        del _ips[k]
    for k in [k for k in _disk if k < (now_h - KEEP_H) // 24]:
        del _disk[k]
    for k in [k for k in _ipdep if k < (now_h - KEEP_H) // 24]:
        del _ipdep[k]
    # Client-Listen pro Tag klein halten
    for day, d in _ips.items():
        if len(d) > IP_CAP * 4 and day < now_h // 24:
            _ips[day] = dict(sorted(d.items(), key=lambda x: -x[1])[:IP_CAP])


def maybe_save(force=False):
    global _last_save, _dirty
    if not _loaded:
        return
    if force or (_dirty and time.time() - _last_save > 300):
        prune()
        store.save(FILE, {"hours": {str(k): v for k, v in _h.items()}, "ips": {str(k): v for k, v in _ips.items()},
                          "disk": {str(k): v for k, v in _disk.items()},
                          "ipdep": {str(k): v for k, v in _ipdep.items()}, "meta": meta})
        _last_save = time.time()
        _dirty = False


RANGES = {"24h": (24, 1), "7d": (7 * 24, 6), "30d": (30 * 24, 24), "90d": (90 * 24, 24), "365d": (365 * 24, 24 * 7)}


def series(rng: str) -> dict:
    load()
    hours, step = RANGES.get(rng, RANGES["30d"])
    now_h = int(time.time() // 3600)
    first = now_h - hours + 1
    first -= (first - (first // step) * step) if step > 1 else 0   # an Bucket-Grenzen ausrichten
    pts = []
    tot = {"hit": 0, "miss": 0, "req": 0}
    svc = defaultdict(lambda: [0, 0])
    peak_h, peak_v = None, 0
    h = first
    while h <= now_h:
        hb = mb = rx = tx = 0
        has_net = False
        psvc: dict = {}
        for x in range(h, min(h + step, now_h + 1)):
            b = _h.get(x)
            if not b:
                continue
            hb += b["hb"]; mb += b["mb"]
            if "rx" in b:
                has_net = True
                rx += b["rx"]; tx += b["tx"]
            tot["req"] += b["hr"] + b["mr"]
            for s, (a, m) in b["svc"].items():
                svc[s][0] += a; svc[s][1] += m
                ps = psvc.setdefault(s, [0, 0]); ps[0] += a; ps[1] += m
            if b["hb"] + b["mb"] > peak_v:
                peak_v, peak_h = b["hb"] + b["mb"], x
        tot["hit"] += hb; tot["miss"] += mb
        pts.append({"t": h * 3600, "hit": hb, "miss": mb, "rx": rx if has_net else None, "tx": tx if has_net else None,
                    "svc": psvc})
        h += step
    deps = defaultdict(lambda: [0, 0])
    for x in range(first, now_h + 1):
        for dpt, (a, m) in ((_h.get(x) or {}).get("dep") or {}).items():
            deps[dpt][0] += a; deps[dpt][1] += m
    ips = defaultdict(int)
    for day, d in _ips.items():
        if day * 24 + 23 >= first:
            for ip, v in d.items():
                ips[ip] += v
    ipdep: dict = defaultdict(lambda: defaultdict(int))
    for day, d in _ipdep.items():
        if day * 24 + 23 >= first:
            for ip, idep in d.items():
                for dp, v in idep.items():
                    ipdep[ip][dp] += v
    disk = [{"t": d * 86400, **v} for d, v in sorted(_disk.items()) if d * 24 + 23 >= first]
    total = tot["hit"] + tot["miss"]
    days = max(1, hours / 24)
    return {
        "range": rng, "step_h": step, "points": pts,
        "hit_bytes": tot["hit"], "miss_bytes": tot["miss"], "requests": tot["req"],
        "hit_ratio": round(tot["hit"] / total * 100, 1) if total else None,
        "per_day": round(total / days),
        "peak": {"t": peak_h * 3600 if peak_h is not None else None, "bytes": peak_v, "bps": round(peak_v / 3600)},
        "services": sorted(({"name": s, "hit": a, "miss": m} for s, (a, m) in svc.items()),
                           key=lambda x: -(x["hit"] + x["miss"]))[:15],
        "clients": sorted(({"ip": ip, "bytes": v, "deps": dict(ipdep.get(ip) or {})} for ip, v in ips.items()), key=lambda x: -x["bytes"])[:25],
        "depots": {d: v for d, v in deps.items()},
        "disk": disk,
        "since": meta.get("since"),
        "backfill": {"done": meta["bf_done"], "pos": meta["bf_pos"], "size": meta["bf_size"],
                     "lines": meta["bf_lines"], "error": meta["bf_error"]},
        "depot_backfill": {"done": meta.get("dbf_done", False), "pos": meta.get("dbf_pos", 0), "size": meta.get("dbf_size", 0)},
    }

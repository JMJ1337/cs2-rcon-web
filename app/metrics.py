"""Verlaufs-Metriken je Spielserver (Minutenwerte, 24 h, im Volume gespeichert)."""
import time

from . import store

FILE = "metrics.json"
KEEP = 24 * 60
_series: dict[str, dict[int, dict]] = {}   # server_id -> minute -> Punkt
_loaded = False
_last_save = 0.0


def _load():
    global _loaded
    if _loaded:
        return
    raw = store.load(FILE, {})
    for sid, pts in raw.items():
        _series[sid] = {int(k): v for k, v in pts.items()}
    _loaded = True


def record(sid: str, state: dict, load: dict | None) -> None:
    """Wird alle ~10 s aufgerufen; pro Minute wird ein Punkt verdichtet."""
    _load()
    minute = int(time.time() // 60)
    s = _series.setdefault(sid, {})
    p = s.get(minute)
    online = bool(state.get("online"))
    players = int(state.get("humans") or 0) if online else 0
    pings = [pl.get("ping") for pl in state.get("players") or [] if not pl.get("bot") and isinstance(pl.get("ping"), int)]
    cpu = (load or {}).get("cpu_host") if (load or {}).get("state") == "running" else None
    mem = (load or {}).get("mem_mb") if (load or {}).get("state") == "running" else None
    if p is None:
        p = s[minute] = {"pl": players, "on": 1 if online else 0, "n": 1, "cpu": cpu, "mem": mem,
                         "ping": round(sum(pings) / len(pings)) if pings else None}
    else:
        p["pl"] = max(p["pl"], players)
        p["on"] = p["on"] + (1 if online else 0)
        p["n"] += 1
        if cpu is not None:
            p["cpu"] = round(((p["cpu"] or 0) * (p["n"] - 1) + cpu) / p["n"], 1) if p["cpu"] is not None else cpu
        if mem is not None:
            p["mem"] = mem
        if pings:
            p["ping"] = round(sum(pings) / len(pings))
    cutoff = minute - KEEP
    for k in [k for k in s if k < cutoff]:
        del s[k]


def record_host(cpu, mem_used_mb, mem_total_mb) -> None:
    """Gesamtlast des Hosts als eigene Reihe '_host' (cpu = %, mem = % belegt)."""
    _load()
    if cpu is None or not mem_total_mb:
        return
    minute = int(time.time() // 60)
    s = _series.setdefault("_host", {})
    mem_pct = round(mem_used_mb / mem_total_mb * 100, 1)
    p = s.get(minute)
    if p is None:
        s[minute] = {"pl": 0, "on": 1, "n": 1, "cpu": cpu, "mem": mem_pct, "cpu_max": cpu}
    else:
        p["n"] += 1
        p["cpu"] = round((p["cpu"] * (p["n"] - 1) + cpu) / p["n"], 1)
        p["cpu_max"] = max(p.get("cpu_max", cpu), cpu)
        p["mem"] = mem_pct
    for k in [k for k in s if k < minute - KEEP]:
        del s[k]


def forget(valid_ids: set[str]) -> None:
    valid_ids = set(valid_ids) | {"_host"}
    for sid in [k for k in _series if k not in valid_ids]:
        del _series[sid]


def maybe_save(force=False) -> None:
    global _last_save
    if force or time.time() - _last_save > 300:
        store.save(FILE, {sid: {str(k): v for k, v in pts.items()} for sid, pts in _series.items()})
        _last_save = time.time()


def summary(sid: str, minutes: int = 360, buckets: int = 72) -> dict:
    """Downsampling auf `buckets` Werte + Kennzahlen."""
    _load()
    pts = _series.get(sid, {})
    now = int(time.time() // 60)
    step = max(1, minutes // buckets)
    players, cpu, mem = [], [], []
    for b in range(buckets):
        start = now - minutes + 1 + b * step
        seg = [pts[m] for m in range(start, start + step) if m in pts]
        players.append(max((x["pl"] for x in seg), default=None) if seg else None)
        c = [x["cpu"] for x in seg if x.get("cpu") is not None]
        cpu.append(round(sum(c) / len(c), 1) if c else None)
        r = [x["mem"] for x in seg if x.get("mem") is not None]
        mem.append(r[-1] if r else None)
    day = [pts[m] for m in range(now - KEEP, now + 1) if m in pts]
    up = round(sum(x["on"] / x["n"] for x in day) / len(day) * 100, 1) if day else None
    peak = max((x["pl"] for x in day), default=0)
    pings = [x["ping"] for x in day[-30:] if x.get("ping") is not None]
    return {"players": players, "cpu": cpu, "mem": mem, "step_min": step, "minutes": minutes,
            "peak_24h": peak, "uptime_24h": up, "ping": round(sum(pings) / len(pings)) if pings else None,
            "samples": len(day)}

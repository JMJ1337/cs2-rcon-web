"""Lancache-Metriken aus dem access.log des monolithic-Containers (per docker exec, inkrementell)."""
import json
import re
import time
from collections import defaultdict
from datetime import datetime

import asyncio

from . import cache_history, docker_api

LOG = "/data/logs/access.log"
MAX_READ = 20_000_000          # max. Bytes pro Abruf
FIRST_READ = 5_000_000         # beim Start: letzte 5 MB
KEEP_MIN = 24 * 60             # Minuten-Buckets für 24 h

RE_LINE = re.compile(
    r'^\[(?P<svc>[^\]]*)\] (?P<ip>\S+) / \S+ - \S+ \[(?P<t>[^\]]+)\] "(?P<req>[^"]*)" (?P<st>\d{3}) (?P<b>\d+) '
    r'"[^"]*" "[^"]*" "(?P<cache>[^"]*)" "(?P<host>[^"]*)"')

state = {"container": None, "offset": 0, "buckets": {}, "disk": None, "error": None, "updated": None,
         "detected": False}


def _bucket(minute):
    b = state["buckets"].get(minute)
    if b is None:
        b = state["buckets"][minute] = {"hit_b": 0, "miss_b": 0, "hit": 0, "miss": 0,
                                        "svc": defaultdict(lambda: [0, 0]), "ip": defaultdict(int)}
    return b


def _parse(line: str):
    line = line.strip()
    if not line:
        return None
    if line.startswith("{"):
        try:
            j = json.loads(line)
            return (j.get("cache_identifier", "?"), j.get("remote_addr", "?"), float(j.get("timestamp", 0)),
                    int(j.get("bytes_sent") or 0), j.get("upstream_cache_status", ""))
        except (ValueError, TypeError):
            return None
    m = RE_LINE.match(line)
    if not m:
        return None
    try:
        ts = datetime.strptime(m.group("t"), "%d/%b/%Y:%H:%M:%S %z").timestamp()
    except ValueError:
        return None
    return m.group("svc"), m.group("ip"), ts, int(m.group("b")), m.group("cache")


def ingest(text: str) -> int:
    n = 0
    for line in text.splitlines():
        p = _parse(line)
        if not p:
            continue
        svc, ip, ts, size, cache = p
        hit = cache == "HIT"
        if hit or cache in ("MISS", "EXPIRED", "STALE", "UPDATING", "REVALIDATED", "BYPASS"):
            cache_history.live(svc, ip, ts, size, hit)
        b = _bucket(int(ts // 60))
        if cache == "HIT":
            b["hit_b"] += size; b["hit"] += 1; b["svc"][svc][0] += size
        elif cache in ("MISS", "EXPIRED", "STALE", "UPDATING", "REVALIDATED", "BYPASS"):
            b["miss_b"] += size; b["miss"] += 1; b["svc"][svc][1] += size
        else:
            continue
        b["ip"][ip] += size
        n += 1
    cache_history.commit_watermark()
    cutoff = int(time.time() // 60) - KEEP_MIN
    for k in [k for k in state["buckets"] if k < cutoff]:
        del state["buckets"][k]
    return n


async def detect(preferred: str = "") -> str | None:
    if preferred:
        return preferred
    for c in await docker_api.list_containers():
        img, name = (c["image"] or "").lower(), c["name"].lower()
        if "monolithic" in img or ("lancache" in name and "dns" not in name and "dns" not in img):
            return c["name"]
    return None


async def poll(preferred: str = "") -> None:
    if not docker_api.available():
        state["error"] = "Docker-Socket nicht eingebunden"
        return
    try:
        name = await detect(preferred)
        state["detected"] = bool(name)
        if not name:
            state["error"] = "Kein Lancache-Container gefunden (Image lancachenet/monolithic)"
            return
        if name != state["container"]:
            state.update(container=name, offset=0, buckets={})
        size_out = (await docker_api.exec_cmd(name, ["stat", "-c", "%s", LOG])).strip()
        size = int(size_out) if size_out.isdigit() else 0
        if size < state["offset"]:          # Log rotiert
            state["offset"] = 0
        first = state["offset"] == 0
        start = max(0, size - FIRST_READ) if first else state["offset"]
        if size > start:
            length = min(size - start, MAX_READ)
            data = await docker_api.exec_cmd(name, ["sh", "-c", f"tail -c +{start + 1} {LOG} | head -c {length}"])
            raw = data.encode("utf-8", "replace")
            end = raw.rfind(b"\n") + 1            # nur vollständige Zeilen
            begin = 0
            if first and start > 0:                 # erste Zeile ist evtl. angeschnitten
                begin = raw.find(b"\n") + 1
            if end > begin:
                ingest(raw[begin:end].decode("utf-8", "replace"))
            state["offset"] = start + end if end > 0 else start
        df = (await docker_api.exec_cmd(name, ["df", "-B1", "-P", "/data/cache"])).strip().splitlines()
        if len(df) >= 2:
            parts = df[-1].split()
            state["disk"] = {"total": int(parts[1]), "used": int(parts[2]), "free": int(parts[3])}
            cache_history.record_disk(state["disk"])
        state["error"] = None
        state["updated"] = time.time()
    except (docker_api.DockerError, ValueError, IndexError) as e:
        state["error"] = str(e)


def summary() -> dict:
    now_min = int(time.time() // 60)

    def agg(minutes):
        hit_b = miss_b = hit = miss = 0
        svc = defaultdict(lambda: [0, 0])
        ips = defaultdict(int)
        for k, b in state["buckets"].items():
            if k >= now_min - minutes:
                hit_b += b["hit_b"]; miss_b += b["miss_b"]; hit += b["hit"]; miss += b["miss"]
                for s, (h, m) in b["svc"].items():
                    svc[s][0] += h; svc[s][1] += m
                for ip, v in b["ip"].items():
                    ips[ip] += v
        total = hit_b + miss_b
        return {
            "hit_bytes": hit_b, "miss_bytes": miss_b, "requests": hit + miss,
            "hit_ratio": round(hit_b / total * 100, 1) if total else None,
            "services": sorted(({"name": s, "hit": h, "miss": m} for s, (h, m) in svc.items()),
                               key=lambda x: -(x["hit"] + x["miss"]))[:6],
            "clients": sorted(({"ip": ip, "bytes": v} for ip, v in ips.items()), key=lambda x: -x["bytes"])[:5],
        }

    last2 = [state["buckets"].get(now_min - i) for i in (1, 2)]
    rate = sum((b["hit_b"] + b["miss_b"]) for b in last2 if b) / 120
    hit_rate = sum(b["hit_b"] for b in last2 if b) / 120
    return {"container": state["container"], "error": state["error"], "updated": state["updated"],
            "disk": state["disk"], "rate_bps": round(rate), "hit_rate_bps": round(hit_rate),
            "last_hour": agg(60), "last_day": agg(KEEP_MIN)}


BF_CHUNK = 16_000_000
_bf_running = False


async def backfill() -> None:
    """Einmaliger Rückimport des kompletten access.log in den Langzeit-Verlauf (läuft im Hintergrund, setzt nach Neustart fort)."""
    global _bf_running
    cache_history.init()
    m = cache_history.meta
    name = state["container"]
    if _bf_running or m["bf_done"] or not name or m["bf_cut"] is None:
        return
    _bf_running = True
    try:
        size_out = (await docker_api.exec_cmd(name, ["stat", "-c", "%s", LOG])).strip()
        size = int(size_out) if size_out.isdigit() else 0
        if not m["bf_size"]:
            m["bf_size"] = size
        if size < m["bf_pos"]:            # Log wurde inzwischen rotiert -> Rest ist weg
            m.update(bf_done=True, bf_error="access.log wurde rotiert – Rückimport unvollständig")
            return
        while m["bf_pos"] < m["bf_size"]:
            length = min(BF_CHUNK, m["bf_size"] - m["bf_pos"])
            data = await docker_api.exec_cmd(name, ["sh", "-c", f"tail -c +{m['bf_pos'] + 1} {LOG} | head -c {length}"])
            raw = data.encode("utf-8", "replace")
            end = raw.rfind(b"\n") + 1
            if end <= 0:
                if length < BF_CHUNK:      # letzter Rest ohne Zeilenende
                    break
                end = len(raw)
            n = 0
            for line in raw[:end].decode("utf-8", "replace").splitlines():
                p = _parse(line)
                if not p:
                    continue
                svc, ip, ts, sz, cache = p
                hit = cache == "HIT"
                if hit or cache in ("MISS", "EXPIRED", "STALE", "UPDATING", "REVALIDATED", "BYPASS"):
                    cache_history.backfill_line(svc, ip, ts, sz, hit)
                    n += 1
            m["bf_pos"] += end
            m["bf_lines"] += n
            cache_history.maybe_save()
            await asyncio.sleep(0.2)
        m["bf_done"] = True
        cache_history.maybe_save(force=True)
    except (docker_api.DockerError, ValueError) as e:
        m["bf_error"] = str(e)
    finally:
        _bf_running = False

"""Lancache-Metriken aus dem access.log des monolithic-Containers (per docker exec, inkrementell)."""
import json
import re
import time
from collections import defaultdict
from datetime import datetime

import asyncio

from . import cache_history, docker_api, store, timings

LOG = "/data/logs/access.log"
MAX_READ = 20_000_000          # max. Bytes pro Abruf
FIRST_READ = 5_000_000         # beim Start: letzte 5 MB
KEEP_MIN = 24 * 60             # Minuten-Buckets für 24 h

RE_LINE = re.compile(
    r'^\[(?P<svc>[^\]]*)\] (?P<ip>\S+) / \S+ - \S+ \[(?P<t>[^\]]+)\] "(?P<req>[^"]*)" (?P<st>\d{3}) (?P<b>\d+) '
    r'"[^"]*" "[^"]*" "(?P<cache>[^"]*)" "(?P<host>[^"]*)"')

from collections import deque
_recent: deque = deque()        # (Zeitstempel, Bytes, Treffer) der letzten 2 Minuten für den Live-Durchsatz

storage = {"measured": None, "cache_bytes": None, "logs": [], "limit": None, "max_age": None, "updated": None, "running": False, "error": None}

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


RE_DEPOT = re.compile(r'"[A-Z]+ /depot/(\d+)/')


RE_EPIC = re.compile(r'"[A-Z]+ /Builds/(?:Org/(o-[a-z0-9]+)/([A-Za-z0-9]+)|([A-Za-z0-9_\-]+))/')
RE_BNET = re.compile(r'"[A-Z]+ /tpr/([A-Za-z0-9_\-]+)/')


def depot_of(line: str, svc: str) -> str | None:
    """Steam: Depot-ID · Epic: epic:<Spiel> · Battle.net: bnet:<CDN-Pfad> (Spiel aus der Download-Adresse)."""
    if svc == "steam":
        m = RE_DEPOT.search(line)
        return m.group(1) if m else None
    if svc == "epicgames":
        m = RE_EPIC.search(line)
        if m:
            return f"epic:{m.group(3) or m.group(2)}"
        return None
    if svc == "blizzard":
        m = RE_BNET.search(line)
        return f"bnet:{m.group(1).lower()}" if m else None
    return None


def ingest(text: str) -> int:
    n = 0
    for line in text.splitlines():
        p = _parse(line)
        if not p:
            continue
        svc, ip, ts, size, cache = p
        hit = cache == "HIT"
        if hit or cache in ("MISS", "EXPIRED", "STALE", "UPDATING", "REVALIDATED", "BYPASS"):
            cache_history.live(svc, ip, ts, size, hit, depot_of(line, svc))
        if ts > time.time() - 120:
            _recent.append((ts, size, hit, ip, svc, depot_of(line, svc)))
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


async def reset() -> None:
    """Live-Zähler leeren und das Zugriffslog des Lancache leeren (alte Einträge gehören zum alten Cache)."""
    name = state.get("container")
    state.update(offset=0, buckets={})
    _recent.clear()
    if name:
        await docker_api.exec_cmd(name, ["sh", "-c", f": > {LOG}"])
    storage.update(measured=None, cache_bytes=None, updated=None)


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

    cut = time.time() - 60
    while _recent and _recent[0][0] < time.time() - 120:
        _recent.popleft()
    win = [x for x in _recent if x[0] >= cut]
    per_ip: dict = {}
    for x in win:
        per_ip[x[3]] = per_ip.get(x[3], 0) + x[1]
    live_clients = sorted(({"ip": k, "bps": round(v / 60)} for k, v in per_ip.items()), key=lambda c: -c["bps"])[:5]
    # Was wird gerade geladen? (Client + Spiel, letzte 60 s) – aus den ohnehin gelesenen Log-Zeilen, kein Mehraufwand
    from . import depots
    grp: dict = {}
    for x in win:
        if str(x[3]).startswith("127.") or x[3] in ("::1", "localhost"):   # Heartbeat/Healthcheck
            continue
        dep = x[5] if len(x) > 5 else None
        e = depots.lookup(dep) if dep else None
        key = (x[3], x[4] if len(x) > 4 else "?", e["app"] if e else (f"d{dep}" if dep else ""))
        g = grp.setdefault(key, {"ip": x[3], "service": key[1], "app": e["app"] if e else None,
                                 "name": (e or {}).get("name") or (f"Depot {dep}" if dep else None), "bytes": 0, "hit": 0})
        g["bytes"] += x[1]
        if x[2]:
            g["hit"] += x[1]
        if dep and not e:
            depots.want([dep])
    live_downloads = sorted(({**g, "bps": round(g["bytes"] / 60), "hit_pct": round(g["hit"] / g["bytes"] * 100) if g["bytes"] else None}
                             for g in grp.values() if g["bytes"] >= 256 * 1024), key=lambda g: -g["bytes"])[:12]
    rate = sum(x[1] for x in win) / 60
    hit_rate = sum(x[1] for x in win if x[2]) / 60
    return {"container": state["container"], "error": state["error"], "updated": state["updated"],
            "disk": state["disk"], "storage": {k: v for k, v in storage.items() if k != "running"} | {"busy": storage["running"]}, "rate_bps": round(rate), "hit_rate_bps": round(hit_rate), "live_clients": live_clients, "live_downloads": live_downloads,
            "last_5m": agg(5), "last_hour": agg(60), "last_day": agg(KEEP_MIN)}


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
                    cache_history.backfill_line(svc, ip, ts, sz, hit, depot_of(line, svc))
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


async def tail(lines: int = 40) -> str:
    if not state["container"]:
        return ""
    return await docker_api.exec_cmd(state["container"], ["tail", "-n", str(max(1, min(lines, 200))), LOG])


def _size(txt: str) -> int | None:
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*([kmgtp]?)", (txt or "").lower())
    if not m:
        return None
    return int(float(m.group(1)) * {"": 1, "k": 1e3, "m": 1e6, "g": 1e9, "t": 1e12, "p": 1e15}[m.group(2)])


DU_OUT = "/tmp/gsm_cache_du.out"
# Läuft losgelöst IM Lancache-Container weiter (auch wenn das Tool neu startet) und schreibt Fortschritt in DU_OUT:
# TOTAL <Ordner> · D <Bytes bisher> je fertigem Ordner · END <Bytes>
DU_SH = (
    "cd /data/cache/cache 2>/dev/null || cd /data/cache || exit 1; "
    "set -- */; echo \"TOTAL $#\"; T=0; "
    "P=''; command -v ionice >/dev/null && P='ionice -c3'; "
    "for d in \"$@\"; do b=$($P nice -n19 du -sb \"$d\" 2>/dev/null | cut -f1); T=$((T+${b:-0})); echo \"D $T\"; done; "
    "F=$(find . -maxdepth 1 -type f -printf '%s\\n' 2>/dev/null | awk '{s+=$1} END {print s+0}'); "
    "echo \"END $((T+F))\""
)


def _load_saved() -> None:
    d = store.load("cache_storage.json", {})
    for k in ("measured", "cache_bytes", "method", "fs"):
        if d.get(k) is not None and storage.get(k) is None:
            storage[k] = d[k]


def _save_measure() -> None:
    store.save("cache_storage.json", {k: storage.get(k) for k in ("measured", "cache_bytes", "method", "fs")})


async def poll_storage(full: bool = False) -> None:
    """Log-Dateien messen und die Belegung des Cache-Dateisystems (df, sofort). full = zusätzlich genau zählen (du,
    losgelöst im Lancache-Container mit Fortschritt – kann bei vielen Dateien lange dauern)."""
    _load_saved()
    name = state["container"]
    if not name or storage["running"]:
        return
    storage["running"] = True
    try:
        info = await docker_api.inspect(name)
        env = dict(e.split("=", 1) for e in (info.get("Config", {}).get("Env") or []) if "=" in e)
        storage["limit"] = _size(env.get("CACHE_DISK_SIZE", "")) if env.get("CACHE_DISK_SIZE") else None
        storage["limit_raw"] = env.get("CACHE_DISK_SIZE")
        storage["max_age"] = env.get("CACHE_MAX_AGE")
        cmd = ("for f in /data/logs/*; do [ -f \"$f\" ] && echo \"$(stat -c %s \"$f\")\t$f\"; done; echo '#DF'; "
               "df -B1 -P /data/cache 2>/dev/null | tail -1")
        out = await docker_api.exec_cmd(name, ["sh", "-c", cmd], timeout=30)
        logs_part, _, df_part = out.partition("#DF")
        logs = []
        for line in logs_part.splitlines():
            p = line.split("\t", 1)
            if len(p) == 2 and p[0].strip().isdigit():
                logs.append({"name": p[1].strip().rsplit("/", 1)[-1], "bytes": int(p[0])})
        storage["logs"] = sorted(logs, key=lambda x: -x["bytes"])
        f = df_part.split()
        if len(f) >= 6 and f[2].isdigit():
            storage["fs"] = {"total": int(f[1]), "used": int(f[2]), "free": int(f[3]), "mount": f[5], "t": time.time()}
            if full or storage.get("method") != "du":
                # eigenes Dateisystem für den Cache (z. B. iSCSI-LUN) -> „belegt“ ist praktisch die Cache-Größe
                storage.update(cache_bytes=int(f[2]), measured=time.time(), method="df")
                _save_measure()
        if full:
            await du_start(name)
        storage["updated"] = time.time()
        storage["error"] = None
    except (docker_api.DockerError, ValueError) as e:
        storage["error"] = str(e)
        storage["updated"] = time.time()
    finally:
        storage["running"] = False


async def du_start(name: str) -> None:
    """Genaues Zählen losgelöst starten (läuft im Lancache-Container weiter)."""
    st = await du_status(name)
    if st and st.get("active"):
        return
    body = {"Cmd": ["sh", "-c", f"( {DU_SH} ) > {DU_OUT}.tmp 2>&1; mv {DU_OUT}.tmp {DU_OUT}"], "AttachStdout": False, "AttachStderr": False}
    e = (await docker_api._req("POST", f"/containers/{name}/exec", json=body)).json()
    await docker_api._req("POST", f"/exec/{e['Id']}/start", json={"Detach": True, "Tty": False})
    storage["du"] = {"active": True, "done": 0, "total": None, "bytes": 0, "started": time.time(), "changed": time.time()}


async def du_status(name: str | None = None) -> dict | None:
    """Fortschritt des genauen Zählens lesen; ist es fertig, Ergebnis übernehmen."""
    name = name or state["container"]
    if not name:
        return None
    try:
        out = await docker_api.exec_cmd(name, ["sh", "-c", f"cat {DU_OUT}.tmp 2>/dev/null || (echo '#FINAL'; cat {DU_OUT} 2>/dev/null)"], timeout=15)
    except docker_api.DockerError:
        return storage.get("du")
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    final = bool(lines) and lines[0] == "#FINAL"
    total = next((int(ln.split()[1]) for ln in lines if ln.startswith("TOTAL ") and ln.split()[1].isdigit()), None)
    ds = [int(ln.split()[1]) for ln in lines if ln.startswith("D ") and ln.split()[1].isdigit()]
    end = next((int(ln.split()[1]) for ln in lines if ln.startswith("END ") and ln.split()[1].isdigit()), None)
    prev = storage.get("du") or {}
    if final:
        if end is not None:
            done_t = prev.get("finished") or time.time()
            if prev.get("active") or storage.get("method") != "du" or not storage.get("measured"):
                storage.update(cache_bytes=end, measured=done_t, method="du")
                _save_measure()
                if prev.get("active") and prev.get("started"):
                    timings.record("cache_measure", "full", done_t - prev["started"])
            storage["du"] = {"active": False, "done": total, "total": total, "bytes": end, "finished": done_t,
                             "started": prev.get("started")}
        else:
            storage["du"] = {**prev, "active": False}
        return storage["du"]
    if total is None and not ds:
        storage["du"] = {**prev, "active": False} if not lines else prev
        return storage["du"]
    changed = prev.get("changed") or time.time()
    if len(ds) != prev.get("done"):
        changed = time.time()
    storage["du"] = {"active": True, "done": len(ds), "total": total, "bytes": ds[-1] if ds else 0,
                     "started": prev.get("started") or time.time(), "changed": changed,
                     "stalled": time.time() - changed > 1800}
    return storage["du"]


_dbf_running = False


async def backfill_depots() -> None:
    """Einmalig: Steam-Depots (= welches Spiel) aus dem alten access.log nachtragen."""
    global _dbf_running
    cache_history.init()
    m = cache_history.meta
    name = state["container"]
    if _dbf_running or m.get("dbf_done") or not name or m.get("dep_cut") is None:
        return
    _dbf_running = True
    try:
        size_out = (await docker_api.exec_cmd(name, ["stat", "-c", "%s", LOG])).strip()
        size = int(size_out) if size_out.isdigit() else 0
        m.setdefault("dbf_pos", 0)
        if not m.get("dbf_size"):
            m["dbf_size"] = size
        if size < m["dbf_pos"]:
            m["dbf_done"] = True
            return
        while m["dbf_pos"] < m["dbf_size"]:
            length = min(BF_CHUNK, m["dbf_size"] - m["dbf_pos"])
            data = await docker_api.exec_cmd(name, ["sh", "-c", f"tail -c +{m['dbf_pos'] + 1} {LOG} | head -c {length} | grep '/depot/' ; echo '#END'"])
            # grep liefert nur Steam-Depot-Zeilen; Position über die gelesene Länge (Zeilengrenze am Ende ignorieren)
            for line in data.splitlines():
                if line.startswith("#END"):
                    continue
                p = _parse(line)
                if not p:
                    continue
                svc, ip, ts, sz, cache = p
                hit = cache == "HIT"
                if hit or cache in ("MISS", "EXPIRED", "STALE", "UPDATING", "REVALIDATED", "BYPASS"):
                    cache_history.depot_backfill_line(ts, depot_of(line, svc), sz, hit)
            m["dbf_pos"] += length
            cache_history.maybe_save()
            await asyncio.sleep(0.1)
        m["dbf_done"] = True
        cache_history.maybe_save(force=True)
    except (docker_api.DockerError, ValueError):
        pass
    finally:
        _dbf_running = False

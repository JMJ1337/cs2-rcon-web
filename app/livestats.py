"""Live-Messung im Sekundentakt.

- Container: dauerhafter Docker-Stats-Stream je Container (Docker liefert ~1 Wert/s mit eigenem Zeitstempel).
  Raten werden aus den Zählern und den Docker-Zeitstempeln berechnet -> keine Abweichung durch Abfragedauer.
- Host-Netz: echte Netzwerkkarten des Docker-Hosts aus /host/proc/1/net/dev (Stack: /proc:/host/proc:ro).
  Ohne diesen Mount: Summe der Container.
- Ringpuffer (10 min, 1 s) für die Live-Diagramme.
"""
import asyncio
import json
import os
import re
import time
from collections import deque
from datetime import datetime

from . import docker_api, hoststats

HOST_NET = os.getenv("HOST_NET_DEV", "/host/proc/1/net/dev")
KEEP = 600

data: dict[str, dict] = {}            # Container -> letzter Wert
rings: dict[str, deque] = {}          # Container / "_host" -> (t, cpu, mem, rx, tx)
_tasks: dict[str, asyncio.Task] = {}
_host_prev: tuple[float, int, int] | None = None
host: dict = {"rx_bps": None, "tx_bps": None, "source": None, "ifaces": [], "nic_rx_bps": None, "nic_tx_bps": None}
cache_name: str | None = None          # Lancache-Container: sein Upload geht an die LAN-Clients, nicht ins Internet
_pk: dict[int, dict] = {}              # Minute -> Höchstwerte (für die Balken-Skala: Max der letzten 24 h)


def _peak(key: str, v) -> None:
    if v is None:
        return
    m = int(time.time() // 60)
    b = _pk.setdefault(m, {})
    if v > b.get(key, 0):
        b[key] = v
    if len(_pk) > 1445:
        for k in [k for k in _pk if k < m - 1440]:
            del _pk[k]


def peak24() -> dict:
    out: dict = {}
    for b in _pk.values():
        for k, v in b.items():
            if v > out.get(k, 0):
                out[k] = v
    return out


LAN_ONLY = {"steamprefill", "bnetprefill", "epicprefill"}   # Prefill lädt vom Lancache (LAN)


def _ts(s: str) -> float | None:
    m = re.match(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d+))?", s or "")
    if not m or s.startswith("0001"):
        return None
    t = datetime.fromisoformat(m.group(1) + "+00:00").timestamp()
    return t + (float("0." + m.group(2)) if m.group(2) else 0.0)


def _ring(key: str) -> deque:
    r = rings.get(key)
    if r is None:
        r = rings[key] = deque(maxlen=KEEP)
    return r


WIN = 4.0   # Sekunden: Rate über ein gleitendes Fenster (Docker liefert Netzwerkzähler teils verzögert/doppelt)


async def _stream(name: str):
    prev = None
    hist: deque = deque()
    while True:
        try:
            async with docker_api._client(timeout=None) as cl:
                async with cl.stream("GET", f"/containers/{name}/stats", params={"stream": "1"}) as r:
                    if r.status_code >= 400:
                        raise docker_api.DockerError(f"Stats {r.status_code}")
                    async for line in r.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            s = json.loads(line)
                        except ValueError:
                            continue
                        t = _ts(s.get("read")) or time.time()
                        cpu = s.get("cpu_stats") or {}
                        pre = s.get("precpu_stats") or {}
                        cpu_pct = None
                        try:
                            d_cpu = cpu["cpu_usage"]["total_usage"] - pre["cpu_usage"]["total_usage"]
                            d_sys = cpu["system_cpu_usage"] - pre["system_cpu_usage"]
                            ncpu = cpu.get("online_cpus") or len(cpu["cpu_usage"].get("percpu_usage") or [1])
                            cpu_pct = round(d_cpu / d_sys * ncpu * 100, 1) if d_sys > 0 else 0.0
                        except (KeyError, TypeError):
                            pass
                        mem = s.get("memory_stats") or {}
                        used = (mem.get("usage") or 0) - ((mem.get("stats") or {}).get("inactive_file") or 0)
                        nets = s.get("networks")
                        rx = sum((n or {}).get("rx_bytes", 0) for n in nets.values()) if nets else None
                        tx = sum((n or {}).get("tx_bytes", 0) for n in nets.values()) if nets else None
                        rx_bps = tx_bps = None
                        if rx is not None:
                            hist.append((t, rx, tx))
                            while len(hist) > 2 and t - hist[1][0] >= WIN:
                                hist.popleft()
                            t0, r0, x0 = hist[0]
                            if t > t0:
                                rx_bps = max(0.0, (rx - r0) / (t - t0))
                                tx_bps = max(0.0, (tx - x0) / (t - t0))
                        prev = (t, rx, tx)
                        cores = hoststats.state.get("cores") or 1
                        d = {"t": t, "cpu": cpu_pct, "cpu_host": round(cpu_pct / cores, 1) if cpu_pct is not None else None,
                             "mem_mb": round(used / 1048576) if used > 0 else None, "rx_bps": rx_bps, "tx_bps": tx_bps,
                             "net": nets is not None, "running": True}
                        data[name] = d
                        _ring(name).append((t, d["cpu_host"], d["mem_mb"], rx_bps, tx_bps))
            # Stream endet, wenn der Container stoppt
            data[name] = {"t": time.time(), "running": False, "cpu": 0, "cpu_host": 0, "mem_mb": 0,
                          "rx_bps": 0, "tx_bps": 0, "net": data.get(name, {}).get("net", False)}
            prev = None
            hist.clear()
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            raise
        except (docker_api.DockerError, Exception):  # noqa: BLE001
            prev = None
            await asyncio.sleep(5)


def ensure(names: set[str]) -> None:
    if not docker_api.available():
        return
    for n in list(_tasks):
        if n not in names:
            _tasks.pop(n).cancel()
            data.pop(n, None)
            rings.pop(n, None)
    for n in names:
        t = _tasks.get(n)
        if t is None or t.done():
            _tasks[n] = asyncio.create_task(_stream(n))


def _read_host_net():
    """Summe der physischen Netzwerkkarten des Hosts (ohne lo, docker, veth, Bridges)."""
    with open(HOST_NET) as f:
        lines = f.read().splitlines()[2:]
    rx = tx = 0
    ifaces = []
    for line in lines:
        name, _, rest = line.partition(":")
        name = name.strip()
        if re.match(r"^(lo|docker\d*|veth|br-|virbr|tun|tap|wg|zt|cali|flannel|cni|kube|tailscale)", name):
            continue
        v = rest.split()
        if len(v) < 9:
            continue
        rx += int(v[0]); tx += int(v[8])
        ifaces.append(name)
    return rx, tx, ifaces


def sample_host() -> None:
    """Jede Sekunde aufrufen."""
    global _host_prev
    now = time.time()
    h = hoststats.state
    rx_bps = tx_bps = None
    try:
        rx, tx, ifaces = _read_host_net()
        if _host_prev and now > _host_prev[0]:
            dt = now - _host_prev[0]
            rx_bps, tx_bps = max(0.0, (rx - _host_prev[1]) / dt), max(0.0, (tx - _host_prev[2]) / dt)
        _host_prev = (now, rx, tx)
        host.update(source="host", ifaces=ifaces)
    except OSError:
        vals = [d for d in data.values() if d.get("running") and d.get("rx_bps") is not None and now - d["t"] < 5]
        if vals:
            rx_bps, tx_bps = sum(d["rx_bps"] for d in vals), sum(d["tx_bps"] for d in vals)
        host.update(source="container", ifaces=[])
    # Internet-Durchsatz statt Netzwerkkarte: die Karte zählt auch das LAN (Cache -> Clients, NAS).
    # ↓ = alles, was die Container empfangen (Cache holt fehlende Daten aus dem Internet, Spielserver von Spielern)
    # ↑ = was die Spielserver senden (ohne Lancache, der liefert ins LAN)
    vals = {n: d for n, d in data.items() if d.get("running") and d.get("rx_bps") is not None and now - d["t"] < 5 and n not in LAN_ONLY}
    nic_rx, nic_tx = rx_bps, tx_bps
    if vals:
        rx_bps = sum(d["rx_bps"] for d in vals.values())
        tx_bps = sum(d["tx_bps"] or 0 for n, d in vals.items() if n != cache_name)
    host.update(rx_bps=rx_bps, tx_bps=tx_bps, nic_rx_bps=nic_rx, nic_tx_bps=nic_tx, t=now, inet=bool(vals))
    _peak("rx", rx_bps); _peak("tx", tx_bps)
    if nic_rx is not None:
        _peak("nic", nic_rx + (nic_tx or 0))
    cd = data.get(cache_name or "") or {}
    if cd.get("tx_bps") is not None and now - cd.get("t", 0) < 5:
        _peak("cache", cd["tx_bps"])
    mem_pct = round(h["mem_used_mb"] / h["mem_total_mb"] * 100, 1) if h.get("mem_total_mb") else None
    _ring("_host").append((now, h.get("cpu"), mem_pct, rx_bps, tx_bps))


def series(key: str, seconds: int = 300, step: int = 2) -> dict:
    """Live-Reihe im Format von metrics.summary (cpu, mem, rx, tx), gemittelt je `step` Sekunden."""
    r = list(rings.get(key) or [])
    now = time.time()
    n = max(1, seconds // step)
    cpu, mem, rx, tx = [], [], [], []
    start = now - n * step
    j = 0
    for b in range(n):
        lo, hi = start + b * step, start + (b + 1) * step
        seg = []
        while j < len(r) and r[j][0] < hi:
            if r[j][0] >= lo:
                seg.append(r[j])
            j += 1

        def avg(i, seg=seg):
            v = [x[i] for x in seg if x[i] is not None]
            return round(sum(v) / len(v), 1) if v else None
        cpu.append(avg(1)); mem.append(avg(2)); rx.append(avg(3)); tx.append(avg(4))
    return {"cpu": cpu, "mem": mem, "rx": rx, "tx": tx, "samples": len(r), "minutes": seconds / 60, "step_s": step}


# ---------------------------------------------------------------- Speicher / Zugriffszeiten / TCP
HOST_PROC1 = os.getenv("HOST_PROC1", "/host/proc/1")
HOST_PROC = os.getenv("HOST_PROC_ROOT", "/host/proc")
_io_prev: dict = {}
io: dict = {"mounts": [], "disks": [], "tcp": None, "t": None, "available": False}


def _read(path):
    with open(path) as f:
        return f.read()


def _mountstats() -> dict:
    """NFS-Mounts des Hosts: kumulierte Byte- und RPC-Zähler."""
    out, cur = {}, None
    for line in _read(f"{HOST_PROC1}/mountstats").splitlines():
        if line.startswith("device "):
            m = re.match(r"device (\S+) mounted on (\S+) with fstype (nfs\d?)", line)
            cur = None
            if m:
                cur = out[m.group(2)] = {"src": m.group(1), "bytes": None, "ops": {}}
            continue
        if cur is None:
            continue
        t = line.strip()
        if t.startswith("bytes:"):
            cur["bytes"] = [int(x) for x in t.split()[1:]]
        else:
            m = re.match(r"^([A-Z_]+):\s+(\d+(?:\s+\d+){7,})", t)
            if m:
                cur["ops"][m.group(1)] = [int(x) for x in m.group(2).split()]
    return out


def _diskstats() -> dict:
    out = {}
    for line in _read(f"{HOST_PROC}/diskstats").splitlines():
        p = line.split()
        if len(p) < 14 or not re.match(r"^(sd[a-z]+|nvme\d+n\d+|vd[a-z]+|xvd[a-z]+|md\d+|mmcblk\d+)$", p[2]):
            continue
        v = [int(x) for x in p[3:14]]
        out[p[2]] = {"rd": v[0], "rd_sec": v[2], "rd_ms": v[3], "wr": v[4], "wr_sec": v[6], "wr_ms": v[7], "io_ms": v[9]}
    return out


def _tcp() -> dict | None:
    lines = [x for x in _read(f"{HOST_PROC1}/net/snmp").splitlines() if x.startswith("Tcp:")]
    if len(lines) < 2:
        return None
    d = dict(zip(lines[0].split()[1:], lines[1].split()[1:]))
    return {"out": int(d.get("OutSegs", 0)), "retrans": int(d.get("RetransSegs", 0))}


def sample_io() -> None:
    """Alle 2 s: NFS-Latenz (RTT/Ausführungszeit), Durchsatz und Ops je Mount, Plattenauslastung, TCP-Wiederholungen."""
    now = time.time()
    try:
        ms = _mountstats()
    except OSError:
        ms = {}
    try:
        ds = _diskstats()
    except OSError:
        ds = {}
    try:
        tcp = _tcp()
    except OSError:
        tcp = None
    if not ms and not ds and tcp is None:
        io["available"] = False
        return
    prev = _io_prev.get("v")
    _io_prev["v"] = (now, ms, ds, tcp)
    io["available"] = True
    if not prev:
        return
    t0, ms0, ds0, tcp0 = prev
    dt = max(0.001, now - t0)
    mounts = []
    tot_ops = tot_rtt = 0
    for path, m in ms.items():
        p = ms0.get(path)
        if not p or not m["bytes"] or not p["bytes"]:
            continue
        ops = rtt = exe = 0
        for op, v in m["ops"].items():
            pv = p["ops"].get(op)
            if pv:
                ops += v[0] - pv[0]; rtt += v[6] - pv[6]; exe += v[7] - pv[7]
        rd = (m["bytes"][4] - p["bytes"][4]) if len(m["bytes"]) > 5 else 0
        wr = (m["bytes"][5] - p["bytes"][5]) if len(m["bytes"]) > 5 else 0
        tot_ops += ops; tot_rtt += rtt
        mounts.append({"path": path, "src": m["src"], "read_bps": max(0, rd) / dt, "write_bps": max(0, wr) / dt,
                       "ops_s": max(0, ops) / dt, "rtt_ms": round(rtt / ops, 1) if ops > 0 else None,
                       "exec_ms": round(exe / ops, 1) if ops > 0 else None})
    disks = []
    for name, d in ds.items():
        p = ds0.get(name)
        if not p:
            continue
        n = (d["rd"] - p["rd"]) + (d["wr"] - p["wr"])
        disks.append({"name": name, "util": round(min(100.0, (d["io_ms"] - p["io_ms"]) / (dt * 1000) * 100), 1),
                      "await_ms": round(((d["rd_ms"] - p["rd_ms"]) + (d["wr_ms"] - p["wr_ms"])) / n, 1) if n > 0 else None,
                      "read_bps": (d["rd_sec"] - p["rd_sec"]) * 512 / dt, "write_bps": (d["wr_sec"] - p["wr_sec"]) * 512 / dt,
                      "iops": n / dt})
    tcpr = None
    if tcp and tcp0:
        o, r = tcp["out"] - tcp0["out"], tcp["retrans"] - tcp0["retrans"]
        tcpr = {"retrans_s": max(0, r) / dt, "retrans_pct": round(r / o * 100, 2) if o > 0 else 0.0, "out_s": max(0, o) / dt}
    io.update(mounts=sorted(mounts, key=lambda x: -(x["read_bps"] + x["write_bps"] + x["ops_s"])), disks=disks, tcp=tcpr, t=now)
    nfs_rtt = round(tot_rtt / tot_ops, 1) if tot_ops > 0 else None
    util = max((d["util"] for d in disks), default=None)
    nfs_bps = sum(m["read_bps"] + m["write_bps"] for m in mounts) if mounts else None
    _ring("_io").append((now, nfs_rtt, util, nfs_bps, tcpr["retrans_pct"] if tcpr else None))

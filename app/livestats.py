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
host: dict = {"rx_bps": None, "tx_bps": None, "source": None, "ifaces": []}


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


async def _stream(name: str):
    prev = None
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
                        if rx is not None and prev and prev[1] is not None and t > prev[0]:
                            dt = t - prev[0]
                            rx_bps = max(0.0, (rx - prev[1]) / dt)
                            tx_bps = max(0.0, (tx - prev[2]) / dt)
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
    host.update(rx_bps=rx_bps, tx_bps=tx_bps, t=now)
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

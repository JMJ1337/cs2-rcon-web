"""Gesamtlast des Docker-Hosts aus /proc (im Container sind /proc/stat, /proc/meminfo und /proc/loadavg die Werte des Hosts)."""
import os
import time

PROC = os.getenv("HOST_PROC", "/proc")
_prev: tuple[int, int] | None = None
state: dict = {"cpu": None, "cores": os.cpu_count(), "mem_total_mb": None, "mem_used_mb": None,
               "load": None, "updated": None}


def _cpu_times():
    with open(f"{PROC}/stat") as f:
        parts = [int(x) for x in f.readline().split()[1:]]
    idle = parts[3] + (parts[4] if len(parts) > 4 else 0)  # idle + iowait
    return sum(parts), idle


def sample() -> dict:
    global _prev
    try:
        total, idle = _cpu_times()
        if _prev:
            dt, di = total - _prev[0], idle - _prev[1]
            state["cpu"] = round(100 * (dt - di) / dt, 1) if dt > 0 else 0.0
        _prev = (total, idle)
        mem = {}
        with open(f"{PROC}/meminfo") as f:
            for line in f:
                k, v = line.split(":", 1)
                mem[k] = int(v.split()[0])
        state["mem_total_mb"] = round(mem["MemTotal"] / 1024)
        state["mem_used_mb"] = round((mem["MemTotal"] - mem.get("MemAvailable", mem.get("MemFree", 0))) / 1024)
        with open(f"{PROC}/loadavg") as f:
            state["load"] = [float(x) for x in f.read().split()[:3]]
        state["updated"] = time.time()
    except (OSError, ValueError, KeyError):
        pass
    return state

"""Spielserver im LAN finden (A2S, Satisfactory-Query, Docker-Container)."""
import asyncio
import ipaddress
import logging
import os
import random
import struct
import time

from . import docker_api
from .games import a2s

log = logging.getLogger("cs2rcon.scan")

A2S_PORTS = [p for p in range(27015, 27031)] + list(range(27045, 27055)) + [27116, 27117, 2457, 2459, 2461, 2463, 2465]
SF_PORTS = [7777, 7778, 7779]
CONCURRENCY = int(os.getenv("SCAN_CONCURRENCY", "256"))

APPIDS = {440: "tf2", 730: "cs2", 892970: "valheim", 896660: "valheim", 228380: "wreckfest", 361580: "wreckfest",
          1203190: "wreckfest", 3519390: "wreckfest"}

IMAGE_HINTS = {
    "cs2": ["cs2", "counter-strike"], "factorio": ["factorio"],
    "satisfactory": ["satisfactory"], "valheim": ["valheim"], "wreckfest": ["wreckfest"], "tf2": ["tf2", "team-fortress", "teamfortress"],
    "minecraft": ["minecraft"], "teamspeak": ["teamspeak", "ts3"],
}

state = {"running": False, "last": None, "subnets": [], "results": [], "error": None, "duration": None}


def guess_game_a2s(info: dict) -> str | None:
    g = APPIDS.get(info.get("appid"))
    if g:
        return g
    folder = (info.get("folder") or "").lower()
    if "valheim" in folder:
        return "valheim"
    if "wreckfest" in folder or "wreckfest" in (info.get("game") or "").lower():
        return "wreckfest"
    if folder == "tf":
        return "tf2"
    if folder in ("csgo", "cs2") or "counter-strike" in (info.get("game") or "").lower():
        return "cs2"
    return None


async def _probe_a2s(sem, host, port):
    async with sem:
        try:
            info = await a2s.info(host, port, timeout=1.2)
        except Exception:  # noqa: BLE001
            return None
    game = guess_game_a2s(info)
    if not game:
        return None
    # Valheim antwortet auf dem Query-Port (Spielport + 1)
    return {"game": game, "host": host, "port": port, "name": info.get("name"), "map": info.get("map"),
            "players": info.get("players"), "max_players": info.get("max_players"), "source": "A2S"}


class _SFProto(asyncio.DatagramProtocol):
    def __init__(self, fut):
        self.fut = fut

    def datagram_received(self, data, addr):
        if not self.fut.done():
            self.fut.set_result(data)


async def satisfactory_query(host: str, port: int, timeout=1.2) -> dict | None:
    """Satisfactory Lightweight Query API (UDP): Poll Server State."""
    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    cookie = random.getrandbits(64)
    tr, _ = await loop.create_datagram_endpoint(lambda: _SFProto(fut), remote_addr=(host, port))
    try:
        tr.sendto(struct.pack("<HBBQB", 0xF6D5, 0, 1, cookie, 1))
        data = await asyncio.wait_for(fut, timeout)
    except (asyncio.TimeoutError, OSError):
        return None
    finally:
        tr.close()
    try:
        magic, mtype, _ver, ck = struct.unpack_from("<HBBQ", data, 0)
        if magic != 0xF6D5 or mtype != 1 or ck != cookie:
            return None
        i = 12
        srv_state = data[i]
        i += 1 + 4 + 8  # state, netcl, flags
        n_sub = data[i]
        i += 1 + n_sub * 3
        nlen = struct.unpack_from("<H", data, i)[0]
        name = data[i + 2:i + 2 + nlen].decode("utf-8", "replace")
    except (struct.error, IndexError):
        name, srv_state = "Satisfactory", None
    states = {0: "offline", 1: "leer", 2: "lädt", 3: "läuft"}
    return {"game": "satisfactory", "host": host, "port": port, "name": name, "map": states.get(srv_state, ""),
            "players": None, "max_players": None, "source": "Satisfactory-Query"}


async def _probe_sf(sem, host, port):
    async with sem:
        try:
            return await satisfactory_query(host, port)
        except Exception:  # noqa: BLE001
            return None


async def docker_candidates() -> list[dict]:
    if not docker_api.available():
        return []
    out = []
    try:
        for c in await docker_api.list_containers():
            img = (c.get("image") or "").lower()
            game = c["labels"].get("gsm.game")
            if not game:
                game = next((g for g, hints in IMAGE_HINTS.items() if any(h in img for h in hints)), None)
            if not game:
                continue
            out.append({"game": game, "host": None, "port": None, "name": c["name"], "map": c["state"],
                        "players": None, "max_players": None, "source": "Docker", "container": c["name"],
                        "ports": c["ports"]})
    except docker_api.DockerError as e:
        log.warning("Docker-Scan: %s", e)
    return out


def subnets_for(hosts: list[str], extra: list[str]) -> list[ipaddress.IPv4Network]:
    nets = []
    for h in hosts + extra:
        h = (h or "").strip()
        if not h:
            continue
        try:
            net = ipaddress.ip_network(h if "/" in h else f"{h}/24", strict=False)
        except ValueError:
            continue
        if net.version == 4 and net.num_addresses <= 1024 and not net.is_loopback and net not in nets:
            nets.append(net)
    return nets


async def scan(nets: list[ipaddress.IPv4Network]) -> list[dict]:
    if state["running"]:
        return state["results"]
    state.update(running=True, error=None, subnets=[str(n) for n in nets])
    t0 = time.time()
    try:
        sem = asyncio.Semaphore(CONCURRENCY)
        tasks = []
        for net in nets:
            for ip in net.hosts():
                h = str(ip)
                tasks += [_probe_a2s(sem, h, p) for p in A2S_PORTS]
                tasks += [_probe_sf(sem, h, p) for p in SF_PORTS]
        found = [r for r in await asyncio.gather(*tasks) if r]
        found += await docker_candidates()
        state["results"] = found
        state["last"] = time.time()
        state["duration"] = round(time.time() - t0, 1)
        log.info("Scan %s: %d Treffer in %.1fs", state["subnets"], len(found), state["duration"])
        return found
    except Exception as e:  # noqa: BLE001
        state["error"] = str(e)
        raise
    finally:
        state["running"] = False

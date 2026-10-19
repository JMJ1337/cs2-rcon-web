"""Rechnernamen zu IP-Adressen (Reverse-DNS, sonst NetBIOS; Docker-Container per Docker-API)."""
import asyncio
import ipaddress
import os
import socket
import struct
import time

from . import docker_api

_cache: dict[str, tuple[float, str | None]] = {}
TTL_OK, TTL_FAIL = 900, 300


def _nbstat_packet() -> bytes:
    name = b"*" + b"\x00" * 15
    enc = bytes([0x20]) + b"".join(bytes([0x41 + (c >> 4), 0x41 + (c & 0x0F)]) for c in name) + b"\x00"
    return struct.pack(">HHHHHH", os.getpid() & 0xFFFF, 0, 1, 0, 0, 0) + enc + struct.pack(">HH", 0x21, 1)


class _NB(asyncio.DatagramProtocol):
    def __init__(self, fut):
        self.fut = fut

    def datagram_received(self, data, addr):
        if not self.fut.done():
            self.fut.set_result(data)


def parse_nbstat(data: bytes) -> str | None:
    try:
        i = 12 + 34 + 4 + 4 + 2       # Header, Name, Typ/Klasse, TTL, Länge
        n = data[i]
        i += 1
        for k in range(n):
            e = data[i + k * 18:i + k * 18 + 18]
            nm, suffix, flags = e[:15].decode("ascii", "replace").strip(), e[15], struct.unpack(">H", e[16:18])[0]
            if suffix == 0 and not flags & 0x8000 and nm:
                return nm
    except (IndexError, struct.error):
        return None
    return None


async def netbios(ip: str, timeout=0.8) -> str | None:
    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    try:
        tr, _ = await loop.create_datagram_endpoint(lambda: _NB(fut), remote_addr=(ip, 137))
    except OSError:
        return None
    try:
        tr.sendto(_nbstat_packet())
        return parse_nbstat(await asyncio.wait_for(fut, timeout))
    except (asyncio.TimeoutError, OSError):
        return None
    finally:
        tr.close()


async def rdns(ip: str, timeout=1.0) -> str | None:
    loop = asyncio.get_running_loop()
    try:
        name = (await asyncio.wait_for(loop.run_in_executor(None, socket.gethostbyaddr, ip), timeout))[0]
    except (OSError, asyncio.TimeoutError):
        return None
    if not name or name == ip:
        return None
    return name


async def forward(name: str, timeout=1.0) -> list[str]:
    loop = asyncio.get_running_loop()
    try:
        infos = await asyncio.wait_for(loop.run_in_executor(None, socket.getaddrinfo, name, None, socket.AF_INET), timeout)
    except (OSError, asyncio.TimeoutError):
        return []
    return sorted({i[4][0] for i in infos})


def _short(name: str) -> str:
    return name if name.replace(".", "").isdigit() else name.split(".")[0]


async def check(ip: str) -> dict:
    """Diagnose: was liefern DNS (PTR + Gegenprobe) und NetBIOS für diese IP?"""
    ptr, nb = await asyncio.gather(rdns(ip), netbios(ip))
    fwd = await forward(ptr) if ptr else []
    return {"ip": ip, "ptr": ptr, "ptr_forward": fwd, "ptr_confirmed": ip in fwd, "netbios": nb,
            "chosen": await _resolve(ip, force=True)}


async def _resolve(ip: str, force: bool = False) -> str | None:
    """Name ermitteln. Privat: NetBIOS (der Rechner antwortet selbst) vor DNS. DNS-Namen nur, wenn
    die Gegenprobe (Name -> IP) dieselbe IP liefert – sonst ist der PTR-Eintrag veraltet (DHCP hat die IP neu vergeben)."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return None
    if addr.is_private:
        ptr, nb = await asyncio.gather(rdns(ip), netbios(ip))
    else:
        ptr, nb = await rdns(ip), None
    if nb:
        return nb.strip()
    if ptr and ip in await forward(ptr):
        return _short(ptr)
    return None


_containers: dict[str, str] = {}
_containers_at = 0.0


async def _container_ips() -> dict[str, str]:
    global _containers, _containers_at
    if time.time() - _containers_at < 120 or not docker_api.available():
        return _containers
    out = {}
    try:
        r = await docker_api._req("GET", "/containers/json")
        for c in r.json():
            nm = (c.get("Names") or ["/?"])[0].lstrip("/")
            for net in ((c.get("NetworkSettings") or {}).get("Networks") or {}).values():
                if net.get("IPAddress"):
                    out[net["IPAddress"]] = nm
        r = await docker_api._req("GET", "/networks")
        for n in r.json():
            for cfg in ((n.get("IPAM") or {}).get("Config") or []):
                if cfg.get("Gateway"):
                    out[cfg["Gateway"]] = "@gw"
    except docker_api.DockerError:
        return _containers
    _containers, _containers_at = out, time.time()
    return out


async def name_of(ip: str, host_ips: set[str] | None = None) -> str | None:
    if host_ips and ip in host_ips:
        return "Docker-Host (Spielserver/Container)"
    cips = await _container_ips()
    if ip in cips:
        return "Docker-Container auf dem Server" if cips[ip] == "@gw" else f"Container {cips[ip]}"
    hit = _cache.get(ip)
    if hit and time.time() - hit[0] < (TTL_OK if hit[1] else TTL_FAIL):
        return hit[1]
    name = await _resolve(ip)
    _cache[ip] = (time.time(), name)
    return name


async def annotate(clients: list[dict], host_ips: set[str] | None = None) -> list[dict]:
    names = await asyncio.gather(*(name_of(c["ip"], host_ips) for c in clients))
    return [{**c, "name": n} for c, n in zip(clients, names)]

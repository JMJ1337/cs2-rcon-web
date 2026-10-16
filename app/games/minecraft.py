"""Minecraft (Java): Status per Server-List-Ping, Konsole per rcon-cli im itzg-Container."""
import asyncio
import json
import re
import struct
import time


class MinecraftError(Exception):
    pass


def _varint(n: int) -> bytes:
    out = b""
    n &= 0xFFFFFFFF
    while True:
        b = n & 0x7F
        n >>= 7
        out += bytes([b | (0x80 if n else 0)])
        if not n:
            return out


async def _read_varint(r: asyncio.StreamReader) -> int:
    n = shift = 0
    for _ in range(5):
        b = (await r.readexactly(1))[0]
        n |= (b & 0x7F) << shift
        if not b & 0x80:
            return n
        shift += 7
    raise MinecraftError("Ungültige Antwort")


def _motd(desc) -> str:
    if isinstance(desc, str):
        return re.sub(r"§.", "", desc)
    if isinstance(desc, dict):
        return re.sub(r"§.", "", (desc.get("text") or "") + "".join(_motd(x) for x in desc.get("extra") or []))
    if isinstance(desc, list):
        return "".join(_motd(x) for x in desc)
    return ""


async def ping(host: str, port: int, timeout: float = 4.0) -> dict:
    try:
        r, w = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
    except (OSError, asyncio.TimeoutError) as e:
        raise MinecraftError(f"Keine Verbindung zu {host}:{port}") from e
    try:
        hb = host.encode()
        hs = b"\x00" + _varint(767) + _varint(len(hb)) + hb + struct.pack(">H", port) + _varint(1)
        w.write(_varint(len(hs)) + hs + _varint(1) + b"\x00")
        await w.drain()
        await asyncio.wait_for(_read_varint(r), timeout)          # Paketlänge
        if await asyncio.wait_for(_read_varint(r), timeout) != 0:
            raise MinecraftError("Unerwartete Antwort")
        ln = await asyncio.wait_for(_read_varint(r), timeout)
        data = await asyncio.wait_for(r.readexactly(ln), timeout)
        return json.loads(data.decode("utf-8", "replace"))
    except (asyncio.IncompleteReadError, asyncio.TimeoutError, ValueError) as e:
        raise MinecraftError(f"Keine gültige Antwort von {host}:{port} (startet der Server noch?)") from e
    finally:
        w.close()


async def status(host: str, port: int) -> dict:
    j = await ping(host, port)
    pl = j.get("players") or {}
    motd = _motd(j.get("description")).strip()
    ver = (j.get("version") or {}).get("name")
    names = [p.get("name") for p in pl.get("sample") or [] if p.get("name")]
    return {
        "map": motd or "–", "humans": int(pl.get("online") or 0), "bots": 0, "max_players": int(pl.get("max") or 0),
        "players": [{"name": n, "time": ""} for n in names],
        "version": ver, "hostname": motd or None,
        "mode": {"key": "minecraft", "label": "Minecraft " + (ver or "")},
        "extra": {k: v for k, v in {"MOTD": motd, "Version": ver,
                                    "Mods": "ja" if j.get("modinfo") or j.get("forgeData") else None}.items() if v},
        "updated": time.time(),
    }

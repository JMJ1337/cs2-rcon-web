"""Ist ein Server online (in der Steam-Serverliste) oder nur im LAN?

Steam listet jeden Gameserver, der sich beim Master-Server meldet. Die öffentliche Web-API
ISteamApps/GetServersAtAddress liefert alle Server unter einer IP – ohne API-Schlüssel.
Abfrage höchstens alle 2 Minuten; bei Fehlern bleibt das letzte Ergebnis stehen.
"""
import asyncio
import ipaddress
import socket
import time

import httpx

URL = "https://api.steampowered.com/ISteamApps/GetServersAtAddress/v1/"
TTL = 120
# Spiele, deren Server sich bei Steam melden (Factorio/Satisfactory/Minecraft/TeamSpeak haben eigene Listen)
NOT_STEAM = {"factorio", "satisfactory", "minecraft", "teamspeak"}

_cache: dict = {"ip": None, "t": 0.0, "servers": [], "ok": False}


async def listed(ip: str | None) -> dict:
    if not ip:
        return {"ok": False, "servers": []}
    try:
        ipaddress.ip_address(ip)
    except ValueError:                      # DNS-Name -> IP
        try:
            ip = await asyncio.get_running_loop().run_in_executor(None, socket.gethostbyname, ip)
        except OSError:
            return {"ok": False, "servers": []}
    if _cache["ip"] == ip and time.time() - _cache["t"] < TTL:
        return _cache
    _cache.update(ip=ip, t=time.time())
    try:
        async with httpx.AsyncClient(timeout=6) as cl:
            r = await cl.get(URL, params={"addr": ip, "format": "json"})
        resp = r.json().get("response") or {}
        if resp.get("success"):
            _cache["servers"] = resp.get("servers") or []
            _cache["ok"] = True
    except (httpx.HTTPError, ValueError):
        pass
    return _cache


def reach(game: str, server: dict, state: dict, steam: dict, wan: str | None) -> dict:
    """{"kind": "online"|"lan"|"direct", "label", "detail"}"""
    if game == "wreckfest":
        return {"kind": "direct", "label": "eigene Serverliste",
                "detail": "Wreckfest meldet sich nicht in Steams öffentlicher Liste, sondern beim eigenen Dienst – "
                          "Online-Status hier nicht prüfbar. Erreichbar, wenn UDP 27015, 27016, 27017 und 33540 weitergeleitet sind."}
    if game in NOT_STEAM:
        return {"kind": "direct", "label": "IP-Verbindung",
                "detail": "Kein Steam-Listing – aus dem Internet erreichbar, wenn die Ports weitergeleitet sind"}
    if str(state.get("sv_lan") or "").strip() in ("1", "1.000000", "true"):
        return {"kind": "lan", "label": "LAN", "detail": "Mit sv_lan 1 gestartet – nur im lokalen Netz spielbar"}
    ports = {int(p) for p in (server.get("port"), server.get("game_port")) if str(p or "").isdigit()}
    hit = None
    for e in steam.get("servers") or []:
        try:
            qp = int(str(e.get("addr", "")).rsplit(":", 1)[1])
        except (IndexError, ValueError):
            qp = None
        if ports & {qp, e.get("gameport")}:
            hit = e
            break
    if hit:
        return {"kind": "online", "label": "Online",
                "detail": f"Bei Steam gelistet unter {wan}:{hit.get('gameport')}" + (" (VAC)" if hit.get("secure") else "")}
    if not steam.get("ok"):
        return {"kind": "lan", "label": "LAN?", "detail": "Steam-Liste gerade nicht abrufbar"}
    if not state.get("online"):
        return {"kind": "lan", "label": "offline", "detail": "Server läuft nicht"}
    return {"kind": "lan", "label": "nur LAN",
            "detail": f"Nicht in der Steam-Liste unter {wan or 'der öffentlichen IP'} – im Internet-Browser unsichtbar "
                      "(Ports weitergeleitet? Server meldet sich nicht bei Steam?)"}

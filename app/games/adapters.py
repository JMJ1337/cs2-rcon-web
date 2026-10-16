"""Status/Befehle für Factorio (RCON) und Valheim (A2S)."""
import re
import time

from . import a2s
from ..rcon import RconClient


async def factorio_status(c: RconClient) -> dict:
    online = await c.execute("/players online")
    players = []
    for line in online.splitlines()[1:]:
        m = re.match(r"^\s*(.+?)\s*\(online\)\s*$", line)
        if m:
            players.append({"name": m.group(1)})
    version = (await c.execute("/version")).strip()
    gametime = (await c.execute("/time")).strip()
    maxp = None
    try:
        out = await c.execute("/config get max-players")
        m = re.search(r"(\d+)", out)
        maxp = int(m.group(1)) if m else None
        if maxp == 0:
            maxp = None  # 0 = unbegrenzt
    except Exception:  # noqa: BLE001
        pass
    evo = ""
    try:
        out = await c.execute("/evolution")
        m = re.search(r"([0-9]*\.?[0-9]+)", out)
        evo = f"{float(m.group(1)) * 100:.1f} %" if m else ""
    except Exception:  # noqa: BLE001
        pass
    return {
        "map": "Factorio-Welt", "humans": len(players), "bots": 0, "max_players": maxp,
        "players": players, "version": version or None, "hostname": None,
        "mode": {"key": "factorio", "label": "Factorio"},
        "extra": {k: v for k, v in {"Spielzeit": gametime, "Evolution": evo, "Version": version}.items() if v},
        "updated": time.time(),
    }


async def valheim_status(host: str, port: int) -> dict:
    info = await a2s.info(host, port)
    try:
        pl = await a2s.players(host, port)
    except a2s.A2SError:
        pl = []
    kw = info.get("keywords", "")
    m = re.search(r"g=([\d.]+)", kw)
    version = m.group(1) if m else info.get("version")
    return {
        "map": info.get("map") or info.get("name"), "humans": info["players"], "bots": 0,
        "max_players": info["max_players"],
        "players": [{"name": p["name"] or "(lädt …)", "time": f"{p['time'] // 60} min"} for p in pl],
        "version": version, "hostname": info["name"],
        "mode": {"key": "valheim", "label": "Valheim"},
        "extra": {k: v for k, v in {"Servername": info["name"], "Version": version,
                                    "Passwort": "ja" if info["password"] else "nein"}.items() if v},
        "updated": time.time(),
    }

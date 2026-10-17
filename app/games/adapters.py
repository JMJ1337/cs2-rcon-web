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
    name = None
    try:
        out = (await c.execute("/config get name")).strip()
        if out and "unknown" not in out.lower() and "error" not in out.lower() and "/config" not in out and len(out) < 100:
            name = out.split(":", 1)[1].strip() if ":" in out else out
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
        "players": players, "version": version or None, "hostname": name,
        "mode": {"key": "factorio", "label": "Factorio"},
        "extra": {k: v for k, v in {"Spielzeit": gametime, "Evolution": evo, "Version": version}.items() if v},
        "updated": time.time(),
    }


async def wreckfest_status(host: str, port: int) -> dict:
    info = await a2s.info(host, port)
    try:
        pl = await a2s.players(host, port)
    except a2s.A2SError:
        pl = []
    return {
        "map": info.get("map") or "–", "humans": info["players"], "bots": info.get("bots") or 0,
        "max_players": info["max_players"],
        "players": [{"name": p["name"] or "(verbindet …)", "time": f"{p['time'] // 60} min"} for p in pl],
        "version": info.get("version"), "hostname": info["name"],
        "mode": {"key": "wreckfest", "label": "Wreckfest"},
        "extra": {k: v for k, v in {"Servername": info["name"], "Strecke": info.get("map"),
                                    "Bots": info.get("bots") or None, "Version": info.get("version"),
                                    "Passwort": "ja" if info["password"] else "nein"}.items() if v},
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


WF_SH = r"""
c=/serverdata/serverfiles/server_config.cfg
[ -f "$c" ] && grep -E '^[[:space:]]*(server_name|max_players|password|gamemode|track|game_port|query_port|steam_port|bots|laps)[[:space:]]*=' "$c"
echo '#LOG'
tail -n 400 /serverdata/serverfiles/log.txt 2>/dev/null
echo '#PROC'
pgrep -f Wreckfest_x64.exe >/dev/null && echo running
"""

WF_TRACKS_HINT = {"": "Rotation"}


def _wf_parse(out: str) -> dict:
    cfg, log, proc, sec = {}, [], False, "cfg"
    for line in out.splitlines():
        if line.startswith("#LOG"):
            sec = "log"; continue
        if line.startswith("#PROC"):
            sec = "proc"; continue
        if sec == "cfg" and "=" in line:
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip().strip('"')
        elif sec == "log":
            log.append(line.strip())
        elif sec == "proc" and line.strip() == "running":
            proc = True
    # nur den letzten Serverstart betrachten
    start = max([i for i, l in enumerate(log) if "Starting server" in l] or [0])
    cur = log[start:]
    connected = any("Server connected" in l for l in cur)
    players: dict[str, bool] = {}
    for l in cur:
        m = re.search(r"\d\d:\d\d:\d\d\s+(.+?)\s+(?:has\s+)?(joined|left|disconnected|was kicked|timed out)", l, re.I)
        if m:
            players[m.group(1)] = m.group(2).lower() == "joined"
    return {"cfg": cfg, "connected": connected, "running": proc, "players": [n for n, on in players.items() if on],
            "log_tail": cur[-5:]}


async def wreckfest_container_status(container: str) -> dict:
    """Wreckfest beantwortet keine A2S-Abfragen – Zustand direkt aus Container (Konfiguration + log.txt)."""
    from .. import docker_api
    try:
        out = await docker_api.exec_cmd(container, ["sh", "-c", WF_SH])
    except docker_api.DockerError as e:
        raise a2s.A2SError(f"Container nicht erreichbar: {e}") from e
    p = _wf_parse(out)
    if not p["running"]:
        raise a2s.A2SError("Wreckfest-Prozess läuft nicht (Container startet/installiert?)")
    if not p["connected"]:
        raise a2s.A2SError("Wreckfest startet noch …")
    cfg = p["cfg"]
    mx = int(cfg["max_players"]) if cfg.get("max_players", "").isdigit() else 0
    names = p["players"]
    return {
        "map": cfg.get("track") or "–", "humans": len(names), "bots": int(cfg["bots"]) if cfg.get("bots", "").isdigit() else 0,
        "max_players": mx,
        "players": [{"name": n, "time": ""} for n in names],
        "version": None, "hostname": cfg.get("server_name"),
        "mode": {"key": "wreckfest", "label": (cfg.get("gamemode") or "Wreckfest").title()},
        "password": cfg.get("password") or "",
        "extra": {k: v for k, v in {"Servername": cfg.get("server_name"), "Strecke": cfg.get("track"),
                                    "Modus": cfg.get("gamemode"), "Runden": cfg.get("laps"),
                                    "Spielport": cfg.get("game_port"),
                                    "Passwort": cfg.get("password") or "keins"}.items() if v},
        "updated": time.time(),
    }


TF2_MODES = {"ctf": "Capture the Flag", "cp": "Control Point", "pl": "Payload", "plr": "Payload Race",
             "koth": "King of the Hill", "arena": "Arena", "mvm": "Mann vs. Machine", "pd": "Player Destruction",
             "sd": "Special Delivery", "tc": "Territorial Control", "rd": "Robot Destruction", "pass": "PASS Time",
             "tr": "Training", "vsh": "Versus Saxton Hale", "zi": "Zombie Infection", "mge": "MGE", "jump": "Jump"}


async def tf2_status(host: str, port: int) -> dict:
    info = await a2s.info(host, port)
    try:
        pl = await a2s.players(host, port)
    except a2s.A2SError:
        pl = []
    m = info.get("map") or ""
    prefix = m.split("_")[0].lower() if "_" in m else ""
    mode = TF2_MODES.get(prefix, "Team Fortress 2")
    humans = max(0, info["players"] - (info.get("bots") or 0))
    return {
        "map": m or "–", "humans": humans, "bots": info.get("bots") or 0, "max_players": info["max_players"],
        "players": [{"name": p["name"] or "(verbindet …)", "time": f"{p['time'] // 60} min", "score": p.get("score")}
                    for p in pl if p.get("name")],
        "version": info.get("version"), "hostname": info["name"],
        "mode": {"key": prefix or "tf2", "label": mode},
        "extra": {k: v for k, v in {"Map": m, "Modus": mode, "Bots": info.get("bots") or None,
                                    "Version": info.get("version"), "Passwort": "ja" if info["password"] else "nein"}.items() if v},
        "updated": time.time(),
    }


async def tf2_rcon_status(c: RconClient) -> dict:
    """TF2-Status per RCON 'status' (zuverlässiger als A2S, liefert Spielernamen und Ping)."""
    raw = await c.execute("status")
    g = lambda rx: (re.search(rx, raw, re.M) or [None, None])[1]  # noqa: E731
    host = g(r"^hostname\s*:\s*(.*)$")
    m = g(r"^map\s*:\s*(\S+)")
    pm = re.search(r"^players\s*:\s*(\d+) humans?,\s*(\d+) bots?\s*\((\d+)", raw, re.M)
    humans, bots, mx = (int(pm.group(1)), int(pm.group(2)), int(pm.group(3))) if pm else (0, 0, 0)
    players = []
    for line in raw.splitlines():
        r = re.match(r'^#\s*(\d+)\s+"(.*)"\s+(\[U:\S+\]|BOT)\s+(\S+)?\s*(\d+)?\s*(\d+)?\s*(\w+)?\s*(\S+)?', line)
        if r and r.group(3) != "BOT":
            players.append({"name": r.group(2), "time": r.group(4) or "", "ping": int(r.group(5)) if r.group(5) else None})
    prefix = m.split("_")[0].lower() if m and "_" in m else ""
    mode = TF2_MODES.get(prefix, "Team Fortress 2")
    ver = g(r"^version\s*:\s*(\S+)")
    acct = g(r"^account\s*:\s*(.*)$")
    return {
        "map": m or "–", "humans": humans, "bots": bots, "max_players": mx, "players": players,
        "version": ver, "hostname": host, "raw": raw,
        "mode": {"key": prefix or "tf2", "label": mode},
        "extra": {k: v for k, v in {"Map": m, "Modus": mode, "Bots": bots or None, "Version": ver,
                                    "Steam-Login": acct}.items() if v},
        "updated": time.time(),
    }


async def generic_a2s_status(host: str, port: int, label: str) -> dict:
    info = await a2s.info(host, port)
    try:
        pl = await a2s.players(host, port)
    except a2s.A2SError:
        pl = []
    bots = info.get("bots") or 0
    return {
        "map": info.get("map") or "–", "humans": max(0, info["players"] - bots), "bots": bots, "max_players": info["max_players"],
        "players": [{"name": p["name"] or "(verbindet …)", "time": f"{p['time'] // 60} min"} for p in pl if p.get("name") is not None],
        "version": info.get("version"), "hostname": info["name"], "mode": {"key": "game", "label": label},
        "extra": {k: v for k, v in {"Map": info.get("map"), "Version": info.get("version"), "Bots": bots or None,
                                    "Passwort": "ja" if info["password"] else "nein"}.items() if v},
        "updated": time.time(),
    }


async def tcp_status(host: str, port: int, label: str) -> dict:
    import asyncio
    try:
        _, w = await asyncio.wait_for(asyncio.open_connection(host, port), 3)
        w.close()
    except (OSError, asyncio.TimeoutError) as e:
        raise a2s.A2SError(f"Port {host}:{port} nicht erreichbar") from e
    return {"map": "–", "humans": 0, "bots": 0, "max_players": 0, "players": [], "version": None, "hostname": None,
            "mode": {"key": "game", "label": label}, "extra": {"Port": f"{port} erreichbar"}, "updated": time.time(),
            "players_unknown": True}


async def ac_status(host: str, port: int) -> dict:
    import httpx
    try:
        async with httpx.AsyncClient(timeout=4) as cl:
            j = (await cl.get(f"http://{host}:{port}/INFO")).json()
    except (httpx.HTTPError, ValueError) as e:
        raise a2s.A2SError(f"Assetto-Corsa-HTTP {host}:{port} antwortet nicht") from e
    return {"map": j.get("track") or "–", "humans": int(j.get("clients") or 0), "bots": 0, "max_players": int(j.get("maxclients") or 0),
            "players": [], "version": None, "hostname": j.get("name"), "mode": {"key": "ac", "label": "Assetto Corsa"},
            "extra": {k: v for k, v in {"Strecke": j.get("track"), "Autos": ", ".join(j.get("cars") or [])[:80],
                                        "Passwort": "ja" if j.get("pass") else "nein"}.items() if v},
            "updated": time.time()}


async def valheim_container_status(container: str) -> dict:
    """Fallback ohne Steam-Abfrage (z. B. mit -crossplay): Zustand aus dem Server-Log."""
    from .. import docker_api
    try:
        txt = await docker_api.logs(container, 600)
    except docker_api.DockerError as e:
        raise a2s.A2SError(str(e)) from e
    lines = txt.splitlines()
    up = any(re.search(r"(Game server connected|Session .* registered|Opened Steam server|Registering lobby|World saved|SaveSystem)", l) for l in lines)
    if not up:
        raise a2s.A2SError("Valheim startet noch (kein „Game server connected“ im Log)")
    conns = [int(m.group(1)) for l in lines for m in [re.search(r"Connections (\d+)", l)] if m]
    world = next((m.group(1) for l in reversed(lines) for m in [re.search(r"Load world:? ?(\S+)|Get create world (\S+)", l)] if m and m.group(1)), None)
    return {"map": world or "–", "humans": conns[-1] if conns else 0, "bots": 0, "max_players": 10, "players": [],
            "version": None, "hostname": None, "mode": {"key": "valheim", "label": "Valheim"},
            "extra": {"Quelle": "Server-Log (Steam-Abfrage aus, z. B. Crossplay)"}, "updated": time.time()}


async def factorio_container_status(container: str) -> dict:
    """Fallback ohne RCON: Spieler aus [JOIN]/[LEAVE] im Log."""
    from .. import docker_api
    try:
        txt = await docker_api.logs(container, 2000)
    except docker_api.DockerError as e:
        raise a2s.A2SError(str(e)) from e
    lines = txt.splitlines()
    if not any("Hosting game" in l or "changing state from(CreatingGame) to(InGame)" in l or "Matching server game" in l for l in lines):
        raise a2s.A2SError("Factorio startet noch")
    online: dict[str, bool] = {}
    for l in lines:
        m = re.search(r"\[(JOIN|LEAVE)\] (\S+)", l)
        if m:
            online[m.group(2)] = m.group(1) == "JOIN"
    names = [n for n, on in online.items() if on]
    save = next((m.group(1) for l in reversed(lines) for m in [re.search(r"Loading map (\S+)", l)] if m), None)
    return {"map": (save or "–").rsplit("/", 1)[-1], "humans": len(names), "bots": 0, "max_players": 0,
            "players": [{"name": n, "time": ""} for n in names], "version": None, "hostname": None,
            "mode": {"key": "factorio", "label": "Factorio"},
            "extra": {"Quelle": "Server-Log – RCON-Port nicht freigegeben (Konsole ohne RCON nicht möglich)"}, "updated": time.time()}

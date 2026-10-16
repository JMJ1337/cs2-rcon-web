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

"""Steam-Bot: eigener Container (node + steam-user), vom Tool gesteuert.

- an/aus: Container starten/stoppen
- automatisch neue LAN-Spieler (SteamID aus der Spielerliste) als Freund anfragen
- Nachrichten an einzelne oder alle Spieler der LAN schicken (nur an bestätigte Freunde möglich – Steam-Regel)

Das Bot-Konto braucht ein „nicht eingeschränktes“ Steam-Konto (mind. 5 $ ausgegeben), sonst kann es keine
Freundschaftsanfragen verschicken. Das Passwort wird nicht gespeichert, nur das Anmelde-Token im Bot-Ordner.
"""
import base64
import secrets
import socket
import time
from pathlib import Path

import httpx

from . import docker_api, playerdb, store

NAME = "steambot"
IMAGE = "node:20-alpine"
PORT = 8091
FILE = "steambot.json"
SRC = Path(__file__).parent / "steambot"
ADD_PER_HOUR = 10          # Steam mag keine Anfrage-Salven

DEFAULTS = {"enabled": False, "auto_add": True, "bot_name": "LAN-Bot", "key": "", "requested": {}, "since": None,
            "recent_hours": 24, "max_age_days": 7, "adds": []}


def settings() -> dict:
    d = {**DEFAULTS, **store.load(FILE, {})}
    if not d.get("key"):
        d["key"] = secrets.token_hex(16)
        store.save(FILE, d)
    return d


def save(new: dict) -> dict:
    d = settings()
    for k in ("enabled", "auto_add", "bot_name", "recent_hours", "max_age_days", "requested", "since", "adds"):
        if k in new:
            d[k] = new[k]
    store.save(FILE, d)
    return d


VOLUME = "gsm-steambot"     # lokales Docker-Volume (kein NFS: dort darf root keine Rechte setzen)


async def _own_network() -> str | None:
    """Netz, in dem dieses Tool läuft – der Bot kommt ins selbe Netz, dann ist er per Name erreichbar."""
    try:
        info = await docker_api.inspect(socket.gethostname())
        nets = list(((info.get("NetworkSettings") or {}).get("Networks") or {}).keys())
        return next((n for n in nets if n not in ("host", "none")), None)
    except docker_api.DockerError:
        return None


async def _write_sources() -> None:
    files = {"bot.js": (SRC / "bot.js").read_bytes(), "package.json": (SRC / "package.json").read_bytes()}
    cmd = "mkdir -p /t/app /t/data && " + " && ".join(
        f"echo {base64.b64encode(v).decode()} | base64 -d > /t/app/{k}" for k, v in files.items()) + " && chown -R 1000:1000 /t && echo ok"
    await docker_api.run_helper([f"{VOLUME}:/t"], ["sh", "-c", cmd], timeout=120)


async def state() -> dict | None:
    try:
        info = await docker_api.inspect(NAME)
    except docker_api.DockerError:
        return None
    s = info.get("State") or {}
    return {"running": s.get("Running"), "status": s.get("Status"), "started": s.get("StartedAt")}


async def start() -> None:
    d = settings()
    await _write_sources()
    try:
        await docker_api.remove_container(NAME)
    except docker_api.DockerError:
        pass
    if not await docker_api.image_exists(IMAGE):
        await docker_api.pull(IMAGE)
    net = await _own_network()
    spec = {"Image": IMAGE, "User": "1000:1000", "WorkingDir": "/srv/app",
            "Cmd": ["sh", "-c", "(test -d node_modules/steam-user || npm install --omit=dev --no-audit --no-fund) && exec node bot.js"],
            "Env": [f"BOT_KEY={d['key']}", f"BOT_NAME={d.get('bot_name') or 'LAN-Bot'}", "HOME=/srv/data", "npm_config_cache=/srv/data/.npm",
                    "BOT_DATA=/srv/data"],
            "Labels": {"gsm.helper": "steambot"},
            "HostConfig": {"Binds": [f"{VOLUME}:/srv"], "RestartPolicy": {"Name": "unless-stopped"},
                           **({"NetworkMode": net} if net else {})}}
    if net:
        spec["NetworkingConfig"] = {"EndpointsConfig": {net: {"Aliases": [NAME]}}}
    await docker_api.create_container(NAME, spec)


async def stop() -> None:
    try:
        await docker_api._req("POST", f"/containers/{NAME}/stop", params={"t": "5"}, timeout=30)
    except docker_api.DockerError:
        pass


async def api(method: str, path: str, body: dict | None = None, timeout: float = 20) -> dict:
    d = settings()
    async with httpx.AsyncClient(timeout=timeout) as cl:
        r = await cl.request(method, f"http://{NAME}:{PORT}{path}", json=body, headers={"x-bot-key": d["key"]})
    try:
        j = r.json()
    except ValueError:
        j = {"error": r.text[:200]}
    if r.status_code >= 400:
        raise RuntimeError(j.get("error") or f"Bot antwortet mit {r.status_code}")
    return j


async def status() -> dict:
    c = await state()
    out = {"container": c, "bot": None, "error": None}
    if c and c.get("running"):
        try:
            out["bot"] = await api("GET", "/status", timeout=5)
        except (httpx.HTTPError, RuntimeError) as e:
            out["error"] = "Bot startet noch (lädt beim ersten Mal die Steam-Bibliothek) …" \
                if time.time() - _started(c) < 300 else f"Bot nicht erreichbar: {e}"
    return out


def _started(c: dict) -> float:
    from datetime import datetime
    try:
        return datetime.fromisoformat((c.get("started") or "")[:19] + "+00:00").timestamp()
    except ValueError:
        return 0.0


def lan_players(hours: float | None = None) -> list[dict]:
    """Spieler mit SteamID, die auf den Servern gesehen wurden (zuletzt zuerst)."""
    now = time.time()
    out = []
    for p in playerdb.all_players():
        sid = str(p.get("steamid") or "")
        if not sid.isdigit() or len(sid) != 17:
            continue
        last = p.get("last_seen") or 0
        if hours and now - last > hours * 3600:
            continue
        if not playerdb.on_lan(p):              # nur Spieler auf der LAN (nicht, wer übers Internet mitspielt)
            continue
        out.append({"steamid": sid, "name": playerdb.display(p), "last_seen": last, "first_seen": p.get("first_seen"),
                    "games": p.get("games") or [], "avatar": p.get("avatar"), "lan_manual": p.get("lan") is not None})
    return sorted(out, key=lambda x: -(x["last_seen"] or 0))


async def tick() -> None:
    """Jede Minute: neue Spieler automatisch als Freund anfragen (wenn eingeschaltet)."""
    d = settings()
    if not d.get("enabled") or not d.get("auto_add"):
        return
    st = await status()
    bot = st.get("bot") or {}
    if bot.get("state") != "angemeldet" or bot.get("can_invite") is False:
        return
    friends = {f["steamid"] for f in bot.get("friends") or []}
    req = d.get("requested") or {}
    now = time.time()
    adds = [t for t in (d.get("adds") or []) if now - t < 3600]
    me = bot.get("steamid")
    for p in lan_players(float(d.get("max_age_days") or 7) * 24):
        if len(adds) >= ADD_PER_HOUR:
            break
        sid = p["steamid"]
        if sid in friends or sid in req or sid == me:
            continue
        try:
            await api("POST", "/add", {"steamid": sid})
            req[sid] = now
        except (httpx.HTTPError, RuntimeError) as e:
            req[sid] = -now                    # merken, nicht dauernd neu versuchen
            if "nicht angemeldet" in str(e):
                break
        adds.append(now)
    save({"requested": req, "adds": adds})

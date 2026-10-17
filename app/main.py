import asyncio
import ipaddress
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import automation, cache_history, configfiles, depots, filebrowser, hoststorage, prefill, diagnostics, livestats, netnames, cache_stats, docker_api, hoststats, install_watch, metrics, scanner, steam, store, templates, users
from .games import GAMES, adapters, game_of
from .games import satisfactory as sfmod
from .games import minecraft as mcmod
from .games import teamspeak as tsmod
from .games import catalog as catmod
from .rcon import RconAuthError, RconClient, RconError

log = logging.getLogger("cs2rcon")
logging.basicConfig(level=logging.INFO)

DATA_DIR = store.DATA_DIR
SERVERS_FILE = DATA_DIR / "servers.json"
SECRET_FILE = DATA_DIR / ".secret"
STATIC_DIR = Path(__file__).parent / "static"

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
if not ADMIN_PASSWORD:
    ADMIN_PASSWORD = "changeme"
    log.warning("ADMIN_PASSWORD nicht gesetzt – Standardpasswort 'changeme' aktiv!")
SESSION_HOURS = int(os.getenv("SESSION_HOURS", "24"))
RCON_TIMEOUT = float(os.getenv("RCON_TIMEOUT", "4"))
WATCH_ENABLED = os.getenv("WATCH_ENABLED", "1") != "0"

if not SECRET_FILE.exists():
    SECRET_FILE.write_text(secrets.token_hex(32))
SECRET = SECRET_FILE.read_text().strip().encode()
COOKIE = "cs2rcon_session"


@asynccontextmanager
async def lifespan(_app):
    tasks = [asyncio.create_task(watcher()), asyncio.create_task(scan_loop()),
             asyncio.create_task(load_loop()), asyncio.create_task(live_loop())] if WATCH_ENABLED else []
    yield
    for t in tasks:
        t.cancel()
    try:
        metrics.maybe_save(force=True)
        cache_history.maybe_save(force=True)
    except Exception:  # noqa: BLE001
        pass


app = FastAPI(title="CS2 RCON Web", docs_url=None, redoc_url=None, lifespan=lifespan)


# ---------------------------------------------------------------- Auth / Benutzer
users.bootstrap(ADMIN_PASSWORD)


def _sign(value: str) -> str:
    return hmac.new(SECRET, value.encode(), hashlib.sha256).hexdigest()


def make_token(username: str) -> str:
    payload = f"{int(time.time()) + SESSION_HOURS * 3600}.{username}.{int(time.time())}"
    return f"{payload}.{_sign(payload)}"


def token_user(token: str | None) -> dict | None:
    if not token or token.count(".") != 3:
        return None
    exp, name, iat, sig = token.split(".")
    if not hmac.compare_digest(sig, _sign(f"{exp}.{name}.{iat}")):
        return None
    if not exp.isdigit() or int(exp) < time.time():
        return None
    u = users.find(name)
    if not u or int(iat) < int(u.get("pw_changed") or 0):
        return None  # gelöscht oder Passwort geändert -> neu anmelden
    return u


ADMIN_PATHS = ("/api/users", "/api/create", "/api/settings", "/api/prefill", "/api/storage")


def require_auth(request: Request):
    u = token_user(request.cookies.get(COOKIE))
    if not u:
        raise HTTPException(401, "Nicht angemeldet")
    level = users.ROLES.get(u["role"], 0)
    path, method = request.url.path, request.method
    if method != "GET" and level < 2 and not path.startswith("/api/me"):
        raise HTTPException(403, "Nur Ansicht – keine Berechtigung für Änderungen")
    admin_only = (path.startswith(ADMIN_PATHS) and not (path == "/api/settings" and method == "GET")) or \
        (method in ("POST", "PUT", "DELETE") and re.fullmatch(r"/api/servers(/[\w-]+)?", path)) or \
        re.fullmatch(r"/api/servers/[\w-]+/(delete(-preview)?|container/(diag|use-lancache|steamfix|env)|wreckfest/.*|config(/file)?|satisfactory/options|files(/.*)?|saves(/.*)?)", path)
    if admin_only and level < 3:
        raise HTTPException(403, "Nur für Administratoren")
    request.state.user = u
    return u


class LoginIn(BaseModel):
    username: str = Field("admin", max_length=32)
    password: str


@app.post("/api/login")
async def login(data: LoginIn, response: Response):
    name = (data.username or "admin").strip().lower()
    u = users.verify(name, data.password)
    if not u and name == "admin" and hmac.compare_digest(data.password.encode(), ADMIN_PASSWORD.encode()):
        u = users.find("admin")  # Notfall-Login mit ADMIN_PASSWORD aus dem Stack
        if not u:
            users.bootstrap(ADMIN_PASSWORD)
            u = users.find("admin")
    if not u:
        await asyncio.sleep(1.0)  # Brute-Force bremsen
        raise HTTPException(401, "Benutzername oder Passwort falsch")
    response.set_cookie(COOKIE, make_token(u["username"]), httponly=True, samesite="strict",
                        max_age=SESSION_HOURS * 3600)
    return {"ok": True, "user": users.public(u)}


@app.post("/api/logout")
async def logout(response: Response):
    response.delete_cookie(COOKIE)
    return {"ok": True}


@app.get("/api/version")
async def version():
    return {"version": os.getenv("APP_VERSION", "dev"), "commit": os.getenv("APP_COMMIT", "lokal")[:7],
            "date": os.getenv("BUILD_DATE") or None}


@app.get("/api/me")
async def me(request: Request):
    u = token_user(request.cookies.get(COOKIE))
    return {"authenticated": bool(u), "user": users.public(u) if u else None}


auth = [Depends(require_auth)]


class UserIn(BaseModel):
    username: str = Field(min_length=1, max_length=32)
    password: str | None = Field(None, max_length=128)
    role: str | None = None


@app.get("/api/users", dependencies=auth)
async def list_users():
    return {"users": [users.public(u) for u in users.load()], "roles": users.ROLE_LABELS}


@app.post("/api/users", dependencies=auth)
async def add_user(data: UserIn):
    if users.find(data.username):
        raise HTTPException(400, "Benutzer existiert bereits")
    try:
        return users.public(users.upsert(data.username, data.password, data.role or "user"))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.put("/api/users/{username}", dependencies=auth)
async def update_user(username: str, data: UserIn):
    if not users.find(username):
        raise HTTPException(404, "Benutzer nicht gefunden")
    try:
        return users.public(users.upsert(username, data.password or None, data.role))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.delete("/api/users/{username}", dependencies=auth)
async def del_user(username: str, request: Request):
    if username == request.state.user["username"]:
        raise HTTPException(400, "Du kannst dich nicht selbst löschen")
    try:
        users.delete(username)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


class PwIn(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6, max_length=128)


@app.post("/api/me/password", dependencies=auth)
async def change_own_password(data: PwIn, request: Request, response: Response):
    u = request.state.user
    if not users.verify(u["username"], data.old_password):
        raise HTTPException(400, "Altes Passwort falsch")
    users.upsert(u["username"], data.new_password, None)
    await asyncio.sleep(1.1)  # neues Token muss nach pw_changed liegen
    response.set_cookie(COOKIE, make_token(u["username"]), httponly=True, samesite="strict",
                        max_age=SESSION_HOURS * 3600)
    return {"ok": True}


# ---------------------------------------------------------------- Server-Speicher
class ServerIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(27015, ge=1, le=65535)
    password: str | None = None  # None/"" beim Update = unverändert lassen
    notes: str = ""
    auto_slots: bool = True
    game: str = "cs2"
    container: str = ""
    web_url: str = Field("", max_length=255)
    game_port: int | None = Field(None, ge=1, le=65535)   # Port zum Beitreten, falls abweichend
    name_from_game: bool = True                            # Namen automatisch aus dem Spiel übernehmen
    mode_name: bool = True                                 # CS2: Servername im Spiel nach aktuellem Modus setzen


_store_lock = asyncio.Lock()
_clients: dict[str, RconClient] = {}
_state: dict[str, dict] = {}        # letzter bekannter Zustand je Server (Watcher/Status)
_last_workshop: dict[str, dict] = {}  # zuletzt per Tool geladene Workshop-Map je Server


def load_servers() -> list[dict]:
    return store.load("servers.json", [])


def save_servers(servers: list[dict]) -> None:
    store.save("servers.json", servers)


def public(s: dict) -> dict:
    out = {k: v for k, v in s.items() if k != "password"}
    out.setdefault("auto_slots", True)
    out.setdefault("game", "cs2")
    out.setdefault("container", "")
    out.setdefault("web_url", "")
    out.setdefault("game_port", None)
    out.setdefault("name_from_game", True)
    out.setdefault("mode_name", True)
    return out | {"has_password": bool(s.get("password"))}


def get_server(sid: str) -> dict:
    for s in load_servers():
        if s["id"] == sid:
            return s
    raise HTTPException(404, "Server nicht gefunden")


def drop_client(sid: str):
    c = _clients.pop(sid, None)
    if c:
        c.close()
    _sf_clients.pop(sid, None)


_sf_clients: dict[str, sfmod.SatisfactoryClient] = {}


def sf_client(s: dict) -> sfmod.SatisfactoryClient:
    c = _sf_clients.get(s["id"])
    if c is None:
        c = sfmod.SatisfactoryClient(s["host"], int(s["port"]), s.get("password", ""))
        _sf_clients[s["id"]] = c
    return c


_ts_tried: dict[str, float] = {}


async def _ts_password_from_logs(s: dict) -> None:
    """serveradmin-Passwort + Admin-Token aus dem Log des TeamSpeak-Containers übernehmen (nur beim ersten Start geloggt)."""
    if time.time() - _ts_tried.get(s["id"], 0) < 600:
        return
    _ts_tried[s["id"]] = time.time()
    try:
        lg = await docker_api._req("GET", f"/containers/{s['container']}/logs", params={"stdout": "1", "stderr": "1", "tail": "all"}, timeout=30)
        info = await docker_api.inspect(s["container"])
        text = lg.content.decode("utf-8", "replace") if info.get("Config", {}).get("Tty") else docker_api._demux(lg.content)
    except docker_api.DockerError:
        return
    pw = re.findall(r'loginname=\s*"serveradmin",\s*password=\s*"([^"]+)"', text)
    tok = re.findall(r"token=([A-Za-z0-9+]+)", text)
    if pw:
        notes = s.get("notes") or ""
        if tok and "Admin-Token" not in notes:
            notes = (notes + "\n" if notes else "") + f"Admin-Token (Berechtigungsschlüssel): {tok[-1]}"
        await _set_server_fields(s["id"], password=pw[-1], notes=notes)
        s["password"] = pw[-1]
        s["notes"] = notes


def ts_query(s: dict):
    return tsmod.Query(s["host"], int(s["port"]), s.get("password", ""), int(s["game_port"]) if s.get("game_port") else None)


def client_for(s: dict) -> RconClient:
    c = _clients.get(s["id"])
    if c is None:
        c = RconClient(s["host"], int(s["port"]), s.get("password", ""), RCON_TIMEOUT)
        _clients[s["id"]] = c
    return c


async def run(s: dict, command: str) -> str:
    try:
        return await client_for(s).execute(command)
    except RconAuthError as e:
        drop_client(s["id"])
        raise HTTPException(502, str(e))
    except RconError as e:
        raise HTTPException(502, str(e))


@app.get("/api/servers", dependencies=auth)
async def list_servers():
    return [public(s) for s in load_servers()]


@app.post("/api/servers", dependencies=auth)
async def add_server(data: ServerIn):
    async with _store_lock:
        servers = load_servers()
        s = {"id": uuid.uuid4().hex[:10], "name": data.name, "host": data.host.strip(),
             "port": data.port, "password": data.password or "", "notes": data.notes,
             "auto_slots": data.auto_slots, "game": data.game if data.game in GAMES else "cs2",
             "container": data.container.strip(), "web_url": data.web_url.strip(),
             "game_port": data.game_port, "name_from_game": data.name_from_game,
             "mode_name": data.mode_name}
        servers.append(s)
        save_servers(servers)
    return public(s)


@app.put("/api/servers/{sid}", dependencies=auth)
async def update_server(sid: str, data: ServerIn):
    async with _store_lock:
        servers = load_servers()
        for s in servers:
            if s["id"] == sid:
                s.update(name=data.name, host=data.host.strip(), port=data.port, notes=data.notes,
                         auto_slots=data.auto_slots, game=data.game if data.game in GAMES else "cs2",
                         container=data.container.strip(), web_url=data.web_url.strip(),
                         game_port=data.game_port, name_from_game=data.name_from_game,
                         mode_name=data.mode_name)
                if data.password:
                    s["password"] = data.password
                save_servers(servers)
                drop_client(sid)
                return public(s)
    raise HTTPException(404, "Server nicht gefunden")


@app.delete("/api/servers/{sid}", dependencies=auth)
async def delete_server(sid: str):
    async with _store_lock:
        servers = [s for s in load_servers() if s["id"] != sid]
        save_servers(servers)
        drop_client(sid)
        _state.pop(sid, None)
    return {"ok": True}


# ---------------------------------------------------------------- RCON-Aktionen
class CommandIn(BaseModel):
    command: str = Field(min_length=1, max_length=4000)


@app.post("/api/servers/{sid}/command", dependencies=auth)
async def command(sid: str, data: CommandIn):
    s = get_server(sid)
    g = game_of(s)
    if g == "satisfactory":
        try:
            d = await sf_client(s).call("RunCommand", {"Command": data.command})
        except sfmod.SatisfactoryError as e:
            raise HTTPException(502, str(e))
        return {"output": (d or {}).get("commandResult", "")}
    if g == "minecraft":
        if not s.get("container"):
            raise HTTPException(400, "Minecraft-Konsole braucht den zugeordneten Docker-Container (unter „Bearbeiten“)")
        try:
            out = await docker_api.exec_cmd(s["container"], ["rcon-cli", data.command])
        except docker_api.DockerError as e:
            raise HTTPException(502, str(e))
        return {"output": re.sub(r"\x1b\[[0-9;]*m|§.", "", out).strip() or "(keine Ausgabe)"}
    if g == "teamspeak":
        try:
            out = (await ts_query(s).run(data.command))[0]
        except tsmod.TeamSpeakError as e:
            raise HTTPException(502, str(e))
        rows = tsmod.parse(out) if out.strip() else []
        return {"output": "\n".join(" ".join(f"{k}={v}" for k, v in r.items()) for r in rows) or "OK"}
    if not GAMES[g]["console"]:
        raise HTTPException(400, f"{GAMES[g]['label']} hat keine Remote-Konsole")
    out = await run(s, data.command)
    return {"output": out}


RE_PLAYER = re.compile(
    r"^\s*(\d+)\s+(\S+)\s+(\d+)\s+(\d+)\s+([A-Za-z]+)\s+(\d+)\s*(.*?)\s*'(.*)'\s*$")


def parse_status(text: str) -> dict:
    info: dict = {"hostname": None, "map": None, "humans": None, "bots": None,
                  "max_players": None, "version": None, "hibernating": None, "players": []}
    for line in text.splitlines():
        l = line.strip()
        if m := re.match(r"^hostname\s*:\s*(.*)$", l):
            info["hostname"] = m.group(1).strip()
        elif m := re.match(r"^version\s*:\s*(.*)$", l):
            info["version"] = m.group(1).strip()
        elif m := re.match(r"^map\s*:\s*(\S+)", l):
            info["map"] = info["map"] or m.group(1)
        elif m := re.match(r"^loaded spawngroup\(\s*\d+\)\s*:\s*SV:\s*\[\d+:\s*([^\s|]+)", l):
            info["map"] = info["map"] or m.group(1)
        elif m := re.match(r"^players\s*:\s*(\d+)\s+humans?,\s*(\d+)\s+bots?\s*\((\d+)\s+max\)(.*)", l):
            info["humans"], info["bots"], info["max_players"] = int(m.group(1)), int(m.group(2)), int(m.group(3))
            info["hibernating"] = "not hibernating" not in m.group(4) and "hibernating" in m.group(4)
        elif m := RE_PLAYER.match(line):
            uid, t, ping, loss, state, rate, adr, name = m.groups()
            if uid == "65535":
                continue
            is_bot = t.upper() == "BOT" or "BOT" in adr.upper() or (adr == "" and state.lower() == "active" and rate == "0")
            info["players"].append({
                "id": int(uid), "time": t, "ping": int(ping), "loss": int(loss), "state": state,
                "address": "" if is_bot else adr, "name": name, "bot": is_bot,
            })
    return info


STATE_CVARS = ["game_type", "game_mode", "sv_visiblemaxplayers", "mp_maxrounds", "sv_password", "bot_quota"]


async def _matchzy_info(s: dict) -> dict:
    """MatchZy-Erkennung (gecacht 5 Min.) + optional get5_status."""
    st = _state.setdefault(s["id"], {})
    mz = st.get("_matchzy")
    if not mz or time.time() - mz["checked"] > 300:
        try:
            out = await client_for(s).execute("css_plugins list")
        except RconError:
            out = ""
        m = re.search(r"MatchZy[^\n]*?(\d+\.\d+\.\d+)", out, re.I)
        mz = {"installed": bool(re.search(r"matchzy", out, re.I)), "version": m.group(1) if m else None,
              "checked": time.time()}
        st["_matchzy"] = mz
    info = {"installed": mz["installed"], "version": mz["version"], "match": None}
    if mz["installed"]:
        try:
            out = await client_for(s).execute("get5_status")
            j = out[out.find("{"):out.rfind("}") + 1] if "{" in out else ""
            if j:
                data = json.loads(j)
                info["match"] = {
                    "state": data.get("gamestate") or data.get("game_state"),
                    "matchid": data.get("matchid"),
                    "team1": (data.get("team1") or {}).get("name"),
                    "team2": (data.get("team2") or {}).get("name"),
                    "score1": (data.get("team1") or {}).get("series_score"),
                    "score2": (data.get("team2") or {}).get("series_score"),
                    "map_number": data.get("map_number"),
                }
        except (RconError, ValueError):
            pass
    return info


# ---------------------------------------------------------------- Beitreten / Namen aus dem Spiel
def _join_host(s: dict) -> str:
    h = s["host"]
    if h in ("127.0.0.1", "localhost", "::1", "0.0.0.0"):
        return _docker_host_ip()
    return h


def join_info(s: dict, password: str | None = None) -> dict:
    """Adresse + Steam-Link zum direkten Beitreten."""
    g, host, port = game_of(s), _join_host(s), int(s["port"])
    gp = s.get("game_port")
    if g == "cs2":
        p = gp or port
        url = f"steam://connect/{host}:{p}" + (f"/{password}" if password else "")
        return {"address": f"{host}:{p}", "url": url, "hint": "Startet CS2 und verbindet direkt."}
    if g in catmod.CATALOG:
        c = catmod.CATALOG[g]
        p = gp or port
        if c["join"][0] == "steam":
            return {"address": f"{host}:{p}", "url": f"steam://connect/{host}:{p}" + (f"/{password}" if password else ""),
                    "hint": f"Startet {c['label']} über Steam und verbindet direkt."}
        return {"address": f"{host}:{p}", "url": f"steam://run/{c['appid']}" if c.get("appid") and c["join"][0] == "addr" and c.get("image", "").startswith("ghcr.io/ich777") else None,
                "hint": c.get("hint") or f"Im Spiel {c['label']} → Mehrspieler → Server/IP hinzufügen: {host}:{p}"}
    if g == "minecraft":
        p = gp or port
        return {"address": f"{host}:{p}" if p != 25565 else host, "url": None,
                "hint": "Minecraft → Multiplayer → Server hinzufügen → diese Adresse eintragen."}
    if g == "teamspeak":
        p = gp or 9987
        return {"address": f"{host}:{p}" if p != 9987 else host, "url": f"ts3server://{host}?port={p}",
                "hint": "Öffnet TeamSpeak 3 und verbindet direkt."}
    if g == "tf2":
        p = gp or port
        url = f"steam://connect/{host}:{p}" + (f"/{password}" if password else "")
        return {"address": f"{host}:{p}", "url": url, "hint": "Startet TF2 und verbindet direkt."}
    if g == "factorio":
        p = gp or 34197
        return {"address": f"{host}:{p}", "url": f"steam://run/427520//--mp-connect%20{host}:{p}/",
                "hint": "Startet Factorio über Steam und verbindet direkt."}
    if g == "valheim":
        p = gp or (port - 1)
        return {"address": f"{host}:{p}", "url": f"steam://run/892970//+connect%20{host}:{p}/",
                "hint": "Startet Valheim und verbindet – Passwort im Spiel eingeben."}
    if g == "wreckfest":
        # Wreckfest beantwortet keine Steam-Serverabfragen -> steam://connect scheitert ("App-ID ungültig").
        # Daher Spiel starten und im Server-Browser des Spiels nach dem Namen suchen.
        p = gp or 33540
        return {"address": f"{host}:{p}", "url": "steam://run/228380",
                "hint": "Startet Wreckfest – dann Mehrspieler → Server-Browser und nach dem Servernamen suchen."
                        + (f" Passwort: {password}" if password else "")}
    if g == "satisfactory":
        p = gp or port
        return {"address": f"{host}:{p}", "url": None,
                "hint": "Im Spiel: Server-Manager → Server hinzufügen → diese Adresse eintragen."}
    return {"address": f"{host}:{port}", "url": None, "hint": ""}


_renaming: set[str] = set()


async def _sync_name(s: dict, name: str | None):
    """Server in der Liste so nennen wie im Spiel."""
    name = (name or "").strip()[:64]
    if not name or not s.get("name_from_game", True) or name == s.get("name") or s["id"] in _renaming:
        return
    _renaming.add(s["id"])
    try:
        async with _store_lock:
            servers = load_servers()
            for x in servers:
                if x["id"] == s["id"]:
                    x["name"] = name
            save_servers(servers)
        s["name"] = name
    finally:
        _renaming.discard(s["id"])


def _server_nr(s: dict, hostname: str | None) -> int:
    """Nummer des Servers: aus dem bisherigen Namen (#3), sonst aus dem Container (…CS3), sonst Reihenfolge."""
    for txt in (hostname or "", s.get("name") or ""):
        if m := re.search(r"#\s*(\d+)", txt):
            return int(m.group(1))
    if m := re.search(r"(\d+)\s*$", s.get("container") or ""):
        return int(m.group(1))
    cs = [x["id"] for x in load_servers() if x.get("game", "cs2") == "cs2"]
    return cs.index(s["id"]) + 1 if s["id"] in cs else 1


def _mode_hostname(s: dict, hostname: str | None, mode_label: str, settings: dict) -> str | None:
    pattern = (settings.get("hostname_pattern") or "").strip()
    if not pattern:
        return None
    name = pattern.replace("{nr}", str(_server_nr(s, hostname))).replace("{mode}", mode_label)
    return re.sub(r'["\\;]', "", name).strip()[:63] or None


async def collect_state(s: dict, apply_auto: bool = False, with_matchzy: bool = False) -> dict:
    """Status + wichtige Cvars lesen, optional Spieleranzahl automatisch setzen."""
    if game_of(s) != "cs2":
        return await collect_generic(s)
    c = client_for(s)
    raw = await c.execute("status")
    st = parse_status(raw)
    cv = automation.parse_cvars(await c.execute(";".join(STATE_CVARS)), STATE_CVARS)
    settings = automation.get_settings()
    mode = automation.mode_for(cv["game_type"], cv["game_mode"], settings)
    target, reason = automation.target_players(st["map"], cv["game_type"], cv["game_mode"], settings)
    capped = False
    if target and st["max_players"] and target > st["max_players"]:
        target, capped = st["max_players"], True
    visible = int(float(cv["sv_visiblemaxplayers"])) if cv["sv_visiblemaxplayers"] not in (None, "") else None
    applied = None
    auto_on = s.get("auto_slots", True)
    if apply_auto and auto_on and target and visible != target:
        await c.execute(f"sv_visiblemaxplayers {target}")
        applied, visible = target, target
        log.info("%s: sv_visiblemaxplayers %s (%s)", s["name"], target, reason)
    ws = _last_workshop.get(s["id"])
    base = automation.map_basename(st["map"])
    if ws:
        if not ws.get("map"):
            if base and base != ws.get("from_map"):
                ws["map"] = base                      # neue Map ist geladen -> zuordnen
            elif time.time() - ws.get("at", 0) > 300:
                ws = _last_workshop.pop(s["id"], None) and None
        elif base and base != ws["map"]:
            ws = _last_workshop.pop(s["id"], None) and None   # inzwischen andere Map
        if ws and not ws.get("map"):
            ws = None                                 # noch nicht geladen -> nicht anzeigen
    result = {
        "online": True, "raw": raw, **st,
        "mode": {"key": mode["key"], "label": mode["label"]} if mode else
                {"key": None, "label": f"type {cv['game_type']} / mode {cv['game_mode']}"},
        "game_type": cv["game_type"], "game_mode": cv["game_mode"],
        "visible_players": visible, "maxrounds": cv["mp_maxrounds"],
        "password_set": bool(cv["sv_password"]), "bot_quota": cv["bot_quota"],
        "auto": {"enabled": auto_on, "target": target, "reason": reason, "capped": capped, "applied": applied},
        "join": join_info(s, cv["sv_password"] or None),
        "workshop": ws,
        "updated": time.time(),
    }
    if apply_auto and mode and s.get("mode_name", True):
        want = _mode_hostname(s, st.get("hostname"), mode["label"], settings)
        if want and want != st.get("hostname"):
            await c.execute(f'hostname "{want}"')
            log.info("%s: hostname -> %s", s["name"], want)
            st["hostname"] = result["hostname"] = want
    if with_matchzy:
        result["matchzy"] = await _matchzy_info(s)
    elif "matchzy" in _state.get(s["id"], {}):
        result["matchzy"] = _state[s["id"]]["matchzy"]
    prev = _state.get(s["id"], {})
    _state[s["id"]] = {**{k: v for k, v in prev.items() if k.startswith("_")}, **result}
    await _sync_name(s, st.get("hostname"))
    return result


async def collect_generic(s: dict) -> dict:
    g = game_of(s)
    try:
        if g == "factorio":
            try:
                st = await adapters.factorio_status(client_for(s))
            except RconError:
                if not (s.get("container") and docker_api.available()):
                    raise
                st = await adapters.factorio_container_status(s["container"])
        elif g == "satisfactory":
            st = await sfmod.status(sf_client(s))
        elif g == "valheim":
            try:
                st = await adapters.valheim_status(s["host"], int(s["port"]))
            except adapters.a2s.A2SError:
                if not (s.get("container") and docker_api.available()):
                    raise
                st = await adapters.valheim_container_status(s["container"])
        elif g == "tf2":
            try:
                st = await adapters.tf2_rcon_status(client_for(s))
            except RconError:
                st = await adapters.tf2_status(s["host"], int(s.get("game_port") or s["port"]))
        elif g == "minecraft":
            st = await mcmod.status(s["host"], int(s.get("game_port") or s["port"]))
        elif g in catmod.CATALOG:
            c = catmod.CATALOG[g]
            kind = c["status"][0]
            if kind == "a2s":
                try:
                    st = await adapters.generic_a2s_status(s["host"], int(s["port"]), c["label"])
                except adapters.a2s.A2SError:
                    if not (s.get("container") and docker_api.available()):
                        raise
                    cport = next((p[4] for p in c["ports"] if p[0] == c["status"][1]), None)
                    try:
                        info = await adapters.a2s.info_inside(s["container"], cport)
                    except docker_api.DockerError as e:
                        raise adapters.a2s.A2SError(str(e)) from e
                    st = adapters.from_info(info, c["label"], "Abfrage im Container (von außen keine Antwort)")
            elif kind == "tcp":
                st = await adapters.tcp_status(s["host"], int(s["port"]), c["label"])
            elif kind == "ac":
                st = await adapters.ac_status(s["host"], int(s["port"]))
            else:
                if not s.get("container"):
                    raise RconError("Kein Container zugeordnet – Status nicht ermittelbar")
                try:
                    info = await docker_api.inspect(s["container"])
                except docker_api.DockerError as e:
                    raise RconError(str(e)) from e
                if not (info.get("State") or {}).get("Running"):
                    raise RconError("Container läuft nicht")
                st = {"map": "–", "humans": 0, "bots": 0, "max_players": 0, "players": [], "version": None, "hostname": None,
                      "mode": {"key": "game", "label": c["label"]}, "extra": {"Container": "läuft"}, "updated": time.time(),
                      "players_unknown": True}
        elif g == "teamspeak":
            if not s.get("password") and s.get("container") and docker_api.available():
                await _ts_password_from_logs(s)
            try:
                st = await tsmod.status(ts_query(s))
            except tsmod.TeamSpeakError as e:
                if "permission" in str(e) or "id 520" in str(e) or "id 2568" in str(e):
                    raise tsmod.TeamSpeakError("ServerQuery-Login fehlt/falsch – unter „Bearbeiten“ das serveradmin-Passwort eintragen "
                                               "(steht beim allerersten Start im Container-Log)") from e
                raise
        elif g == "wreckfest":
            if s.get("container") and docker_api.available():
                st = await adapters.wreckfest_container_status(s["container"])
            else:
                st = await adapters.wreckfest_status(s["host"], int(s["port"]))
        else:
            raise RconError("Unbekanntes Spiel")
    except (sfmod.SatisfactoryError, adapters.a2s.A2SError, mcmod.MinecraftError, tsmod.TeamSpeakError) as e:
        raise RconError(str(e)) from e
    if g == "satisfactory" and not st.get("hostname"):
        q = await scanner.satisfactory_query(s["host"], int(s["port"]))
        if q:
            st["hostname"] = q["name"]
    pw = st.pop("password", None) if g == "wreckfest" else None
    result = {"online": True, "game": g, **st, "join": join_info(s, pw)}
    await _sync_name(s, st.get("hostname"))
    prev = _state.get(s["id"], {})
    _state[s["id"]] = {**{k: v for k, v in prev.items() if k.startswith("_")}, **result}
    return result


@app.get("/api/servers/{sid}/status", dependencies=auth)
async def status(sid: str):
    s = get_server(sid)
    try:
        return await collect_state(s, apply_auto=True, with_matchzy=True)
    except RconAuthError as e:
        drop_client(sid)
        raise HTTPException(502, str(e))
    except RconError as e:
        _state[sid] = {**_state.get(sid, {}), "online": False, "error": str(e), "updated": time.time()}
        raise HTTPException(502, str(e))


@app.get("/api/overview", dependencies=auth)
async def overview():
    out = []
    for s in load_servers():
        st = _state.get(s["id"], {})
        item = {"server": public(s), **{k: v for k, v in st.items() if not k.startswith("_") and k != "raw"}}
        if s.get("container"):
            ld = _loads.get(s["container"])
            item["load"] = {k: v for k, v in ld.items() if not k.startswith("_")} if ld else None
            item["install"] = install_watch.state.get(s["container"])
        probs = list((diagnostics.state.get(s.get("container") or "") or {}).get("problems") or [])
        if st.get("online"):
            probs += diagnostics.status_hints(game_of(s), st)
        item["problems"] = probs
        out.append(item)
    return out


# ---------------------------------------------------------------- Last (Host + Container)
_loads: dict[str, dict] = {}   # Containername -> {cpu, cores, mem_mb, state}


async def _container_load(name: str):
    """Status per inspect, Last/Netz aus dem Live-Stream (livestats)."""
    try:
        info = await docker_api.inspect(name)
        running = info.get("State", {}).get("Running")
        d = livestats.data.get(name) or {}
        fresh = running and d.get("running") and time.time() - d.get("t", 0) < 6
        _loads[name] = {"state": info.get("State", {}).get("Status"),
                        "cpu": d.get("cpu") if fresh else (0 if not running else None),
                        "cpu_host": d.get("cpu_host") if fresh else (0 if not running else None),
                        "mem_mb": d.get("mem_mb") if fresh else (0 if not running else None),
                        "updated": time.time(),
                        "net_host": (info.get("HostConfig") or {}).get("NetworkMode") == "host",
                        "rx_bps": round(d["rx_bps"]) if fresh and d.get("rx_bps") is not None else None,
                        "tx_bps": round(d["tx_bps"]) if fresh and d.get("tx_bps") is not None else None}
    except docker_api.DockerError as e:
        _loads[name] = {"state": "unbekannt", "error": str(e), "updated": time.time()}


async def live_loop():
    """Sekundentakt: Host-CPU/RAM/Netz, Live-Streams der Container nachführen."""
    n = 0
    while True:
        try:
            hoststats.sample()
            livestats.sample_host()
            if n % 2 == 0:
                livestats.sample_io()
            if n % 5 == 0 and docker_api.available():
                names = {s["container"] for s in load_servers() if s.get("container")}
                if cache_stats.state.get("container"):
                    names.add(cache_stats.state["container"])
                names.add(prefill.NAME)
                livestats.ensure(names)
        except Exception:  # noqa: BLE001
            log.exception("Live-Messung")
        n += 1
        await asyncio.sleep(1)


async def load_loop():
    """Host-Last alle 2,5 s, Container-Last/Netz und Lancache alle 5 s."""
    n = 0
    while True:
        await asyncio.sleep(2.5)
        n += 1
        if n % 2 == 0 and docker_api.available():
            await cache_stats.poll(automation.get_settings().get("cache_container") or "")
            st_ = cache_stats.storage
            if cache_stats.state["container"] and not st_["running"] and (st_["updated"] is None or time.time() - st_["updated"] > 1800):
                st_["updated"] = st_["updated"] or 0.0
                asyncio.create_task(cache_stats.poll_storage())
            if (cache_stats.state["container"] and cache_history.meta["bf_done"] and not cache_history.meta.get("dbf_done")
                    and not cache_stats._dbf_running):
                asyncio.create_task(cache_stats.backfill_depots())
            if cache_stats.state["container"] and not cache_history.meta["bf_done"] and not cache_stats._bf_running:
                asyncio.create_task(cache_stats.backfill())
            cache_history.maybe_save()
        if n % 2 == 0 and docker_api.available():
            names = sorted({s["container"] for s in load_servers() if s.get("container")})
            lc = cache_stats.state.get("container")
            if lc and lc not in names:
                names.append(lc)
            if names:
                await asyncio.gather(*(_container_load(x) for x in names))
                await asyncio.gather(*(install_watch.poll(x) for x in names
                                       if (_loads.get(x) or {}).get("state") in ("running", "restarting")))
            for k in list(_loads):
                if k not in names:
                    _loads.pop(k, None)
        if n % 2 == 0 and docker_api.available():
            try:
                lc_ = cache_stats.state.get("container")
                cd = livestats.data.get(lc_ or "") or {}
                pd = livestats.data.get(prefill.NAME) or {}
                dls = [x["name"] for x in load_servers() if x.get("container") and
                       ((install_watch.state.get(x["container"]) or {}).get("progress") or {}).get("phase") == "downloading"]
                lh = livestats.host
                await prefill.yield_check(cd.get("tx_bps"), pd.get("rx_bps"), dls,
                                          lh.get("tx_bps") if lh.get("source") == "host" else None)
            except docker_api.DockerError:
                pass
            except Exception:  # noqa: BLE001
                log.exception("SteamPrefill-Pause")
        if n % 24 == 3 and docker_api.available():
            try:
                await prefill_scheduler()
            except Exception:  # noqa: BLE001
                log.exception("SteamPrefill-Zeitplan")
        if n % 12 == 1 and docker_api.available():
            todo = [(x["container"], game_of(x)) for x in load_servers() if x.get("container")]
            cips = await lancache_dns() or []
            dl = lambda c: bool(((install_watch.state.get(c) or {}).get("progress") or {}).get("phase") == "downloading")  # noqa: E731
            await asyncio.gather(*(diagnostics.check(c, g, dl(c), cips) for c, g in todo), return_exceptions=True)
        h = hoststats.state
        lc = cache_stats.state.get("container")
        lh = livestats.host
        metrics.record_host(h.get("cpu"), h.get("mem_used_mb"), h.get("mem_total_mb"),
                            round(lh["rx_bps"]) if lh.get("rx_bps") is not None else None,
                            round(lh["tx_bps"]) if lh.get("tx_bps") is not None else None)
        if n % 2 == 0:
            if lc and _loads.get(lc):
                metrics.record("_cache", {}, _loads[lc])
                ld = _loads[lc]
                if ld.get("rx_bps") is not None:
                    cache_history.add_net((ld["rx_bps"] or 0) * 5, (ld["tx_bps"] or 0) * 5)
            servers = load_servers()
            for s in servers:
                metrics.record(s["id"], _state.get(s["id"], {}), _loads.get(s.get("container") or ""))
            metrics.forget({s["id"] for s in servers})
            metrics.maybe_save()


# ---------------------------------------------------------------- Server komplett löschen
def _path_check(path: str, other_sources: list[str]) -> str | None:
    """None = darf gelöscht werden, sonst Grund."""
    p = os.path.normpath(path or "")
    base = os.path.normpath(automation.get_settings().get("games_base") or "/mnt/grohlan")
    if not p.startswith("/mnt/"):
        return "nur Ordner unter /mnt werden gelöscht"
    if len(p.strip("/").split("/")) < 3:
        return "Ordner zu weit oben (geschützt)"
    if p == base or os.path.dirname(p) == base:
        return "Basis- bzw. Spielordner ist geschützt"
    for o in other_sources:
        o = os.path.normpath(o)
        if o == p or o.startswith(p + "/"):
            return "wird noch von einem anderen Container genutzt"
    return None


async def _delete_plan(s: dict) -> dict:
    plan = {"server": public(s), "container": None, "paths": [], "volumes": [], "docker": docker_api.available()}
    c = s.get("container")
    if not (c and docker_api.available()):
        return plan
    try:
        own = await docker_api.mounts(c)
    except docker_api.DockerError as e:
        plan["container_error"] = str(e)
        return plan
    plan["container"] = c
    others = await docker_api.all_mounts()
    other_src = [m["source"] for n, ms in others.items() if n != c for m in ms if m["type"] == "bind" and m["source"]]
    other_vol = {m["name"] for n, ms in others.items() if n != c for m in ms if m["type"] == "volume"}
    binds = [m["source"] for m in own if m["type"] == "bind" and m["source"]]
    # mehrere Unterordner eines gemeinsamen Datenordners (z. B. config + server) -> den Datenordner anbieten
    parents = {os.path.dirname(os.path.normpath(b)) for b in binds}
    if len(binds) > 1 and len(parents) == 1 and _path_check(next(iter(parents)), other_src) is None:
        binds = [next(iter(parents))]
    for b in binds:
        plan["paths"].append({"path": b, "blocked": _path_check(b, other_src)})
    for m in own:
        if m["type"] == "volume" and m["name"]:
            plan["volumes"].append({"name": m["name"], "blocked": "wird noch von einem anderen Container genutzt"
                                    if m["name"] in other_vol else None})
    return plan


@app.get("/api/servers/{sid}/delete-preview", dependencies=auth)
async def delete_preview(sid: str):
    return await _delete_plan(get_server(sid))


class DeleteIn(BaseModel):
    remove_container: bool = False
    delete_data: bool = False
    confirm: str = ""


async def _delete_job(job: dict, s: dict, plan: dict, data: DeleteIn):
    try:
        if data.remove_container and plan["container"]:
            _job_log(job, f"Container {plan['container']} stoppen und entfernen")
            await docker_api.remove_container(plan["container"])
        if data.delete_data:
            for p in plan["paths"]:
                if p["blocked"]:
                    _job_log(job, f"Übersprungen: {p['path']} ({p['blocked']})")
                    continue
                parent, base = os.path.dirname(p["path"]), os.path.basename(p["path"])
                _job_log(job, f"Lösche {p['path']} … (kann bei großen Spielen dauern)")
                await docker_api.run_helper([f"{parent}:/p"], ["rm", "-rf", f"/p/{base}"], timeout=3600)
            for v in plan["volumes"]:
                if not v["blocked"]:
                    _job_log(job, f"Lösche Volume {v['name']}")
                    await docker_api.remove_volume(v["name"])
        async with _store_lock:
            save_servers([x for x in load_servers() if x["id"] != s["id"]])
        drop_client(s["id"])
        _state.pop(s["id"], None)
        job["done"] = True
        _job_log(job, "Fertig – Server gelöscht")
    except docker_api.DockerError as e:
        job["error"], job["done"] = str(e), True
        _job_log(job, "Fehler: " + str(e))


@app.post("/api/servers/{sid}/delete", dependencies=auth)
async def delete_full(sid: str, data: DeleteIn):
    s = get_server(sid)
    plan = await _delete_plan(s)
    if data.delete_data and data.confirm.strip() != s["name"]:
        raise HTTPException(400, "Zum Löschen der Daten bitte den Servernamen exakt eintippen")
    if not data.remove_container and not data.delete_data:
        async with _store_lock:
            save_servers([x for x in load_servers() if x["id"] != sid])
        drop_client(sid)
        _state.pop(sid, None)
        return {"done": True}
    if data.delete_data and not data.remove_container and plan["container"]:
        raise HTTPException(400, "Daten können nur zusammen mit dem Container gelöscht werden")
    jid = secrets.token_hex(6)
    job = {"id": jid, "game": game_of(s), "title": f"{s['name']} löschen", "log": [], "step": "", "done": False,
           "error": None, "server_id": None}
    _jobs[jid] = job
    asyncio.create_task(_delete_job(job, s, plan, data))
    return job


@app.get("/api/activity", dependencies=auth)
async def activity():
    """Laufende Installationen/Updates, Fehler aus den Logs und Anlege-Jobs (für die Seitenleiste)."""
    items = []
    for s in load_servers():
        c = s.get("container")
        st = install_watch.state.get(c) if c else None
        if st and (st.get("progress") or st.get("errors")):
            items.append({"server_id": s["id"], "name": s["name"], "game": game_of(s), "container": c,
                          "progress": st.get("progress"), "errors": st.get("errors") or []})
    try:
        pst = await prefill.container_state()
        if pst and pst.get("running"):
            pp = prefill.parse_progress(await prefill.log(1500))
            cur = pp["current"]
            d = livestats.data.get(prefill.NAME) or {}
            done = sum(1 for a in pp["apps"] if a["state"] in ("fertig", "aktuell"))
            if prefill.auto.get("paused"):
                cur = dict(cur or {"name": "", "pct": 0.0}); cur["name"] = (cur["name"] + " – pausiert").strip(" –")
            items.append({"server_id": None, "name": "SteamPrefill" + (f": {cur['name']}" if cur else ""), "game": "prefill",
                          "container": prefill.NAME, "errors": [], "prefill": True,
                          "progress": {"label": "Vorladen", "pct": cur["pct"] if cur else 0.0, "rate": d.get("rx_bps"),
                                       "apps_done": done, "apps_total": len(pp["apps"])}})
    except docker_api.DockerError:
        pass
    jobs = [{"id": j["id"], "game": j["game"], "step": j["step"], "error": j["error"], "done": j["done"],
             "server_id": j["server_id"], "title": j.get("title")} for j in _jobs.values() if not j["done"] or j["error"]]
    return {"items": items, "jobs": jobs[-5:]}


@app.post("/api/activity/dismiss/{container}", dependencies=auth)
async def activity_dismiss(container: str):
    install_watch.dismiss(container)
    return {"ok": True}


@app.get("/api/metrics", dependencies=auth)
async def server_metrics(minutes: int = 360):
    if minutes <= 10:      # Live-Ansicht aus dem Sekundenpuffer
        sec = max(60, minutes * 60)
        out = {}
        for s_ in load_servers():
            c = s_.get("container") or ""
            ser = livestats.series(c, sec) if c in livestats.rings else {"cpu": [], "mem": [], "rx": [], "tx": [], "samples": 0}
            m = metrics.summary(s_["id"], 60)
            hum = (_state.get(s_["id"]) or {}).get("humans") if (_state.get(s_["id"]) or {}).get("online") else 0
            out[s_["id"]] = {**m, **{k: ser[k] for k in ("cpu", "mem", "rx", "tx")}, "players": [hum or 0] * len(ser["cpu"] or [0]),
                             "minutes": sec / 60, "samples": max(m.get("samples") or 0, ser["samples"])}
        out["_host"] = {**livestats.series("_host", sec)}
        io_s = livestats.series("_io", sec)
        out["_io"] = {"rtt": io_s["cpu"], "util": io_s["mem"], "nfs": io_s["rx"], "retrans": io_s["tx"], "samples": io_s["samples"],
                      "minutes": io_s["minutes"]}
        lc = cache_stats.state.get("container")
        if lc and lc in livestats.rings:
            out["_cache"] = livestats.series(lc, sec)
        return out
    minutes = max(30, min(minutes, 24 * 60))
    out = {s["id"]: metrics.summary(s["id"], minutes) for s in load_servers()}
    out["_host"] = metrics.summary("_host", minutes)
    out["_cache"] = metrics.summary("_cache", minutes)
    return out


GAME_APPS = {"cs2": 730, "tf2": 440, "valheim": 892970, "wreckfest": 228380, "factorio": 427520, "satisfactory": 526870,
             **{k: c["appid"] for k, c in catmod.CATALOG.items() if c.get("appid")}}


@app.get("/api/gameicons", dependencies=auth)
async def game_icons(apps: str = ""):
    """Icons der Spiele (Steam) – für Seitenleiste, Karten und Lancache-Liste."""
    ids = sorted({int(x) for x in apps.split(",") if x.strip().isdigit()} | set(GAME_APPS.values()))[:60]
    try:
        ic = await depots.icons(ids)
    except Exception:  # noqa: BLE001
        ic = {}
    return {"apps": ic, "games": {g: ic.get(str(a), "") for g, a in GAME_APPS.items()}}


@app.get("/api/live", dependencies=auth)
async def live_values():
    """Kompakte Sekundenwerte für die Anzeigen (Seitenleiste, Karten)."""
    h = hoststats.state
    now = time.time()
    srv = {}
    for s_ in load_servers():
        d = livestats.data.get(s_.get("container") or "")
        if d and now - d.get("t", 0) < 6:
            srv[s_["id"]] = {k: d.get(k) for k in ("cpu_host", "cpu", "mem_mb", "rx_bps", "tx_bps", "running")}
    lc = cache_stats.state.get("container")
    cd = livestats.data.get(lc or "") or {}
    return {"t": now, "cpu": h.get("cpu"), "mem_used_mb": h.get("mem_used_mb"), "mem_total_mb": h.get("mem_total_mb"),
            "net": {k: livestats.host.get(k) for k in ("rx_bps", "tx_bps", "source")},
            "cache": {"rx_bps": cd.get("rx_bps"), "tx_bps": cd.get("tx_bps")} if cd else None, "servers": srv,
            "io": livestats.io}


@app.get("/api/cache", dependencies=auth)
async def cache_metrics():
    if not docker_api.available():
        return {"error": "Docker-Socket nicht eingebunden", "container": None}
    if cache_stats.state["updated"] is None:
        await cache_stats.poll(automation.get_settings().get("cache_container") or "")
    out = cache_stats.summary()
    out["storage"] = _storage_view()
    try:
        out["games_24h"] = _enrich_games(depots.games(cache_history.series("24h").get("depots") or {})[:6])
        asyncio.create_task(depots.run())
    except Exception:  # noqa: BLE001
        out["games_24h"] = []
    ld = livestats.data.get(out.get("container") or "") or {}
    fresh = ld and time.time() - ld.get("t", 0) < 6
    out["net"] = {"rx_bps": ld.get("rx_bps") if fresh else None, "tx_bps": ld.get("tx_bps") if fresh else None,
                  "host_mode": bool(ld) and not ld.get("net")}
    hosts = {x["host"] for x in load_servers()}
    if out.get("live_clients"):
        out["live_clients"] = await netnames.annotate(out["live_clients"], hosts)
    for k in ("last_hour", "last_day"):
        if out.get(k, {}).get("clients"):
            out[k]["clients"] = await netnames.annotate(out[k]["clients"], hosts)
    return out


async def lancache_dns() -> list[str] | None:
    """DNS für Spielserver-Container: Einstellung, sonst automatisch der Docker-Host, wenn dort lancache-dns läuft."""
    manual = (automation.get_settings().get("container_dns") or "").strip()
    if manual:
        return [x.strip() for x in re.split(r"[,\s]+", manual) if x.strip()]
    if not docker_api.available():
        return None
    try:
        cs = await docker_api.list_containers()
    except docker_api.DockerError:
        return None
    dns = [c for c in cs if c["state"] == "running" and ("lancache-dns" in (c["image"] or "").lower()
                                                         or ("lancache" in c["name"].lower() and "dns" in c["name"].lower()))]
    if not dns:
        return None
    hosts = [x["host"] for x in load_servers() if re.fullmatch(r"\d+\.\d+\.\d+\.\d+", x.get("host") or "")]
    if not hosts:
        return None
    return [max(set(hosts), key=hosts.count)]


DNS_CHECK_SH = "getent hosts lancache.steamcontent.com 2>/dev/null | head -1 || nslookup lancache.steamcontent.com 2>/dev/null | tail -2; echo '#'; grep nameserver /etc/resolv.conf | head -3"


@app.get("/api/cache/log", dependencies=auth)
async def cache_log(lines: int = 40):
    """Letzte Zeilen des Lancache-access.log (Live-Ansicht)."""
    try:
        return {"container": cache_stats.state["container"], "log": await cache_stats.tail(lines)}
    except docker_api.DockerError as e:
        raise HTTPException(502, str(e))


@app.get("/api/cache/dns-check", dependencies=auth)
async def cache_dns_check():
    """Prüft je Spielserver-Container, ob Downloads über den Lancache laufen (lancache.steamcontent.com auflösbar)."""
    want = await lancache_dns()
    names = sorted({(x["container"], x["name"]) for x in load_servers() if x.get("container")})

    async def one(cname, sname):
        item = {"container": cname, "server": sname, "dns": None, "resolves": None, "ok": None, "managed": False}
        try:
            info = await docker_api.inspect(cname)
            item["dns"] = (info.get("HostConfig") or {}).get("Dns") or []
            item["managed"] = (info.get("Config", {}).get("Labels") or {}).get("gsm.managed") == "1"
            item["stack"] = (info.get("Config", {}).get("Labels") or {}).get("com.docker.compose.project")
            if not info.get("State", {}).get("Running"):
                item["note"] = "Container läuft nicht"
                return item
            out = await asyncio.wait_for(docker_api.exec_cmd(cname, ["sh", "-c", DNS_CHECK_SH]), 8)
            res, _, ns = out.partition("#")
            m = re.search(r"(\d+\.\d+\.\d+\.\d+)", res)
            item["resolves"] = m.group(1) if m else None
            item["nameserver"] = re.findall(r"nameserver\s+(\S+)", ns)
            item["ok"] = bool(m) and ipaddress.ip_address(m.group(1)).is_private
            if item["ok"]:
                ip = m.group(1)
                hb = (f"(curl -s -m 4 -D - -o /dev/null -H 'Host: lancache.steamcontent.com' http://{ip}/lancache-heartbeat 2>/dev/null"
                      f" || wget -S -q -T 4 -O /dev/null --header='Host: lancache.steamcontent.com' http://{ip}/lancache-heartbeat 2>&1"
                      f" || bash -c 'exec 3<>/dev/tcp/{ip}/80 && printf \"GET /lancache-heartbeat HTTP/1.1\\r\\nHost: lancache.steamcontent.com\\r\\nConnection: close\\r\\n\\r\\n\" >&3 && timeout 4 head -c 400 <&3' 2>&1) | head -c 600;"
                      " echo '#CDN'; getent hosts cache1-fra1.steamcontent.com 2>/dev/null | head -1; getent hosts steampipe.akamaized.net 2>/dev/null | head -1")
                out2 = await asyncio.wait_for(docker_api.exec_cmd(cname, ["sh", "-c", hb]), 10)
                head, _, cdn = out2.partition("#CDN")
                item["reach"] = bool(re.search(r"HTTP/1\.[01] 204|X-LanCache", head, re.I))
                item["reach_raw"] = head.strip().splitlines()[0][:120] if head.strip() else "keine Antwort"
                item["cdn"] = re.findall(r"(\d+\.\d+\.\d+\.\d+)\s+(\S+)", cdn)
                if not item["reach"]:
                    item["ok"] = False
                    item["note"] = f"DNS stimmt, aber Lancache auf {ip}:80 aus dem Container nicht erreichbar ({item['reach_raw']})"
        except (docker_api.DockerError, asyncio.TimeoutError, ValueError) as e:
            item["note"] = str(e) or "Zeitüberschreitung"
        return item

    return {"dns": want, "items": await asyncio.gather(*(one(c, n) for c, n in names))}


@app.post("/api/servers/{sid}/container/use-lancache", dependencies=auth)
async def container_use_lancache(sid: str):
    """Vom Tool angelegten Container mit Lancache-DNS neu erstellen (Daten bleiben, liegen im Ordner)."""
    name = _container_of(sid)
    dns = await lancache_dns()
    if not dns:
        raise HTTPException(400, "Kein Lancache-DNS gefunden – unter „Automatik & Einstellungen“ eintragen")
    try:
        info = await docker_api.inspect(name)
        cfg, hc = info["Config"], dict(info["HostConfig"])
        if (cfg.get("Labels") or {}).get("gsm.managed") != "1":
            raise HTTPException(400, "Nur für Container, die dieses Tool angelegt hat – bei Portainer-Stacks "
                                     f"im Stack „dns: [{dns[0]}]“ eintragen")
        hc["Dns"] = dns
        spec = {k: cfg.get(k) for k in ("Image", "Env", "Cmd", "Entrypoint", "ExposedPorts", "Labels", "WorkingDir",
                                         "User", "Tty", "OpenStdin", "StopSignal", "Volumes") if cfg.get(k) is not None}
        spec["HostConfig"] = hc
        tmp = f"{name}-alt-{int(time.time())}"
        await docker_api._req("POST", f"/containers/{name}/stop", params={"t": "30"}, timeout=60)
        await docker_api._req("POST", f"/containers/{name}/rename", params={"name": tmp})
        try:
            await docker_api.create_container(name, spec)
        except docker_api.DockerError:
            await docker_api._req("POST", f"/containers/{tmp}/rename", params={"name": name})
            await docker_api._req("POST", f"/containers/{name}/start", timeout=60)
            raise
        await docker_api._req("DELETE", f"/containers/{tmp}", params={"force": "1"}, timeout=60)
    except docker_api.DockerError as e:
        raise HTTPException(502, str(e))
    drop_client(sid)
    return {"ok": True, "dns": dns}


@app.get("/api/cache/history", dependencies=auth)
async def cache_history_api(range: str = "30d"):
    if range not in cache_history.RANGES:
        raise HTTPException(400, "Zeitraum unbekannt")
    out = cache_history.series(range)
    out["container"] = cache_stats.state["container"]
    out["error"] = cache_stats.state["error"]
    out["disk_now"] = cache_stats.state["disk"]
    out["storage"] = _storage_view()
    out["games"] = _enrich_games(depots.games(out.pop("depots", {}) or {})[:30])
    asyncio.create_task(depots.run())
    out["clients"] = await netnames.annotate(out["clients"], {x["host"] for x in load_servers()})
    return out


def _storage_view() -> dict:
    st = {k: v for k, v in cache_stats.storage.items() if k != "running"} | {"busy": cache_stats.storage["running"]}
    # Schätzung ohne Festplattenzugriff: alles je aus dem Internet Geholte (365 Tage), höchstens das Limit
    try:
        est = sum(v.get("mb", 0) for v in cache_history._h.values())
    except Exception:  # noqa: BLE001
        est = None
    if est is not None and st.get("limit"):
        est = min(est, st["limit"])
    st["estimate"] = est
    return st


@app.post("/api/cache/measure", dependencies=auth)
async def cache_measure():
    """Cache-Ordner einmal genau messen (du, niedrige I/O-Priorität – dauert bei vielen TB lange)."""
    if cache_stats.storage["running"]:
        return {"ok": True, "busy": True}
    asyncio.create_task(cache_stats.poll_storage(full=True))
    return {"ok": True}


def _enrich_games(games: list[dict]) -> list[dict]:
    """Wie weit ist jedes Spiel im Cache? -> alles, was je aus dem Internet geholt wurde, im Verhältnis zur Spielgröße."""
    alltime = {g["app"]: g for g in depots.games(cache_history.series("365d").get("depots") or {}) if g.get("app")}
    for g in games:
        a = g.get("app")
        size = depots.app_size(a) if a else None
        stored = (alltime.get(a) or {}).get("miss") or 0
        g["size"] = size
        g["stored"] = stored
        g["cached_pct"] = round(min(100.0, stored / size * 100), 1) if size else None
    asyncio.create_task(depots.ensure_sizes([g["app"] for g in games if g.get("app") and not g.get("size")]))
    return games


@app.get("/api/host", dependencies=auth)
async def host_load():
    h = dict(hoststats.state)
    if h.get("updated") is None:
        h = dict(hoststats.sample())
    games = [v for v in _loads.values() if v.get("cpu") is not None]
    h["games"] = {"containers": len(_loads), "running": sum(1 for v in _loads.values() if v.get("state") == "running"),
                  "cpu_host": round(sum(v.get("cpu_host") or 0 for v in games), 1),
                  "mem_mb": sum(v.get("mem_mb") or 0 for v in games),
                  "rx_bps": sum(v.get("rx_bps") or 0 for v in games), "tx_bps": sum(v.get("tx_bps") or 0 for v in games)}
    h["net"] = {k: livestats.host.get(k) for k in ("rx_bps", "tx_bps", "source", "ifaces")}
    return h


async def watcher():
    """Pollt alle Server, setzt Spieleranzahl bei Modus-/Mapwechsel automatisch."""
    await asyncio.sleep(3)
    while True:
        interval = max(5, int(automation.get_settings().get("watch_interval") or 10))
        servers = load_servers()

        async def one(s):
            try:
                await asyncio.wait_for(collect_state(s, apply_auto=True), timeout=RCON_TIMEOUT * 3)
            except Exception as e:  # noqa: BLE001 – Watcher darf nie sterben
                _state[s["id"]] = {**_state.get(s["id"], {}), "online": False,
                                   "error": str(e) or e.__class__.__name__, "updated": time.time()}
        if servers:
            await asyncio.gather(*(one(s) for s in servers))
        await asyncio.sleep(interval)


@app.post("/api/servers/{sid}/auto/apply", dependencies=auth)
async def auto_apply(sid: str):
    s = get_server(sid)
    try:
        st = await collect_state(s, apply_auto=True)
    except RconError as e:
        raise HTTPException(502, str(e))
    return st["auto"] | {"visible_players": st["visible_players"]}


class CvarsIn(BaseModel):
    names: list[str] = Field(max_length=100)


@app.post("/api/servers/{sid}/cvars", dependencies=auth)
async def get_cvars(sid: str, data: CvarsIn):
    s = get_server(sid)
    names = [n for n in data.names if re.fullmatch(r"[A-Za-z0-9_]+", n)]
    if not names:
        return {}
    raw = await run(s, ";".join(names))
    return automation.parse_cvars(raw, names)


class TestIn(BaseModel):
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(27015, ge=1, le=65535)
    password: str | None = None
    server_id: str | None = None


@app.post("/api/test", dependencies=auth)
async def test_connection(data: TestIn):
    pw = data.password
    if not pw and data.server_id:
        pw = get_server(data.server_id).get("password", "")
    c = RconClient(data.host.strip(), data.port, pw or "", RCON_TIMEOUT)
    try:
        raw = await c.execute("status")
    except RconError as e:
        raise HTTPException(502, str(e))
    finally:
        c.close()
    st = parse_status(raw)
    return {"hostname": st["hostname"], "map": st["map"]}


class BroadcastIn(BaseModel):
    command: str = Field(min_length=1, max_length=4000)
    server_ids: list[str]


@app.post("/api/broadcast", dependencies=auth)
async def broadcast(data: BroadcastIn):
    servers = [s for s in load_servers() if s["id"] in set(data.server_ids)]

    async def one(s):
        try:
            return {"id": s["id"], "name": s["name"], "ok": True,
                    "output": await client_for(s).execute(data.command)}
        except RconError as e:
            return {"id": s["id"], "name": s["name"], "ok": False, "output": str(e)}

    return await asyncio.gather(*(one(s) for s in servers))


# ---------------------------------------------------------------- Map / Modus wechseln
class MapIn(BaseModel):
    map: str | None = Field(None, max_length=128)
    workshop_id: str | None = Field(None, max_length=32)
    mode: str | None = None  # Modus-Key, None = beibehalten


@app.post("/api/servers/{sid}/map", dependencies=auth)
async def change_map(sid: str, data: MapIn):
    s = get_server(sid)
    settings = automation.get_settings()
    cmds = []
    mode = next((m for m in settings["modes"] if m["key"] == data.mode), None) if data.mode else None
    if mode:
        cmds += [f"game_type {int(mode['game_type'])}", f"game_mode {int(mode['game_mode'])}"]
    if data.workshop_id:
        wid = steam.parse_workshop_id(data.workshop_id)
        if not wid:
            raise HTTPException(400, "Ungültige Workshop-ID")
        cmds.append(f"host_workshop_map {wid}")
        title = ""
        try:
            d = await steam.workshop_details([wid])
            title = d[0]["title"] if d else ""
            preview = d[0]["preview"] if d else ""
        except steam.SteamError:
            preview = ""
        _last_workshop[sid] = {"id": wid, "title": title, "preview": preview, "at": time.time(), "map": "",
                               "from_map": automation.map_basename(_state.get(sid, {}).get("map"))}
    elif data.map:
        m = re.sub(r"[^\w\-/]", "", data.map)
        if not m:
            raise HTTPException(400, "Ungültiger Mapname")
        cmds.append(f"map {m}" if mode else f"changelevel {m}")
        _last_workshop.pop(sid, None)
    else:
        raise HTTPException(400, "Map oder Workshop-ID fehlt")
    out = await run(s, "; ".join(cmds))
    # Spieleranzahl nach dem Laden der Map automatisch nachziehen
    asyncio.create_task(_delayed_apply(s))
    target, reason = (None, None)
    if mode:
        target, reason = automation.target_players(data.map or (_last_workshop.get(sid) or {}).get("title"),
                                                   mode["game_type"], mode["game_mode"], settings)
    return {"command": "; ".join(cmds), "output": out, "expected_players": target, "reason": reason}


async def _delayed_apply(s: dict):
    for delay in (8, 15, 30):
        await asyncio.sleep(delay)
        try:
            await collect_state(s, apply_auto=True)
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------- Einstellungen (global)
class SettingsIn(BaseModel):
    modes: list[dict] | None = None
    map_rules: list[dict] | None = None
    public_url: str | None = None
    watch_interval: int | None = Field(None, ge=5, le=300)
    scan_interval: int | None = Field(None, ge=0, le=1440)
    scan_subnets: str | None = Field(None, max_length=200)
    games_base: str | None = Field(None, max_length=200)
    cache_container: str | None = Field(None, max_length=100)
    hostname_pattern: str | None = Field(None, max_length=60)
    container_dns: str | None = Field(None, max_length=100)


@app.get("/api/settings", dependencies=auth)
async def get_settings():
    return automation.get_settings()


@app.put("/api/settings", dependencies=auth)
async def put_settings(data: SettingsIn):
    payload = data.model_dump(exclude_none=True)
    if "modes" in payload:
        clean = []
        for m in payload["modes"]:
            try:
                clean.append({"key": re.sub(r"[^\w]", "", str(m["key"]))[:32], "label": str(m.get("label", m["key"]))[:48],
                              "game_type": int(m["game_type"]), "game_mode": int(m["game_mode"]),
                              "players": max(1, min(64, int(m["players"])))})
            except (KeyError, ValueError, TypeError):
                raise HTTPException(400, f"Ungültiger Modus: {m}")
        payload["modes"] = clean
    if "map_rules" in payload:
        clean = []
        for r in payload["map_rules"]:
            pat = str(r.get("pattern", "")).strip()[:64]
            if not pat:
                continue
            try:
                clean.append({"pattern": pat, "players": max(1, min(64, int(r["players"]))),
                              "label": str(r.get("label", ""))[:48]})
            except (KeyError, ValueError, TypeError):
                raise HTTPException(400, f"Ungültige Map-Regel: {r}")
        payload["map_rules"] = clean
    if "public_url" in payload:
        payload["public_url"] = payload["public_url"].strip().rstrip("/")
    if "games_base" in payload:
        gb = payload["games_base"].strip().rstrip("/")
        if gb and not gb.startswith("/"):
            raise HTTPException(400, "Basisordner muss ein absoluter Pfad sein (z. B. /mnt/grohlan)")
        payload["games_base"] = gb or "/mnt/grohlan"
    if "cache_container" in payload:
        payload["cache_container"] = payload["cache_container"].strip()
        cache_stats.state.update(container=None, offset=0, buckets={}, updated=None)
    return automation.save_settings(payload)


# ---------------------------------------------------------------- Workshop
@app.get("/api/workshop/search", dependencies=auth)
async def workshop_search(q: str = "", sort: str = "", page: int = 1):
    try:
        return await steam.workshop_search(q[:100], sort, page)
    except steam.SteamError as e:
        raise HTTPException(502, str(e))


@app.get("/api/workshop/favorites", dependencies=auth)
async def workshop_favorites():
    return store.load("workshop_favorites.json", [])


class FavIn(BaseModel):
    id: str = Field(max_length=200)


@app.post("/api/workshop/favorites", dependencies=auth)
async def add_favorite(data: FavIn):
    wid = steam.parse_workshop_id(data.id)
    if not wid:
        raise HTTPException(400, "Ungültige Workshop-ID oder Link")
    favs = store.load("workshop_favorites.json", [])
    if any(f["id"] == wid for f in favs):
        return favs
    try:
        d = await steam.workshop_details([wid])
    except steam.SteamError:
        d = []
    item = d[0] if d else {"id": wid, "title": wid, "preview": "", "size_mb": 0, "tags": []}
    favs.append({k: item.get(k) for k in ("id", "title", "preview", "size_mb", "tags")})
    store.save("workshop_favorites.json", favs)
    return favs


@app.delete("/api/workshop/favorites/{wid}", dependencies=auth)
async def del_favorite(wid: str):
    favs = [f for f in store.load("workshop_favorites.json", []) if f["id"] != wid]
    store.save("workshop_favorites.json", favs)
    return favs


# ---------------------------------------------------------------- Spieler (SteamIDs)
class PlayerIn(BaseModel):
    input: str = Field(min_length=1, max_length=200)
    name: str | None = Field(None, max_length=64)


@app.get("/api/players", dependencies=auth)
async def list_players():
    return store.load("players.json", [])


@app.post("/api/players", dependencies=auth)
async def add_player(data: PlayerIn):
    try:
        p = await steam.resolve_player(data.input)
    except steam.SteamError as e:
        raise HTTPException(400, str(e))
    players = store.load("players.json", [])
    name = (data.name or p["name"] or p["steamid"]).strip()
    existing = next((x for x in players if x["steamid"] == p["steamid"]), None)
    if existing:
        existing.update(name=data.name or existing["name"], avatar=p["avatar"] or existing.get("avatar", ""))
    else:
        players.append({"steamid": p["steamid"], "name": name, "avatar": p["avatar"], "added": int(time.time())})
    store.save("players.json", players)
    return {"player": existing or players[-1], "players": players, "offline": p["offline"]}


class PlayerUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=64)


@app.put("/api/players/{steamid}", dependencies=auth)
async def rename_player(steamid: str, data: PlayerUpdate):
    players = store.load("players.json", [])
    for p in players:
        if p["steamid"] == steamid:
            p["name"] = data.name.strip()
    store.save("players.json", players)
    return players


@app.delete("/api/players/{steamid}", dependencies=auth)
async def delete_player(steamid: str):
    players = [p for p in store.load("players.json", []) if p["steamid"] != steamid]
    store.save("players.json", players)
    return players


@app.post("/api/servers/{sid}/players/import", dependencies=auth)
async def import_players(sid: str):
    """Versucht SteamIDs der verbundenen Spieler über die Server-Konsole zu lesen."""
    s = get_server(sid)
    found, tried = [], []
    for cmd in ("status_json", "css_players", "status"):
        try:
            out = await client_for(s).execute(cmd)
        except RconError as e:
            raise HTTPException(502, str(e))
        tried.append(cmd)
        found = steam.extract_steamids(out)
        if found:
            break
    players = store.load("players.json", [])
    known = {p["steamid"] for p in players}
    added = 0
    for f in found:
        if f["steamid"] not in known:
            players.append({"steamid": f["steamid"], "name": f["name"] or f["steamid"], "avatar": "",
                            "added": int(time.time())})
            known.add(f["steamid"])
            added += 1
    if added:
        store.save("players.json", players)
    return {"found": found, "added": added, "tried": tried, "players": players}


# ---------------------------------------------------------------- Wettkampf (MatchZy)
MATCH_PRESETS = {
    "wingman": {
        "label": "Wingman (2v2)", "players_per_team": 2, "game_type": 0, "game_mode": 2,
        "maps": ["de_inferno", "de_nuke", "de_overpass", "de_vertigo", "de_ancient"],
        "cvars": {"mp_maxrounds": "16", "mp_overtime_enable": "1", "mp_overtime_maxrounds": "6",
                  "mp_roundtime": "1.5", "mp_roundtime_defuse": "1.5",
                  "matchzy_minimum_ready_required": "4"},
    },
    "competitive": {
        "label": "Competitive (5v5)", "players_per_team": 5, "game_type": 0, "game_mode": 1,
        "maps": ["de_ancient", "de_anubis", "de_dust2", "de_inferno", "de_mirage", "de_nuke", "de_train"],
        "cvars": {"mp_maxrounds": "24", "mp_overtime_enable": "1", "mp_overtime_maxrounds": "6",
                  "mp_roundtime": "1.92", "mp_roundtime_defuse": "1.92",
                  "matchzy_minimum_ready_required": "10"},
    },
}


@app.get("/api/match/presets", dependencies=auth)
async def match_presets():
    return MATCH_PRESETS


class PugIn(BaseModel):
    preset: str
    map: str = Field(min_length=1, max_length=128)
    workshop_id: str | None = None


@app.post("/api/servers/{sid}/pug", dependencies=auth)
async def pug_start(sid: str, data: PugIn):
    """MatchZy ohne Teamliste: jeder darf joinen, Start sobald genug Spieler .ready sind."""
    s = get_server(sid)
    p = MATCH_PRESETS.get(data.preset)
    if not p:
        raise HTTPException(400, "Unbekanntes Preset")
    cmds = [f"game_type {p['game_type']}", f"game_mode {p['game_mode']}",
            "matchzy_kick_when_no_match_loaded 0"]
    cmds += [f"{k} {v}" for k, v in p["cvars"].items()]
    wid = steam.parse_workshop_id(data.workshop_id or "")
    cmds.append(f"host_workshop_map {wid}" if wid else f"map {re.sub(r'[^\w\-/]', '', data.map)}")
    out = await run(s, "; ".join(cmds))
    asyncio.create_task(_delayed_apply(s))
    return {"command": "; ".join(cmds), "output": out}


class TeamIn(BaseModel):
    name: str = Field(min_length=1, max_length=32)
    players: list[str] = Field(default_factory=list, max_length=10)


class MatchIn(BaseModel):
    team1: TeamIn
    team2: TeamIn
    num_maps: int = Field(1, ge=1, le=5)
    maplist: list[str] = Field(min_length=1, max_length=10)
    players_per_team: int = Field(5, ge=1, le=10)
    skip_veto: bool = True
    side_type: str = "standard"
    clinch_series: bool = True
    spectators: list[str] = Field(default_factory=list, max_length=10)
    cvars: dict[str, str] = Field(default_factory=dict)
    public_url: str | None = None
    preset: str | None = None  # wingman / competitive


def build_match(data: MatchIn) -> dict:
    db = {p["steamid"]: p["name"] for p in store.load("players.json", [])}
    maps = [re.sub(r"[^\w\-/]", "", m) for m in data.maplist if m.strip()]
    if len(maps) < data.num_maps:
        raise HTTPException(400, f"Mindestens {data.num_maps} Map(s) in der Mapliste nötig")
    for t in (data.team1, data.team2):
        bad = [p for p in t.players if not re.fullmatch(r"7656119\d{10}", p)]
        if bad:
            raise HTTPException(400, f"Ungültige SteamID64 in {t.name}: {', '.join(bad)}")
    overlap = set(data.team1.players) & set(data.team2.players)
    if overlap:
        raise HTTPException(400, "Spieler doppelt in beiden Teams: " + ", ".join(db.get(i, i) for i in overlap))
    side = data.side_type if data.side_type in ("standard", "always_knife", "never_knife", "random") else "standard"
    preset = MATCH_PRESETS.get(data.preset or "", {})
    merged = {**preset.get("cvars", {}), **data.cvars}
    cvars = {k: str(v).replace('"', "").replace(";", "").replace("\n", " ")
             for k, v in merged.items() if re.fullmatch(r"[A-Za-z0-9_]+", k) and str(v).strip() != ""}
    cfg = {
        "matchid": int(time.time()) % 10_000_000,
        "team1": {"name": data.team1.name, "players": {p: db.get(p, p) for p in data.team1.players}},
        "team2": {"name": data.team2.name, "players": {p: db.get(p, p) for p in data.team2.players}},
        "num_maps": data.num_maps,
        "maplist": maps,
        "skip_veto": data.skip_veto,
        "side_type": side,
        "clinch_series": data.clinch_series,
        "players_per_team": data.players_per_team,
        "cvars": cvars,
    }
    if data.players_per_team == 2:
        cfg["wingman"] = True
    if data.spectators:
        cfg["spectators"] = {"players": {p: db.get(p, p) for p in data.spectators}}
    return cfg


@app.post("/api/servers/{sid}/match/preview", dependencies=auth)
async def match_preview(sid: str, data: MatchIn):
    get_server(sid)
    return build_match(data)


@app.post("/api/servers/{sid}/match", dependencies=auth)
async def match_start(sid: str, data: MatchIn, request: Request):
    s = get_server(sid)
    cfg = build_match(data)
    token = secrets.token_urlsafe(12)
    store.save(f"matches/{token}.json", cfg)
    base = (data.public_url or automation.get_settings().get("public_url") or str(request.base_url)).rstrip("/")
    url = f"{base}/match/{token}.json"
    pre = ""
    p = MATCH_PRESETS.get(data.preset or "")
    if p:  # Spielmodus vorher setzen, damit die Map im richtigen Modus lädt
        pre = f"game_type {p['game_type']}; game_mode {p['game_mode']}; "
    out = await run(s, f'{pre}matchzy_loadmatch_url "{url}"')
    asyncio.create_task(_delayed_apply(s))
    idx = store.load("matches.json", [])
    idx.insert(0, {"token": token, "server": sid, "server_name": s["name"], "created": int(time.time()),
                   "team1": data.team1.name, "team2": data.team2.name, "maps": cfg["maplist"],
                   "num_maps": cfg["num_maps"], "url": url})
    store.save("matches.json", idx[:50])
    return {"url": url, "output": out, "config": cfg}


@app.get("/api/matches", dependencies=auth)
async def list_matches():
    return store.load("matches.json", [])


@app.post("/api/matches/{token}/reload/{sid}", dependencies=auth)
async def match_reload(token: str, sid: str):
    s = get_server(sid)
    m = next((x for x in store.load("matches.json", []) if x["token"] == token), None)
    if not m:
        raise HTTPException(404, "Match nicht gefunden")
    out = await run(s, f'matchzy_loadmatch_url "{m["url"]}"')
    return {"url": m["url"], "output": out}


@app.get("/match/{token}.json")
async def match_file(token: str):
    """Öffentlich (ohne Login) – wird vom CS2-Server per matchzy_loadmatch_url abgerufen."""
    if not re.fullmatch(r"[A-Za-z0-9_\-]{8,64}", token):
        raise HTTPException(404)
    cfg = store.load(f"matches/{token}.json", None)
    if cfg is None:
        raise HTTPException(404)
    return JSONResponse(cfg)



# ---------------------------------------------------------------- Spiele allgemein
@app.get("/api/games", dependencies=auth)
async def games_meta():
    return {"games": GAMES, "docker": docker_api.available()}


class SaveIn(BaseModel):
    name: str = Field("", max_length=64)


@app.post("/api/servers/{sid}/save", dependencies=auth)
async def save_game(sid: str, data: SaveIn):
    s = get_server(sid)
    g = game_of(s)
    name = re.sub(r"[^\w\-]", "_", data.name.strip()) or time.strftime("lan_%Y%m%d_%H%M")
    if g == "factorio":
        out = await run(s, f"/server-save {name}" if data.name.strip() else "/server-save")
        return {"output": out or "Gespeichert"}
    if g == "satisfactory":
        try:
            await sf_client(s).call("SaveGame", {"SaveName": name})
        except sfmod.SatisfactoryError as e:
            raise HTTPException(502, str(e))
        return {"output": f"Spielstand „{name}“ gespeichert"}
    if g == "cs2":
        raise HTTPException(400, "CS2 hat keine Spielstände")
    raise HTTPException(400, "Speichern wird für dieses Spiel nicht unterstützt")


class ClaimIn(BaseModel):
    server_name: str = Field(min_length=1, max_length=64)
    admin_password: str = Field(min_length=1, max_length=128)


@app.post("/api/servers/{sid}/claim", dependencies=auth)
async def claim_server(sid: str, data: ClaimIn):
    """Satisfactory: frischen Server beanspruchen und Admin-Passwort setzen."""
    s = get_server(sid)
    if game_of(s) != "satisfactory":
        raise HTTPException(400, "Nur für Satisfactory")
    try:
        await sf_client(s).claim(data.server_name, data.admin_password)
    except sfmod.SatisfactoryError as e:
        raise HTTPException(502, str(e))
    await _set_server_fields(sid, password=data.admin_password)
    return {"ok": True}


async def _set_server_fields(sid: str, **fields):
    async with _store_lock:
        servers = load_servers()
        for x in servers:
            if x["id"] == sid:
                x.update(fields)
        save_servers(servers)
    drop_client(sid)


# ---------------------------------------------------------------- Docker / Container
def _need_docker():
    if not docker_api.available():
        raise HTTPException(400, "Docker-Socket nicht eingebunden – im Stack /var/run/docker.sock mounten")


@app.get("/api/docker/containers", dependencies=auth)
async def docker_containers():
    _need_docker()
    try:
        return await docker_api.list_containers()
    except docker_api.DockerError as e:
        raise HTTPException(502, str(e))


def _container_of(sid: str) -> str:
    s = get_server(sid)
    if not s.get("container"):
        raise HTTPException(400, "Kein Container verknüpft (Server bearbeiten → Container)")
    _need_docker()
    return s["container"]


@app.get("/api/servers/{sid}/container", dependencies=auth)
async def container_info(sid: str):
    name = _container_of(sid)
    try:
        i = await docker_api.inspect(name)
        st = i.get("State", {})
        info = {"name": name, "image": i.get("Config", {}).get("Image"), "state": st.get("Status"),
                "started": st.get("StartedAt"), "health": (st.get("Health") or {}).get("Status"),
                "restarts": i.get("RestartCount"), "stats": None}
        if st.get("Running"):
            info["stats"] = await docker_api.stats(name)
        return info
    except docker_api.DockerError as e:
        raise HTTPException(502, str(e))


@app.post("/api/servers/{sid}/container/{act}", dependencies=auth)
async def container_action(sid: str, act: str):
    name = _container_of(sid)
    try:
        await docker_api.action(name, act)
    except docker_api.DockerError as e:
        raise HTTPException(502, str(e))
    drop_client(sid)
    return {"ok": True}


DIAG_SH = r"""
echo '=== Prozesse'; ps -eo pid,etime,pcpu,rss,args 2>/dev/null | cut -c1-220 | head -40
echo '=== UDP-Sockets (lokale Ports)'; for h in $(cat /proc/net/udp /proc/net/udp6 2>/dev/null | awk 'NR>1 && $2 ~ /:/{split($2,a,":"); print a[2]}' | sort -u); do printf "%d " 0x$h; done; echo
echo '=== TCP-Listen'; for h in $(cat /proc/net/tcp /proc/net/tcp6 2>/dev/null | awk '$4=="0A"{split($2,a,":"); print a[2]}' | sort -u); do printf "%d " 0x$h; done; echo
echo '=== TCP-Verbindungen (Ziel-IP:Port Anzahl)'; cat /proc/net/tcp 2>/dev/null | awk 'NR>1 && $4=="01"{print "#TCP " $3}' | sort | uniq -c | sort -rn | head -12
echo '=== Datenträger'; df -h /serverdata/serverfiles 2>/dev/null | tail -1
for c in /serverdata/serverfiles/server_config.cfg /serverdata/serverfiles/server/server_config.cfg; do
  [ -f "$c" ] && { echo "=== $c"; grep -v '^[[:space:]]*#' "$c" | grep -v '^[[:space:]]*$' | grep -iv 'password' | head -80; }
done
[ -f /serverdata/serverfiles/initial_server_config.cfg ] && { echo '=== Vorlage (steam/token/lan)'; grep -inE 'token|steam|lan|auth|owner' /serverdata/serverfiles/initial_server_config.cfg | cut -c1-200 | head -30; }
echo '=== Dateien'; ls -la /serverdata/serverfiles 2>/dev/null | head -40
for l in $(ls -t /serverdata/serverfiles/*.log /serverdata/serverfiles/log.txt /serverdata/serverfiles/*/*.log 2>/dev/null | head -3); do echo "=== $l"; tail -n 60 "$l" | cut -c1-240; done
[ -d /serverdata/serverfiles/crash ] && { echo '=== Absturzberichte'; ls -la /serverdata/serverfiles/crash | tail -n 10; }
if [ -n "$BASH_VERSION" ] || command -v bash >/dev/null; then
  echo '=== A2S-Test im Container'
  for p in $(for h in $(cat /proc/net/udp /proc/net/udp6 2>/dev/null | awk 'NR>1 && $2 ~ /:/{split($2,a,":"); print a[2]}' | sort -u); do printf "%d " 0x$h; done); do
    r=$(bash -c 'exec 3<>/dev/udp/127.0.0.1/'$p' && printf "\xff\xff\xff\xffTSource Engine Query\x00" >&3 && timeout 2 dd bs=1400 count=1 <&3 2>/dev/null | tr -c "[:print:]" "."' 2>/dev/null)
    echo "$p: ${r:-keine Antwort}"
  done
fi
"""


@app.get("/api/servers/{sid}/container/diag", dependencies=auth)
async def container_diag(sid: str):
    """Fest vorgegebene Diagnose (Prozesse, Ports, Konfiguration) – nur Admins, keine freien Befehle."""
    name = _container_of(sid)
    try:
        out = await docker_api.exec_cmd(name, ["sh", "-c", DIAG_SH])

        def conv(m):
            h, p = m.group(2).split(":")
            ip = ".".join(str(int(h[k:k + 2], 16)) for k in (6, 4, 2, 0))
            return f"{ip}:{int(p, 16)} x{m.group(1)}"
        return {"output": re.sub(r"^\s*(\d+) #TCP ([0-9A-Fa-f]{8}:[0-9A-Fa-f]{4})\s*$", conv, out, flags=re.M)}
    except docker_api.DockerError as e:
        raise HTTPException(502, str(e))


STEAMFIX_SH = r"""
set -e
SC=/serverdata/steamcmd/steamcmd.sh
[ -x "$SC" ] || { echo "steamcmd nicht gefunden"; exit 1; }
echo "== Alte Installationsinfos entfernen …"
rm -f /serverdata/serverfiles/steamapps/appmanifest_$GAME_ID.acf
rm -rf /serverdata/serverfiles/steamapps/downloading/$GAME_ID /serverdata/serverfiles/steamapps/temp/$GAME_ID
echo "== Lade als Windows (Plattform-Workaround) …"
$SC +force_install_dir /serverdata/serverfiles +login anonymous +@sSteamCmdForcePlatformType windows +app_update $GAME_ID +quit | grep -E "Success|Error|ERROR" || true
echo "== Lade als Linux und prüfe …"
$SC +force_install_dir /serverdata/serverfiles +login anonymous +@sSteamCmdForcePlatformType linux +app_update $GAME_ID validate +quit | grep -E "Success|Error|ERROR" || true
echo "== Rechte zurücksetzen ($OWNER)"
chown -R "$OWNER" /serverdata/serverfiles /serverdata/steamcmd 2>/dev/null || true
"""


@app.post("/api/servers/{sid}/container/steamfix", dependencies=auth)
async def container_steamfix(sid: str):
    """SteamCMD-Plattform-Workaround für ich777-Images (Windows-, dann Linux-Download), danach Container starten."""
    name = _container_of(sid)
    try:
        info = await docker_api.inspect(name)
        cfg = info.get("Config") or {}
        env = cfg.get("Env") or []
        if not any(e.startswith("GAME_ID=") for e in env) or "/serverdata" not in " ".join((info.get("HostConfig") or {}).get("Binds") or []):
            raise HTTPException(400, "Nur für SteamCMD-Container (ich777-Images)")
        await docker_api._req("POST", f"/containers/{name}/stop", params={"t": "20"}, timeout=60)
        uid = next((e.split("=", 1)[1] for e in env if e.startswith("UID=")), "99")
        gid = next((e.split("=", 1)[1] for e in env if e.startswith("GID=")), "100")
        code, out = await docker_api.run_once(cfg["Image"], STEAMFIX_SH, (info.get("HostConfig") or {}).get("Binds") or [],
                                              user=f"{uid}:{gid}",   # als Spiel-Benutzer: NFS mit root_squash erlaubt root keine Schreibrechte
                                              env=[e for e in env if e.startswith("GAME_ID=")] + [f"OWNER={uid}:{gid}", "HOME=/serverdata/steamcmd"],
                                              timeout=7200)
        await docker_api._req("POST", f"/containers/{name}/start", timeout=60)
    except docker_api.DockerError as e:
        raise HTTPException(502, str(e))
    return {"ok": code == 0, "output": out[-2000:]}


ENV_KEYS = {
    "_ich777": [("GAME_PARAMS", "Startparameter"), ("VALIDATE", "Dateien beim Start prüfen (true/leer)")],
    "valheim": [("SERVER_NAME", "Servername"), ("SERVER_PASS", "Passwort (min. 5 Zeichen)"), ("WORLD_NAME", "Welt"),
                ("SERVER_PUBLIC", "Öffentlich gelistet (true/false)"), ("SERVER_ARGS", "Zusätzliche Argumente (z. B. -crossplay -preset casual)"),
                ("BACKUPS_MAX_COUNT", "Anzahl Backups")],
    "minecraft": [("MOTD", "Servername (MOTD)"), ("MAX_PLAYERS", "Max. Spieler"), ("MEMORY", "Arbeitsspeicher (z. B. 6G)"),
                  ("VERSION", "Version (LATEST oder z. B. 1.21.4)"), ("TYPE", "Typ (PAPER, VANILLA, FABRIC, FORGE …)"),
                  ("DIFFICULTY", "Schwierigkeit"), ("MODE", "Spielmodus"), ("OPS", "Operatoren (kommagetrennt)"),
                  ("ONLINE_MODE", "online-mode (TRUE/FALSE)"), ("VIEW_DISTANCE", "Sichtweite")],
    "tf2": [("SRCDS_MAXPLAYERS", "Max. Spieler"), ("SRCDS_STARTMAP", "Startmap"), ("SRCDS_PW", "Server-Passwort"),
            ("SRCDS_TOKEN", "Steam-Token (GSLT)"), ("SRCDS_TICKRATE", "Tickrate"), ("SRCDS_FPSMAX", "Max. FPS")],
    "teamspeak": [("TS3SERVER_DEFAULT_VOICE_PORT", "Sprach-Port")],
    "factorio": [("SAVE_NAME", "Spielstand"), ("LOAD_LATEST_SAVE", "Letzten Spielstand laden (true/false)")],
    "satisfactory": [("MAXPLAYERS", "Max. Spieler"), ("AUTOSAVENUM", "Anzahl Autosaves"), ("SKIPUPDATE", "Updates überspringen (true/false)")],
    "enshrouded": [("SERVER_NAME", "Servername"), ("SERVER_PASSWORD", "Passwort"), ("SERVER_SLOTS", "Max. Spieler")],
    "projectzomboid": [("SRV_NAME", "Servername"), ("ADMIN_PWD", "Admin-Passwort")],
    "vrising": [("SERVER_NAME", "Servername"), ("WORLD_NAME", "Welt")],
    "dontstarve": [("CLUSTER_TOKEN", "Klei-Server-Token")],
}


def _env_keys(game: str, env: list[str]) -> list[tuple[str, str]]:
    keys = list(ENV_KEYS.get(game, []))
    if any(e.startswith("GAME_ID=") for e in env):
        keys = keys + [k for k in ENV_KEYS["_ich777"] if k[0] not in {x[0] for x in keys}]
    return keys


class EnvIn(BaseModel):
    env: dict[str, str]


@app.post("/api/servers/{sid}/container/env", dependencies=auth)
async def container_set_env(sid: str, data: EnvIn):
    """Umgebungsvariablen ändern – Container wird mit gleichen Daten neu erstellt (nur vom Tool angelegte Container)."""
    s = get_server(sid)
    name = _container_of(sid)
    try:
        info = await docker_api.inspect(name)
        if ((info.get("Config") or {}).get("Labels") or {}).get("gsm.managed") != "1":
            raise HTTPException(400, "Nur für Container, die dieses Tool angelegt hat – sonst im Portainer-Stack ändern")
        allowed = {k for k, _ in _env_keys(game_of(s), (info.get("Config") or {}).get("Env") or [])}
        changes = {k: str(v)[:500].replace("\n", " ") for k, v in data.env.items() if k in allowed}
        if not changes:
            return {"ok": True, "changed": 0}

        def mutate(cfg, hc):
            env = [e for e in (cfg.get("Env") or []) if e.split("=", 1)[0] not in changes]
            env += [f"{k}={v}" for k, v in changes.items()]
            cfg["Env"] = env
        await docker_api.recreate(name, mutate)
    except docker_api.DockerError as e:
        raise HTTPException(502, str(e))
    drop_client(sid)
    return {"ok": True, "changed": len(changes)}


@app.get("/api/servers/{sid}/container/env", dependencies=auth)
async def container_get_env(sid: str):
    s = get_server(sid)
    name = _container_of(sid)
    try:
        info = await docker_api.inspect(name)
    except docker_api.DockerError as e:
        raise HTTPException(502, str(e))
    envl = (info.get("Config") or {}).get("Env") or []
    cur = dict(e.split("=", 1) for e in envl if "=" in e)
    keys = _env_keys(game_of(s), envl)
    return {"fields": [{"key": k, "label": lbl, "value": cur.get(k, ""), "present": k in cur} for k, lbl in keys],
            "env": {k: cur[k] for k in ("GAME_PARAMS", "GAME_ID", "VALIDATE") if k in cur},
            "managed": ((info.get("Config") or {}).get("Labels") or {}).get("gsm.managed") == "1"}


# ---------------------------------------------------------------- Konfigurationsdateien
@app.get("/api/servers/{sid}/config", dependencies=auth)
async def config_list(sid: str):
    s = get_server(sid)
    return {"files": [{"path": f["path"], "label": f["label"], "fmt": f["fmt"], "form": bool(f.get("fields")),
                       "fields": f.get("fields") or []} for f in configfiles.files_for(game_of(s))],
            "container": bool(s.get("container"))}


@app.get("/api/servers/{sid}/config/file", dependencies=auth)
async def config_read(sid: str, path: str):
    s = get_server(sid)
    try:
        name = _container_of(sid)
        r = await configfiles.read(name, game_of(s), path)
        if game_of(s) == "minecraft" and path.endswith("server.properties"):
            # itzg überschreibt diese Werte bei jedem Start aus den Umgebungsvariablen
            env = dict(e.split("=", 1) for e in ((await docker_api.inspect(name)).get("Config") or {}).get("Env") or [] if "=" in e)
            mp = {"MOTD": "motd", "MAX_PLAYERS": "max-players", "MODE": "gamemode", "DIFFICULTY": "difficulty", "PVP": "pvp",
                  "ONLINE_MODE": "online-mode", "VIEW_DISTANCE": "view-distance", "SIMULATION_DISTANCE": "simulation-distance",
                  "SPAWN_PROTECTION": "spawn-protection", "SEED": "level-seed", "HARDCORE": "hardcore", "ALLOW_FLIGHT": "allow-flight",
                  "ENABLE_WHITELIST": "white-list", "ENABLE_COMMAND_BLOCK": "enable-command-block", "MAX_WORLD_SIZE": "max-world-size"}
            r["locked"] = {prop: k for k, prop in mp.items() if k in env}
        return r
    except configfiles.ConfigError as e:
        raise HTTPException(400, str(e))
    except docker_api.DockerError as e:
        raise HTTPException(502, str(e))


class ConfigWrite(BaseModel):
    path: str
    content: str | None = None
    values: dict | None = None
    restart: bool = False


@app.put("/api/servers/{sid}/config/file", dependencies=auth)
async def config_write(sid: str, data: ConfigWrite):
    s = get_server(sid)
    name = _container_of(sid)
    g = game_of(s)
    try:
        content = data.content
        if data.values is not None:
            cur = await configfiles.read(name, g, data.path)
            content = configfiles.apply(cur["spec"], cur["content"], data.values)
        if content is None:
            raise HTTPException(400, "Nichts zu speichern")
        await configfiles.write(name, g, data.path, content)
        if data.restart:
            await docker_api.action(name, "restart")
    except configfiles.ConfigError as e:
        raise HTTPException(400, str(e))
    except docker_api.DockerError as e:
        raise HTTPException(502, str(e))
    drop_client(sid)
    return {"ok": True}


# ---------------------------------------------------------------- Datei-Browser & Spielstände
from fastapi.responses import Response as _Resp  # noqa: E402
from urllib.parse import quote as _urlq  # noqa: E402


def _fb_err(e):
    if isinstance(e, filebrowser.FileError):
        return HTTPException(400, str(e))
    return HTTPException(502, str(e))


@app.get("/api/servers/{sid}/files", dependencies=auth)
async def files_list(sid: str, path: str = ""):
    name = _container_of(sid)
    try:
        rs = await filebrowser.roots(name)
        if not rs:
            raise filebrowser.FileError("Container hat keine eingebundenen Datenordner")
        res = await filebrowser.listdir(name, path or rs[0])
        return {"roots": rs, **res}
    except (filebrowser.FileError, docker_api.DockerError) as e:
        raise _fb_err(e)


@app.get("/api/servers/{sid}/files/text", dependencies=auth)
async def files_text(sid: str, path: str):
    try:
        return await filebrowser.read_text(_container_of(sid), path)
    except (filebrowser.FileError, docker_api.DockerError) as e:
        raise _fb_err(e)


class FileTextIn(BaseModel):
    path: str
    content: str = Field(max_length=2 * 1024 * 1024)


@app.put("/api/servers/{sid}/files/text", dependencies=auth)
async def files_text_put(sid: str, data: FileTextIn):
    try:
        await filebrowser.write_text(_container_of(sid), data.path, data.content)
    except (filebrowser.FileError, docker_api.DockerError) as e:
        raise _fb_err(e)
    return {"ok": True}


@app.get("/api/servers/{sid}/files/download", dependencies=auth)
async def files_download(sid: str, path: str):
    try:
        fname, data, mt = await filebrowser.download(_container_of(sid), path)
    except (filebrowser.FileError, docker_api.DockerError) as e:
        raise _fb_err(e)
    return _Resp(content=data, media_type=mt,
                 headers={"Content-Disposition": f"attachment; filename*=UTF-8''{_urlq(fname)}"})


@app.post("/api/servers/{sid}/files/upload", dependencies=auth)
async def files_upload(sid: str, request: Request, dir: str, name: str):
    body = await request.body()
    if len(body) > 1024 * 1024 * 1024:
        raise HTTPException(413, "Datei zu groß (max. 1 GB)")
    try:
        p = await filebrowser.upload(_container_of(sid), dir, name, body)
    except (filebrowser.FileError, docker_api.DockerError) as e:
        raise _fb_err(e)
    return {"ok": True, "path": p}


@app.delete("/api/servers/{sid}/files", dependencies=auth)
async def files_delete(sid: str, path: str):
    try:
        await filebrowser.delete(_container_of(sid), path)
    except (filebrowser.FileError, docker_api.DockerError) as e:
        raise _fb_err(e)
    return {"ok": True}


@app.get("/api/servers/{sid}/saves", dependencies=auth)
async def saves_list(sid: str):
    s = get_server(sid)
    g = game_of(s)
    out = {"game": g, "files": [], "sessions": None, "can_save": g in ("satisfactory", "factorio", "minecraft"),
           "can_load": g in ("satisfactory", "factorio")}
    if s.get("container") and docker_api.available():
        try:
            out["files"] = await filebrowser.saves(s["container"], g)
        except docker_api.DockerError as e:
            out["error"] = str(e)
    if g == "satisfactory":
        try:
            d = await sf_client(s).call("EnumerateSessions")
            out["sessions"] = [{"name": x.get("sessionName"), "saves": [{"name": v.get("saveName"), "time": v.get("saveDateTime"),
                                                                          "playtime": v.get("playDurationSeconds")}
                                                                         for v in (x.get("saveHeaders") or [])]}
                               for x in (d or {}).get("sessions") or []]
            out["current"] = (d or {}).get("currentSessionIndex")
        except sfmod.SatisfactoryError as e:
            out["error"] = str(e)
    return out


class SaveNowIn(BaseModel):
    name: str = Field("", max_length=64)


@app.post("/api/servers/{sid}/saves/now", dependencies=auth)
async def saves_now(sid: str, data: SaveNowIn):
    s = get_server(sid)
    g = game_of(s)
    name = re.sub(r"[^\w\-]", "_", data.name.strip()) or time.strftime("lan_%Y%m%d_%H%M")
    try:
        if g == "satisfactory":
            await sf_client(s).call("SaveGame", {"SaveName": name})
            return {"ok": True, "output": f"Gespeichert als {name}"}
        if g == "factorio":
            try:
                out = await run(s, f"/server-save {name}")
            except HTTPException:
                raise HTTPException(400, "Factorio speichert nur über RCON – RCON-Port im Stack freigeben (z. B. 27100:27015/tcp)")
            return {"ok": True, "output": out or f"Gespeichert als {name}"}
        if g == "minecraft":
            out = await docker_api.exec_cmd(_container_of(sid), ["rcon-cli", "save-all"])
            return {"ok": True, "output": out.strip() or "Welt gespeichert"}
    except sfmod.SatisfactoryError as e:
        raise HTTPException(502, str(e))
    except docker_api.DockerError as e:
        raise HTTPException(502, str(e))
    raise HTTPException(400, "Für dieses Spiel nicht unterstützt – Spielstand über den Datei-Browser sichern")


class LoadIn(BaseModel):
    name: str = Field(max_length=200)


@app.post("/api/servers/{sid}/saves/load", dependencies=auth)
async def saves_load(sid: str, data: LoadIn):
    s = get_server(sid)
    g = game_of(s)
    try:
        if g == "satisfactory":
            await sf_client(s).call("LoadGame", {"SaveName": data.name, "EnableAdvancedGameSettings": False})
            return {"ok": True, "output": f"Lade {data.name} …"}
        if g == "factorio":
            # factoriotools lädt beim Start den neuesten Spielstand -> gewählte Datei zum neuesten machen und neu starten
            p = await filebrowser.check(_container_of(sid), data.name)
            if not p.startswith("/factorio/saves/") or not p.endswith(".zip"):
                raise HTTPException(400, "Bitte einen Spielstand aus /factorio/saves wählen")
            await docker_api.exec_cmd(_container_of(sid), ["touch", p])
            await docker_api.action(_container_of(sid), "restart")
            return {"ok": True, "output": "Server startet mit diesem Spielstand neu"}
    except sfmod.SatisfactoryError as e:
        raise HTTPException(502, str(e))
    except (filebrowser.FileError, docker_api.DockerError) as e:
        raise _fb_err(e)
    raise HTTPException(400, "Laden wird für dieses Spiel nicht unterstützt")


# ---------------------------------------------------------------- Satisfactory-Optionen (offizielle API)
SF_OPTS = [("FG.DSAutoPause", "Pausieren ohne Spieler", "bool"), ("FG.DSAutoSaveOnDisconnect", "Speichern, wenn jemand geht", "bool"),
           ("FG.AutosaveInterval", "Autosave alle (s)", "number"), ("FG.ServerRestartTimeSlot", "Täglicher Neustart (Min. nach Mitternacht)", "number"),
           ("FG.NetworkQuality", "Netzwerkqualität (0–3)", "number"), ("FG.SendGameplayData", "Spieldaten an Coffee Stain senden", "bool")]


@app.get("/api/servers/{sid}/satisfactory/options", dependencies=auth)
async def sf_options(sid: str):
    s = get_server(sid)
    if game_of(s) != "satisfactory":
        raise HTTPException(400, "Nur für Satisfactory")
    try:
        c = sf_client(s)
        d = await c.call("GetServerOptions")
        st = await c.call("QueryServerState")
    except sfmod.SatisfactoryError as e:
        raise HTTPException(502, str(e))
    opts = (d or {}).get("serverOptions") or {}
    gs = (st or {}).get("serverGameState") or {}
    return {"fields": [{"key": k, "label": l, "type": t, "value": opts.get(k)} for k, l, t in SF_OPTS],
            "session": gs.get("activeSessionName"), "name": s.get("name")}


class SfOptsIn(BaseModel):
    options: dict[str, str] = {}
    server_name: str | None = Field(None, max_length=64)
    client_password: str | None = Field(None, max_length=64)


@app.put("/api/servers/{sid}/satisfactory/options", dependencies=auth)
async def sf_options_put(sid: str, data: SfOptsIn):
    s = get_server(sid)
    try:
        c = sf_client(s)
        opts = {k: str(v) for k, v in data.options.items() if k in {o[0] for o in SF_OPTS}}
        if opts:
            await c.call("ApplyServerOptions", {"UpdatedServerOptions": opts})
        if data.server_name:
            await c.call("RenameServer", {"ServerName": data.server_name})
        if data.client_password is not None:
            await c.call("SetClientPassword", {"Password": data.client_password})
    except sfmod.SatisfactoryError as e:
        raise HTTPException(502, str(e))
    return {"ok": True}


@app.get("/api/servers/{sid}/container/logs", dependencies=auth)
async def container_logs(sid: str, tail: int = 300):
    name = _container_of(sid)
    try:
        return {"logs": await docker_api.logs(name, tail)}
    except docker_api.DockerError as e:
        raise HTTPException(502, str(e))


# ---------------------------------------------------------------- Neue Server anlegen
_jobs: dict[str, dict] = {}


@app.get("/api/templates", dependencies=auth)
async def list_templates():
    base = (automation.get_settings().get("games_base") or "/mnt/grohlan").rstrip("/")
    tpl = {k: {**v, "data_default": v["data_default"].replace("{base}", base)} for k, v in templates.TEMPLATES.items()}
    return {"templates": tpl, "docker": docker_api.available(), "games_base": base}


async def _used_ports() -> dict[int, str]:
    used = {}
    if docker_api.available():
        try:
            used.update(await docker_api.used_host_ports())
        except docker_api.DockerError:
            pass
    for s in load_servers():   # auch Server ohne Container (z. B. auf anderen Rechnern mit gleicher IP)
        for key in ("port", "game_port"):
            if s.get(key):
                used.setdefault(int(s[key]), s["name"])
    return used


@app.get("/api/templates/{game}/suggest", dependencies=auth)
async def suggest(game: str):
    if game not in templates.TEMPLATES:
        raise HTTPException(404)
    used = await _used_ports()
    n = sum(1 for s in load_servers() if game_of(s) == game) + 1
    names = {s.get("container") for s in load_servers()} | {s["name"] for s in load_servers()}
    while any(x and str(n) in x and game in x.lower() for x in names) and n < 99:
        n += 1
    return {"values": templates.suggest_ports(game, set(used)), "n": n,
            "used": sorted(used)[:500]}


class CreateIn(BaseModel):
    game: str
    values: dict[str, str]
    data_dir: str = Field(min_length=2, max_length=255)
    host: str | None = Field(None, max_length=255)  # Adresse, unter der der neue Server erreichbar ist


def _job_log(job, msg):
    job["log"].append(f"[{time.strftime('%H:%M:%S')}] {msg}")
    job["log"] = job["log"][-200:]
    job["step"] = msg


async def _create_job(job: dict, data: CreateIn, host: str):
    try:
        b = templates.build(data.game, data.values, data.data_dir)
        _job_log(job, f"Ordner vorbereiten: {', '.join(b['dirs'])}")
        own = f" && chown -R {b['uid']}:{b['gid']} /target" if b["uid"] else ""
        for d in b["dirs"]:
            await docker_api.run_helper([f"{d}:/target"], ["sh", "-c", f"mkdir -p /target{own} && echo ok"])
        _job_log(job, f"Image laden: {b['image']} (kann beim ersten Mal dauern)")
        last = {"t": 0.0}

        def prog(m):
            if time.time() - last["t"] > 3:
                last["t"] = time.time()
                job["step"] = "Image laden: " + m[:80]
        try:
            await docker_api.pull(b["image"], prog)
        except docker_api.DockerError as e:
            if not await docker_api.image_exists(b["image"]):
                raise
            _job_log(job, f"Pull fehlgeschlagen ({e}) – nutze vorhandenes lokales Image")
        dns = await lancache_dns()
        if dns:
            b["spec"]["HostConfig"]["Dns"] = dns
            _job_log(job, f"DNS {', '.join(dns)} (Lancache) – Downloads laufen über den Cache")
        _job_log(job, f"Container {b['name']} anlegen und starten")
        await docker_api.create_container(b["name"], b["spec"])
        srv = {"id": uuid.uuid4().hex[:10], "name": b["name"], "host": host, "port": b["server"]["port"],
               "password": b["server"].get("password", ""), "notes": "angelegt vom Spielservermanager",
               "auto_slots": True, "game": data.game, "container": b["name"],
               "web_url": b["server"].get("web_url", "").replace("{host}", host),
               "game_port": b["server"].get("game_port"), "name_from_game": True}
        async with _store_lock:
            servers = load_servers()
            servers.append(srv)
            save_servers(servers)
        job["server_id"] = srv["id"]
        _job_log(job, "Server in die Liste eingetragen")
        if data.game == "factorio":
            _job_log(job, "Warte auf RCON-Passwort (config/rconpw) …")
            for _ in range(60):
                await asyncio.sleep(5)
                try:
                    pw = (await docker_api.exec_cmd(b["name"], ["cat", "/factorio/config/rconpw"])).strip()
                except docker_api.DockerError:
                    pw = ""
                if pw and "No such file" not in pw:
                    await _set_server_fields(srv["id"], password=pw)
                    _job_log(job, "RCON-Passwort übernommen")
                    break
        if data.game == "satisfactory" and b["server"]["claim"]["password"]:
            _job_log(job, "Warte, bis Satisfactory bereit ist, um den Server zu beanspruchen (Download ~10 GB) …")
            c = sfmod.SatisfactoryClient(host, b["server"]["port"], "")
            for _ in range(240):
                await asyncio.sleep(15)
                try:
                    if await c.unclaimed():
                        await c.claim(b["server"]["claim"]["name"], b["server"]["claim"]["password"])
                        await _set_server_fields(srv["id"], password=b["server"]["claim"]["password"])
                        _job_log(job, "Server beansprucht, Admin-Passwort gesetzt")
                        break
                except sfmod.SatisfactoryError:
                    continue
        if data.game == "teamspeak":
            _job_log(job, "Warte auf das ServerQuery-Passwort und den Admin-Token aus dem Log …")
            for _ in range(60):
                await asyncio.sleep(5)
                try:
                    lg = await docker_api.logs(b["name"], 400)
                except docker_api.DockerError:
                    continue
                pw = re.search(r'loginname=\s*"serveradmin",\s*password=\s*"([^"]+)"', lg)
                tok = re.search(r"token=([A-Za-z0-9+]+)", lg)
                if pw:
                    await _set_server_fields(srv["id"], password=pw.group(1),
                                             notes="angelegt vom Spielservermanager" + (f"\nAdmin-Token (Berechtigungsschlüssel): {tok.group(1)}" if tok else ""))
                    _job_log(job, "ServerQuery-Passwort übernommen" + (" · Admin-Token steht in den Notizen des Servers" if tok else ""))
                    break
        if data.game == "wreckfest" and b["server"].get("wf_config"):
            _job_log(job, "Wreckfest: Servername, Passwort und Ports werden nach der Installation automatisch eingetragen")
            asyncio.create_task(_wf_after_install(b["name"], b["server"]["wf_config"]))
        job["done"] = True
        _job_log(job, "Fertig")
    except (ValueError, docker_api.DockerError) as e:
        job["error"] = str(e)
        job["done"] = True
        _job_log(job, "Fehler: " + str(e))
    except Exception as e:  # noqa: BLE001
        log.exception("Anlegen fehlgeschlagen")
        job["error"] = str(e) or e.__class__.__name__
        job["done"] = True


# ---------------------------------------------------------------- Wreckfest: server_config.cfg
WF_CFG = "/serverdata/serverfiles/server_config.cfg"
WF_KEYS = {"server_name": "Servername", "welcome_message": "Begrüßung", "password": "Passwort", "max_players": "Max. Spieler",
           "admin_steam_ids": "Admin-SteamIDs", "op_steam_ids": "Moderator-SteamIDs", "gamemode": "Spielmodus",
           "track": "Strecke", "laps": "Runden", "bots": "Bots", "ai_difficulty": "KI-Stärke", "car_class_restriction": "Fahrzeugklasse",
           "vehicle_damage": "Schaden", "lobby_countdown": "Lobby-Countdown", "game_port": "Spielport",
           "query_port": "Query-Port", "steam_port": "Steam-Port"}
WF_QUOTED = {"server_name", "welcome_message"}


async def _wf_read(container: str) -> str | None:
    out = await docker_api.exec_cmd(container, ["sh", "-c", f"[ -f {WF_CFG} ] && cat {WF_CFG} || echo __NOFILE__"])
    return None if "__NOFILE__" in out else out


def _wf_values(text: str) -> dict:
    vals = {}
    for line in text.splitlines():
        m = re.match(r"^\s*([a-z_]+)\s*=\s*(.*?)\s*$", line)
        if m and m.group(1) in WF_KEYS:
            vals[m.group(1)] = m.group(2).strip('"')
    return vals


def _wf_apply(text: str, changes: dict) -> str:
    lines = text.splitlines()
    for k, v in changes.items():
        v = re.sub(r'[\r\n"]', "", str(v)).strip()
        new = f'{k}="{v}"' if k in WF_QUOTED else f"{k}={v}"
        for i, line in enumerate(lines):
            if re.match(rf"^\s*#?\s*{k}\s*=", line) and (not line.lstrip().startswith("#") or k in ("admin_steam_ids", "op_steam_ids")):
                lines[i] = new
                break
        else:
            lines.append(new)
    return "\n".join(lines) + "\n"


async def _wf_write(container: str, changes: dict) -> None:
    import base64
    text = await _wf_read(container)
    if text is None:
        raise HTTPException(409, "server_config.cfg gibt es noch nicht – Server installiert sich noch")
    data = base64.b64encode(_wf_apply(text, changes).encode()).decode()
    out = await docker_api.exec_cmd(container, ["sh", "-c", f"echo {data} | base64 -d > {WF_CFG}.new && "
                                                             f"chown 99:100 {WF_CFG}.new 2>/dev/null; mv {WF_CFG}.new {WF_CFG} && echo OK"])
    if "OK" not in out:
        raise HTTPException(502, f"Konnte Konfiguration nicht schreiben: {out.strip()[:200]}")


async def _wf_after_install(container: str, cfg: dict) -> None:
    """Nach der ersten Installation Ports/Name/Passwort in server_config.cfg eintragen und neu starten."""
    clean = {k: v for k, v in cfg.items() if v not in (None, "") or k == "password"}
    for _ in range(360):            # bis zu 3 h
        await asyncio.sleep(30)
        try:
            if await _wf_read(container) is not None:
                await asyncio.sleep(20)
                await _wf_write(container, clean)
                await docker_api.action(container, "restart")
                log.info("%s: Wreckfest-Konfiguration eingetragen", container)
                return
        except (docker_api.DockerError, HTTPException):
            continue


def _wf_server(sid: str) -> dict:
    s = get_server(sid)
    if game_of(s) != "wreckfest" or not s.get("container"):
        raise HTTPException(400, "Nur für Wreckfest-Server mit zugeordnetem Container")
    return s


@app.get("/api/servers/{sid}/wreckfest/config", dependencies=auth)
async def wf_config_get(sid: str):
    s = _wf_server(sid)
    try:
        text = await _wf_read(s["container"])
        info = await docker_api.inspect(s["container"])
    except docker_api.DockerError as e:
        raise HTTPException(502, str(e))
    vals = _wf_values(text or "")
    q = vals.get("query_port", "")
    binds = (info.get("HostConfig") or {}).get("PortBindings") or {}
    q_host = ((binds.get(f"{q}/udp") or [{}])[0] or {}).get("HostPort")
    lan_ok = q.isdigit() and (26900 <= int(q) <= 26905 or (27015 <= int(q) <= 27020)) and q_host == q
    return {"exists": text is not None, "values": vals, "labels": WF_KEYS, "lan_ok": lan_ok,
            "managed": (info.get("Config", {}).get("Labels") or {}).get("gsm.managed") == "1"}


class WfConfigIn(BaseModel):
    values: dict[str, str]
    restart: bool = True


@app.put("/api/servers/{sid}/wreckfest/config", dependencies=auth)
async def wf_config_put(sid: str, data: WfConfigIn):
    s = _wf_server(sid)
    changes = {k: v for k, v in data.values.items() if k in WF_KEYS and k not in ("game_port", "query_port", "steam_port")}
    if "admin_steam_ids" in changes:
        changes["admin_steam_ids"] = re.sub(r"[^0-9,]", "", changes["admin_steam_ids"])
    try:
        await _wf_write(s["container"], changes)
        if data.restart:
            await docker_api.action(s["container"], "restart")
    except docker_api.DockerError as e:
        raise HTTPException(502, str(e))
    return {"ok": True}


@app.post("/api/servers/{sid}/wreckfest/lan", dependencies=auth)
async def wf_lan_fix(sid: str):
    """Query-Port in den LAN-Suchbereich 26900–26905 legen, Ports innen = außen, Container neu erstellen."""
    s = _wf_server(sid)
    name = s["container"]
    try:
        info = await docker_api.inspect(name)
        if (info.get("Config", {}).get("Labels") or {}).get("gsm.managed") != "1":
            raise HTTPException(400, "Nur für Container, die dieses Tool angelegt hat")
        text = await _wf_read(name)
        if text is None:
            raise HTTPException(409, "server_config.cfg gibt es noch nicht – Server installiert sich noch")
        vals = _wf_values(text)
        used = await docker_api.used_host_ports()
        own = {int(b["HostPort"]) for lst in ((info.get("HostConfig") or {}).get("PortBindings") or {}).values()
               for b in (lst or []) if str(b.get("HostPort", "")).isdigit()}
        free = lambda p: p not in used or p in own  # noqa: E731
        q = next((p for p in range(26900, 26906) if free(p)), None)
        if q is None:
            raise HTTPException(409, "Alle LAN-Query-Ports 26900–26905 sind belegt")
        gport = int(vals.get("game_port") or s.get("game_port") or 33540)
        sport = next(p for p in range(27115, 27200) if free(p) and p != q)
        await _wf_write(name, {"query_port": q, "steam_port": sport, "game_port": gport})

        def mutate(cfg, hc):
            web = (hc.get("PortBindings") or {}).get("8080/tcp")
            hc["PortBindings"] = {f"{gport}/udp": [{"HostPort": str(gport)}], f"{q}/udp": [{"HostPort": str(q)}],
                                  f"{sport}/udp": [{"HostPort": str(sport)}]}
            cfg["ExposedPorts"] = {f"{gport}/udp": {}, f"{q}/udp": {}, f"{sport}/udp": {}}
            if web:
                hc["PortBindings"]["8080/tcp"] = web
                cfg["ExposedPorts"]["8080/tcp"] = {}
        await docker_api.recreate(name, mutate)
    except docker_api.DockerError as e:
        raise HTTPException(502, str(e))
    await _set_server_fields(sid, port=q, game_port=gport)
    return {"ok": True, "query_port": q, "steam_port": sport, "game_port": gport}


# ---------------------------------------------------------------- Speicher / iSCSI (nur Planung + lesende Prüfung)
@app.get("/api/storage", dependencies=auth)
async def storage_get():
    st = hoststorage.settings()
    io = livestats.io or {}
    mnt = hoststorage.mount_status(st["mountpoint"])
    dev = (mnt.get("device") or "").rsplit("/", 1)[-1]
    disk = next((d for d in io.get("disks") or [] if dev.startswith(d["name"])), None) if dev else None
    return {"settings": {**st, "chap_pw": "••••" if st.get("chap_pw") else ""}, "mount": mnt, "disk": disk,
            "mounts": hoststorage.iscsi_disks(), "script": hoststorage.script(st)}


class StorageIn(BaseModel):
    portal: str = Field("", max_length=100)
    target: str = Field("", max_length=223)
    chap_user: str = Field("", max_length=64)
    chap_pw: str | None = Field(None, max_length=64)
    fs: str = "ext4"
    mountpoint: str = Field("/mnt/lancache", max_length=120)
    format: bool = True
    label: str = Field("lancache", max_length=20)
    purpose: str = "lancache"
    old_path: str = Field("/mnt/cachenew", max_length=120)


@app.put("/api/storage", dependencies=auth)
async def storage_put(data: StorageIn):
    d = data.model_dump()
    if d.get("chap_pw") in (None, "••••"):
        d.pop("chap_pw")
    try:
        hoststorage.save(d)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return await storage_get()


@app.get("/api/storage/script", dependencies=auth)
async def storage_script():
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(hoststorage.script(hoststorage.settings()),
                             headers={"Content-Disposition": 'attachment; filename="iscsi-einbinden.sh"'})


# ---------------------------------------------------------------- SteamPrefill
_prefill_files: dict = {"files": [], "t": 0.0}


@app.get("/api/prefill", dependencies=auth)
async def prefill_state(tail: int = 300):
    if not docker_api.available():
        raise HTTPException(400, "Docker-Socket nicht eingebunden")
    st = await prefill.container_state()
    if time.time() - _prefill_files["t"] > 60:
        _prefill_files.update(files=await prefill.config_files(), t=time.time())
    files = _prefill_files["files"]
    lg = await prefill.log(tail) if st else ""
    prog = None
    for line in reversed(lg.splitlines()):
        m = re.search(r"(\d{1,3}(?:[.,]\d+)?)\s*%", line)
        if m:
            prog = {"pct": float(m.group(1).replace(",", ".")), "line": line.strip()[:160]}
            break
    pp = prefill.parse_progress(lg) if lg else {"apps": [], "current": None}
    asyncio.create_task(_prefill_autoadd([a["name"] for a in pp["apps"]]))
    who = []
    if prefill.auto.get("paused") and not prefill.auto.get("manual"):
        try:
            who = await netnames.annotate((cache_stats.summary().get("live_clients") or [])[:3], {x["host"] for x in load_servers()})
        except Exception:  # noqa: BLE001
            who = []
    return {"settings": prefill.settings(), "container": st, "apps_progress": pp["apps"],
            "rate": (livestats.data.get(prefill.NAME) or {}).get("rx_bps") if st and st.get("running") else None, "config_dir": prefill.config_dir(), "files": files,
            "logged_in": any(f.lower().startswith("account") or f.endswith(".dat") or "token" in f.lower() for f in files),
            "log": lg, "prompt": prefill.prompt_of(lg) if st and st.get("running") else None, "progress": prog,
            "job": prefill.job, "dns": await lancache_dns(), "auto": prefill.auto, "who": who}


class PrefillRunIn(BaseModel):
    mode: str = "prefill"


def _server_game_apps() -> list[dict]:
    """Steam-Spiele aller eingetragenen Spielserver (damit Spieler sie aus dem Cache laden)."""
    out, seen = [], set()
    for x in load_servers():
        g = game_of(x)
        a = GAMES.get(g, {}).get("appid")
        if a and a not in seen:
            seen.add(a)
            out.append({"id": int(a), "name": GAMES[g]["label"], "server": True})
    return out


async def _prefill_sync_server_games() -> None:
    s = prefill.settings()
    apps = list(s.get("apps") or [])
    have = {a["id"] for a in apps}
    if s.get("server_games", True):
        new = [a for a in _server_game_apps() if a["id"] not in have]
        if new:
            apps += new
            prefill.save_settings({"apps": apps})
    if apps:
        await prefill.write_apps([a["id"] for a in apps])


async def _prefill_start(mode: str):
    try:
        await _prefill_sync_server_games()
    except docker_api.DockerError:
        pass
    s = prefill.settings()
    prefill.job.update(running=True, step="startet …", error=None)
    try:
        await prefill.start(prefill.build_cmd(mode, s["flags"]), await lancache_dns())
        prefill.save_settings({"last_run": time.time()})
        prefill.job.update(running=False, step=None)
    except docker_api.DockerError as e:
        prefill.job.update(running=False, step=None, error=str(e))
        raise


@app.post("/api/prefill/run", dependencies=auth)
async def prefill_run(data: PrefillRunIn):
    if data.mode not in ("prefill", "select-apps"):
        raise HTTPException(400, "Unbekannter Modus")
    try:
        await _prefill_start(data.mode)
    except docker_api.DockerError as e:
        raise HTTPException(502, str(e))
    _prefill_files["t"] = 0
    return {"ok": True}


class PrefillInput(BaseModel):
    text: str = Field("", max_length=200)


@app.post("/api/prefill/input", dependencies=auth)
async def prefill_input(data: PrefillInput):
    try:
        await prefill.send(data.text)
    except docker_api.DockerError as e:
        raise HTTPException(502, str(e))
    _prefill_files["t"] = 0
    return {"ok": True}


@app.post("/api/prefill/stop", dependencies=auth)
async def prefill_stop():
    try:
        await prefill.stop()
    except docker_api.DockerError as e:
        raise HTTPException(502, str(e))
    return {"ok": True}


class PrefillPause(BaseModel):
    on: bool


@app.post("/api/prefill/pause", dependencies=auth)
async def prefill_pause(data: PrefillPause):
    try:
        await prefill.manual_pause(data.on)
    except docker_api.DockerError as e:
        raise HTTPException(502, str(e))
    return {"ok": True}


@app.get("/api/prefill/search", dependencies=auth)
async def prefill_search(q: str):
    if len(q.strip()) < 2:
        return []
    try:
        return await prefill.search(q.strip())
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Steam-Suche nicht erreichbar ({e.__class__.__name__})")


class PrefillApps(BaseModel):
    apps: list[dict]


@app.put("/api/prefill/apps", dependencies=auth)
async def prefill_apps(data: PrefillApps):
    apps = [{"id": int(a["id"]), "name": str(a.get("name") or a["id"])[:80], **({"auto": True} if a.get("auto") else {}),
             **({"server": True} if a.get("server") else {})}
            for a in data.apps if str(a.get("id", "")).isdigit()]
    try:
        await prefill.write_apps([a["id"] for a in apps])
    except docker_api.DockerError as e:
        raise HTTPException(502, str(e))
    prefill.save_settings({"apps": apps})
    _prefill_files["t"] = 0
    return {"ok": True, "apps": apps}


class PrefillSettings(BaseModel):
    server_games: bool = True
    schedule: str = Field("", max_length=5)
    flags: dict
    yield_: bool = Field(True, alias="yield")
    yield_mbs: float = Field(2.0, ge=0.1, le=1000)


@app.put("/api/prefill/settings", dependencies=auth)
async def prefill_settings(data: PrefillSettings):
    if data.schedule and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", data.schedule):
        raise HTTPException(400, "Uhrzeit als HH:MM angeben")
    f = data.flags
    flags = {"recent": bool(f.get("recent")), "recently_purchased": bool(f.get("recently_purchased")),
             "top": max(0, min(100, int(f.get("top") or 0))), "all": bool(f.get("all")), "force": bool(f.get("force")),
             "verbose": bool(f.get("verbose")), "os": f.get("os") if f.get("os") in ("windows", "linux", "macos") else "windows"}
    out = prefill.save_settings({"schedule": data.schedule, "flags": flags, "yield": data.yield_, "yield_mbs": data.yield_mbs,
                                 "server_games": data.server_games})
    if data.server_games:
        try:
            await _prefill_sync_server_games()
        except docker_api.DockerError:
            pass
    return prefill.settings()


_autoadd_busy = {"on": False}


async def _prefill_autoadd(names: list[str]):
    """Spiele, die SteamPrefill über die Optionen (zuletzt gespielt, alle …) lädt, in die Liste übernehmen."""
    s = prefill.settings()
    known = {a["name"].lower() for a in s.get("apps") or []}
    new = [n for n in dict.fromkeys(names) if n and n.lower() not in known]
    if not new or _autoadd_busy["on"]:
        return
    _autoadd_busy["on"] = True
    try:
        apps = list(s.get("apps") or [])
        for n in new[:10]:
            try:
                res = await prefill.search(n)
            except Exception:  # noqa: BLE001
                continue
            hit = next((r for r in res if r["name"].lower() == n.lower()), None)
            if hit:
                apps.append({"id": hit["id"], "name": hit["name"], "auto": True})
        if len(apps) != len(s.get("apps") or []):
            prefill.save_settings({"apps": apps})
    finally:
        _autoadd_busy["on"] = False


async def prefill_scheduler():
    s = prefill.settings()
    if not prefill.due(s.get("schedule"), s.get("last_scheduled") or ""):
        return
    prefill.save_settings({"last_scheduled": time.strftime("%Y-%m-%d")})
    st = await prefill.container_state()
    if st and st.get("running"):
        return
    try:
        await _prefill_start("prefill")
        log.info("SteamPrefill: geplanter Lauf gestartet")
    except docker_api.DockerError as e:
        log.warning("SteamPrefill: %s", e)


@app.post("/api/create", dependencies=auth)
async def create_server(data: CreateIn, request: Request):
    _need_docker()
    if data.game not in templates.TEMPLATES:
        raise HTTPException(400, "Unbekanntes Spiel")
    try:
        b = templates.build(data.game, data.values, data.data_dir)  # früh validieren
    except ValueError as e:
        raise HTTPException(400, str(e))
    used = await _used_ports()
    clash = [f"{p} (belegt von {used[p]})" for p in templates.host_ports(b["spec"]) if p in used]
    if clash:
        raise HTTPException(400, "Port bereits vergeben: " + ", ".join(clash))
    inner: dict[int, set] = {}
    for key, lst in b["spec"]["HostConfig"]["PortBindings"].items():
        for x in lst:
            inner.setdefault(int(x["HostPort"]), set()).add(key.split("/")[0])
    dup = [str(p) for p, k in inner.items() if len(k) > 1]
    if dup:
        raise HTTPException(400, "Port doppelt angegeben: " + ", ".join(dup))
    host = (data.host or "").strip() or _docker_host_ip(request)
    data.values["_host"] = host
    jid = secrets.token_hex(6)
    job = {"id": jid, "game": data.game, "log": [], "step": "", "done": False, "error": None, "server_id": None}
    _jobs[jid] = job
    asyncio.create_task(_create_job(job, data, host))
    return job


@app.get("/api/jobs/{jid}", dependencies=auth)
async def get_job(jid: str):
    if jid not in _jobs:
        raise HTTPException(404)
    return _jobs[jid]


def _docker_host_ip(request: Request | None = None) -> str:
    pub = automation.get_settings().get("public_url") or ""
    m = re.match(r"https?://([^:/]+)", pub)
    if m:
        return m.group(1)
    if request and request.url.hostname:
        return request.url.hostname
    return _seen_hosts[-1] if _seen_hosts else "127.0.0.1"


# ---------------------------------------------------------------- Netzwerk-Scan
_seen_hosts: list[str] = []


@app.middleware("http")
async def remember_host(request: Request, call_next):
    h = request.url.hostname or ""
    if re.fullmatch(r"\d+\.\d+\.\d+\.\d+", h) and not h.startswith("127.") and h not in _seen_hosts:
        _seen_hosts.append(h)
        del _seen_hosts[:-5]
    return await call_next(request)


def _scan_nets():
    st = automation.get_settings()
    hosts = list(_seen_hosts) + [s["host"] for s in load_servers()]
    m = re.match(r"https?://([^:/]+)", st.get("public_url") or "")
    if m:
        hosts.insert(0, m.group(1))
    extra = [x for x in re.split(r"[,\s]+", st.get("scan_subnets") or "") if x]
    return scanner.subnets_for(hosts, extra)


def _annotate(results):
    known = {(s["host"], int(s["port"])) for s in load_servers()}
    known_c = {s.get("container") for s in load_servers() if s.get("container")}
    out = []
    for r in results:
        k = (r["host"], r["port"]) in known if r.get("host") else r.get("container") in known_c
        out.append({**r, "known": k})
    return out


@app.get("/api/scan", dependencies=auth)
async def scan_state():
    st = scanner.state
    return {**{k: v for k, v in st.items() if k != "results"}, "results": _annotate(st["results"]),
            "planned": [str(n) for n in _scan_nets()]}


@app.post("/api/scan", dependencies=auth)
async def scan_now():
    nets = _scan_nets()
    if not nets:
        raise HTTPException(400, "Kein Netz bekannt – unter „Automatik & Modi“ ein Subnetz eintragen (z. B. 192.168.200.0/24)")
    if not scanner.state["running"]:
        asyncio.create_task(scanner.scan(nets))
    await asyncio.sleep(0.1)
    return await scan_state()


async def scan_loop():
    await asyncio.sleep(20)
    while True:
        minutes = int(automation.get_settings().get("scan_interval") or 0)
        if minutes > 0:
            nets = _scan_nets()
            if nets:
                try:
                    await scanner.scan(nets)
                except Exception:  # noqa: BLE001
                    log.exception("Automatischer Scan fehlgeschlagen")
            await asyncio.sleep(minutes * 60)
        else:
            await asyncio.sleep(60)

# ---------------------------------------------------------------- Frontend
@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})


# allgemeine Container-Aktion (/container/{act}) erst nach den speziellen Routen prüfen
_generic = [r for r in app.router.routes if getattr(r, "path", "") == "/api/servers/{sid}/container/{act}"]
for _r in _generic:
    app.router.routes.remove(_r)
    app.router.routes.append(_r)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

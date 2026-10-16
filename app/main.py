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

from . import automation, cache_history, netnames, cache_stats, docker_api, hoststats, install_watch, metrics, scanner, steam, store, templates, users
from .games import GAMES, adapters, game_of
from .games import satisfactory as sfmod
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
             asyncio.create_task(load_loop())] if WATCH_ENABLED else []
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


ADMIN_PATHS = ("/api/users", "/api/create", "/api/settings")


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
        re.fullmatch(r"/api/servers/[\w-]+/(delete(-preview)?|container/(diag|use-lancache))", path)
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
            st = await adapters.factorio_status(client_for(s))
        elif g == "satisfactory":
            st = await sfmod.status(sf_client(s))
        elif g == "valheim":
            st = await adapters.valheim_status(s["host"], int(s["port"]))
        elif g == "tf2":
            st = await adapters.tf2_status(s["host"], int(s.get("game_port") or s["port"]))
        elif g == "wreckfest":
            if s.get("container") and docker_api.available():
                st = await adapters.wreckfest_container_status(s["container"])
            else:
                st = await adapters.wreckfest_status(s["host"], int(s["port"]))
        else:
            raise RconError("Unbekanntes Spiel")
    except (sfmod.SatisfactoryError, adapters.a2s.A2SError) as e:
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
        out.append(item)
    return out


# ---------------------------------------------------------------- Last (Host + Container)
_loads: dict[str, dict] = {}   # Containername -> {cpu, cores, mem_mb, state}


async def _container_load(name: str):
    try:
        info = await docker_api.inspect(name)
        running = info.get("State", {}).get("Running")
        st = await docker_api.stats(name) if running else {"cpu": 0, "mem_mb": 0, "mem_limit_mb": None}
        cores = hoststats.state.get("cores") or 1
        now = time.time()
        prev = _loads.get(name) or {}
        rx_bps = tx_bps = None
        if st.get("net_rx") is not None and prev.get("_rx") is not None and now > prev.get("updated", now):
            dt = now - prev["updated"]
            rx_bps = max(0, round((st["net_rx"] - prev["_rx"]) / dt))
            tx_bps = max(0, round((st["net_tx"] - prev["_tx"]) / dt))
        _loads[name] = {"state": info.get("State", {}).get("Status"), "cpu": st["cpu"],
                        "cpu_host": round(st["cpu"] / cores, 1) if st["cpu"] is not None else None,
                        "mem_mb": st["mem_mb"], "updated": now,
                        "net_host": (info.get("HostConfig") or {}).get("NetworkMode") == "host",
                        "rx_bps": rx_bps, "tx_bps": tx_bps, "_rx": st.get("net_rx"), "_tx": st.get("net_tx")}
    except docker_api.DockerError as e:
        _loads[name] = {"state": "unbekannt", "error": str(e), "updated": time.time()}


async def load_loop():
    """Host-Last alle 5 s, Container-Last aller verknüpften Container alle 10 s."""
    hoststats.sample()
    n = 0
    while True:
        await asyncio.sleep(5)
        hoststats.sample()
        n += 1
        if n % 2 == 0 and docker_api.available():
            await cache_stats.poll(automation.get_settings().get("cache_container") or "")
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
        h = hoststats.state
        lc = cache_stats.state.get("container")
        nets = [v for v in _loads.values() if v.get("state") == "running" and v.get("rx_bps") is not None]
        metrics.record_host(h.get("cpu"), h.get("mem_used_mb"), h.get("mem_total_mb"),
                            sum(v["rx_bps"] for v in nets) if nets else None, sum(v["tx_bps"] or 0 for v in nets) if nets else None)
        if n % 2 == 0:
            if lc and _loads.get(lc):
                metrics.record("_cache", {}, _loads[lc])
                ld = _loads[lc]
                if ld.get("rx_bps") is not None:
                    cache_history.add_net((ld["rx_bps"] or 0) * 10, (ld["tx_bps"] or 0) * 10)
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
    jobs = [{"id": j["id"], "game": j["game"], "step": j["step"], "error": j["error"], "done": j["done"],
             "server_id": j["server_id"], "title": j.get("title")} for j in _jobs.values() if not j["done"] or j["error"]]
    return {"items": items, "jobs": jobs[-5:]}


@app.post("/api/activity/dismiss/{container}", dependencies=auth)
async def activity_dismiss(container: str):
    install_watch.dismiss(container)
    return {"ok": True}


@app.get("/api/metrics", dependencies=auth)
async def server_metrics(minutes: int = 360):
    minutes = max(30, min(minutes, 24 * 60))
    out = {s["id"]: metrics.summary(s["id"], minutes) for s in load_servers()}
    out["_host"] = metrics.summary("_host", minutes)
    out["_cache"] = metrics.summary("_cache", minutes)
    return out


@app.get("/api/cache", dependencies=auth)
async def cache_metrics():
    if not docker_api.available():
        return {"error": "Docker-Socket nicht eingebunden", "container": None}
    if cache_stats.state["updated"] is None:
        await cache_stats.poll(automation.get_settings().get("cache_container") or "")
    out = cache_stats.summary()
    ld = _loads.get(out.get("container") or "") or {}
    out["net"] = {"rx_bps": ld.get("rx_bps"), "tx_bps": ld.get("tx_bps"), "host_mode": ld.get("net_host")}
    hosts = {x["host"] for x in load_servers()}
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
    out["clients"] = await netnames.annotate(out["clients"], {x["host"] for x in load_servers()})
    return out


@app.get("/api/host", dependencies=auth)
async def host_load():
    h = dict(hoststats.state)
    if h.get("updated") is None or time.time() - h["updated"] > 15:
        h = dict(hoststats.sample())
    games = [v for v in _loads.values() if v.get("cpu") is not None]
    h["games"] = {"containers": len(_loads), "running": sum(1 for v in _loads.values() if v.get("state") == "running"),
                  "cpu_host": round(sum(v.get("cpu_host") or 0 for v in games), 1),
                  "mem_mb": sum(v.get("mem_mb") or 0 for v in games),
                  "rx_bps": sum(v.get("rx_bps") or 0 for v in games), "tx_bps": sum(v.get("tx_bps") or 0 for v in games)}
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


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

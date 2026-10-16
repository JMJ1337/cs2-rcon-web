import asyncio
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

from . import automation, steam, store
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
    task = asyncio.create_task(watcher()) if WATCH_ENABLED else None
    yield
    if task:
        task.cancel()


app = FastAPI(title="CS2 RCON Web", docs_url=None, redoc_url=None, lifespan=lifespan)


# ---------------------------------------------------------------- Auth
def _sign(value: str) -> str:
    return hmac.new(SECRET, value.encode(), hashlib.sha256).hexdigest()


def make_token() -> str:
    exp = str(int(time.time()) + SESSION_HOURS * 3600)
    return f"{exp}.{_sign(exp)}"


def valid_token(token: str | None) -> bool:
    if not token or "." not in token:
        return False
    exp, sig = token.split(".", 1)
    if not hmac.compare_digest(sig, _sign(exp)):
        return False
    return exp.isdigit() and int(exp) > time.time()


def require_auth(request: Request):
    if not valid_token(request.cookies.get(COOKIE)):
        raise HTTPException(401, "Nicht angemeldet")


class LoginIn(BaseModel):
    password: str


@app.post("/api/login")
async def login(data: LoginIn, response: Response):
    if not hmac.compare_digest(data.password.encode(), ADMIN_PASSWORD.encode()):
        await asyncio.sleep(1.0)  # Brute-Force bremsen
        raise HTTPException(401, "Falsches Passwort")
    response.set_cookie(COOKIE, make_token(), httponly=True, samesite="strict",
                        max_age=SESSION_HOURS * 3600)
    return {"ok": True}


@app.post("/api/logout")
async def logout(response: Response):
    response.delete_cookie(COOKIE)
    return {"ok": True}


@app.get("/api/me")
async def me(request: Request):
    return {"authenticated": valid_token(request.cookies.get(COOKIE))}


auth = [Depends(require_auth)]


# ---------------------------------------------------------------- Server-Speicher
class ServerIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(27015, ge=1, le=65535)
    password: str | None = None  # None/"" beim Update = unverändert lassen
    notes: str = ""
    auto_slots: bool = True


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
             "auto_slots": data.auto_slots}
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
                         auto_slots=data.auto_slots)
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


async def collect_state(s: dict, apply_auto: bool = False, with_matchzy: bool = False) -> dict:
    """Status + wichtige Cvars lesen, optional Spieleranzahl automatisch setzen."""
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
        "workshop": ws,
        "updated": time.time(),
    }
    if with_matchzy:
        result["matchzy"] = await _matchzy_info(s)
    elif "matchzy" in _state.get(s["id"], {}):
        result["matchzy"] = _state[s["id"]]["matchzy"]
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
        out.append({"server": public(s), **{k: v for k, v in st.items() if not k.startswith("_") and k != "raw"}})
    return out


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
        "maps": ["de_inferno", "de_nuke", "de_overpass", "de_vertigo", "de_palais"],
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


# ---------------------------------------------------------------- Frontend
@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

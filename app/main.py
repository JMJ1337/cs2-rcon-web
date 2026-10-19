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
import urllib.parse
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import mapimages, gslt, matchlog, steamlist, playerdb, notify, prefill_more
from . import automation, cache_history, configfiles, depots, filebrowser, hoststorage, prefill, diagnostics, livestats, netnames, cache_stats, docker_api, hoststats, install_watch, metrics, scanner, steam, store, templates, users
from .games import GAMES, adapters, game_of
from .games import satisfactory as sfmod
from .games import minecraft as mcmod
from .games import teamspeak as tsmod
from .games import catalog as catmod
from .games import wreckfest_data as wfd
from .rcon import RconAuthError, RconClient, RconError

gslt.register_catalog(catmod.CATALOG)
for _g in gslt.APPS:
    if _g in GAMES:
        GAMES[_g]["gslt"] = True

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
             asyncio.create_task(load_loop()), asyncio.create_task(live_loop()),
             asyncio.create_task(player_loop()), asyncio.create_task(monitor_loop()),
             asyncio.create_task(gslt_loop()), asyncio.create_task(backup_loop())] if WATCH_ENABLED else []
    try:
        _resume_jobs()
    except Exception:  # noqa: BLE001
        log.exception("Anlege-Jobs konnten nicht fortgesetzt werden")
    yield
    for t in tasks:
        t.cancel()
    try:
        metrics.maybe_save(force=True)
        cache_history.maybe_save(force=True)
        playerdb.save(True)
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


ADMIN_PATHS = ("/api/users", "/api/gslt", "/api/notify", "/api/backup", "/api/settings", "/api/prefill", "/api/storage", "/api/scan", "/api/cache/measure", "/api/cache/reset", "/api/docker/image-check", "/api/docker/helperlogs")

# Benötigte Rechtestufe für Server-Unterseiten (users.LEVELS): 1 sehen, 2 bedienen, 3 verwalten, 4 anlegen/löschen
_MANAGE_RX = re.compile(r"(config(/file)?|files(/.*)?|saves/load|container(/(env|diag|use-lancache|steamfix))?|wreckfest/.*|sleep/config|gslt|cstv|"
                        r"satisfactory/options|claim)")
_MANAGE_GET_RX = re.compile(r"(config(/file)?|files(/.*)?|container/env|wreckfest/config|satisfactory/options)")


def _need_level(method: str, sub: str) -> int:
    sub = sub.strip("/")
    if method == "GET":
        if sub == "delete-preview":
            return 4
        return 3 if _MANAGE_GET_RX.fullmatch(sub) else 1
    if sub in ("", "delete") and method == "DELETE" or sub == "delete":
        return 4
    if sub == "" and method == "PUT":
        return 3
    return 3 if _MANAGE_RX.fullmatch(sub) else 2


def _server_game(sid: str) -> str | None:
    for x in load_servers():
        if x["id"] == sid:
            return game_of(x)
    return None


def require_auth(request: Request):
    u = token_user(request.cookies.get(COOKIE))
    if not u:
        raise HTTPException(401, "Nicht angemeldet")
    request.state.user = u
    if u.get("role") == "admin":
        return u
    path, method = request.url.path, request.method
    if path.startswith("/api/me"):
        return u
    if path.startswith(ADMIN_PATHS) and not (path in ("/api/settings", "/api/scan") and method == "GET"):
        raise HTTPException(403, "Nur für Administratoren")
    m = re.fullmatch(r"/api/servers/([\w-]+)(/.*)?", path)
    if m:
        game = _server_game(m.group(1))
        need = _need_level(method, m.group(2) or "")
        have = users.level(u, game)
        if have < need:
            raise HTTPException(403, f"Keine Berechtigung ({users.LEVELS.get(need)} nötig, du hast: {users.LEVELS.get(have)})")
        return u
    if method != "GET" and path not in ("/api/create", "/api/servers", "/api/logout") and users.max_level(u, GAMES) < 2:
        raise HTTPException(403, "Nur Ansicht – keine Berechtigung für Änderungen")
    return u


def need_game(request: Request, game: str | None, level: int):
    u = getattr(request.state, "user", None)
    if users.level(u, game) < level:
        raise HTTPException(403, f"Keine Berechtigung für dieses Spiel ({users.LEVELS.get(level)} nötig)")


def visible(request: Request, s: dict) -> bool:
    return users.level(getattr(request.state, "user", None), game_of(s)) >= 1


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


# ---------------------------------------------------------------- Öffentliche Ansicht (ohne Login)
JOIN_PW_ENV = ("SERVER_PASS", "SERVER_PASSWORD", "SRCDS_PW", "SERVERPASSWORD", "JOIN_PASSWORD", "GAME_PASSWORD", "SRV_PWD", "PASSWORD")
_join_pw: dict[str, tuple[float, str]] = {}


async def _join_password(s: dict) -> str:
    """Beitritts-Passwort (nicht RCON/Admin): aus dem Spielstatus, sonst aus Container-Umgebung bzw. Factorio-Einstellungen."""
    st = _state.get(s["id"], {})
    if st.get("join_password"):
        return st["join_password"]
    if game_of(s) in ("cs2", "tf2") and "join_password" in st:
        return ""
    c = s.get("container")
    if not c or not docker_api.available():
        return ""
    hit = _join_pw.get(c)
    if hit and time.time() - hit[0] < 300:
        return hit[1]
    pw = ""
    try:
        info = await docker_api.inspect(c)
        env = dict(e.split("=", 1) for e in (info.get("Config") or {}).get("Env") or [] if "=" in e)
        pw = next((env[k] for k in JOIN_PW_ENV if env.get(k)), "")
        if not pw and game_of(s) == "factorio" and (info.get("State") or {}).get("Running"):
            raw = await docker_api.exec_cmd(c, ["sh", "-c", "cat /factorio/config/server-settings.json 2>/dev/null"], timeout=8)
            try:
                pw = json.loads(raw).get("game_password") or ""
            except ValueError:
                pw = ""
    except docker_api.DockerError:
        pw = ""
    _join_pw[c] = (time.time(), pw)
    return pw


def _map_image(g: str, st: dict) -> str | None:
    track = wfd.track_name(st.get("map")) if g == "wreckfest" else None
    return mapimages.image_for(g, st.get("map"), st.get("workshop"), track)


def _wf_layout(track: str | None) -> str | None:
    return mapimages.wf_layouts([k for k, _, _ in wfd.TRACKS]).get(track or "") if track else None


def _pending_installs(known: set) -> list[dict]:
    """Server, die gerade angelegt werden (Kopieren/Image laden …) und noch keinen Eintrag haben – für die Übersicht."""
    out = []
    for j in list(_jobs.values()):
        if j.get("done") or j.get("error"):
            continue
        if j.get("plans"):      # Stapel: noch nicht begonnene Server als „wartet“
            for pl in j["plans"][len(j.get("batch") or []):]:
                out.append({"id": f"job-{j['id']}-{pl['values'].get('name')}", "game": j["game"], "name": pl["values"].get("name") or j["game"],
                            "online": False, "pending": True, "install": {"label": "wartet (wird nacheinander angelegt)", "pct": 0, "eta": None}})
            continue
        if j.get("req") is None or (j.get("server_id") and j["server_id"] in known):
            continue
        pg = j.get("progress") or {}
        label = pg.get("label") or ("Spieldateien kopieren" if j.get("stage") == "copy" else (j.get("step") or "wird angelegt")[:60])
        out.append({"id": f"job-{j['id']}", "game": j["game"], "name": j.get("title") or j["game"], "online": False, "pending": True,
                    "install": {"label": label, "pct": round(pg.get("pct") or 0, 1), "eta": pg.get("eta"),
                                "rate_bps": pg.get("rate_bps"), "rate_kind": "Kopieren"}})
    return out


def _public_install(s: dict) -> dict | None:
    p = ((install_watch.state.get(s.get("container") or "") or {}).get("progress")) if s.get("container") else None
    if not p:
        return None
    ld = livestats.data.get(s.get("container") or "") or {}
    rate = ld.get("rx_bps") if ld and time.time() - ld.get("t", 0) < 10 else None
    return {"label": p.get("label") or "Installation", "pct": round(p.get("pct") or 0, 1), "eta": p.get("eta"),
            "phase": p.get("phase"), "total": p.get("total"), "rate_bps": round(rate) if rate else None, "rate_kind": "Download"}


_rot_cache: dict[str, tuple[float, list]] = {}


async def _public_rotation(s: dict) -> list[dict]:
    """Rotation/Mapcycle für die öffentliche Ansicht (5 min gecacht)."""
    hit = _rot_cache.get(s["id"])
    if hit and time.time() - hit[0] < 300:
        return hit[1]
    g, c, out = game_of(s), s.get("container"), []
    try:
        if c and docker_api.available():
            if g == "wreckfest":
                text = await _wf_read(c) or ""
                lay = mapimages.wf_layouts([k for k, _, _ in wfd.TRACKS])
                out = [{"name": wfd.track_name(e.get("track")), "layout": lay.get(e.get("track") or ""),
                        "image": mapimages.wf_photo(wfd.track_name(e.get("track"))),
                        "sub": " · ".join(x for x in (wfd.MODE_NAMES.get(e.get("gamemode") or "racing", e.get("gamemode") or ""),
                                                      f"{e['laps']} Runden" if e.get("laps") else "",
                                                      f"Klasse {e['car_class_restriction'].upper()}" if e.get("car_class_restriction") else "") if x)}
                       for e in wfd.parse_events(text)]
            elif g == "tf2":
                raw = await docker_api.exec_cmd(c, ["sh", "-c", "cat /home/steam/tf-dedicated/tf/cfg/mapcycle.txt 2>/dev/null"], timeout=8)
                out = [{"name": ln.strip()} for ln in raw.splitlines() if ln.strip() and not ln.strip().startswith("//")][:60]
    except docker_api.DockerError:
        out = []
    _rot_cache[s["id"]] = (time.time(), out)
    return out


@app.get("/api/public/{sid}")
async def public_server(sid: str):
    """Details für die öffentliche Ansicht: Spieler (nur Name/Zeit/Punkte) und Rotation."""
    s = next((x for x in load_servers() if x["id"] == sid), None)
    if not s:
        raise HTTPException(404, "Server nicht gefunden")
    st = _state.get(sid, {})
    g = game_of(s)
    players = []
    for p in (st.get("players") or [])[:128]:
        if isinstance(p, dict) and p.get("name"):
            players.append({k: p.get(k) for k in ("name", "time", "score", "ping", "bot") if p.get(k) not in (None, "")})
    current = st.get("map")
    if g == "wreckfest":
        current = wfd.track_name(current)
    return {"id": sid, "game": g, "name": st.get("hostname") or s.get("name"), "online": bool(st.get("online")),
            "map": current, "mode": (st.get("mode") or {}).get("label") if isinstance(st.get("mode"), dict) else None,
            "players": players, "max_players": st.get("max_players"), "rotation": await _public_rotation(s),
            "matches": [_public_match(m) for m in matchlog.recent(sid, 3)]}


@app.post("/api/matchzy/events/{sid}")
async def matchzy_event(sid: str, request: Request):
    """Empfang der MatchZy-Ereignisse (vom CS2-Server, mit geheimem Header)."""
    s = next((x for x in load_servers() if x["id"] == sid), None)
    if not s or not hmac.compare_digest(request.headers.get("x-gsm-key", ""), matchlog.secret(sid, SECRET)):
        raise HTTPException(403, "falscher Schlüssel")
    try:
        ev = await request.json()
    except ValueError:
        raise HTTPException(400, "kein JSON")
    if isinstance(ev, dict):
        matchlog.ingest(sid, s.get("name") or sid, ev)
    return {"ok": True}


def _public_match(m: dict) -> dict:
    return {k: m.get(k) for k in ("server", "sid", "map", "maps", "live", "finished", "started", "ended", "updated", "series")} | {
        "team1": m["team1"], "team2": m["team2"]}


@app.get("/api/public")
async def public_servers(request: Request):
    """Alle Server mit Status und Beitrittsdaten – ohne Anmeldung (keine RCON-/Admin-Daten)."""
    out = []
    wan = await wan_host()
    steam = await steamlist.listed(wan)
    for s in load_servers():
        st = _state.get(s["id"], {})
        g = game_of(s)
        try:
            join = st.get("join") or join_info(s)
        except Exception:  # noqa: BLE001
            join = None
        out.append({"id": s["id"], "game": g, "name": (st.get("hostname") if s.get("name_from_game", True) else None) or s.get("name") or g,
                    "online": bool(st.get("online")), "sleeping": (_asleep.get(s["id"]) or {}).get("mode"),
                    "install": _public_install(s),
                    "reach": steamlist.reach(g, s, st, steam, wan),
                    "tv": (st.get("tv") or {}).get("enabled") and bool((st.get("join") or {}).get("tv_url")), "players": st.get("humans"),
                    "max_players": st.get("max_players"), "map": st.get("map"),
                    "map_label": wfd.track_name(st.get("map")) if g == "wreckfest" else (mapimages.workshop_title(st.get("map")) or st.get("map")),
                    "map_image": _map_image(g, st),
                    "map_layout": _wf_layout(st.get("map")) if g == "wreckfest" else None,
                    "workshop": {k: (st.get("workshop") or {}).get(k) for k in ("preview", "title")} if st.get("workshop") else None,
                    "mode": (st.get("mode") or {}).get("label") if isinstance(st.get("mode"), dict) else None,
                    "version": st.get("version"), "join": await localize_join(request, s, join), "join_password": await _join_password(s)})
    out += _pending_installs({x["id"] for x in out})
    out.sort(key=lambda x: (not x["online"], GAMES.get(x["game"], {}).get("label", x["game"]), x["name"].lower()))
    games = {k: {kk: v.get(kk) for kk in ("label", "short", "color")} for k, v in GAMES.items()}
    lan = client_is_lan(request)
    lc = cache_stats.state.get("container")
    ld = livestats.data.get(lc or "") or {}
    fresh = ld and time.time() - ld.get("t", 0) < 10
    try:
        hr = (cache_stats.summary().get("last_hour") or {}).get("hit_ratio")
    except Exception:  # noqa: BLE001
        hr = None
    now = time.time()
    skip = {prefill.NAME, "spielservermanager"}
    rx = [d.get("rx_bps") for n_, d in livestats.data.items()
          if n_ not in skip and d.get("running") and d.get("rx_bps") is not None and now - d.get("t", 0) < 10]
    internet = {"down_bps": round(sum(rx)) if rx else None}  # Bytes/s
    cache = {"found": bool(lc), "running": bool(fresh and ld.get("running", True)) if lc else False,
             "tx_bps": ld.get("tx_bps") if fresh else None, "rx_bps": ld.get("rx_bps") if fresh else None, "hit_ratio": hr}
    return {"servers": out, "games": games, "updated": time.time(), "net": "lan" if lan else "internet", "cache": cache,
            "internet": internet,
            "matches": [_public_match(m) for m in matchlog.recent(None, 6)],
            "address": None if lan else await wan_host()}


@app.get("/api/version")
async def version():
    return {"version": os.getenv("APP_VERSION", "dev"), "commit": os.getenv("APP_COMMIT", "lokal")[:7],
            "date": os.getenv("BUILD_DATE") or None}


auth = [Depends(require_auth)]
prefill.EXTRA_NAMES[:] = [sv["name"] for sv in prefill_more.SERVICES.values()]


@app.get("/api/me")
async def me(request: Request):
    u = token_user(request.cookies.get(COOKIE))
    pl = None
    if u:
        p = next((x for x in playerdb.all_players() if x.get("user") == u["username"]), None)
        if p:
            pl = {"id": p["id"], "name": playerdb.display(p), "nick": p.get("nick") or "", "steamid": p.get("steamid") or "",
                  "avatar": p.get("avatar") or "", "admin": sorted(playerdb.admin_games(p, _user_admin_games))}
    return {"authenticated": bool(u), "user": users.public(u) if u else None, "player": pl}


class MeProfileIn(BaseModel):
    nick: str | None = Field(None, max_length=64)
    steamid: str | None = Field(None, max_length=200)


@app.put("/api/me/profile", dependencies=auth)
async def me_profile(data: MeProfileIn, request: Request):
    """Eigenes Spielerprofil: Nickname und SteamID (legt den Spieler an, falls es noch keinen gibt)."""
    u = request.state.user
    p = next((x for x in playerdb.all_players() if x.get("user") == u["username"]), None)
    sid = ""
    if data.steamid:
        try:
            sid = (await steam.resolve_player(data.steamid))["steamid"]
        except steam.SteamError as e:
            raise HTTPException(400, str(e))
        other = playerdb.get(sid)
        if other and other is not p:
            if other.get("user") and other["user"] != u["username"]:
                raise HTTPException(409, "Diese SteamID gehört schon zu einem anderen Konto")
            if p is None:
                p = other                         # vorhandenen Spieler mit dieser SteamID übernehmen
            else:
                playerdb.merge(p["id"], other["id"])
                p = playerdb.get(p["id"]) or playerdb.get(sid)
    if p is None:
        p = playerdb.add_manual(sid, data.nick or u["username"], "") if sid else playerdb.seen(name=data.nick or u["username"], game="manuell")
    fields = {"user": u["username"]}
    if data.nick is not None:
        fields["nick"] = data.nick
    if sid:
        fields["steamid"] = sid
    try:
        playerdb.update(p["id"], fields)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return await me(request)


auth = [Depends(require_auth)]


def _is_admin(request: Request) -> bool:
    return ((getattr(request.state, "user", None) or {}).get("role")) == "admin"


def _need_admin(request: Request) -> None:
    if not _is_admin(request):
        raise HTTPException(403, "Nur für Administratoren")


class UserIn(BaseModel):
    username: str = Field(min_length=1, max_length=32)
    password: str | None = Field(None, max_length=128)
    role: str | None = None
    perms: dict[str, int] | None = None


@app.get("/api/users", dependencies=auth)
async def list_users():
    linked = {p.get("user"): playerdb.display(p) for p in playerdb.all_players() if p.get("user")}
    return {"users": [{**users.public(u), "player": linked.get(u["username"])} for u in users.load()], "roles": users.ROLE_LABELS,
            "levels": users.LEVELS, "level_hints": users.LEVEL_HINTS}


@app.post("/api/users", dependencies=auth)
async def add_user(data: UserIn):
    if users.find(data.username):
        raise HTTPException(400, "Benutzer existiert bereits")
    try:
        return users.public(users.upsert(data.username, data.password, data.role or "user", data.perms))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.put("/api/users/{username}", dependencies=auth)
async def update_user(username: str, data: UserIn):
    if not users.find(username):
        raise HTTPException(404, "Benutzer nicht gefunden")
    try:
        return users.public(users.upsert(username, data.password or None, data.role, data.perms))
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


_ts_fail: dict[str, tuple[float, str, str, str]] = {}


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
async def list_servers(request: Request):
    u = request.state.user
    return [public(s) | {"perm": users.level(u, game_of(s))} for s in load_servers() if visible(request, s)]


@app.post("/api/servers", dependencies=auth)
async def add_server(data: ServerIn, request: Request):
    need_game(request, data.game if data.game in GAMES else "cs2", 4)
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


STATE_CVARS = ["game_type", "game_mode", "sv_visiblemaxplayers", "mp_maxrounds", "sv_password", "bot_quota", "sv_hibernate_when_empty",
               "tv_enable", "tv_port", "sv_lan"]


async def _matchzy_info(s: dict) -> dict:
    """MatchZy-Erkennung (gecacht 5 Min.) + optional get5_status."""
    st = _state.setdefault(s["id"], {})
    mz = st.get("_matchzy")
    if not mz or (time.time() - mz["checked"] > 300 and not mz.get("unloaded")):
        try:
            out = await client_for(s).execute("css_plugins list")
        except RconError:
            out = ""
        m = re.search(r"MatchZy[^\n]*?(\d+\.\d+\.\d+)", out, re.I)
        mz = {"installed": bool(re.search(r"matchzy", out, re.I)), "version": m.group(1) if m else None,
              "checked": time.time()}
        st["_matchzy"] = mz
    info = {"installed": mz["installed"], "version": mz.get("version"), "match": None, "unloaded": bool(mz.get("unloaded"))}
    if mz["installed"] and not mz.get("unloaded"):
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


# ---------------------------------------------------------------- LAN oder Internet: passende Adresse zum Beitreten
_wan: dict = {"ip": None, "t": 0.0}


def client_ip(request: Request) -> str:
    """IP des Besuchers – hinter einem Reverse-Proxy aus X-Forwarded-For."""
    ip = request.client.host if request.client else ""
    fwd = request.headers.get("x-forwarded-for") or request.headers.get("x-real-ip") or ""
    try:
        if fwd and ipaddress.ip_address(ip).is_private:
            ip = fwd.split(",")[0].strip()
    except ValueError:
        pass
    return ip


def client_is_lan(request: Request) -> bool:
    try:
        a = ipaddress.ip_address(client_ip(request))
        return a.is_private or a.is_loopback or a.is_link_local
    except ValueError:
        return True


async def wan_host() -> str | None:
    """Öffentliche Adresse: aus den Einstellungen, sonst automatisch (stündlich ermittelt)."""
    manual = (automation.get_settings().get("internet_host") or "").strip()
    if manual:
        return manual
    if _wan["ip"] and time.time() - _wan["t"] < 3600:
        return _wan["ip"]
    if time.time() - _wan["t"] < 300 and not _wan["ip"]:
        return None
    _wan["t"] = time.time()
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5) as cl:
            r = await cl.get("https://api.ipify.org")
        ip = r.text.strip()
        ipaddress.ip_address(ip)
        _wan["ip"] = ip
    except Exception:  # noqa: BLE001
        _wan["ip"] = None
    return _wan["ip"]


async def localize_join(request: Request, s: dict, join: dict | None) -> dict | None:
    """Für Besucher aus dem Internet die öffentliche Adresse statt der LAN-IP einsetzen."""
    if not join or client_is_lan(request):
        return join and {**join, "net": "lan"}
    wan = await wan_host()
    if not wan:
        return {**join, "net": "lan", "hint": (join.get("hint") or "") + " (Öffentliche Adresse unbekannt – in den Einstellungen eintragen.)"}
    lan = _join_host(s)
    j = dict(join)
    for k in ("address", "url", "tv_url", "tv_address"):
        if j.get(k):
            j[k] = j[k].replace(lan, wan)
    if j.get("hint"):
        j["hint"] = j["hint"].replace(lan, wan)
    j["net"] = "internet"
    return j


# ---------------------------------------------------------------- Beitreten / Namen aus dem Spiel
def _join_host(s: dict) -> str:
    h = s["host"]
    if h in ("127.0.0.1", "localhost", "::1", "0.0.0.0"):
        return _docker_host_ip()
    return h


def _with_tv(j: dict, s: dict, cv: dict) -> dict:
    """CSTV (Zuschauen): CS2 direkt mit „connect TV-Port“ starten (steam://connect scheitert an der Server-Abfrage), wenn tv_enable an ist."""
    try:
        on = str(cv.get("tv_enable") or "").strip() in ("1", "true", "1.000000")
        port = int(float(cv.get("tv_port") or 0))
    except ValueError:
        on, port = False, 0
    if on and port:
        host = _join_host(s)
        return {**j, "tv_url": f"steam://run/730//+connect%20{host}:{port}", "tv_address": f"{host}:{port}"}
    return j


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
                "hint": "Startet Wreckfest – dann Mehrspieler → Server-Browser → Reiter „LAN“ (oder Online, nach dem Servernamen suchen)."
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
        if m := re.match(r"^Groh\s+.+?\s(\d+)(?=\s|$)", txt, re.I):  # „Groh CS 1 Wingman“, alt „Groh Wettkampf 2“
            return int(m.group(1))
    if m := re.search(r"(\d+)\s*$", s.get("container") or ""):
        return int(m.group(1))
    same = [x["id"] for x in load_servers() if game_of(x) == game_of(s)]
    return same.index(s["id"]) + 1 if s["id"] in same else 1


def _auto_name(s: dict, hostname: str | None, mode_label: str = "") -> str | None:
    """Einheitlicher Servername für alle Spiele außer CS2: z. B. „TF2 #1 Payload“, „Wreckfest #2 Derby“, „Valheim #1“."""
    if not s.get("mode_name", True):
        return None
    pattern = (automation.get_settings().get("names_pattern") or "").strip()
    if not pattern:
        return None
    g = game_of(s)
    short = (GAMES.get(g) or {}).get("short") or g
    # ohne {game} im Muster und ohne Modus steht dort der Spielname
    mode = mode_label or ((GAMES.get(g) or {}).get("short") if "{game}" not in pattern else "") or ""
    name = pattern.replace("{game}", short).replace("{nr}", str(_server_nr(s, hostname))).replace("{mode}", mode)
    name = re.sub(r'["\\;]', "", re.sub(r"\s+", " ", name)).strip(" -·|")[:63]
    return name or None


async def _apply_auto_name(s: dict, g: str, st: dict) -> None:
    """Live umbenennen, wo das Spiel es ohne Neustart erlaubt (TF2 per RCON, Satisfactory per API)."""
    try:
        if g == "tf2":
            want = _auto_name(s, st.get("hostname"), (st.get("mode") or {}).get("label") or "")
            if want and want != st.get("hostname"):
                await client_for(s).execute(f'hostname "{want}"')
                st["hostname"] = want
        elif g == "satisfactory" and st.get("privilege") == "Administrator":
            want = _auto_name(s, st.get("hostname"), "")
            if want and want != st.get("hostname"):
                await sf_client(s).call("RenameServer", {"ServerName": want})
                st["hostname"] = want
    except Exception as e:  # noqa: BLE001 – Umbenennen darf den Status nie verhindern
        log.debug("Umbenennen von %s fehlgeschlagen: %s", s.get("name"), e)


def _mode_hostname(s: dict, hostname: str | None, mode_label: str, settings: dict) -> str | None:
    pattern = (settings.get("hostname_pattern") or "").strip()
    if not pattern:
        return None
    name = pattern.replace("{nr}", str(_server_nr(s, hostname))).replace("{mode}", mode_label)
    return re.sub(r'["\\;]', "", name).strip()[:63] or None


_mzlog_set: dict[str, float] = {}
_tvpw_set: dict[str, float] = {}
TOOL_PORT = int(os.getenv("TOOL_PORT", "8090"))


def _tool_url(s: dict) -> str:
    """Adresse, unter der die Spielserver das Tool erreichen (Einstellung public_url, sonst LAN-IP:8090)."""
    pub = (automation.get_settings().get("public_url") or "").rstrip("/")
    return pub or f"http://{_join_host(s)}:{TOOL_PORT}"


_mz_off: dict[str, float] = {}          # Server -> MatchZy von uns entladen (Zeitpunkt)


async def _auto_matchzy(s: dict, c, mode: dict | None) -> None:
    """MatchZy nur in Competitive/Wingman: in anderen Modi stören Ready-System/Warmup – dann entladen, zurück wieder laden."""
    key = (mode or {}).get("key")
    if key is None:
        return
    comp = key in COMPETITIVE_MODES
    if comp:
        if s["id"] in _mz_off:
            out = await c.execute("css_plugins load MatchZy")
            _mz_off.pop(s["id"], None)
            _state.get(s["id"], {}).pop("_matchzy", None)
            log.info("%s: Wettkampfmodus – MatchZy geladen (%s)", s["name"], out.strip()[:80])
        return
    if s["id"] in _mz_off:
        if _mz_off[s["id"]] > time.time():       # gerade für ein Match geladen
            return
        if not (_state.get(s["id"], {}).get("_matchzy") or {}).get("unloaded"):
            _mz_off.pop(s["id"], None)           # wieder geladen (Match vorbei?) -> neu bewerten
        else:
            return
    mz = await _matchzy_info(s)
    if not mz.get("installed"):
        return
    state = ((mz.get("match") or {}).get("state") or "none").lower()
    if state not in ("none", "pre_veto", ""):
        return                                    # laufendes Match nie unterbrechen
    await c.execute("css_plugins unload MatchZy")
    _mz_off[s["id"]] = time.time()
    st = _state.setdefault(s["id"], {})
    st["_matchzy"] = {**(st.get("_matchzy") or {}), "installed": True, "unloaded": True, "checked": time.time()}
    log.info("%s: Modus %s – MatchZy entladen", s["name"], key)


async def ensure_matchzy(s: dict) -> None:
    """Vor einem Match MatchZy laden, falls wir es im Freizeit-Modus entladen hatten."""
    if s["id"] in _mz_off:
        try:
            await client_for(s).execute("css_plugins load MatchZy")
        except RconError:
            pass
        _mz_off[s["id"]] = time.time() + 3600      # eine Stunde lang nicht wieder entladen (Match läuft an)
        _state.get(s["id"], {}).pop("_matchzy", None)
        await asyncio.sleep(2)


_bots_set: dict[str, int] = {}          # Server -> von uns gesetzte bot_quota
COMPETITIVE_MODES = {"competitive", "wingman", "premier"}


async def _auto_bots(s: dict, c, st: dict, cv: dict, mode: dict | None, slots: int | None) -> str | None:
    """Nicht-kompetitive Modi: Ist nur ein Spieler da, mit Bots auffüllen; ab dem zweiten Spieler wieder entfernen."""
    humans = st.get("humans") or 0
    key = (mode or {}).get("key")
    try:
        quota = int(float(cv.get("bot_quota") or 0))
    except ValueError:
        quota = 0
    if key in COMPETITIVE_MODES or key is None:
        if s["id"] in _bots_set and quota:
            await c.execute("bot_quota 0; bot_kick")
            _bots_set.pop(s["id"], None)
            return "Wettkampfmodus – Bots entfernt"
        return None
    want = max(2, min(int(slots or 10), 10)) if humans == 1 else 0
    if want and quota != want:
        await c.execute(f"bot_quota_mode fill; bot_quota {want}; bot_difficulty 2")
        _bots_set[s["id"]] = want
        log.info("%s: allein auf dem Server – mit Bots auf %s aufgefüllt", s["name"], want)
        return f"Mit Bots auf {want} aufgefüllt (nur 1 Spieler)"
    if not want and s["id"] in _bots_set and quota:
        await c.execute("bot_quota 0; bot_kick")
        _bots_set.pop(s["id"], None)
        log.info("%s: %s Spieler – Bots entfernt", s["name"], humans)
        return "Bots entfernt"
    return f"Bots aktiv ({quota})" if s["id"] in _bots_set and quota else None


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
    if apply_auto and s.get("hibernate") is not None:
        want_h = "1" if s.get("hibernate") else "0"
        if str(cv.get("sv_hibernate_when_empty") or "").strip() not in (want_h, want_h + ".000000"):
            await c.execute(f"sv_hibernate_when_empty {want_h}")
    bots_auto = None
    if apply_auto and settings.get("auto_matchzy", True):
        try:
            await _auto_matchzy(s, c, mode)
        except RconError:
            pass
    if apply_auto and s.get("auto_bots", True) and settings.get("auto_bots", True):
        bots_auto = await _auto_bots(s, c, st, cv, mode, target or visible)
    mzc = (_state.get(s["id"], {}).get("_matchzy") or {})
    if apply_auto and mzc.get("installed") and not mzc.get("unloaded") and time.time() - _mzlog_set.get(s["id"], 0) > 1800:
        try:   # MatchZy meldet Matches (Teams, Spielstand, Spielerwerte) an das Tool
            url = f"{_tool_url(s)}/api/matchzy/events/{s['id']}"
            await c.execute(f'matchzy_remote_log_url "{url}"; matchzy_remote_log_header_key "X-GSM-Key"; '
                            f'matchzy_remote_log_header_value "{matchlog.secret(s["id"], SECRET)}"')
            _mzlog_set[s["id"]] = time.time()
        except RconError:
            pass
    if str(cv.get("tv_enable") or "").strip() in ("1", "1.000000") and time.time() - _tvpw_set.get(s["id"], 0) > 600:
        try:   # Zuschauer brauchen kein Passwort (Image-Standard „changeme“ überschreiben)
            await c.execute('tv_password ""')
            _tvpw_set[s["id"]] = time.time()
        except RconError:
            pass
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
    if ws and ws.get("map"):
        mapimages.remember_workshop_map(ws["map"], ws)
    result = {
        "online": True, "raw": raw, **st,
        "mode": {"key": mode["key"], "label": mode["label"]} if mode else
                {"key": None, "label": f"type {cv['game_type']} / mode {cv['game_mode']}"},
        "game_type": cv["game_type"], "game_mode": cv["game_mode"],
        "visible_players": visible, "maxrounds": cv["mp_maxrounds"],
        "password_set": bool(cv["sv_password"]), "join_password": cv["sv_password"] or "", "bot_quota": cv["bot_quota"],
        "auto": {"enabled": auto_on, "target": target, "reason": reason, "capped": capped, "applied": applied, "bots": bots_auto},
        "join": _with_tv(join_info(s, cv["sv_password"] or None), s, cv),
        "workshop": ws,
        "sv_lan": cv.get("sv_lan"),
        "tv": {"enabled": str(cv.get("tv_enable") or "").strip() in ("1", "true", "1.000000"),
               "port": int(float(cv["tv_port"])) if str(cv.get("tv_port") or "").replace(".", "").isdigit() else None},
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
            # Nach falschem Login nicht weiter probieren – sonst sperrt TeamSpeak die IP (Flood-Ban, id 3329)
            # Pause endet bei neuem Passwort oder Neustart des Containers (z. B. nach serveradmin_password=…)
            key = (s.get("password") or "")
            fail = _ts_fail.get(s["id"])
            if fail and fail[1] == key and time.time() - fail[0] < 900:
                started = ""
                if s.get("container") and docker_api.available():
                    try:
                        started = ((await docker_api.inspect(s["container"])).get("State") or {}).get("StartedAt") or ""
                    except docker_api.DockerError:
                        pass
                if started == fail[3]:
                    raise tsmod.TeamSpeakError(fail[2])
            started_now = ""
            if s.get("container") and docker_api.available():
                try:
                    started_now = ((await docker_api.inspect(s["container"])).get("State") or {}).get("StartedAt") or ""
                except docker_api.DockerError:
                    pass
            try:
                st = await tsmod.status(ts_query(s))
                _ts_fail.pop(s["id"], None)
            except tsmod.TeamSpeakError as e:
                if "permission" in str(e) or "id 520" in str(e) or "id 2568" in str(e) or "banned" in str(e) or "id 3329" in str(e):
                    msg = ("ServerQuery-Login falsch – unter „Bearbeiten“ das serveradmin-Passwort eintragen. Unbekannt? Im Stack einmal "
                           "command: ts3server serveradmin_password=NEUES_PASSWORT setzen, neu starten, Passwort hier eintragen. "
                           "(Weitere Versuche pausiert, damit TeamSpeak nicht sperrt.)")
                    _ts_fail[s["id"]] = (time.time(), key, msg, started_now)
                    raise tsmod.TeamSpeakError(msg) from e
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
    await _apply_auto_name(s, g, st)
    result = {"online": True, "game": g, **st, "join": join_info(s, pw)}
    if pw:
        result["join_password"] = pw
    await _sync_name(s, st.get("hostname"))
    prev = _state.get(s["id"], {})
    _state[s["id"]] = {**{k: v for k, v in prev.items() if k.startswith("_")}, **result}
    return result


@app.get("/api/servers/{sid}/status", dependencies=auth)
async def status(sid: str, request: Request):
    s = get_server(sid)
    if sid in _asleep:
        raise HTTPException(503, f"Server schläft ({'pausiert' if _asleep[sid]['mode'] == 'pause' else 'angehalten'}) – „Aufwecken“ klicken")
    try:
        r = await collect_state(s, apply_auto=True, with_matchzy=True)
        return {**r, "join": await localize_join(request, s, r.get("join")), "map_image": _map_image(game_of(s), r)}
    except RconAuthError as e:
        drop_client(sid)
        raise HTTPException(502, str(e))
    except RconError as e:
        _state[sid] = {**_state.get(sid, {}), "online": False, "error": str(e), "updated": time.time()}
        raise HTTPException(502, str(e))


@app.get("/api/overview", dependencies=auth)
async def overview(request: Request):
    out = []
    wan = await wan_host()
    steam = await steamlist.listed(wan)
    for s in load_servers():
        if not visible(request, s):
            continue
        st = _state.get(s["id"], {})
        item = {"server": public(s), **{k: v for k, v in st.items() if not k.startswith("_") and k != "raw"}}
        if item.get("join"):
            item["join"] = await localize_join(request, s, item["join"])
        item["sleeping"] = (_asleep.get(s["id"]) or {}).get("mode")
        item["map_image"] = _map_image(game_of(s), st)
        if game_of(s) == "wreckfest":
            item["map_layout"] = _wf_layout(st.get("map"))
        item["reach"] = steamlist.reach(game_of(s), s, st, steam, wan)
        if game_of(s) == "cs2" and not item.get("workshop") and mapimages.workshop_title(st.get("map")):
            item["map_title"] = mapimages.workshop_title(st.get("map"))
        item["sleep_mode"] = s.get("sleep_mode") or "off"
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
                names |= {sv["name"] for sv in prefill_more.SERVICES.values()}
                livestats.ensure(names)
        except Exception:  # noqa: BLE001
            log.exception("Live-Messung")
        n += 1
        await asyncio.sleep(1)


def _lan_client_tx(lh: dict) -> float | None:
    """Was der Host wirklich an LAN-Clients sendet: Netzwerkkarte minus Schreiben aufs NAS (iSCSI-LUN und NFS).
    Sonst zählt der Prefill sich selbst – er lässt den Lancache auf die iSCSI-LUN schreiben, das geht als Upload raus."""
    if lh.get("source") != "host" or lh.get("tx_bps") is None:
        return None
    io = livestats.io or {}
    storage = sum(m.get("write_bps") or 0 for m in io.get("mounts") or [])
    try:
        dev = (hoststorage.mount_status(hoststorage.settings()["mountpoint"]).get("device") or "").rsplit("/", 1)[-1]
    except Exception:  # noqa: BLE001
        dev = ""
    if dev:
        storage += sum(d.get("write_bps") or 0 for d in io.get("disks") or [] if dev.startswith(d["name"]))
    return max(0.0, lh["tx_bps"] - storage * 1.08)       # +8 % für iSCSI/TCP-Overhead


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
                prx = sum((livestats.data.get(n_) or {}).get("rx_bps") or 0 for n_ in [prefill.NAME] + prefill.EXTRA_NAMES)
                # alles, was gerade installiert, lädt, kopiert oder aktualisiert -> Prefills pausieren
                dls = [x["name"] for x in load_servers() if x.get("container") and
                       (install_watch.state.get(x["container"]) or {}).get("progress")]
                dls += [j.get("title") or j.get("game") for j in _jobs.values() if not j.get("done") and j.get("req")]
                lh = livestats.host
                await prefill.yield_check(cd.get("tx_bps"), prx, dls, _lan_client_tx(lh))
                await _prefill_queue_tick()
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
            try:                                   # LAN-Weiterleiter (Wreckfest) mit entfernen
                await docker_api.remove_container(_relay_name(plan["container"]))
            except docker_api.DockerError:
                pass
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
                                       "apps_done": done, "apps_total": len(pp["apps"])}, "svc": "steam"})
    except docker_api.DockerError:
        pass
    for svc, sv in prefill_more.SERVICES.items():      # Battle.net / Epic
        try:
            pst = await prefill_more.state(svc)
            if not (pst and pst.get("running")):
                continue
            text = await prefill_more.log(svc, 1500)
            pp = prefill.parse_progress(text)
            cur = pp["current"]
            d = livestats.data.get(sv["name"]) or {}
            done = sum(1 for a in pp["apps"] if a["state"] in ("fertig", "aktuell"))
            waiting = prefill_more.prompt_of(text)
            items.append({"server_id": None, "name": f"{sv['label']}-Prefill" + (": Anmeldung nötig" if waiting else f": {cur['name']}" if cur else ""),
                          "game": "prefill", "container": sv["name"], "errors": [], "prefill": True, "svc": svc,
                          "progress": {"label": "wartet auf Anmeldung" if waiting else "Vorladen", "pct": cur["pct"] if cur else 0.0,
                                       "rate": d.get("rx_bps"), "apps_done": done, "apps_total": len(pp["apps"])}})
        except docker_api.DockerError:
            pass
    jobs = [{"id": j["id"], "game": j["game"], "step": j["step"], "error": j["error"], "done": j["done"],
             "server_id": j["server_id"], "title": j.get("title"), "progress": j.get("progress")}
            for j in _jobs.values() if (not j["done"] or j["error"]) and not j.get("cancelled")]
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


@app.get("/api/appicon/{appid}")
async def app_icon(appid: int):
    """Spiel-Icon aus dem lokalen Speicher (einmal von Steam geholt)."""
    f = await depots.icon_file(appid)
    if not f:
        raise HTTPException(404, "kein Icon")
    return FileResponse(f, media_type="image/png" if f.read_bytes()[:4] == b"\x89PNG" else "image/jpeg",
                        headers={"Cache-Control": "public, max-age=2592000, immutable"})


LOGO_URLS = {"teamspeak": "https://icons.duckduckgo.com/ip3/teamspeak.com.ico",
             "minecraft": "https://icons.duckduckgo.com/ip3/minecraft.net.ico"}


@app.get("/api/logo/{key}")
async def logo(key: str):
    """Logos von Spielen ohne Steam-Icon (TeamSpeak, Minecraft) – einmal holen, dann lokal ausliefern."""
    url = LOGO_URLS.get(key)
    if not url:
        raise HTTPException(404, "unbekannt")
    depots.ICON_DIR.mkdir(parents=True, exist_ok=True)
    f = depots.ICON_DIR / f"logo_{key}.img"
    if not (f.exists() and f.stat().st_size > 0):
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10, follow_redirects=True, headers={"User-Agent": "Spielservermanager"}) as cl:
                r = await cl.get(url)
            if r.status_code != 200 or len(r.content) < 50:
                raise HTTPException(404, "Logo nicht erreichbar")
            f.write_bytes(r.content)
        except httpx.HTTPError as e:
            raise HTTPException(404, "Logo nicht erreichbar") from e
    data = f.read_bytes()
    mt = "image/png" if data[:4] == b"\x89PNG" else "image/svg+xml" if data.lstrip()[:4] in (b"<svg", b"<?xm") else "image/x-icon"
    return Response(data, media_type=mt, headers={"Cache-Control": "public, max-age=2592000"})


def _likely_apps() -> list[int]:
    """Apps, deren Depots wahrscheinlich im Cache landen: Prefill-Liste und Spielserver."""
    try:
        return [int(a["id"]) for a in prefill.settings().get("apps") or [] if str(a.get("id", "")).isdigit()] + \
            [a["id"] for a in _server_game_apps()]
    except Exception:  # noqa: BLE001
        return []


depots.extra_apps = _likely_apps


@app.get("/api/gameicons")
async def game_icons(apps: str = ""):
    """Icons der Spiele (Steam) – für Seitenleiste, Karten und Lancache-Liste."""
    ids = sorted({int(x) for x in apps.split(",") if x.strip().isdigit()} | set(GAME_APPS.values()))[:60]
    try:
        ic = await depots.icons(ids)
    except Exception:  # noqa: BLE001
        ic = {}
    return {"apps": ic, "games": {g: ic.get(str(a), "") for g, a in GAME_APPS.items()}}


_disks: dict = {"items": [], "t": 0.0, "busy": False}


async def _poll_disks():
    """Belegung der eigenen Platte und aller /mnt-Mounts des Hosts (kurzer, nur lesender Hilfs-Container)."""
    if _disks["busy"]:
        return
    _disks["busy"] = True
    try:
        out = await docker_api.run_helper(["/:/h:ro"], ["sh", "-c", "df -P -B1 /h /h/mnt/* 2>/dev/null | tail -n +2"], timeout=60)
        items = []
        for line in out.splitlines():
            p = line.split()
            if len(p) >= 6 and p[1].isdigit():
                mnt = p[5][2:] or "/"
                items.append({"mount": mnt, "device": p[0], "size": int(p[1]), "used": int(p[2]), "avail": int(p[3]),
                              "network": ":" in p[0] or p[0].startswith("//")})
        seen, uniq = set(), []
        for it in items:
            if it["mount"] in seen:
                continue
            seen.add(it["mount"]); uniq.append(it)
        _disks.update(items=uniq, t=time.time())
    except docker_api.DockerError as e:
        _disks["error"] = str(e)
    finally:
        _disks["busy"] = False


_sizes: dict = {"items": [], "t": 0.0, "busy": False, "error": None}
SIZES_EVERY = 1800


# Größenmessung mit niedrigster Priorität: wenig CPU, Idle-I/O, Pausen zwischen den Ordnern,
# und nur, wenn NAS, Cache-Leitung und Host gerade ruhig sind.
SIZE_SCRIPT = r"""
renice -n 19 $$ >/dev/null 2>&1; ionice -c 3 -p $$ >/dev/null 2>&1
: > /tmp/e; cd "/h$1" 2>/dev/null || { echo NODIR; exit 0; }
df -P . | tail -1 | awk '{printf "DF\t%s\t%.0f\t%s\n", $1, $4*1024, $6}'
one(){ s=$(du -sk -- "$1" 2>>/tmp/e | cut -f1); echo "S	${s:-0}"; sleep 0.05; }
for e in * .[!.]*; do
  [ -e "$e" ] || [ -L "$e" ] || continue
  if [ -d "$e" ] && [ ! -L "$e" ]; then
    for f in "$e"/* "$e"/.[!.]*; do [ -e "$f" ] || [ -L "$f" ] || continue; one "$f"; done
  else one "$e"; fi
done
echo "E	$(cat /tmp/e 2>/dev/null | grep -c .)"
"""
SIZE_LIMITS = {"CpuShares": 2, "NanoCpus": 250_000_000, "Memory": 128 * 1024 * 1024}


def _busy_reason() -> str | None:
    """Gründe, die Messung zu verschieben (Last soll nicht spürbar werden)."""
    io = livestats.io or {}
    mounts = io.get("mounts") or []
    nfs_bps = sum((m.get("read_bps") or 0) + (m.get("write_bps") or 0) for m in mounts)
    rtts = [m["rtt_ms"] for m in mounts if m.get("rtt_ms") is not None and (m.get("ops_s") or 0) > 1]
    lc = livestats.data.get(cache_stats.state.get("container") or "") or {}
    cache_bps = (lc.get("tx_bps") or 0) if time.time() - lc.get("t", 0) < 10 else 0
    cpu = hoststats.state.get("cpu") or 0
    if cache_bps > 5e6:
        return f"Lancache liefert gerade {cache_bps / 1e6:.0f} MB/s"
    if nfs_bps > 20e6:
        return f"NAS überträgt gerade {nfs_bps / 1e6:.0f} MB/s"
    if rtts and max(rtts) > 15:
        return f"NAS antwortet langsam ({max(rtts):.0f} ms)"
    if cpu > 70:
        return f"Server-CPU bei {cpu:.0f} %"
    return None


async def _wait_calm(max_wait: float = 1200) -> bool:
    t0 = time.time()
    while True:
        r = _busy_reason()
        if not r:
            return True
        _sizes["waiting"] = r
        if time.time() - t0 > max_wait:
            return False
        await asyncio.sleep(20)


async def _poll_sizes():
    """Größe der Datenordner aller Spielserver (du im Hilfs-Container, nur lesend, niedrigste Priorität)."""
    if _sizes["busy"]:
        return
    _sizes["busy"] = True
    _sizes["waiting"] = None
    try:
        per: list[tuple[dict, list[str]]] = []
        for s_ in load_servers():
            c = s_.get("container")
            if not c:
                continue
            try:
                info = await docker_api.inspect(c)
            except docker_api.DockerError:
                continue
            src = [m.get("Source") for m in info.get("Mounts") or []
                   if m.get("Source") and m.get("Type") in ("bind", "volume")
                   and not (m.get("Destination") or "").startswith(("/var/run", "/etc", "/proc", "/sys", "/dev"))
                   and not m["Source"].startswith(("/var/run", "/etc", "/proc", "/sys", "/dev", "/run"))]
            if src:
                per.append((s_, src))
        paths = sorted({p for _, ps in per for p in ps})
        old = {p["path"]: p for it in _sizes["items"] for p in it["paths"]}
        info_p: dict[str, dict] = {}
        for path in paths:
            if not await _wait_calm():
                _sizes["error"] = "Messung verschoben – " + (_sizes.get("waiting") or "Last zu hoch")
                if path in old:
                    info_p[path] = old[path]
                continue
            _sizes["waiting"] = None
            _sizes["current"] = path
            try:
                out = await docker_api.run_helper(["/:/h:ro"], ["sh", "-c", SIZE_SCRIPT, "sh", path], timeout=1800,
                                                  host_extra=SIZE_LIMITS)
            except docker_api.DockerError:
                if path in old:
                    info_p[path] = old[path]
                continue
            d = {"bytes": 0, "errors": 0, "device": "", "avail": None, "mount": "", "nfs": False}
            ok = False
            for line in out.splitlines():
                q = line.split("\t")
                if q[0] == "DF" and len(q) >= 4:
                    ok = True
                    d.update(device=q[1], avail=int(q[2]) if q[2].isdigit() else None, mount=q[3][2:] or "/",
                             nfs=":" in q[1] or q[1].startswith("//"))
                elif q[0] == "S" and len(q) >= 2 and q[1].isdigit():
                    d["bytes"] += int(q[1]) * 1024
                elif q[0] == "E" and len(q) >= 2 and q[1].isdigit():
                    d["errors"] = int(q[1])
            if ok:
                info_p[path] = d
        items = []
        for s_, ps in per:
            parts = [dict(info_p[p], path=p) for p in ps if p in info_p]
            if not parts:
                continue
            items.append({"id": s_["id"], "name": s_.get("name") or s_["id"], "game": s_.get("game"),
                          "bytes": sum(x["bytes"] for x in parts), "nfs_bytes": sum(x["bytes"] for x in parts if x["nfs"]),
                          "partial": any(x["errors"] for x in parts), "paths": parts})
        items.sort(key=lambda x: -x["bytes"])
        _sizes.update(items=items, t=time.time())
        if not _sizes.get("waiting"):
            _sizes["error"] = None
    except docker_api.DockerError as e:
        _sizes["error"] = str(e)
        _sizes["t"] = time.time() - SIZES_EVERY + 300   # in 5 min erneut versuchen
    finally:
        _sizes["busy"] = False
        _sizes["current"] = None
        _sizes["waiting"] = None


@app.get("/api/serversizes", dependencies=auth)
async def server_sizes(refresh: bool = False):
    if docker_api.available() and (refresh or time.time() - _sizes["t"] > SIZES_EVERY):
        asyncio.create_task(_poll_sizes())
    nfs = {}
    for it in _sizes["items"]:
        for p in it["paths"]:
            if p["nfs"]:
                nfs.setdefault(p["device"].split(":")[0] + ":" + p["mount"], p["avail"])
    return {"items": _sizes["items"], "updated": _sizes["t"] or None, "busy": _sizes["busy"], "error": _sizes["error"],
            "waiting": _sizes.get("waiting"), "current": _sizes.get("current"),
            "total": sum(x["bytes"] for x in _sizes["items"]), "nfs_total": sum(x["nfs_bytes"] for x in _sizes["items"]),
            "nfs_free": max(nfs.values(), default=None) if nfs else None}


@app.get("/api/disks", dependencies=auth)
async def disks():
    if time.time() - _disks["t"] > 120 and docker_api.available():
        asyncio.create_task(_poll_disks())
    return {"items": _disks["items"], "updated": _disks["t"] or None}


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
    if out.get("live_downloads"):
        by_ip = {p.get("lan_ip"): playerdb.display(p) for p in playerdb.all_players() if p.get("lan_ip")}
        ann = await netnames.annotate([{"ip": d["ip"]} for d in out["live_downloads"]], hosts)
        for d, a in zip(out["live_downloads"], ann):
            d["client"] = by_ip.get(d["ip"]) or a.get("name") or d["ip"]
            if d.get("app"):
                d["icon"] = f"/api/appicon/{d['app']}"
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


# Je Dienst eine typische Download-Domain: zeigt der Lancache-DNS sie auf den Cache, wird der Dienst gecacht
CACHE_SERVICE_HOSTS = {"steam": "lancache.steamcontent.com", "epicgames": "epicgames-download1.akamaized.net",
                       "origin": "origin-a.akamaihd.net", "blizzard": "level3.blizzard.com", "riot": "l3cdn.riotgames.com",
                       "wsus": "download.windowsupdate.com", "uplay": "uplaypc-s-ubisoft.cdn.ubi.com",
                       "xboxlive": "assets1.xboxlive.com", "nintendo": "ccs.cdn.wup.shop.nintendo.net",
                       "sony": "gs2.ww.prod.dl.playstation.net", "wargaming": "dl-wot-ak.wargaming.net"}


@app.get("/api/cache/dns-services", dependencies=auth)
async def cache_dns_services():
    """Welche Dienste leitet der Lancache-DNS auf den Cache um?"""
    _need_docker()
    dns = await lancache_dns()
    if not dns:
        raise HTTPException(400, "Kein Lancache-DNS gefunden")
    dns = dns[0] if isinstance(dns, list) else dns
    awk = "awk '/^Address/ && !/(#|:)53$/ {print $NF}'"
    script = " ; ".join(f'echo "{k} $(nslookup {h} {dns} 2>/dev/null | {awk} | tail -1)"' for k, h in CACHE_SERVICE_HOSTS.items())
    try:
        out = await docker_api.run_helper([], ["sh", "-c", script], timeout=60)
    except docker_api.DockerError as e:
        raise HTTPException(502, str(e))
    res = {}
    for line in out.splitlines():
        k, _, ip = line.strip().partition(" ")
        if k in CACHE_SERVICE_HOSTS:
            res[k] = {"host": CACHE_SERVICE_HOSTS[k], "resolves": ip or None,
                      "cached": bool(ip) and ipaddress.ip_address(ip).is_private if ip and re.fullmatch(r"[\d.]+", ip) else False}
    return {"dns": dns, "services": res}


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


@app.post("/api/cache/reset", dependencies=auth)
async def cache_reset():
    """Statistik zurücksetzen (z. B. nach Umzug auf einen neuen, leeren Cache)."""
    cache_history.reset_all()
    try:
        await prefill.forget_downloaded()
    except docker_api.DockerError:
        pass
    prefill.save_settings({"last_full": None})
    try:
        await cache_stats.reset()
    except docker_api.DockerError as e:
        raise HTTPException(502, f"Verlauf gelöscht, Log konnte nicht geleert werden: {e}")
    asyncio.create_task(cache_stats.poll_storage(True))
    return {"ok": True}


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
            if s["id"] in _asleep:
                return
            try:
                await asyncio.wait_for(collect_state(s, apply_auto=True), timeout=RCON_TIMEOUT * 3)
            except Exception as e:  # noqa: BLE001 – Watcher darf nie sterben
                _state[s["id"]] = {**_state.get(s["id"], {}), "online": False,
                                   "error": str(e) or e.__class__.__name__, "updated": time.time()}
        if servers:
            await asyncio.gather(*(one(s) for s in servers))
            try:
                await _sleep_tick(servers)
            except Exception as e:  # noqa: BLE001
                log.warning("Ruhemodus: %s", e)
        await asyncio.sleep(interval)


# ---------------------------------------------------------------- Ruhemodus: leere Server pausieren/anhalten
SLEEP_MODES = {"off": "aus", "pause": "pausieren (RAM bleibt belegt, Aufwachen in 1 s)", "stop": "anhalten (RAM frei, Start dauert länger)"}
_last_active: dict[str, float] = {}     # Server -> zuletzt Spieler gesehen (oder aufgeweckt)
_asleep: dict[str, dict] = store.load("sleep.json", {})   # Server -> {"mode", "since"} (übersteht Neustarts des Tools)


def _save_asleep() -> None:
    store.save("sleep.json", _asleep)


def _sleep_cfg(s: dict) -> dict:
    return {"mode": s.get("sleep_mode") or "off", "after": int(s.get("sleep_after") or 30), "hibernate": s.get("hibernate")}


async def _sleep_tick(servers: list[dict]) -> None:
    now = time.time()
    for s in servers:
        sid, c = s["id"], s.get("container")
        cfg = _sleep_cfg(s)
        if sid in _asleep:
            # von außen geweckt (Portainer, Docker)? -> wieder normal überwachen
            try:
                st_ = ((await docker_api.inspect(c)).get("State") or {}) if c else {}
            except docker_api.DockerError:
                continue
            if st_.get("Running") and not st_.get("Paused"):
                _asleep.pop(sid, None)
                _save_asleep()
                _last_active[sid] = now
            continue
        st = _state.get(sid, {})
        if st.get("online") and (st.get("humans") or 0) > 0:
            _last_active[sid] = now
        _last_active.setdefault(sid, now)
        if cfg["mode"] not in ("pause", "stop") or not c or not docker_api.available():
            continue
        if not st.get("online") or st.get("players_unknown") or (st.get("humans") or 0) > 0:
            continue                         # nur Server, deren Spielerzahl sicher 0 ist
        if (install_watch.state.get(c) or {}).get("progress"):
            continue                         # lädt gerade ein Update
        if now - _last_active[sid] < cfg["after"] * 60:
            continue
        await _put_to_sleep(s, cfg["mode"], reason=f"{cfg['after']} min ohne Spieler")


async def _put_to_sleep(s: dict, mode: str, reason: str = "") -> None:
    c = s["container"]
    if mode == "stop" and game_of(s) in ("factorio", "satisfactory", "minecraft"):
        try:                                  # vorher speichern, wo das Spiel es kann
            if game_of(s) == "satisfactory":
                await sf_client(s).call("SaveGame", {"SaveName": "vor_ruhemodus"})
            elif game_of(s) == "factorio":
                await run(s, "/server-save")
            elif game_of(s) == "minecraft":
                await docker_api.exec_cmd(c, ["rcon-cli", "save-all"], timeout=20)
        except Exception:  # noqa: BLE001
            pass
    await docker_api.action(c, "pause" if mode == "pause" else "stop")
    drop_client(s["id"])
    _asleep[s["id"]] = {"mode": mode, "since": time.time()}
    _save_asleep()
    _state[s["id"]] = {**{k: v for k, v in _state.get(s["id"], {}).items() if k.startswith("_") or k in ("join", "hostname", "map")},
                       "online": False, "sleeping": mode, "error": "schläft (Ruhemodus)", "updated": time.time()}
    log.info("%s: Ruhemodus (%s) – %s", s.get("name"), mode, reason)


async def wake_server(s: dict) -> str:
    c = s.get("container")
    if not c:
        raise HTTPException(400, "Kein Container zugeordnet")
    try:
        st_ = (await docker_api.inspect(c)).get("State") or {}
        if st_.get("Paused"):
            await docker_api.action(c, "unpause")
        elif not st_.get("Running"):
            await docker_api.action(c, "start")
    except docker_api.DockerError as e:
        raise HTTPException(502, str(e))
    was = _asleep.pop(s["id"], {}).get("mode")
    _save_asleep()
    _last_active[s["id"]] = time.time()
    _state[s["id"]] = {**_state.get(s["id"], {}), "sleeping": None, "error": "wacht auf …", "updated": time.time()}
    return was or "running"


class SleepIn(BaseModel):
    mode: str = "off"
    after: int = Field(30, ge=5, le=1440)
    hibernate: bool | None = None


@app.get("/api/servers/{sid}/sleep", dependencies=auth)
async def sleep_get(sid: str):
    s = get_server(sid)
    return {**_sleep_cfg(s), "modes": SLEEP_MODES, "asleep": _asleep.get(sid),
            "idle_s": int(time.time() - _last_active.get(sid, time.time())),
            "hibernate_supported": game_of(s) == "cs2"}


@app.post("/api/servers/{sid}/sleep/config", dependencies=auth)
async def sleep_config(sid: str, data: SleepIn):
    if data.mode not in SLEEP_MODES:
        raise HTTPException(400, "Unbekannter Modus")
    get_server(sid)
    await _set_server_fields(sid, sleep_mode=data.mode, sleep_after=data.after, hibernate=data.hibernate)
    _last_active[sid] = time.time()
    return {"ok": True}


@app.post("/api/servers/{sid}/sleep/now", dependencies=auth)
async def sleep_now(sid: str):
    s = get_server(sid)
    if not s.get("container"):
        raise HTTPException(400, "Kein Container zugeordnet")
    mode = s.get("sleep_mode") if s.get("sleep_mode") in ("pause", "stop") else "pause"
    try:
        await _put_to_sleep(s, mode, reason="von Hand")
    except docker_api.DockerError as e:
        raise HTTPException(502, str(e))
    return {"ok": True, "mode": mode}


@app.post("/api/servers/{sid}/wake", dependencies=auth)
async def wake(sid: str):
    return {"ok": True, "was": await wake_server(get_server(sid))}


_wake_rl: dict[str, float] = {}


@app.post("/api/public/{sid}/wake")
async def public_wake(sid: str, request: Request):
    """Besucher dürfen schlafende Server aufwecken (mehr nicht)."""
    ip = client_ip(request)
    if time.time() - _wake_rl.get(ip, 0) < 10:
        raise HTTPException(429, "Bitte kurz warten")
    _wake_rl[ip] = time.time()
    s = next((x for x in load_servers() if x["id"] == sid), None)
    if not s or sid not in _asleep:
        raise HTTPException(400, "Server schläft nicht")
    return {"ok": True, "was": await wake_server(s)}


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
async def broadcast(data: BroadcastIn, request: Request):
    servers = [s for s in load_servers() if s["id"] in set(data.server_ids)
               and users.level(request.state.user, game_of(s)) >= 2]

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
    names_pattern: str | None = Field(None, max_length=60)
    internet_host: str | None = Field(None, max_length=120)
    auto_bots: bool | None = None
    auto_matchzy: bool | None = None
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


# ---------------------------------------------------------------- Überwachung & Benachrichtigungen
_manual_stop: dict[str, float] = {}       # vom Benutzer gestoppte Server -> kein Alarm
_mon: dict[str, dict] = {}
DOWN_AFTER = 300                          # 5 min offline -> Alarm


async def _monitor_once() -> None:
    now = time.time()
    servers = load_servers()
    busy_jobs = {(j.get("req") or {}).get("values", {}).get("name") for j in _jobs.values() if not j.get("done")}
    for s in servers:
        sid, st = s["id"], _state.get(s["id"]) or {}
        m = _mon.setdefault(sid, {"seen_online": False, "down_since": None, "alerted": False, "inst": False, "humans": 0, "probs": set()})
        name = st.get("hostname") or s.get("name")
        c = s.get("container")
        inst = (install_watch.state.get(c or "") or {}).get("progress") if c else None
        # Server aus / wieder da
        if st.get("online"):
            if m["alerted"]:
                notify.fire(f"🟢 {name} ist wieder online.", event="server_down", key=f"up-{sid}-{int(now)}")
            m.update(seen_online=True, down_since=None, alerted=False)
        elif m["seen_online"] and sid not in _asleep and sid not in _manual_stop and not inst and s.get("name") not in busy_jobs:
            m["down_since"] = m["down_since"] or now
            if not m["alerted"] and now - m["down_since"] > DOWN_AFTER:
                m["alerted"] = True
                err = (st.get("error") or "")[:120]
                notify.fire(f"🔴 {name} antwortet seit {int((now - m['down_since']) // 60)} min nicht." + (f" ({err})" if err else ""),
                            event="server_down", key=f"down-{sid}")
        # Installation fertig
        if inst:
            m["inst"] = True
        elif m["inst"] and st.get("online"):
            m["inst"] = False
            notify.fire(f"✅ {name}: Installation/Update fertig, Server läuft.", event="install_done", key=f"inst-{sid}-{int(now // 600)}")
        # neue Fehler im Log
        probs = {p.get("title") for p in ((diagnostics.state.get(c or "") or {}).get("problems") or [])} if c else set()
        for p in probs - m["probs"]:
            if p:
                notify.fire(f"⚠️ {name}: {p}", event="problem", key=f"prob-{sid}-{p}")
        m["probs"] = probs
        # erster Spieler
        h = st.get("humans") or 0
        if st.get("online") and h and not m["humans"]:
            notify.fire(f"👤 Jemand spielt auf {name} ({h} Spieler).", event="players", key=f"pl-{sid}-{int(now // 1800)}")
        m["humans"] = h if st.get("online") else 0
    # Speicher
    d = cache_stats.state.get("disk") or {}
    if d.get("total") and d.get("used", 0) / d["total"] > 0.9:
        notify.fire(f"💾 Lancache-Platte zu {round(d['used'] / d['total'] * 100)} % voll ({round(d['free'] / 1e9)} GB frei).", event="disk", key="disk-cache")
    try:
        info = await server_sizes()
        nf = info.get("nfs_free")
    except Exception:  # noqa: BLE001
        nf = None
    if nf is not None and nf < 100e9:
        notify.fire(f"💾 NAS-Freigabe fast voll: nur noch {round(nf / 1e9)} GB frei.", event="disk", key="disk-nas")
    # Lancache
    lc = cache_stats.state.get("container")
    if lc:
        ld = livestats.data.get(lc) or {}
        if ld and not ld.get("running", True) and now - ld.get("t", 0) < 30:
            notify.fire("🛑 Lancache-Container läuft nicht – Downloads gehen direkt ins Internet.", event="cache_down", key="cache-down")
    for k in [k for k, v in _manual_stop.items() if now - v > 7 * 86400]:
        _manual_stop.pop(k, None)


async def monitor_loop():
    await asyncio.sleep(90)                 # erst Status sammeln lassen
    while True:
        try:
            await _monitor_once()
        except Exception:  # noqa: BLE001
            log.exception("Überwachung")
        await asyncio.sleep(60)


async def _gslt_maintenance() -> dict:
    """Abgelaufene, benutzte Steam-Tokens erneuern und in die Container eintragen."""
    res = {"renewed": [], "manual": [], "errors": []}
    if not gslt.has_key():
        return res
    try:
        await gslt.sync()
    except gslt.GsltError as e:
        res["errors"].append(str(e))
        return res
    use = await _gslt_reconcile()
    for t in list(gslt.tokens()):
        tok = t.get("token") or ""
        if not t.get("expired") or tok not in use or not t.get("steamid"):
            continue
        srv_name = use[tok]
        try:
            new = await gslt.renew(t["steamid"])
        except gslt.GsltError as e:
            res["errors"].append(f"{srv_name}: {e}")
            continue
        s = next((x for x in load_servers() if x["name"] == srv_name), None)
        done = False
        if s and s.get("container"):
            try:
                info = await docker_api.inspect(s["container"])
                if ((info.get("Config") or {}).get("Labels") or {}).get("gsm.managed") == "1":
                    g = game_of(s)
                    await docker_api.recreate(s["container"], lambda cfg, hc: cfg.update(Env=gslt.set_token_env(g, cfg.get("Env") or [], new["token"])))
                    gslt.assign(new["token"], srv_name)
                    done = True
            except docker_api.DockerError as e:
                res["errors"].append(f"{srv_name}: {e}")
        (res["renewed"] if done else res["manual"]).append(srv_name)
        notify.fire(f"🔑 Steam-Token von {srv_name} war abgelaufen und wurde erneuert"
                    + ("" if done else " – bitte den neuen Token (Einstellungen → Steam-Tokens) im Portainer-Stack eintragen") + ".",
                    event="token", key=f"tok-{t['steamid']}")
    return res


async def gslt_loop():
    await asyncio.sleep(300)
    while True:
        try:
            await _gslt_maintenance()
        except Exception:  # noqa: BLE001
            log.exception("Steam-Tokens prüfen")
        await asyncio.sleep(6 * 3600)


@app.post("/api/gslt/maintain", dependencies=auth)
async def gslt_maintain():
    return await _gslt_maintenance()


@app.post("/api/gslt/cleanup", dependencies=auth)
async def gslt_cleanup():
    """Abgelaufene und nie bzw. nicht mehr benutzte Tokens löschen (bei Steam und in der Liste)."""
    use = await _gslt_reconcile()
    removed = []
    for t in list(gslt.tokens()):
        if (t.get("expired") or t.get("deleted")) and (t.get("token") or "") not in use and not t.get("assigned"):
            if gslt.has_key() and t.get("steamid"):
                try:
                    await gslt.delete_at_steam(t["steamid"])
                except gslt.GsltError:
                    pass
            gslt.remove(t.get("id") or t.get("steamid") or "")
            removed.append(t.get("memo") or t.get("steamid") or "?")
    return {"removed": removed}


class NotifyIn(BaseModel):
    enabled: bool | None = None
    whatsapp: str | None = Field(None, max_length=2000)
    ntfy_url: str | None = Field(None, max_length=300)
    telegram_token: str | None = Field(None, max_length=120)
    telegram_chat: str | None = Field(None, max_length=60)
    events: dict[str, bool] | None = None
    repeat_min: int | None = Field(None, ge=5, le=10080)
    max_per_hour: int | None = Field(None, ge=1, le=120)
    quiet_from: str | None = Field(None, max_length=5)
    quiet_to: str | None = Field(None, max_length=5)


@app.get("/api/notify", dependencies=auth)
async def notify_get():
    return notify.public_settings()


@app.put("/api/notify", dependencies=auth)
async def notify_put(data: NotifyIn):
    if data.ntfy_url and not re.match(r"^https?://", data.ntfy_url):
        raise HTTPException(400, "ntfy-Adresse muss mit http(s):// beginnen")
    for v in (data.quiet_from, data.quiet_to):
        if v and not re.fullmatch(r"\d\d:\d\d", v):
            raise HTTPException(400, "Ruhezeit im Format HH:MM")
    return notify.save(data.model_dump(exclude_none=True))


@app.post("/api/notify/test", dependencies=auth)
async def notify_test():
    errs = await notify.send("Test – Benachrichtigungen funktionieren 👍", force=True)
    if errs:
        raise HTTPException(502, "; ".join(errs))
    return {"ok": True}


# ---------------------------------------------------------------- Sicherungen der Spielstände (nachts, aufs NAS)
SAVE_PATHS = {
    "valheim": ["/config/worlds_local", "/config/worlds"],
    "satisfactory": ["/config/saved", "/config/gamefiles/FactoryGame/Saved/SaveGames"],
    "factorio": ["/factorio/saves", "/factorio/config"],
    "minecraft": ["/data/world", "/data/world_nether", "/data/world_the_end", "/data/server.properties", "/data/ops.json", "/data/whitelist.json"],
    "wreckfest": ["/serverdata/serverfiles/server_config.cfg"],
    "teamspeak": ["/var/ts3server/ts3server.sqlitedb", "/var/ts3server/files"],
    "cs2": ["/home/steam/cs2-dedicated/game/csgo/cfg"],
    "tf2": ["/home/steam/tf-dedicated/tf/cfg"],
}
BACKUP_DEFAULTS = {"enabled": True, "time": "04:30", "keep": 7, "dir": "", "skip": []}
_backup = {"running": False, "last": store.load("backup_state.json", {})}


def _backup_settings() -> dict:
    d = {**BACKUP_DEFAULTS, **store.load("backup.json", {})}
    if not d.get("dir"):
        d["dir"] = os.path.normpath(automation.get_settings().get("games_base") or "/mnt/grohlan") + "/_backups"
    return d


async def _backup_server(s: dict, bdir: str, keep: int) -> dict:
    g, c = game_of(s), s.get("container")
    paths = SAVE_PATHS.get(g) or []
    if not c or not paths:
        return {"ok": None, "msg": "nichts zu sichern"}
    info = await docker_api.inspect(c)
    mounts = [(m.get("Destination") or "", m.get("Source") or "") for m in info.get("Mounts") or [] if m.get("Source")]
    binds, items = [], []
    for p in paths:
        hit = max((m for m in mounts if p == m[0] or p.startswith(m[0].rstrip("/") + "/")), key=lambda m: len(m[0]), default=None)
        if not hit:
            continue
        i = next((k for k, b in enumerate(binds) if b.startswith(hit[1] + ":")), None)
        if i is None:
            i = len(binds)
            binds.append(f"{hit[1]}:/s{i}:ro")
        rel = os.path.relpath(p, hit[0])
        items.append((i, rel))
    if not items:
        return {"ok": None, "msg": "Speicherordner nicht als Volume eingebunden"}
    safe = re.sub(r"[^\w.-]+", "_", s.get("name") or c)[:60]
    stamp = time.strftime("%Y-%m-%d_%H%M")
    # je Quelle ein tar-Teil, am Ende zusammen in einem Archiv-Ordner -> einfach: mehrere -C-Abschnitte in einem tar
    pick = "; ".join(f'[ -e "/s{i}/{rel}" ] && set -- "$@" -C "/s{i}" "{rel}"' for i, rel in items)
    script = (f'set --; {pick}; [ $# -gt 0 ] || {{ echo "keine Speicherdateien gefunden"; exit 3; }}; '
              f'mkdir -p "/b/{safe}" && cd "/b/{safe}" && tar czf "{stamp}.tar.gz.part" "$@" 2>/tmp/err; rc=$?; '
              f'if [ -s "{stamp}.tar.gz.part" ] && [ $rc -eq 0 ]; then mv "{stamp}.tar.gz.part" "{stamp}.tar.gz"; else rm -f "{stamp}.tar.gz.part"; cat /tmp/err; exit 2; fi; '
              f'ls -1t *.tar.gz 2>/dev/null | tail -n +{keep + 1} | xargs -r rm -f; du -k "{stamp}.tar.gz" | cut -f1')
    binds.append(f"{bdir}:/b")
    out = await docker_api.run_helper(binds, ["sh", "-c", script], timeout=3600)
    kb = out.strip().splitlines()[-1] if out.strip() else ""
    return {"ok": True, "file": f"{bdir}/{safe}/{stamp}.tar.gz", "bytes": int(kb) * 1024 if kb.isdigit() else None}


async def _run_backups(only: str | None = None) -> dict:
    if _backup["running"]:
        return {"error": "läuft schon"}
    _backup["running"] = True
    d = _backup_settings()
    res = {}
    try:
        for s in load_servers():
            if (only and s["id"] != only) or (not only and s["id"] in (d.get("skip") or [])):
                continue
            try:
                r = await _backup_server(s, d["dir"], int(d.get("keep") or 7))
            except docker_api.DockerError as e:
                r = {"ok": False, "msg": str(e)[:300]}
            if r.get("ok") is None:
                continue
            res[s["id"]] = {**r, "name": s.get("name"), "t": time.time()}
            if r.get("ok") is False:
                notify.fire(f"💾 Sicherung von {s.get('name')} fehlgeschlagen: {r.get('msg', '')[:120]}", event="backup", key=f"bk-{s['id']}-{time.strftime('%Y%m%d')}")
        _backup["last"].update(res)
        store.save("backup_state.json", _backup["last"])
    finally:
        _backup["running"] = False
    return res


async def backup_loop():
    await asyncio.sleep(120)
    last = max((x.get("t") or 0 for x in _backup["last"].values()), default=0)
    done_day = time.strftime("%Y-%m-%d") if time.time() - last < 20 * 3600 else ""
    while True:
        try:
            d = _backup_settings()
            today = time.strftime("%Y-%m-%d")
            if d.get("enabled") and time.strftime("%H:%M") >= (d.get("time") or "04:30") and done_day != today:
                done_day = today
                await _run_backups()
        except Exception:  # noqa: BLE001
            log.exception("Sicherung")
        await asyncio.sleep(60)


class BackupIn(BaseModel):
    enabled: bool | None = None
    time: str | None = Field(None, max_length=5)
    keep: int | None = Field(None, ge=1, le=90)
    dir: str | None = Field(None, max_length=200)
    skip: list[str] | None = None


@app.get("/api/backup", dependencies=auth)
async def backup_get():
    d = _backup_settings()
    servers = [{"id": s["id"], "name": s.get("name"), "game": game_of(s), "supported": bool(SAVE_PATHS.get(game_of(s)) and s.get("container")),
                "paths": SAVE_PATHS.get(game_of(s)) or [], "last": _backup["last"].get(s["id"])} for s in load_servers()]
    return {"settings": d, "servers": servers, "running": _backup["running"]}


@app.put("/api/backup", dependencies=auth)
async def backup_put(data: BackupIn):
    d = {**BACKUP_DEFAULTS, **store.load("backup.json", {})}
    new = data.model_dump(exclude_none=True)
    if new.get("time") and not re.fullmatch(r"\d\d:\d\d", new["time"]):
        raise HTTPException(400, "Uhrzeit im Format HH:MM")
    if new.get("dir") and not os.path.normpath(new["dir"]).startswith("/mnt/"):
        raise HTTPException(400, "Sicherungsordner muss unter /mnt liegen")
    d.update(new)
    store.save("backup.json", d)
    return await backup_get()


@app.post("/api/backup/run", dependencies=auth)
async def backup_run(sid: str | None = None):
    if _backup["running"]:
        raise HTTPException(409, "Sicherung läuft schon")
    asyncio.create_task(_run_backups(sid))
    return {"ok": True}


# ---------------------------------------------------------------- Alle Server nach Namensschema benennen
@app.post("/api/names/apply", dependencies=auth)
async def names_apply():
    """Namen nach Schema „Groh <Spiel> <Nr> <Modus>“: in der Liste/Übersicht sofort, im Spiel wo möglich
    (CS2/TF2/Satisfactory live, Wreckfest per Konfiguration + Neustart sobald leer)."""
    settings = automation.get_settings()
    out = []
    for s in load_servers():
        g, st = game_of(s), _state.get(s["id"]) or {}
        mode = (st.get("mode") or {}).get("label") if isinstance(st.get("mode"), dict) else ""
        if g == "cs2":
            want = _mode_hostname(s, st.get("hostname"), mode or "", settings)
        else:
            if g in ("teamspeak", "minecraft", "factorio", "valheim", "satisfactory"):
                mode = ""
            want = _auto_name(s, st.get("hostname"), mode or "")
        if not want:
            continue
        how = "Liste"
        if g == "wreckfest" and s.get("container"):
            try:
                await _wf_write(s["container"], {"server_name": want})
                t_ = _wf_pending_restart.get(s["id"])
                if not (t_ and not t_.done()):
                    _wf_pending_restart[s["id"]] = asyncio.create_task(_wf_restart_when_empty(s["id"], s["container"]))
                how = "im Spiel nach Neustart (sobald leer)"
            except (HTTPException, docker_api.DockerError):
                pass
        elif g in ("cs2", "tf2", "satisfactory"):
            how = "im Spiel (live)"
        await _set_server_fields(s["id"], name=want, name_from_game=g in ("cs2", "tf2", "satisfactory", "wreckfest"))
        out.append({"id": s["id"], "old": s.get("name"), "name": want, "how": how})
    return {"renamed": out}


# ---------------------------------------------------------------- Spieler automatisch erfassen
LOG_GAMES = {"cs2", "tf2", "minecraft", "valheim"} | set(gslt.SRCDS_GAMES)
_plog_since: dict[str, int] = {}


async def _collect_players_once() -> None:
    now = int(time.time())
    for s in load_servers():
        g, c = game_of(s), s.get("container")
        st = _state.get(s["id"]) or {}
        name = st.get("hostname") or s.get("name") or g
        # 1) Logs der Container (SteamID + IP beim Verbinden)
        if c and g in LOG_GAMES and docker_api.available():
            since = _plog_since.get(c, 0)
            try:
                text = await docker_api.logs_since(c, since - 5 if since else 0, tail=40000)
                playerdb.parse_log(text, g, s["id"], name)
                _plog_since[c] = now
            except docker_api.DockerError:
                pass
        # 2) aktueller Status (Namen; TeamSpeak mit IP und eindeutiger ID)
        if not st.get("online"):
            continue
        for pl in st.get("players") or []:
            if not isinstance(pl, dict) or pl.get("bot"):
                continue
            if g == "teamspeak":
                if pl.get("uid"):
                    playerdb.link_ts(pl["uid"], pl.get("name") or "", pl.get("ip") or "")
                continue
            if pl.get("name") in ("SourceTV", "GOTV", "CSTV"):
                continue
            stid = playerdb.addr_steamid(pl.get("address")) if g == "cs2" else ""
            playerdb.seen(steamid=stid, name=pl.get("name") or "", ip=pl.get("address") or "", sid=s["id"], server=name, game=g)
    # Steam-Profil (Name, Avatar) für Spieler mit SteamID nachladen
    for p in playerdb.needs_profile():
        try:
            r = await steam.resolve_player(p["steamid"])
            playerdb.set_profile(p["steamid"], r.get("name") or "", r.get("avatar") or "")
        except steam.SteamError:
            playerdb.set_profile(p["steamid"], "", "")
    playerdb.save()
    if time.time() - _admin_sync["t"] > 600:
        await _sync_admins()


async def player_loop():
    await asyncio.sleep(20)
    while True:
        try:
            await _collect_players_once()
        except Exception:  # noqa: BLE001
            log.exception("Spieler erfassen")
        await asyncio.sleep(60)


# ---------------------------------------------------------------- Admin-Listen der Server aus der Spielerliste
CS2_GAME_DIR = "/home/steam/cs2-dedicated/game/csgo"
_admin_sync: dict = {"t": 0.0, "last": store.load("admin_sync.json", {}), "log": []}


def _user_admin_games(username: str) -> set[str]:
    u = users.find(username)
    if not u:
        return set()
    if u.get("role") == "admin":
        return {"*"}
    games = {game_of(s) for s in load_servers()}
    return {g for g in games if users.level(u, g) >= 3}


def _admins_for(game: str) -> dict[str, str]:
    """SteamID -> Anzeigename aller Spieler, die für dieses Spiel Admin sind."""
    out = {}
    for p in playerdb.all_players():
        if not p.get("steamid"):
            continue
        ag = playerdb.admin_games(p, _user_admin_games)
        if "*" in ag or game in ag:
            out[p["steamid"]] = playerdb.display(p)
    return out


async def _exec_read(c: str, path: str) -> str | None:
    out = await docker_api.exec_cmd(c, ["sh", "-c", f'[ -f "{path}" ] && cat "{path}" || echo "#MISSING#"'], timeout=15)
    return None if out.strip() == "#MISSING#" else out


async def _exec_write(c: str, path: str, text: str) -> None:
    import base64
    b64 = base64.b64encode(text.encode()).decode()
    out = await docker_api.exec_cmd(c, ["sh", "-c", f'echo {b64} | base64 -d > "{path}.gsm" && mv "{path}.gsm" "{path}" && echo OK'], timeout=15)
    if "OK" not in out:
        raise docker_api.DockerError(f"{path}: {out.strip()[:150]}")


async def _sync_admins_server(s: dict) -> str | None:
    g, c = game_of(s), s.get("container")
    if not c or g not in ("cs2", "wreckfest", "valheim"):
        return None
    want = _admins_for(g)
    last = set(_admin_sync["last"].get(s["id"]) or [])
    ids = set(want)
    if g == "cs2":
        changed = []
        css = f"{CS2_GAME_DIR}/addons/counterstrikesharp/configs/admins.json"
        raw = await _exec_read(c, css)
        if raw is not None:
            try:
                cur = json.loads(raw or "{}")
            except ValueError:
                cur = None
            if isinstance(cur, dict):
                new = {k: v for k, v in cur.items() if not k.startswith("gsm_")}
                for sid_, nm in want.items():
                    new[f"gsm_{sid_}"] = {"identity": sid_, "flags": ["@css/root"], "immunity": 100}
                if new != cur:
                    await _exec_write(c, css, json.dumps(new, indent=2, ensure_ascii=False))
                    changed.append("CounterStrikeSharp")
        mz = f"{CS2_GAME_DIR}/cfg/MatchZy/admins.json"
        raw = await _exec_read(c, mz)
        if raw is not None:
            try:
                cur = json.loads(raw or "{}")
            except ValueError:
                cur = None
            if isinstance(cur, dict):
                new = {k: v for k, v in cur.items() if k not in last or k in ids}
                for sid_ in ids:
                    new.setdefault(sid_, "")
                if new != cur:
                    await _exec_write(c, mz, json.dumps(new, indent=2))
                    changed.append("MatchZy")
        if changed:
            try:
                await run(s, "css_reloadadmins")
            except Exception:  # noqa: BLE001
                pass
        res = ", ".join(changed) if changed else None
    elif g == "wreckfest":
        text = await _wf_read(c)
        if text is None:
            return None
        cur = [x for x in re.split(r"[,\s]+", _wf_values(text).get("admin_steam_ids") or "") if x]
        new = [x for x in cur if x not in last or x in ids] + [x for x in sorted(ids) if x not in cur]
        res = None
        if new != cur:
            await _wf_write(c, {"admin_steam_ids": ",".join(new)})
            res = "server_config.cfg (gilt ab dem nächsten Neustart)"
    else:   # valheim
        path = "/config/adminlist.txt"
        raw = await _exec_read(c, path)
        cur = [ln.strip() for ln in (raw or "").splitlines()]
        keep = [ln for ln in cur if not ln or ln.startswith("//") or ln not in last or ln in ids]
        new = keep + [x for x in sorted(ids) if x not in cur]
        res = None
        if [x for x in new if x] != [x for x in cur if x]:
            await _exec_write(c, path, "\n".join(new).strip() + "\n")
            res = "adminlist.txt"
    _admin_sync["last"][s["id"]] = sorted(ids)
    return res


async def _sync_admins() -> list[str]:
    _admin_sync["t"] = time.time()
    done = []
    for s in load_servers():
        try:
            r = await _sync_admins_server(s)
            if r:
                done.append(f"{s.get('name')}: {r}")
        except (docker_api.DockerError, HTTPException, RconError) as e:
            done.append(f"{s.get('name')}: Fehler {str(e)[:100]}")
    store.save("admin_sync.json", _admin_sync["last"])
    if done:
        _admin_sync["log"] = (_admin_sync["log"] + [f"{time.strftime('%d.%m. %H:%M')} {x}" for x in done])[-30:]
        log.info("Admin-Listen: %s", "; ".join(done))
    return done


@app.post("/api/players/sync-admins", dependencies=auth)
async def players_sync_admins(request: Request):
    _need_admin(request)
    return {"done": await _sync_admins(), "log": _admin_sync["log"]}


class PlayerEdit(BaseModel):
    nick: str | None = Field(None, max_length=64)
    steamid: str | None = Field(None, max_length=200)
    notes: str | None = Field(None, max_length=500)
    admin: list[str] | None = None
    user: str | None = Field(None, max_length=64)


@app.patch("/api/players/{pid}", dependencies=auth)
async def edit_player(pid: str, data: PlayerEdit, request: Request):
    """Spieler bearbeiten: Nickname, SteamID (jedes Format), Notiz, Admin für Spiele, verknüpftes Tool-Konto."""
    f = data.model_dump(exclude_none=True)
    if not _is_admin(request) and set(f) - {"nick", "notes"}:
        raise HTTPException(403, "SteamID, Admin-Rechte und Konto-Verknüpfung dürfen nur Administratoren ändern")
    if f.get("steamid"):
        try:
            r = await steam.resolve_player(f["steamid"])
        except steam.SteamError as e:
            raise HTTPException(400, str(e))
        f["steamid"] = r["steamid"]
    if f.get("user") and not users.find(f["user"]):
        raise HTTPException(400, "Benutzer gibt es nicht")
    try:
        p = playerdb.update(pid, f)
    except ValueError as e:
        raise HTTPException(409, str(e))
    asyncio.create_task(_sync_admins())
    return _players_out(request)


class AccountIn(BaseModel):
    username: str | None = Field(None, max_length=32)
    role: str = "viewer"


@app.post("/api/players/{pid}/account", dependencies=auth)
async def player_account(pid: str, data: AccountIn, request: Request):
    """Neues Tool-Konto für einen Spieler anlegen und verknüpfen – Passwort wird einmalig angezeigt."""
    _need_admin(request)
    p = playerdb.get(pid)
    if not p:
        raise HTTPException(404, "Spieler nicht gefunden")
    if p.get("user") and users.find(p["user"]):
        raise HTTPException(409, f"Schon mit Konto „{p['user']}“ verknüpft")
    base = re.sub(r"[^a-z0-9._-]", "", (data.username or playerdb.display(p) or "spieler").lower().replace(" ", "."))[:28] or "spieler"
    name, i = base, 2
    while users.find(name):
        name, i = f"{base}{i}", i + 1
    pw = secrets.token_urlsafe(8)[:10]
    try:
        users.upsert(name, pw, data.role if data.role in users.ROLES else "viewer")
    except ValueError as e:
        raise HTTPException(400, str(e))
    playerdb.update(p["id"], {"user": name})
    return {"username": name, "password": pw, "players": _players_out(request)}


class PlayerNew(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    steamid: str | None = Field(None, max_length=200)


@app.post("/api/players/new", dependencies=auth)
async def new_player(data: PlayerNew, request: Request):
    """Spieler von Hand anlegen – auch ohne SteamID."""
    sid = ""
    if data.steamid:
        try:
            sid = (await steam.resolve_player(data.steamid))["steamid"]
        except steam.SteamError as e:
            raise HTTPException(400, str(e))
    p = playerdb.add_manual(sid, data.name.strip(), "") if sid else playerdb.seen(name=data.name.strip(), game="manuell")
    if p is not None and not sid:
        playerdb.update(p["id"], {"nick": data.name.strip()})
    return _players_out(request)


def _players_out(request: Request | None = None) -> list[dict]:
    on = playerdb.online_index(load_servers(), _state, game_of)
    admin = request is None or (getattr(request.state, "user", None) or {}).get("role") == "admin"
    out = []
    for p in playerdb.all_players():
        if not p.get("steamid") and not p.get("names") and not p.get("ts_name") and not p.get("nick"):
            continue
        r = {**p, "steamid": p.get("steamid") or "", "name": playerdb.display(p), "online": on.get(p["id"], []),
             "admin_eff": sorted(playerdb.admin_games(p, _user_admin_games))}
        if not admin:                       # IP-Adressen nur für Administratoren
            r.pop("lan_ip", None); r.pop("wan_ip", None)
        out.append(r)
    out.sort(key=lambda x: (not x["online"], -(x.get("last_seen") or 0)))
    return out


@app.get("/api/players", dependencies=auth)
async def list_players(request: Request):
    return _players_out(request)


@app.post("/api/players", dependencies=auth)
async def add_player(data: PlayerIn, request: Request):
    try:
        p = await steam.resolve_player(data.input)
    except steam.SteamError as e:
        raise HTTPException(400, str(e))
    rec = playerdb.add_manual(p["steamid"], (data.name or "").strip() or p["name"] or "", p["avatar"] or "")
    lst = _players_out(request)
    return {"player": next((x for x in lst if x["id"] == rec["id"]), rec), "players": lst, "offline": p["offline"]}


class PlayerUpdate(BaseModel):
    name: str = Field("", max_length=64)       # Nickname (leer = automatischer Name)


@app.put("/api/players/{pid}", dependencies=auth)
async def rename_player(pid: str, data: PlayerUpdate, request: Request):
    try:
        playerdb.set_nick(pid, data.name)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return _players_out(request)


class MergeIn(BaseModel):
    other: str = Field(max_length=120)


@app.post("/api/players/{pid}/merge", dependencies=auth)
async def merge_player(pid: str, data: MergeIn, request: Request):
    _need_admin(request)
    """Zwei Einträge derselben Person zusammenführen (z. B. TeamSpeak + Steam)."""
    try:
        playerdb.merge(pid, data.other)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return _players_out(request)


@app.delete("/api/players/{pid}", dependencies=auth)
async def delete_player(pid: str, request: Request):
    _need_admin(request)
    playerdb.remove(pid)
    return _players_out(request)


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
    known = {p.get("steamid") for p in playerdb.all_players()}
    added = 0
    for f in found:
        if f["steamid"] not in known:
            added += 1
        playerdb.seen(steamid=f["steamid"], name=f["name"] or "", sid=sid, server=s.get("name") or "", game=game_of(s))
    playerdb.save(True)
    return {"found": found, "added": added, "tried": tried, "players": _players_out()}


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
    await ensure_matchzy(s)
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
    db = {p["steamid"]: playerdb.display(p) for p in playerdb.all_players() if p.get("steamid")}
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
    await ensure_matchzy(s)
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
    await ensure_matchzy(s)
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


@app.get("/api/tools/a2s", dependencies=auth)
async def tool_a2s(host: str, port: int):
    """Steam-Serverabfrage (A2S_INFO) von hier aus – zur Fehlersuche (Antwortet der Server im LAN?)."""
    if not re.fullmatch(r"[\w.\-]{1,100}", host) or not 1 <= port <= 65535:
        raise HTTPException(400, "Ungültige Adresse")
    t0 = time.time()
    try:
        info = await adapters.a2s.info(host, port)
        return {"ok": True, "ms": round((time.time() - t0) * 1000), "info": {k: info.get(k) for k in ("name", "map", "players", "max_players", "version", "port")}}
    except adapters.a2s.A2SError as e:
        return {"ok": False, "ms": round((time.time() - t0) * 1000), "error": str(e)}


@app.get("/api/docker/helperlogs/{name}", dependencies=auth)
async def helper_logs(name: str, tail: int = 60):
    """Log eines Hilfs-Containers (Kopieren usw.) – nur gsm-*-Container."""
    if not re.fullmatch(r"gsm-[\w.\-]{1,80}", name):
        raise HTTPException(400, "Nur Hilfs-Container")
    try:
        return {"logs": await docker_api.logs(name, tail)}
    except docker_api.DockerError as e:
        raise HTTPException(404, str(e))


@app.get("/api/docker/image-check", dependencies=auth)
async def image_check(images: str = ""):
    """Prüft, ob Images in der Registry existieren (ohne Download) – für den Spielekatalog."""
    if not docker_api.available():
        raise HTTPException(400, "Docker nicht erreichbar")
    names = [x.strip() for x in images.split(",") if x.strip()] or sorted({t["image"] for t in templates.TEMPLATES.values()})
    sem = asyncio.Semaphore(4)

    async def one(img):
        async with sem:
            try:
                await docker_api._req("GET", f"/distribution/{img}/json", timeout=30)
                return img, True
            except docker_api.DockerError as e:
                return img, str(e)[:120]
    return dict(await asyncio.gather(*(one(i) for i in names[:80])))


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
    if act in ("stop", "pause"):
        _manual_stop[sid] = time.time()
    elif act in ("start", "unpause", "restart"):
        _manual_stop.pop(sid, None)
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
for f in $(find / -maxdepth 6 \( -path /proc -o -path /sys -o -path '*/game' -o -path '*/steamapps' \) -prune -o -name content_log.txt -print 2>/dev/null | head -3); do
  [ -f "$f" ] && { echo "=== SteamCMD-Downloadlog $f"; grep -iE "lancache|cache server|using .*server|http|CDN|Download" "$f" | tail -n 25 | cut -c1-200; }
done
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
    for ip in 127.0.0.1 $(hostname -i 2>/dev/null | awk '{print $1}'); do
      r=$(bash -c 'exec 3<>/dev/udp/'$ip'/'$p' && printf "\xff\xff\xff\xffTSource Engine Query\x00" >&3 && timeout 2 dd bs=1400 count=1 <&3 2>/dev/null | tr -c "[:print:]" "."' 2>/dev/null)
      echo "$p @$ip: ${r:-keine Antwort}"
    done
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
_jobs_saved = {"t": 0.0}


def _save_jobs(force: bool = False) -> None:
    """Anlege-Jobs im Volume sichern, damit sie ein Neustart des Tools (z. B. Update) überleben."""
    if not force and time.time() - _jobs_saved["t"] < 5:
        return
    _jobs_saved["t"] = time.time()
    keep = [j for j in _jobs.values() if (j.get("req") or j.get("plans")) and (not j["done"] or time.time() - j.get("t_done", time.time()) < 3600)]
    store.save("jobs.json", keep[-20:])


def _resume_jobs() -> None:
    for j in store.load("jobs.json", []):
        _jobs[j["id"]] = j
        if not j.get("done") and j.get("plans"):
            _job_log(j, "Tool wurde neu gestartet – Stapel wird fortgesetzt")
            _job_tasks[j["id"]] = asyncio.create_task(_run_batch(j))
        elif not j.get("done") and j.get("req"):
            _job_log(j, "Tool wurde neu gestartet – Anlegen wird fortgesetzt")
            r = j["req"]
            _job_tasks[j["id"]] = asyncio.create_task(_create_job(j, CreateIn(**{k: r[k] for k in ("game", "values", "data_dir", "host")}), r["host"]))


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


# ---------------------------------------------------------------- Steam-Gameserver-Tokens (GSLT)
async def _token_usage() -> dict[str, str]:
    """Token -> Servername, aus der Umgebung der CS2-/TF2-Container."""
    out = {}
    for s_ in load_servers():
        if game_of(s_) not in gslt.APPS or not s_.get("container"):
            continue
        try:
            env = ((await docker_api.inspect(s_["container"])).get("Config") or {}).get("Env") or []
        except docker_api.DockerError:
            continue
        tok = gslt.token_from_env(env)
        if tok:
            out[tok] = s_["name"]
    return out


async def _gslt_reconcile() -> dict[str, str]:
    use = await _token_usage()
    alive = {x["name"] for x in load_servers()} | {x.get("container") for x in load_servers() if x.get("container")}
    for j in _jobs.values():                 # Server, die gerade angelegt werden
        if not j.get("done"):
            alive |= {((j.get("req") or {}).get("values") or {}).get("name") or ""}
            alive |= {(pl.get("values") or {}).get("name") or "" for pl in j.get("plans") or []}
    if docker_api.available():
        try:
            alive |= {c["name"] for c in await docker_api.list_containers()}
        except docker_api.DockerError:
            return use
    gslt.reconcile(use, alive)
    return use


@app.get("/api/gslt", dependencies=auth)
async def gslt_list():
    use = await _gslt_reconcile()
    lst = gslt.public_list()
    for t, full in zip(lst, gslt.tokens()):      # gleiche Reihenfolge
        t["used_by"] = use.get(full.get("token") or "")
    unknown = [n for tok, n in use.items() if tok not in {x.get("token") for x in gslt.tokens()}]
    return {"has_key": gslt.has_key(), "tokens": lst, "unknown_in_use": unknown,
            "games": {g: (GAMES.get(g) or {}).get("label", g) for g in gslt.APPS}}


class GsltKeyIn(BaseModel):
    key: str = Field("", max_length=64)


@app.put("/api/gslt/key", dependencies=auth)
async def gslt_key(data: GsltKeyIn):
    gslt.set_key(data.key)
    if data.key:
        try:
            n = await gslt.sync()
        except gslt.GsltError as e:
            raise HTTPException(400, str(e))
        return {"ok": True, "synced": n}
    return {"ok": True}


@app.post("/api/gslt/sync", dependencies=auth)
async def gslt_sync():
    try:
        return {"ok": True, "synced": await gslt.sync()}
    except gslt.GsltError as e:
        raise HTTPException(400, str(e))


class GsltNewIn(BaseModel):
    game: str = "cs2"
    memo: str = Field("", max_length=32)
    token: str = Field("", max_length=64)


@app.post("/api/gslt/create", dependencies=auth)
async def gslt_create(data: GsltNewIn):
    if data.game not in gslt.APPS:
        raise HTTPException(400, "Dieses Spiel kennt keine Steam-Gameserver-Tokens")
    try:
        if data.token:
            gslt.add_manual(data.token, gslt.APPS[data.game], data.memo)
            return {"ok": True}
        t = await gslt.create(gslt.APPS[data.game], data.memo or f"GROH LAN {data.game.upper()}")
        return {"ok": True, "memo": t["memo"]}
    except gslt.GsltError as e:
        raise HTTPException(400, str(e))


@app.post("/api/gslt/import", dependencies=auth)
async def gslt_import():
    """Tokens, die laufende CS2/TF2-Server schon benutzen, in die Liste übernehmen (z. B. aus Portainer-Stacks)."""
    known = {t.get("token") for t in gslt.tokens()}
    n = 0
    for s_ in load_servers():
        g = game_of(s_)
        if g not in gslt.APPS or not s_.get("container"):
            continue
        try:
            env = ((await docker_api.inspect(s_["container"])).get("Config") or {}).get("Env") or []
        except docker_api.DockerError:
            continue
        tok = gslt.token_from_env(env)
        if len(tok) >= 20:
            if tok not in known:
                try:
                    gslt.add_manual(tok, gslt.APPS[g], s_["name"][:32])
                    n += 1
                except gslt.GsltError:
                    continue
            gslt.assign(tok, s_["container"])
    return {"ok": True, "imported": n}


@app.post("/api/gslt/renew/{steamid}", dependencies=auth)
async def gslt_renew(steamid: str):
    try:
        await gslt.renew(steamid)
    except gslt.GsltError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.delete("/api/gslt/{tid}", dependencies=auth)
async def gslt_delete(tid: str):
    gslt.remove(tid)
    return {"ok": True}


class TvIn(BaseModel):
    on: bool = True
    delay: int = Field(30, ge=0, le=300)


@app.post("/api/servers/{sid}/cstv", dependencies=auth)
async def cstv_toggle(sid: str, data: TvIn):
    """CSTV (Zuschauen) an/aus. Vom Tool angelegte Container: dauerhaft über TV_ENABLE; sonst per RCON (bis zum Neustart)."""
    s = get_server(sid)
    if game_of(s) != "cs2":
        raise HTTPException(400, "Nur für CS2")
    managed = False
    if s.get("container") and docker_api.available():
        try:
            info = await docker_api.inspect(s["container"])
            managed = ((info.get("Config") or {}).get("Labels") or {}).get("gsm.managed") == "1"
        except docker_api.DockerError:
            pass
    if managed:
        def mutate(cfg, hc):
            env = [e for e in (cfg.get("Env") or []) if not e.startswith(("TV_ENABLE=", "TV_DELAY=", "TV_PW="))]
            pw = next((e.split("=", 1)[1] for e in env if e.startswith("CS2_PW=")), "")
            # Zuschauer ohne Passwort (Image-Standard wäre „changeme“; zusätzlich per RCON tv_password "")
            cfg["Env"] = env + [f"TV_ENABLE={1 if data.on else 0}", f"TV_DELAY={data.delay}", "TV_PW="]
        try:
            await docker_api.recreate(s["container"], mutate)
        except docker_api.DockerError as e:
            raise HTTPException(502, str(e))
        drop_client(sid)
        return {"ok": True, "how": "Container neu erstellt – CSTV ist nach dem Start aktiv"}
    await run(s, f"tv_enable {1 if data.on else 0}; tv_delay {data.delay}; tv_password \"\"")
    return {"ok": True, "how": "Per RCON gesetzt – wirkt ab dem nächsten Mapwechsel. Dauerhaft: im Portainer-Stack TV_ENABLE auf \"1\" stellen."}


@app.post("/api/servers/{sid}/gslt", dependencies=auth)
async def gslt_assign(sid: str):
    """Freien (oder neu erstellten) Token in den Container eintragen – nur für vom Tool angelegte Container."""
    s = get_server(sid)
    g = game_of(s)
    if g not in gslt.APPS:
        raise HTTPException(400, "Dieses Spiel kennt keine Steam-Gameserver-Tokens")
    name = _container_of(sid)
    info = await docker_api.inspect(name)
    if ((info.get("Config") or {}).get("Labels") or {}).get("gsm.managed") != "1":
        raise HTTPException(400, "Container stammt aus einem Portainer-Stack – Token dort als TOKEN eintragen")
    use = await _token_usage()
    old = gslt.token_from_env((info.get("Config") or {}).get("Env") or [])
    try:
        t = await gslt.get_or_create(gslt.APPS[g], name, set(use) | {old})
    except gslt.GsltError as e:
        raise HTTPException(400, str(e))
    if not t:
        raise HTTPException(400, "Kein freier Token – unter Einstellungen → Steam-Tokens einen anlegen oder den API-Schlüssel hinterlegen")

    def mutate(cfg, hc):
        cfg["Env"] = gslt.set_token_env(g, cfg.get("Env") or [], t["token"])
    try:
        await docker_api.recreate(name, mutate)
    except docker_api.DockerError as e:
        raise HTTPException(502, str(e))
    gslt.assign(t["token"], name)
    drop_client(sid)
    return {"ok": True, "memo": t.get("memo")}


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
    if job.get("req"):
        _save_jobs()
    job["log"] = job["log"][-200:]
    job["step"] = msg


COPY_SH = r"""
cd /copysrc || exit 3
T=$(find . -type f 2>/dev/null | wc -l)
B=$(du -sk . 2>/dev/null | cut -f1)
echo "TOTAL $T ${B:-0}"
( while sleep 10; do echo "BYTES $(du -sk /copydst 2>/dev/null | cut -f1)"; done ) &
W=$!
stdbuf -oL cp -ruv /copysrc/. /copydst/ 2>&1 | awk '/->/{n++; if (n % 100 == 0) {print "COPIED " n; fflush()}} /cannot|denied|No space/{print "ERR " $0; fflush()}'
kill $W 2>/dev/null
echo "COPIED_FINAL $(find /copydst -type f 2>/dev/null | wc -l)"
echo DONE
"""


async def _copy_game_files(job: dict, b: dict, src_id: str) -> None:
    """Spieldateien eines vorhandenen Servers desselben Spiels kopieren, bevor der neue Container startet.
    Läuft als eigener Container weiter, auch wenn das Tool neu startet; Fortschritt nach Dateien, mit Restzeit."""
    src = next((x for x in load_servers() if x["id"] == src_id), None)
    if not src or not src.get("container"):
        _job_log(job, "Kopieren übersprungen: Quell-Server ohne Container")
        return
    try:
        info = await docker_api.inspect(src["container"])
    except docker_api.DockerError as e:
        _job_log(job, f"Kopieren übersprungen: {e}")
        return
    src_mounts = {m.get("Destination", "").rstrip("/"): m.get("Source") for m in info.get("Mounts") or [] if m.get("Source")}
    pairs = []
    for bind in b["spec"]["HostConfig"].get("Binds") or []:
        hp, cp = bind.split(":")[0], bind.split(":")[1].rstrip("/")
        sp = src_mounts.get(cp)
        if sp and sp.rstrip("/") != hp.rstrip("/"):
            pairs.append((sp, hp))
    if not pairs:
        _job_log(job, "Kopieren übersprungen: keine passenden Datenordner beim Quell-Server")
        return
    user = f"{b['uid']}:{b['gid']}" if b.get("uid") else ""
    for k, (sp, hp) in enumerate(pairs):
        cname = f"gsm-copy-{b['name']}-{k}"
        try:
            st = (await docker_api.inspect(cname)).get("State") or {}
        except docker_api.DockerError:
            st = None
        if st is None:
            _job_log(job, f"Kopiere {sp} → {hp} von {src['name']} (als {user or 'root'})")
            await docker_api._req("POST", "/containers/create", params={"name": cname}, json={
                "Image": b["image"], "Entrypoint": ["/bin/bash", "-c"], "Cmd": [COPY_SH], "User": user,
                "Labels": {"gsm.helper": "copy", "gsm.copy_for": b["name"]},
                "HostConfig": {"Binds": [f"{sp}:/copysrc:ro", f"{hp}:/copydst"], "AutoRemove": False,
                               "CpuShares": 256}}, timeout=60)
            await docker_api._req("POST", f"/containers/{cname}/start", timeout=60)
        else:
            _job_log(job, "Kopieren läuft bereits – Fortschritt wird weiter verfolgt")
        total, total_kb, t0, n0 = None, 0, time.time(), None
        while True:
            try:
                i2 = await docker_api.inspect(cname)
                lg = await docker_api.logs(cname, 2000)
            except docker_api.DockerError as e:
                raise docker_api.DockerError(f"Kopier-Container verschwunden: {e}") from e
            m = re.search(r"TOTAL (\d+) (\d+)", lg)
            if m:
                total, total_kb = int(m.group(1)), int(m.group(2))
            nums = [int(x) for x in re.findall(r"COPIED (\d+)", lg)]
            n = nums[-1] if nums else 0
            kbs = [int(x) for x in re.findall(r"BYTES (\d+)", lg)]
            if kbs and total_kb:            # Fortschritt nach Datenmenge (genauer als nach Dateien)
                done, whole = kbs[-1], total_kb
            else:
                done, whole = n, total or 0
            if n0 is None:
                n0, t0 = done, time.time()
            rate = (done - n0) / max(1, time.time() - t0)
            pct = min(99.9, done / whole * 100) if whole else 0.0
            eta = round((whole - done) / rate) if whole and rate > 0 else None
            job["progress"] = {"label": "Kopiere Spieldateien", "pct": round(pct, 1), "done_files": n, "total_files": total,
                               "total_bytes": total_kb * 1024, "done_bytes": kbs[-1] * 1024 if kbs else None, "eta": eta,
                               "rate_bps": round(rate * 1024) if kbs and total_kb else None}
            job["step"] = f"Kopiere Spieldateien von {src['name']}: {pct:.0f} %" + (f" · noch ca. {max(1, eta // 60)} min" if eta else "")
            _save_jobs()
            if not (i2.get("State") or {}).get("Running"):
                code = (i2.get("State") or {}).get("ExitCode")
                errs = re.findall(r"^ERR (.*)$", lg, re.M)
                fin = re.search(r"COPIED_FINAL (\d+)", lg)
                if "DONE" not in lg or code not in (0, None):
                    raise docker_api.DockerError(f"Kopieren abgebrochen (Code {code}): {(errs or [lg.strip()[-200:]])[-1][:200]}")
                _job_log(job, f"Kopiert: {fin.group(1) if fin else n} Dateien, {fmt_gb(total_kb * 1024)}"
                              + (f" – {len(errs)} Fehler, erster: {errs[0][:150]}" if errs else ""))
                break
            await asyncio.sleep(5)
        try:
            await docker_api.remove_container(cname)
        except docker_api.DockerError:
            pass
    job.pop("progress", None)


def fmt_gb(b: int) -> str:
    return f"{b / 1e9:.1f} GB" if b >= 1e9 else f"{b / 1e6:.0f} MB"


_create_lock = asyncio.Lock()          # Server werden nacheinander angelegt, nie parallel


async def _create_job(job: dict, data: CreateIn, host: str):
    if _create_lock.locked():
        job["step"] = "wartet – vorheriger Server wird noch angelegt"
        _job_log(job, job["step"])
    async with _create_lock:
        await _create_job_inner(job, data, host)
        if not job.get("error") and job.get("server_id"):
            await _wait_installed(job, job["server_id"])


async def _wait_installed(job: dict, sid: str, timeout: float = 4 * 3600) -> None:
    """Erst wenn der Server fertig installiert/aktualisiert ist und antwortet, kommt der nächste dran."""
    t0 = time.time()
    job["installing"] = True
    try:
        while time.time() - t0 < timeout:
            if job.get("cancelled"):
                return
            st = _state.get(sid) or {}
            s = next((x for x in load_servers() if x["id"] == sid), None)
            if not s:
                return
            prog = (install_watch.state.get(s.get("container") or "") or {}).get("progress")
            if st.get("online") and not prog:
                _job_log(job, "Server ist installiert und online")
                return
            await asyncio.sleep(10)
        _job_log(job, "Installation dauert sehr lange – nächster Server startet trotzdem")
    finally:
        job["installing"] = False


async def _create_job_inner(job: dict, data: CreateIn, host: str):
    try:
        b = templates.build(data.game, data.values, data.data_dir)
        _job_log(job, f"Ordner vorbereiten: {', '.join(b['dirs'])}")
        resumed = job.get("stage") not in (None, "start")
        if "data_new" not in job:              # gab es den Datenordner schon? (nur dann beim Abbrechen nicht löschen)
            job["data_new"] = await _dir_is_new(data.data_dir)
        own = f" && chown -R {b['uid']}:{b['gid']} /target" if b["uid"] and not resumed else ""
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
        src_id = (data.values.get("_copy_from") or "").strip() if data.game == "cs2" else ""
        if src_id and job.get("stage") not in ("copied", "created"):
            job["stage"] = "copy"
            await _copy_game_files(job, b, src_id)
            job["stage"] = "copied"
            _save_jobs(True)
        dns = await lancache_dns()
        if dns:
            b["spec"]["HostConfig"]["Dns"] = dns
            _job_log(job, f"DNS {', '.join(dns)} (Lancache) – Downloads laufen über den Cache")
        exists = True
        try:
            await docker_api.inspect(b["name"])
        except docker_api.DockerError:
            exists = False
        if exists:
            _job_log(job, f"Container {b['name']} gibt es schon – wird gestartet")
            try:
                await docker_api.action(b["name"], "start")
            except docker_api.DockerError:
                pass
        else:
            _job_log(job, f"Container {b['name']} anlegen und starten")
            job["created_container"] = b["name"]
            _save_jobs(True)
            await docker_api.create_container(b["name"], b["spec"])
        job["stage"] = "created"
        _save_jobs(True)
        known = next((x for x in load_servers() if x.get("container") == b["name"]), None)
        if known:
            job["server_id"] = known["id"]
            job["done"] = True
            job["t_done"] = time.time()
            _job_log(job, "Server war schon eingetragen – fertig")
            _save_jobs(True)
            return
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
        job["t_done"] = time.time()
        _job_log(job, "Fertig")
        _save_jobs(True)
        notify.fire(f"✅ {b['name']} ist angelegt und startet (Spieldateien laden ggf. noch).", event="install_done", key=f"job-{job['id']}")
    except asyncio.CancelledError:
        if not job.get("cancelled"):
            _save_jobs(True)             # Tool beendet sich – Job bleibt offen und wird nach dem Neustart fortgesetzt
        raise
    except (ValueError, docker_api.DockerError) as e:
        job["error"] = str(e)
        job["done"] = True
        job["t_done"] = time.time()
        _job_log(job, "Fehler: " + str(e))
        _save_jobs(True)
    except Exception as e:  # noqa: BLE001
        log.exception("Anlegen fehlgeschlagen")
        job["error"] = str(e) or e.__class__.__name__
        job["done"] = True
        job["t_done"] = time.time()
        _save_jobs(True)


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
    host_net = (info.get("HostConfig") or {}).get("NetworkMode") == "host"
    lan_ok = q.isdigit() and (26900 <= int(q) <= 26905 or (27015 <= int(q) <= 27020)) and (q_host == q or host_net)
    return {"exists": text is not None, "values": vals, "labels": WF_KEYS, "lan_ok": lan_ok, "host_net": host_net,
            "relay": await _relay_state(s["container"]),
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


def _wf_tracks() -> list[dict]:
    lay = mapimages.wf_layouts([k for k, _, _ in wfd.TRACKS])
    return [{"id": k, "name": n, "type": t, "layout": lay.get(k), "photo": mapimages.wf_photo(n)} for k, n, t in wfd.TRACKS]


@app.get("/api/servers/{sid}/wreckfest/rotation", dependencies=auth)
async def wf_rotation_get(sid: str):
    s = _wf_server(sid)
    try:
        text = await _wf_read(s["container"])
    except docker_api.DockerError as e:
        raise HTTPException(502, str(e))
    if text is None:
        return {"exists": False}
    glob = {}
    for line in text.splitlines():
        m = re.match(r"^\s*([a-z_]+)\s*=\s*(.*?)\s*$", line)
        if m and m.group(1) in wfd.GLOBAL_KEYS:
            glob[m.group(1)] = m.group(2).strip('"')
    vals = _wf_values(text)
    return {"exists": True, "events": wfd.parse_events(text), "globals": glob, "global_labels": wfd.GLOBAL_KEYS,
            "tracks": _wf_tracks(), "gamemodes": wfd.GAMEMODES,
            "car_classes": wfd.CAR_CLASSES, "current": {k: vals.get(k, "") for k in ("track", "gamemode", "laps", "bots", "server_name")},
            "auto_name": _auto_name(s, vals.get("server_name"), "")}


class WfRotationIn(BaseModel):
    events: list[dict[str, str | int | None]] = Field(default_factory=list, max_length=60)
    globals: dict[str, str] = Field(default_factory=dict)
    restart: bool = True
    when: str = "now"          # now = sofort neu starten · empty = sobald niemand drauf ist · never = nur speichern


@app.put("/api/servers/{sid}/wreckfest/rotation", dependencies=auth)
async def wf_rotation_put(sid: str, data: WfRotationIn):
    """Rotation (Event-Loop) und Lobby-Regeln schreiben; erstes Event wird Startstrecke, Name nach Muster."""
    import base64
    s = _wf_server(sid)
    try:
        text = await _wf_read(s["container"])
        if text is None:
            raise HTTPException(409, "server_config.cfg gibt es noch nicht – Server installiert sich noch")
        changes = {k: re.sub(r"[^\w .,\-]", "", str(v))[:40] for k, v in data.globals.items() if k in wfd.GLOBAL_KEYS}
        ev = [e for e in data.events if str(e.get("track") or "").strip()]
        if ev:
            first = ev[0]
            changes["track"] = str(first["track"])
            if first.get("gamemode"):
                changes["gamemode"] = str(first["gamemode"])
            if str(first.get("laps") or "").isdigit():
                changes["laps"] = str(first["laps"])
        modes = {str(e.get("gamemode") or "racing") for e in ev}
        label = wfd.MODE_NAMES.get(next(iter(modes)), "").split(" (")[0] if len(modes) == 1 else ("Rotation" if ev else "")
        want = _auto_name(s, _wf_values(text).get("server_name"), label)
        if want:
            changes["server_name"] = want
        new = wfd.render_events(_wf_apply(text, changes), ev)
        b64 = base64.b64encode(new.encode()).decode()
        out = await docker_api.exec_cmd(s["container"], ["sh", "-c", f"cp {WF_CFG} {WF_CFG}.bak 2>/dev/null; echo {b64} | base64 -d > {WF_CFG}.new && "
                                                                       f"chown 99:100 {WF_CFG}.new 2>/dev/null; mv {WF_CFG}.new {WF_CFG} && echo OK"])
        if "OK" not in out:
            raise HTTPException(502, f"Konnte Konfiguration nicht schreiben: {out.strip()[:200]}")
        _rot_cache.pop(sid, None)
        when = data.when if data.restart else "never"
        if when == "now":
            await docker_api.action(s["container"], "restart")
        elif when == "empty":
            old_t = _wf_pending_restart.get(sid)
            if old_t and not old_t.done():
                old_t.cancel()
            _wf_pending_restart[sid] = asyncio.create_task(_wf_restart_when_empty(sid, s["container"]))
    except docker_api.DockerError as e:
        raise HTTPException(502, str(e))
    return {"ok": True, "events": len(ev), "server_name": want, "when": when}


_wf_pending_restart: dict[str, asyncio.Task] = {}


async def _wf_restart_when_empty(sid: str, container: str) -> None:
    """Neustart, sobald keine (menschlichen) Spieler mehr auf dem Server sind – höchstens 12 h warten."""
    for _ in range(12 * 60 * 2):
        st = _state.get(sid) or {}
        if not st.get("online") or not (st.get("humans") or 0):
            try:
                await docker_api.action(container, "restart")
                log.info("%s: Rotation – Neustart, Server war leer", container)
            except docker_api.DockerError as e:
                log.warning("%s: Neustart fehlgeschlagen: %s", container, e)
            break
        await asyncio.sleep(30)
    _wf_pending_restart.pop(sid, None)


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


# LAN-Weiterleiter: Wreckfest-Clients suchen im LAN per UDP-Broadcast (Ports 26900–26905). Docker leitet Broadcasts
# nicht an Container mit Portfreigaben weiter. Ein kleiner socat-Container im Host-Netz empfängt die Broadcasts auf einem
# freien Port dieses Bereichs und reicht sie an den freigegebenen Query-Port weiter; Antworten gehen zurück an den Client.
RELAY_IMAGE = "alpine/socat:latest"
RELAY_PORTS = range(26900, 26906)


def _relay_name(container: str) -> str:
    return f"{container}-lanrelay"


async def _relay_state(container: str) -> dict | None:
    try:
        i = await docker_api.inspect(_relay_name(container))
    except docker_api.DockerError:
        return None
    cmd = " ".join((i.get("Config") or {}).get("Cmd") or [])
    m = re.search(r"RECVFROM:(\d+)", cmd)
    return {"running": bool((i.get("State") or {}).get("Running")), "port": int(m.group(1)) if m else None,
            "status": (i.get("State") or {}).get("Status")}


class RelayIn(BaseModel):
    on: bool = True


@app.post("/api/servers/{sid}/wreckfest/lanrelay", dependencies=auth)
async def wf_lanrelay(sid: str, data: RelayIn):
    s = _wf_server(sid)
    name = s["container"]
    rname = _relay_name(name)
    try:
        try:
            await docker_api.remove_container(rname)
        except docker_api.DockerError:
            pass
        if not data.on:
            return {"ok": True, "relay": None}
        vals = _wf_values(await _wf_read(name) or "")
        q = int(vals.get("query_port") or s.get("port") or 26900)
        info = await docker_api.inspect(name)
        if (info.get("HostConfig") or {}).get("NetworkMode") == "host":
            raise HTTPException(400, "Container läuft im Host-Netz – erst „Zurück ins normale Netz“")
        used = await docker_api.used_host_ports()
        rp = next((p for p in reversed(RELAY_PORTS) if p != q and p not in used), None)
        if rp is None:
            raise HTTPException(409, "Kein freier Port in 26900–26905 für den Weiterleiter")
        ip = _join_host(s)
        if not await docker_api.image_exists(RELAY_IMAGE):
            await docker_api.pull(RELAY_IMAGE)
        await docker_api.create_container(rname, {
            "Image": RELAY_IMAGE,
            "Cmd": ["-d", f"UDP4-RECVFROM:{rp},broadcast,reuseaddr,fork", f"UDP4-SENDTO:{ip}:{q}"],
            "Labels": {"gsm.lanrelay": name, "gsm.helper": "lanrelay"},
            "HostConfig": {"NetworkMode": "host", "RestartPolicy": {"Name": "unless-stopped"},
                           "Memory": 32 * 1024 * 1024, "CpuShares": 128}})
    except docker_api.DockerError as e:
        raise HTTPException(502, str(e))
    log.info("%s: LAN-Weiterleiter %s:%s -> %s:%s", name, "0.0.0.0", rp, ip, q)
    return {"ok": True, "relay": await _relay_state(name)}


WF_EXTRA_UDP = 27017


class PortsIn(BaseModel):
    port: int | None = Field(None, ge=1024, le=65535)          # CS2: Spielport · Wreckfest: Spielport (game_port)
    tv_port: int | None = Field(None, ge=1024, le=65535)       # CS2
    query_port: int | None = Field(None, ge=1024, le=65535)    # Wreckfest
    steam_port: int | None = Field(None, ge=1024, le=65535)    # Wreckfest


@app.post("/api/servers/{sid}/ports", dependencies=auth)
async def change_ports(sid: str, data: PortsIn):
    """Ports eines vom Tool angelegten CS2- oder Wreckfest-Containers ändern (Container wird neu erstellt)."""
    s = get_server(sid)
    g, name = game_of(s), s.get("container")
    if g not in ("cs2", "wreckfest") or not name:
        raise HTTPException(400, "Nur für CS2- und Wreckfest-Server mit Container")
    try:
        info = await docker_api.inspect(name)
    except docker_api.DockerError as e:
        raise HTTPException(502, str(e))
    if ((info.get("Config") or {}).get("Labels") or {}).get("gsm.managed") != "1":
        raise HTTPException(400, "Container stammt nicht aus diesem Tool (z. B. Portainer-Stack) – Ports dort ändern")
    used = await docker_api.used_host_ports()
    own = {int(b["HostPort"]) for lst in ((info.get("HostConfig") or {}).get("PortBindings") or {}).values()
           for b in (lst or []) if str(b.get("HostPort", "")).isdigit()}
    env = (info.get("Config") or {}).get("Env") or []
    envd = dict(e.split("=", 1) for e in env if "=" in e)
    if g == "cs2":
        port = data.port or int(envd.get("CS2_PORT") or s.get("port") or 27015)
        tv = data.tv_port or int(envd.get("TV_PORT") or 27020)
        want = {port, tv}
        binds = {f"{port}/tcp": port, f"{port}/udp": port, f"{tv}/udp": tv}
    else:
        vals = _wf_values(await _wf_read(name) or "")
        port = data.port or int(vals.get("game_port") or s.get("game_port") or 33540)
        q = data.query_port or int(vals.get("query_port") or s.get("port") or 27016)
        sp = data.steam_port or int(vals.get("steam_port") or 27015)
        want = {port, q, sp}
        binds = {f"{port}/udp": port, f"{q}/udp": q, f"{sp}/udp": sp}
        if WF_EXTRA_UDP not in want:      # Wreckfest (Wine) öffnet seinen Steam-Socket fest auf 27017
            binds[f"{WF_EXTRA_UDP}/udp"] = WF_EXTRA_UDP
    if len(want) != (2 if g == "cs2" else 3):
        raise HTTPException(400, "Ports müssen verschieden sein")
    clash = sorted(p for p in set(binds.values()) if p in used and p not in own)
    if clash:
        raise HTTPException(409, f"Port {clash[0]} ist schon belegt ({used.get(clash[0])})")
    if g == "wreckfest":
        await _wf_write(name, {"game_port": port, "query_port": q, "steam_port": sp})

    def mutate(cfg, hc):
        keep = {k: v for k, v in (hc.get("PortBindings") or {}).items() if k.endswith("/tcp") and g == "wreckfest"}  # Weboberfläche
        hc["PortBindings"] = {**keep, **{k: [{"HostPort": str(v)}] for k, v in binds.items()}}
        cfg["ExposedPorts"] = {k: {} for k in hc["PortBindings"]}
        if g == "cs2":
            cfg["Env"] = [e for e in (cfg.get("Env") or []) if not e.startswith(("CS2_PORT=", "TV_PORT="))] + [f"CS2_PORT={port}", f"TV_PORT={tv}"]
    try:
        await docker_api.recreate(name, mutate)
    except docker_api.DockerError as e:
        raise HTTPException(502, str(e))
    if g == "cs2":
        await _set_server_fields(sid, port=port)
        res = {"port": port, "tv_port": tv}
    else:
        await _set_server_fields(sid, port=q, game_port=port)
        res = {"game_port": port, "query_port": q, "steam_port": sp}
        if await _relay_state(name):            # LAN-Weiterleiter auf den neuen Query-Port umstellen
            try:
                await wf_lanrelay(sid, RelayIn(on=True))
            except HTTPException:
                pass
    _rot_cache.pop(sid, None)
    log.info("%s: Ports geändert %s", name, res)
    return {"ok": True, **res}


@app.post("/api/servers/{sid}/wreckfest/bridgenet", dependencies=auth)
async def wf_bridgenet(sid: str):
    """Zurück ins normale Docker-Netz mit Portfreigaben (Host-Netz bringt Wreckfest/Wine zum Absturz)."""
    s = _wf_server(sid)
    name = s["container"]
    try:
        text = await _wf_read(name)
        vals = _wf_values(text or "")
        gport, q, sport = int(vals.get("game_port") or 33540), int(vals.get("query_port") or 26900), int(vals.get("steam_port") or 27115)
        web = None
        m = re.search(r"--port (\d+)", " ".join(((await docker_api.inspect(name)).get("Config") or {}).get("Env") or []))
        if m:
            web = m.group(1)

        def mutate(cfg, hc):
            hc["NetworkMode"] = "bridge"
            hc["PortBindings"] = {f"{gport}/udp": [{"HostPort": str(gport)}], f"{q}/udp": [{"HostPort": str(q)}],
                                  f"{sport}/udp": [{"HostPort": str(sport)}]}
            cfg["ExposedPorts"] = {f"{gport}/udp": {}, f"{q}/udp": {}, f"{sport}/udp": {}}
            cfg["Env"] = [e for e in (cfg.get("Env") or []) if not e.startswith("GOTTY_PARAMS=")]
            if web:
                hc["PortBindings"]["8080/tcp"] = [{"HostPort": web}]
                cfg["ExposedPorts"]["8080/tcp"] = {}
        await docker_api.recreate(name, mutate)
    except docker_api.DockerError as e:
        raise HTTPException(502, str(e))
    return {"ok": True}


@app.post("/api/servers/{sid}/wreckfest/hostnet", dependencies=auth)
async def wf_hostnet(sid: str):
    """Wreckfest ins Host-Netzwerk: Die LAN-Suche des Spiels nutzt UDP-Broadcasts, die Docker-Portfreigaben nicht weiterleiten."""
    s = _wf_server(sid)
    name = s["container"]
    try:
        info = await docker_api.inspect(name)
        if (info.get("Config", {}).get("Labels") or {}).get("gsm.managed") != "1":
            raise HTTPException(400, "Nur für Container, die dieses Tool angelegt hat – sonst im Stack network_mode: host setzen")
        text = await _wf_read(name)
        vals = _wf_values(text or "")
        hc0 = info.get("HostConfig") or {}
        web = (((hc0.get("PortBindings") or {}).get("8080/tcp") or [{}])[0] or {}).get("HostPort")
        used = await docker_api.used_host_ports()
        for k in ("game_port", "query_port", "steam_port"):
            p = vals.get(k, "")
            own = {int(b["HostPort"]) for lst in (hc0.get("PortBindings") or {}).values() for b in (lst or []) if str(b.get("HostPort", "")).isdigit()}
            if p.isdigit() and int(p) in used and int(p) not in own:
                raise HTTPException(409, f"Port {p} ist auf dem Host schon belegt – erst „LAN-Sichtbarkeit einrichten“")

        def mutate(cfg, hc):
            hc["NetworkMode"] = "host"
            hc["PortBindings"] = {}
            hc.pop("Dns", None)
            cfg["ExposedPorts"] = {}
            env = [e for e in (cfg.get("Env") or []) if not e.startswith("GOTTY_PARAMS=")]
            if web:   # Webkonsole (gotty) sonst auf 8080 – dort läuft auf dem Host schon etwas
                env.append(f"GOTTY_PARAMS=-w --port {web} --title-format Wreckfest")
            cfg["Env"] = env
        await docker_api.recreate(name, mutate)
    except docker_api.DockerError as e:
        raise HTTPException(502, str(e))
    return {"ok": True}


# ---------------------------------------------------------------- Speicher / iSCSI (nur Planung + lesende Prüfung)
# ---------------------------------------------------------------- Ordner im Spieleverzeichnis (Platz schaffen)
_folders: dict = store.load("folders.json", {}) or {}
_folders.update(busy=False)
for _k, _v in {"items": [], "t": 0.0, "error": None, "base": None}.items():
    _folders.setdefault(_k, _v)
LIST_SH = r"""cd /base || exit 1
for d in */ */*/; do [ -d "$d" ] || continue; echo "D	${d%/}"; done
"""


async def _scan_folders():
    """Erst schnell alle Ordner auflisten, dann Größen einzeln messen (Ergebnis bleibt über Neustarts erhalten)."""
    if _folders["busy"]:
        return
    _folders["busy"] = True
    base = os.path.normpath(automation.get_settings().get("games_base") or "/mnt/grohlan")
    try:
        out = await docker_api.run_helper([f"{base}:/base:ro"], ["sh", "-c", LIST_SH], timeout=120)
        old = {f["rel"]: f.get("bytes") for f in _folders["items"]} if _folders.get("base") == base else {}
        dirs = [ln.split("\t", 1)[1] for ln in out.splitlines() if ln.startswith("D\t")]
        _folders.update(items=[{"rel": d, "path": f"{base}/{d}", "bytes": old.get(d)} for d in dirs], base=base, error=None)
        tops = [d for d in dirs if "/" not in d]
        for top in tops:                       # je Spielordner: Unterordner + Summe
            try:
                res = await docker_api.run_helper([f"{base}/{top}:/t:ro"], ["sh", "-c",
                                                  "cd /t && nice -n 19 du -sk -- */ 2>/dev/null | sed 's|/$||'; echo \"TOTAL $(nice -n 19 du -sk . 2>/dev/null | cut -f1)\""],
                                                  timeout=1800)
            except docker_api.DockerError as e:
                _folders["error"] = f"{top}: {e}"
                continue
            sizes = {}
            for ln in res.splitlines():
                if ln.startswith("TOTAL "):
                    v = ln.split()[1] if len(ln.split()) > 1 else ""
                    if v.isdigit():
                        sizes[top] = int(v) * 1024
                elif "\t" in ln:
                    kb, _, rel = ln.partition("\t")
                    if kb.isdigit():
                        sizes[f"{top}/{rel}"] = int(kb) * 1024
            for f in _folders["items"]:
                if f["rel"] in sizes:
                    f["bytes"] = sizes[f["rel"]]
            _folders["t"] = time.time()
            store.save("folders.json", {k: v for k, v in _folders.items() if k != "busy"})
    except docker_api.DockerError as e:
        _folders["error"] = str(e)
    finally:
        _folders["busy"] = False
        _folders["t"] = time.time()
        store.save("folders.json", {k: v for k, v in _folders.items() if k != "busy"})


@app.get("/api/storage/folders", dependencies=auth)
async def storage_folders(refresh: bool = False):
    """Unterordner (2 Ebenen) des Spieleverzeichnisses mit Größe und welcher Container sie nutzt."""
    _need_docker()
    if refresh or (not _folders["busy"] and time.time() - _folders["t"] > 1800):
        asyncio.create_task(_scan_folders())
    mounts = await docker_api.all_mounts()
    src = [(n, os.path.normpath(m["source"])) for n, ms in mounts.items() for m in ms if m["type"] == "bind" and m["source"]]
    names = {x.get("container"): x["name"] for x in load_servers()}
    items = []
    for f in _folders["items"]:
        p = os.path.normpath(f["path"])
        users = sorted({names.get(n, n) for n, s_ in src if s_ == p or s_.startswith(p + "/") or p.startswith(s_ + "/")})
        items.append({**f, "used_by": users, "depth": f["rel"].count("/") + 1})
    return {"items": items, "busy": _folders["busy"], "error": _folders["error"], "base": _folders["base"],
            "updated": _folders["t"] or None}


class FolderDel(BaseModel):
    path: str = Field(max_length=400)


@app.post("/api/storage/folders/delete", dependencies=auth)
async def storage_folder_delete(data: FolderDel):
    """Ungenutzten Ordner im Spieleverzeichnis samt Inhalt löschen (im Hintergrund)."""
    _need_docker()
    base = os.path.normpath(automation.get_settings().get("games_base") or "/mnt/grohlan")
    p = os.path.normpath(data.path)
    if not p.startswith(base + "/") or ".." in data.path:
        raise HTTPException(400, "Nur Ordner im Spieleverzeichnis")
    if not any(os.path.normpath(f["path"]) == p for f in _folders["items"]):
        raise HTTPException(400, "Ordner nicht in der Liste – bitte neu einlesen")
    mounts = await docker_api.all_mounts()
    src = [os.path.normpath(m["source"]) for ms in mounts.values() for m in ms if m["type"] == "bind" and m["source"]]
    if any(s_ == p or s_.startswith(p + "/") or p.startswith(s_ + "/") for s_ in src):
        raise HTTPException(409, "Ordner wird noch von einem Container genutzt (auch gestoppte zählen) – erst den Server löschen")
    parent, leaf = os.path.dirname(p), os.path.basename(p)

    async def go():
        try:
            await docker_api.run_helper([f"{parent}:/parent"], ["rm", "-rf", "--", f"/parent/{leaf}"], timeout=3600)
            log.info("Ordner gelöscht: %s", p)
        except docker_api.DockerError as e:
            log.warning("Löschen %s: %s", p, e)
            _folders["error"] = f"Löschen von {p}: {e}"
        _folders["items"] = [f for f in _folders["items"] if not (os.path.normpath(f["path"]) == p or f["path"].startswith(p + "/"))]
        asyncio.create_task(_scan_folders())
    _folders["items"] = [{**f, "deleting": True} if os.path.normpath(f["path"]) == p else f for f in _folders["items"]]
    asyncio.create_task(go())
    return {"ok": True}


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
    cstat = _apps_cache_status([a["id"] for a in prefill.settings().get("apps") or []])
    return {"settings": prefill.settings(), "container": st, "apps_progress": pp["apps"], "cache_status": cstat,
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


FULL_CHECK_DAYS = 7
CACHED_PCT = 85      # Spielgröße enthält auch Depots, die nie geladen werden (Sprachen, andere OS)


def _apps_cache_status(appids) -> dict:
    """Wie viel jedes Spiel seit dem letzten Zurücksetzen aus dem Internet in den Cache geholt hat (geschätzt)."""
    stored = {g["app"]: g.get("miss") or 0 for g in depots.games(cache_history.series("365d").get("depots") or {}) if g.get("app")}
    out, missing = {}, []
    for a in appids:
        a = int(a)
        size = depots.app_size(a)
        if not size:
            missing.append(a)
        st = stored.get(a, 0)
        out[str(a)] = {"stored": st, "size": size, "pct": round(min(100.0, st / size * 100), 1) if size else None}
    if missing:
        asyncio.create_task(depots.ensure_sizes(missing[:10]))
    return out


async def _prefill_queue_tick() -> None:
    """Nur ein Prefill gleichzeitig: weitere laufende anhalten und hinten anstellen; sonst den nächsten aus der Warteschlange starten."""
    running = []
    st = await prefill.container_state()
    if st and st.get("running"):
        running.append(("steam", st.get("started") or ""))
    for svc in prefill_more.SERVICES:
        s2 = await prefill_more.state(svc)
        if s2 and s2.get("running"):
            running.append((svc, s2.get("started") or ""))
    if len(running) > 1:
        running.sort(key=lambda x: x[1])
        for svc, _ in running[1:]:
            try:
                if svc == "steam":
                    await docker_api._req("POST", f"/containers/{prefill.NAME}/stop", params={"t": "5"}, timeout=30)
                    prefill_more.enqueue({"svc": "steam", "mode": "prefill"})
                else:
                    await prefill_more.stop(svc)
                    prefill_more.enqueue({"svc": svc, "opts": prefill_more.settings().get(svc) or {}})
                log.info("Prefill %s angehalten – läuft nach %s weiter", svc, running[0][0])
            except docker_api.DockerError:
                pass
        return
    if running:
        return
    item = prefill_more.pop_queue()
    if not item:
        return
    try:
        if item["svc"] == "steam":
            await _prefill_start(item.get("mode") or "prefill", queued=True)
        else:
            opts = item.get("opts") or {}
            if item["svc"] == "battlenet" and opts.get("mode") != "all":
                await prefill_more.write_selection("battlenet", opts.get("products") or [])
            await prefill_more.start(item["svc"], prefill_more.build_cmd(item["svc"], opts), await lancache_dns())
        log.info("Prefill-Warteschlange: %s gestartet", item["svc"])
    except (ValueError, docker_api.DockerError) as e:
        log.warning("Prefill-Warteschlange %s: %s", item.get("svc"), e)


async def _prefill_start(mode: str, queued: bool = False):
    if mode != "select-apps" and not queued:
        other = await prefill_more.any_running()
        if other and other != "steam":
            prefill_more.enqueue({"svc": "steam", "mode": mode})
            prefill.job["note"] = f"wartet – erst wird der {prefill_more.SERVICES[other]['label']}-Prefill fertig"
            return
    try:
        await _prefill_sync_server_games()
    except docker_api.DockerError:
        pass
    s0 = prefill.settings()
    prefill.job["note"] = None
    if mode != "select-apps" and s0.get("apps"):
        # Spiele, die laut Cache-Messung (fast) fehlen, aus SteamPrefills „erledigt“-Liste streichen – sonst meldet er „Up To Date“
        try:
            stat = _apps_cache_status([a["id"] for a in s0["apps"]])
            missing = [a for a in s0["apps"] if (stat.get(str(a["id"])) or {}).get("pct") is not None and stat[str(a["id"])]["pct"] < 50]
            if missing:
                n = await prefill.forget_depots([d for a in missing for d in depots.depots_of(a["id"])])
                if n:
                    prefill.job["note"] = f"{len(missing)} Spiele fehlen im Cache und werden neu geladen: " + ", ".join(a["name"] for a in missing[:5])
        except Exception:  # noqa: BLE001
            log.exception("Prefill: Abgleich mit dem Cache")
    if mode != "select-apps" and s0.get("skip_cached", True) and s0.get("apps"):
        # gecachte Spiele überspringen – einmal pro Woche aber alles laufen lassen, damit Updates mitkommen
        full_due = not s0.get("last_full") or time.time() - s0["last_full"] > FULL_CHECK_DAYS * 86400
        if full_due:
            prefill.save_settings({"last_full": time.time()})
            prefill.job["note"] = "Wöchentlicher Komplettlauf: alle Spiele werden auf Updates geprüft"
        else:
            stat = _apps_cache_status([a["id"] for a in s0["apps"]])
            todo = [a["id"] for a in s0["apps"] if (stat.get(str(a["id"])) or {}).get("pct") is None
                    or stat[str(a["id"])]["pct"] < CACHED_PCT]
            skipped = len(s0["apps"]) - len(todo)
            if skipped:
                prefill.job["note"] = " · ".join(x for x in (prefill.job.get("note"), f"{skipped} Spiele schon im Cache übersprungen, {len(todo)} werden geladen") if x)
            try:
                await prefill.write_apps(todo)
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
    skip_cached: bool = True
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
                                 "server_games": data.server_games, "skip_cached": data.skip_cached})
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


# ---------------------------------------------------------------- Prefill für Battle.net und Epic Games
def _psvc(svc: str) -> str:
    if svc not in prefill_more.SERVICES:
        raise HTTPException(404, "Unbekannter Dienst")
    return svc


@app.get("/api/prefill2/{svc}", dependencies=auth)
async def prefill2_get(svc: str):
    _psvc(svc)
    st = await prefill_more.state(svc) if docker_api.available() else None
    text = await prefill_more.log(svc, 300) if st else ""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return {"service": svc, "label": prefill_more.SERVICES[svc]["label"], "settings": prefill_more.settings().get(svc) or {},
            "state": st, "log": "\n".join(lines[-80:]), "prompt": prefill_more.prompt_of(text) if st and st.get("running") else None,
            "login_url": prefill_more.login_url(text) if st and st.get("running") else None,
            "products": prefill_more.BNET_PRODUCTS if svc == "battlenet" else [],
            "queued": any(x.get("svc") == svc for x in prefill_more.queue()), "queue": [x.get("svc") for x in prefill_more.queue()],
            "paused": prefill.auto.get("paused"), "pause_reason": prefill.auto.get("reason"),
            "rate": (livestats.data.get(prefill_more.SERVICES[svc]["name"]) or {}).get("rx_bps")}


class Prefill2Run(BaseModel):
    products: list[str] | None = None
    mode: str | None = None
    force: bool = False
    schedule: str | None = Field(None, max_length=5)


@app.post("/api/prefill2/{svc}/run", dependencies=auth)
async def prefill2_run(svc: str, data: Prefill2Run):
    _psvc(svc)
    _need_docker()
    opts = {k: v for k, v in data.model_dump().items() if v is not None}
    prefill_more.save_settings(svc, {k: opts[k] for k in ("products", "mode") if k in opts})
    try:
        cmd = prefill_more.build_cmd(svc, opts)
        other = await prefill_more.any_running()
        if other and other != svc:
            prefill_more.enqueue({"svc": svc, "opts": opts})
            return {"ok": True, "queued": True, "after": other}
        if svc == "battlenet" and opts.get("mode") != "all":
            await prefill_more.write_selection(svc, opts.get("products") or [])
        await prefill_more.start(svc, cmd, await lancache_dns())
    except ValueError as e:
        raise HTTPException(400, str(e))
    except docker_api.DockerError as e:
        raise HTTPException(502, str(e))
    return {"ok": True, "cmd": cmd}


@app.put("/api/prefill2/{svc}", dependencies=auth)
async def prefill2_put(svc: str, data: Prefill2Run):
    _psvc(svc)
    if data.schedule and not re.fullmatch(r"\d\d:\d\d", data.schedule):
        raise HTTPException(400, "Zeit im Format HH:MM")
    d = {k: v for k, v in data.model_dump().items() if v is not None and k in ("products", "mode", "schedule")}
    if data.schedule == "":
        d["schedule"] = ""
    return prefill_more.save_settings(svc, d).get(svc)


@app.post("/api/prefill2/{svc}/stop", dependencies=auth)
async def prefill2_stop(svc: str):
    _psvc(svc)
    prefill_more.drop_queue(svc)
    try:
        await prefill_more.stop(svc)
    except docker_api.DockerError as e:
        raise HTTPException(502, str(e))
    return {"ok": True}


class Prefill2Send(BaseModel):
    text: str = Field(max_length=4000)


@app.post("/api/prefill2/{svc}/send", dependencies=auth)
async def prefill2_send(svc: str, data: Prefill2Send):
    _psvc(svc)
    try:
        await prefill_more.send(svc, data.text.strip())
    except (OSError, docker_api.DockerError, asyncio.TimeoutError) as e:
        raise HTTPException(502, str(e))
    return {"ok": True}


async def prefill_scheduler():
    try:
        await prefill_more.run_scheduled(await lancache_dns())
    except Exception:  # noqa: BLE001
        log.exception("Prefill (Battle.net/Epic) geplant")
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
    need_game(request, data.game, 4)
    if data.game in gslt.APPS and not (data.values.get("token") or "").strip():
        try:   # Steam-Token automatisch: freien gespeicherten nehmen oder (mit API-Schlüssel) neu anlegen
            t = await gslt.get_or_create(gslt.APPS[data.game], (data.values.get("name") or data.game)[:32], set(await _gslt_reconcile()))
        except gslt.GsltError as e:
            t = None
            log.warning("GSLT: %s", e)
        if t:
            if gslt.STYLE.get(data.game) == "env":
                data.values["token"] = t["token"]
            else:   # Source-/Sandstorm-Server: Token als Startparameter
                base = data.values.get("params")
                if base is None:
                    base = catmod.CATALOG.get(data.game, {}).get("params", "")
                data.values["params"] = (base + " " + gslt.token_param(data.game, t["token"])).strip()
            gslt.assign(t["token"], data.values.get("name") or "")
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
    try:   # öffentliche IP als Server-Adresse taugt nicht (RCON/Status laufen im LAN) -> LAN-Adresse der anderen Server
        if not ipaddress.ip_address(host).is_private:
            lan = [x["host"] for x in load_servers() if re.fullmatch(r"\d+\.\d+\.\d+\.\d+", x.get("host") or "")
                   and ipaddress.ip_address(x["host"]).is_private]
            if lan:
                host = max(set(lan), key=lan.count)
    except ValueError:
        pass
    data.values["_host"] = host
    jid = secrets.token_hex(6)
    job = {"id": jid, "game": data.game, "log": [], "step": "", "done": False, "error": None, "server_id": None,
           "req": {"game": data.game, "values": data.values, "data_dir": data.data_dir, "host": host}, "stage": "start"}
    _jobs[jid] = job
    _save_jobs(True)
    _job_tasks[jid] = asyncio.create_task(_create_job(job, data, host))
    return job


class BatchIn(BaseModel):
    game: str
    values: dict[str, str]
    data_dir: str = Field(min_length=2, max_length=255)
    host: str | None = Field(None, max_length=255)
    count: int = Field(2, ge=2, le=10)
    n: int = Field(1, ge=1, le=999)        # Nummer des ersten Servers (steckt in Name/Servername/Ordner)


def _renumber(text: str, n0: int, n: int) -> str:
    """Nummer n0 in Namen/Ordnern durch n ersetzen (nur ganze Zahl, z. B. CS4 -> CS5, „#4“ -> „#5“)."""
    return re.sub(rf"(?<!\d){n0}(?!\d)", str(n), text or "")


async def _run_batch(job: dict) -> None:
    """Server eines Stapels nacheinander anlegen. Übersteht Neustarts des Tools: bereits begonnene
    Teil-Jobs laufen über _resume_jobs weiter, hier wird auf sie gewartet und dann mit dem nächsten weitergemacht."""
    plans, host, game = job["plans"], job["host"], job["game"]
    try:
        for k, pl in enumerate(plans):
            if k < len(job["batch"]):                      # schon begonnen (vor einem Neustart)
                sj = _jobs.get(job["batch"][k])
                while sj and not sj["done"]:
                    await asyncio.sleep(3)
                if sj and k == len(job["batch"]) - 1 and not any(f"{pl['values'].get('name')}:" in x for x in job["log"]):
                    _job_log(job, f"{pl['values'].get('name')}: " + ("Fehler – " + sj["error"] if sj["error"] else "fertig"))
                    job["server_id"] = sj.get("server_id") or job["server_id"]
                continue
            job["step"] = f"Server {k + 1} von {len(plans)}: {pl['values'].get('name')}"
            _job_log(job, job["step"])
            vals_k = dict(pl["values"])
            if game == "cs2" and k > 0 and job.get("first_sid"):
                vals_k["_copy_from"] = job["first_sid"]      # vom gerade fertig installierten ersten Server kopieren
            sub = CreateIn(game=game, values=vals_k, data_dir=pl["data_dir"], host=host)
            # Token wie beim Einzelanlegen automatisch
            if sub.game in gslt.APPS and not (sub.values.get("token") or "").strip():
                try:
                    t = await gslt.get_or_create(gslt.APPS[sub.game], (sub.values.get("name") or sub.game)[:32], set(await _gslt_reconcile()))
                except gslt.GsltError as e:
                    t = None
                    _job_log(job, f"Steam-Token: {e}")
                if t:
                    if gslt.STYLE.get(sub.game) == "env":
                        sub.values["token"] = t["token"]
                    else:
                        base = sub.values.get("params")
                        if base is None:
                            base = catmod.CATALOG.get(sub.game, {}).get("params", "")
                        base = re.sub(r"\s*(\+sv_setsteamaccount\s+\S+|-GSLTToken=\S+)", "", base)
                        sub.values["params"] = (base + " " + gslt.token_param(sub.game, t["token"])).strip()
                    gslt.assign(t["token"], sub.values.get("name") or "")
            jid = secrets.token_hex(6)
            sj = {"id": jid, "game": sub.game, "log": [], "step": "", "done": False, "error": None, "server_id": None,
                  "req": {"game": sub.game, "values": sub.values, "data_dir": sub.data_dir, "host": host}, "stage": "start",
                  "title": sub.values.get("name")}
            _jobs[jid] = sj
            job["batch"].append(jid)
            _save_jobs(True)
            await _create_job(sj, sub, host)
            _job_log(job, f"{sub.values.get('name')}: " + ("Fehler – " + sj["error"] if sj["error"] else "fertig"))
            job["server_id"] = sj.get("server_id") or job["server_id"]
            if k == 0 and sj.get("server_id") and not sj.get("error"):
                job["first_sid"] = sj["server_id"]
            _save_jobs(True)
        job["step"] = f"{len(plans)} Server angelegt"
    except asyncio.CancelledError:
        _save_jobs(True)
        raise
    except Exception as e:  # noqa: BLE001 – Fehler im Job anzeigen statt still abbrechen
        log.exception("Stapel-Anlegen")
        job["error"] = str(e) or e.__class__.__name__
    job["done"] = True
    job["t_done"] = time.time()
    _save_jobs(True)


@app.post("/api/create/batch", dependencies=auth)
async def create_batch(data: BatchIn, request: Request):
    """Mehrere Server desselben Spiels nacheinander anlegen: Nummern, Ports, Ordner und Steam-Tokens automatisch."""
    _need_docker()
    if data.game not in templates.TEMPLATES:
        raise HTTPException(400, "Unbekanntes Spiel")
    need_game(request, data.game, 4)
    used = set(await _used_ports())
    names = {x.get("container") for x in load_servers()} | {x["name"] for x in load_servers()}
    port_fields = {f for f, *_ in templates.PORT_PLAN.get(data.game, [])}
    plans = []
    for i in range(data.count):
        n = data.n + i
        vals = dict(data.values)
        if i:
            for k in ("name", "server_name", "memo"):
                if k in vals:
                    vals[k] = _renumber(vals[k], data.n, n)
            vals.update({k: str(v) for k, v in templates.suggest_ports(data.game, used).items()})
            vals.pop("token", None)           # jeder Server bekommt seinen eigenen Token
        try:
            b = templates.build(data.game, vals, _renumber(data.data_dir, data.n, n) if i else data.data_dir)
        except ValueError as e:
            if "Steam-Token" in str(e):       # Token wird erst im Job zugeteilt
                b = None
            else:
                raise HTTPException(400, f"Server {i + 1}: {e}")
        if b:
            clash = [p for p in templates.host_ports(b["spec"]) if p in used]
            if clash:
                raise HTTPException(400, f"Server {i + 1}: Port {clash[0]} schon belegt")
            used |= set(templates.host_ports(b["spec"]))
        else:
            used |= {int(vals[f]) for f in port_fields if str(vals.get(f, "")).isdigit()}
        if vals.get("name") in names:
            raise HTTPException(400, f"Server {i + 1}: Name {vals['name']} gibt es schon")
        names.add(vals.get("name"))
        plans.append({"values": vals, "data_dir": _renumber(data.data_dir, data.n, n) if i else data.data_dir})
    host = (data.host or "").strip() or _docker_host_ip(request)
    bid = secrets.token_hex(6)
    job = {"id": bid, "game": data.game, "title": f"{data.count} × {templates.TEMPLATES[data.game]['label']} anlegen", "log": [],
           "step": "", "done": False, "error": None, "server_id": None, "batch": [], "req": None,
           "plans": plans, "host": host}
    _jobs[bid] = job
    _save_jobs(True)
    _job_tasks[bid] = asyncio.create_task(_run_batch(job))
    return {"id": bid, "names": [p["values"].get("name") for p in plans]}


_job_tasks: dict[str, asyncio.Task] = {}


async def _dir_is_new(path: str) -> bool:
    """True, wenn der Ordner (unter dem Spieleverzeichnis) noch nicht existiert."""
    base = os.path.normpath(automation.get_settings().get("games_base") or "/mnt/grohlan")
    p = os.path.normpath(path or "")
    if not p.startswith(base + "/"):
        return False
    try:
        out = await docker_api.run_helper([f"{base}:/base:ro"], ["sh", "-c", f'[ -e "/base/{os.path.relpath(p, base)}" ] && echo OLD || echo NEW'])
    except docker_api.DockerError:
        return False
    return "NEW" in out


async def _cleanup_job(job: dict) -> list[str]:
    """Nach dem Abbrechen: Kopier-Helfer, Container, Servereintrag, Datenordner (nur wenn neu) und Token-Zuordnung entfernen."""
    done = []
    req = job.get("req") or {}
    vals = req.get("values") or {}
    name = (vals.get("name") or "").strip()
    try:
        name = templates.build(req["game"], vals, req["data_dir"])["name"]
    except Exception:  # noqa: BLE001 – Name reicht zum Aufräumen
        pass
    if name and docker_api.available():
        try:
            for c in await docker_api.list_containers():
                if c["name"].startswith(f"gsm-copy-{name}-"):
                    await docker_api.remove_container(c["name"]); done.append(f"Kopiervorgang {c['name']} beendet")
        except docker_api.DockerError:
            pass
        if job.get("created_container") == name:
            try:
                info = await docker_api.inspect(name)
                if ((info.get("Config") or {}).get("Labels") or {}).get("gsm.managed") == "1":
                    await docker_api.remove_container(name); done.append(f"Container {name} gelöscht")
            except docker_api.DockerError:
                pass
    if job.get("server_id"):
        async with _store_lock:
            save_servers([x for x in load_servers() if x["id"] != job["server_id"]])
        _state.pop(job["server_id"], None)
        done.append("Servereintrag entfernt")
    if req.get("data_dir"):
        try:
            others = await docker_api.all_mounts()
            other_src = [m["source"] for ms in others.values() for m in ms if m["type"] == "bind" and m["source"]]
            p = os.path.normpath(req["data_dir"])
            why = _path_check(p, other_src)
            if why is None:
                await docker_api.run_helper([f"{os.path.dirname(p)}:/p"], ["rm", "-rf", "--", f"/p/{os.path.basename(p)}"], timeout=3600)
                done.append(f"Daten {p} gelöscht")
            else:
                done.append(f"Daten {p} behalten ({why})")
        except docker_api.DockerError as e:
            done.append(f"Daten löschen fehlgeschlagen: {e}")
    if vals.get("token"):
        gslt.assign(vals["token"], None)
    return done


@app.post("/api/jobs/{jid}/cancel", dependencies=auth)
async def cancel_job(jid: str):
    """Anlegen abbrechen – laufende Schritte stoppen, Container und neu angelegte Daten löschen."""
    j = _jobs.get(jid)
    if not j:
        raise HTTPException(404, "Job nicht gefunden")
    if j.get("done") and not j.get("plans"):
        raise HTTPException(409, "Anlegen ist schon fertig – Server stattdessen löschen")
    subs = [_jobs[x] for x in (j.get("batch") or []) if x in _jobs] if j.get("plans") else []
    targets = [j] + [s for s in subs if not s.get("done")]
    for x in targets:
        x["cancelled"] = True
        tk = _job_tasks.pop(x["id"], None)
        if tk and not tk.done():
            tk.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(tk), 5)
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):  # noqa: BLE001
                pass
    log_lines = []
    for x in ([s for s in subs if s.get("cancelled")] if j.get("plans") else [j]):
        log_lines += await _cleanup_job(x)
        x.update(done=True, error="abgebrochen", t_done=time.time())
    j.update(done=True, error="abgebrochen", t_done=time.time())
    for line in log_lines or ["nichts aufzuräumen"]:
        _job_log(j, line)
    _save_jobs(True)
    return {"ok": True, "log": log_lines}


@app.get("/api/jobs/{jid}", dependencies=auth)
async def get_job(jid: str):
    if jid not in _jobs:
        raise HTTPException(404)
    j = _jobs[jid]
    if j.get("batch"):                     # Sammel-Job: Fortschritt und Log des laufenden Servers mit anzeigen
        cur = _jobs.get(j["batch"][-1]) or {}
        return {**j, "progress": cur.get("progress"), "log": j["log"] + [f"  {x}" for x in (cur.get("log") or [])[-12:]],
                "step": j["step"] + (f" – {cur.get('step')}" if cur.get("step") and not j["done"] else "")}
    return j


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

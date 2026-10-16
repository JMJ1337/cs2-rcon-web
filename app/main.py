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
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .rcon import RconAuthError, RconClient, RconError

log = logging.getLogger("cs2rcon")
logging.basicConfig(level=logging.INFO)

DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
SERVERS_FILE = DATA_DIR / "servers.json"
SECRET_FILE = DATA_DIR / ".secret"
STATIC_DIR = Path(__file__).parent / "static"

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
if not ADMIN_PASSWORD:
    ADMIN_PASSWORD = "changeme"
    log.warning("ADMIN_PASSWORD nicht gesetzt – Standardpasswort 'changeme' aktiv!")
SESSION_HOURS = int(os.getenv("SESSION_HOURS", "24"))
RCON_TIMEOUT = float(os.getenv("RCON_TIMEOUT", "4"))

if not SECRET_FILE.exists():
    SECRET_FILE.write_text(secrets.token_hex(32))
SECRET = SECRET_FILE.read_text().strip().encode()
COOKIE = "cs2rcon_session"

app = FastAPI(title="CS2 RCON Web", docs_url=None, redoc_url=None)


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


# ---------------------------------------------------------------- Server-Speicher
class ServerIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(27015, ge=1, le=65535)
    password: str | None = None  # None/"" beim Update = unverändert lassen
    notes: str = ""


_store_lock = asyncio.Lock()
_clients: dict[str, RconClient] = {}


def load_servers() -> list[dict]:
    if not SERVERS_FILE.exists():
        return []
    try:
        return json.loads(SERVERS_FILE.read_text(encoding="utf-8"))
    except Exception:
        log.exception("servers.json konnte nicht gelesen werden")
        return []


def save_servers(servers: list[dict]) -> None:
    tmp = SERVERS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(servers, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(SERVERS_FILE)


def public(s: dict) -> dict:
    return {k: v for k, v in s.items() if k != "password"} | {"has_password": bool(s.get("password"))}


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


auth = [Depends(require_auth)]


@app.get("/api/servers", dependencies=auth)
async def list_servers():
    return [public(s) for s in load_servers()]


@app.post("/api/servers", dependencies=auth)
async def add_server(data: ServerIn):
    async with _store_lock:
        servers = load_servers()
        s = {"id": uuid.uuid4().hex[:10], "name": data.name, "host": data.host.strip(),
             "port": data.port, "password": data.password or "", "notes": data.notes}
        servers.append(s)
        save_servers(servers)
    return public(s)


@app.put("/api/servers/{sid}", dependencies=auth)
async def update_server(sid: str, data: ServerIn):
    async with _store_lock:
        servers = load_servers()
        for s in servers:
            if s["id"] == sid:
                s.update(name=data.name, host=data.host.strip(), port=data.port, notes=data.notes)
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


@app.get("/api/servers/{sid}/status", dependencies=auth)
async def status(sid: str):
    s = get_server(sid)
    raw = await run(s, "status")
    return {"online": True, "raw": raw, **parse_status(raw)}


class CvarsIn(BaseModel):
    names: list[str] = Field(max_length=100)


@app.post("/api/servers/{sid}/cvars", dependencies=auth)
async def get_cvars(sid: str, data: CvarsIn):
    s = get_server(sid)
    names = [n for n in data.names if re.fullmatch(r"[A-Za-z0-9_]+", n)]
    if not names:
        return {}
    raw = await run(s, ";".join(names))
    values: dict[str, str | None] = {n: None for n in names}
    for n in names:
        m = re.search(rf"(?m)^\s*{re.escape(n)}\s*=\s*(\"([^\"]*)\"|(\S+))", raw)
        if m:
            values[n] = m.group(2) if m.group(2) is not None else m.group(3)
    return values


class TestIn(BaseModel):
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(27015, ge=1, le=65535)
    password: str | None = None
    server_id: str | None = None  # gespeichertes Passwort verwenden, falls keins angegeben


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


# ---------------------------------------------------------------- Frontend
@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

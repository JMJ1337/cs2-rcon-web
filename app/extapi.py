"""Externe API (/api/v1) für die Homepage: Turnier (Status, Anmeldung, Teams, Anlegen), Benutzerkonten, Zuschauen/Stream, Steam-Bot.

Zugriff mit API-Schlüssel (Header „X-API-Key: …“ oder „Authorization: Bearer …“), angelegt in der Verwaltung unter
„🔌 API“. Jeder Schlüssel hat Rechte: tournament (lesen + Anmeldung), organize (Turniere anlegen/einstellen),
users (Benutzerkonten von der Homepage anlegen/aktualisieren), bot (Nachrichten, Einladungen, Freunde), stream (lesen). Nur-lesen-Endpunkte für Turnier und Stream gehen ohne Schlüssel, wenn „öffentlich lesbar“ an ist.
Die Homepage ruft die API vom eigenen Server aus auf (Schlüssel nie im Browser!) und reicht die SteamID des
angemeldeten Homepage-Nutzers mit.
"""
import hashlib
import re
import secrets
import time

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from . import store

FILE = "apikeys.json"
SCOPES = ("tournament", "organize", "users", "bot", "stream")
router = APIRouter(prefix="/api/v1", tags=["Homepage-API"])


# ---------------------------------------------------------------- Schlüssel
def _all() -> dict:
    return {"keys": [], "public_read": True, "origins": [], **store.load(FILE, {})}


def _h(k: str) -> str:
    return hashlib.sha256(k.encode()).hexdigest()


def list_keys() -> dict:
    d = _all()
    return {"keys": [{k: x.get(k) for k in ("id", "name", "scopes", "created", "last_used", "uses", "hint")} for x in d["keys"]],
            "public_read": d["public_read"], "origins": d["origins"]}


def create_key(name: str, scopes: list[str]) -> str:
    d = _all()
    raw = "gsm_" + secrets.token_urlsafe(32)
    d["keys"].append({"id": secrets.token_hex(4), "name": name.strip()[:60], "hash": _h(raw), "hint": raw[:8] + "…",
                      "scopes": [s for s in scopes if s in SCOPES] or ["tournament"], "created": time.time(), "uses": 0})
    store.save(FILE, d)
    return raw


def delete_key(kid: str) -> None:
    d = _all()
    d["keys"] = [k for k in d["keys"] if k["id"] != kid]
    store.save(FILE, d)


def set_options(public_read: bool | None, origins: list[str] | None) -> None:
    d = _all()
    if public_read is not None:
        d["public_read"] = public_read
    if origins is not None:
        d["origins"] = [o.strip().rstrip("/") for o in origins if re.match(r"^https?://[\w.\-:]+$", o.strip().rstrip("/"))][:10]
    store.save(FILE, d)


def origins() -> list[str]:
    return _all()["origins"]


_last_save = {"t": 0.0}


def _check(scope: str, key: str | None, read: bool = False) -> None:
    d = _all()
    if not key:
        if read and d["public_read"]:
            return
        raise HTTPException(401, "API-Schlüssel fehlt (Header X-API-Key)")
    hk = _h(key)
    k = next((x for x in d["keys"] if secrets.compare_digest(x["hash"], hk)), None)
    if not k:
        raise HTTPException(401, "API-Schlüssel ungültig")
    if scope not in k["scopes"]:
        raise HTTPException(403, f"Schlüssel hat kein Recht „{scope}“")
    k["uses"] = (k.get("uses") or 0) + 1
    k["last_used"] = time.time()
    if time.time() - _last_save["t"] > 30:                # nicht bei jedem Aufruf schreiben
        _last_save["t"] = time.time()
        store.save(FILE, d)


def _key(x_api_key: str | None, authorization: str | None) -> str | None:
    if x_api_key:
        return x_api_key.strip()
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def auth(scope: str, read: bool = False):
    def dep(x_api_key: str | None = Header(None), authorization: str | None = Header(None)):
        _check(scope, _key(x_api_key, authorization), read)
    return dep


from fastapi import Depends  # noqa: E402

SID = r"^\d{17}$"


def _M():
    from . import main as M      # spät importieren (main importiert dieses Modul)
    return M


def _base(request: Request) -> str:
    return str(request.base_url).rstrip("/")


# ---------------------------------------------------------------- Turnier
@router.get("/tournament", dependencies=[Depends(auth("tournament", read=True))])
async def v1_tournament(request: Request):
    """Komplettes Turnier: Einstellungen, Teams, Spiele (Teams, Runden, Status, Zeit, Server, Ergebnis, Zuschauen-Link)."""
    M = _M()
    d = M.tour.load()
    v = M._tour_out(d)
    for m in v["matches"]:
        m.pop("server", None)
        if m.get("tv_url"):
            m["tv_address"] = m["tv_url"].split("%20", 1)[-1]
    return {**v, "players": [{k: p.get(k) for k in ("steamid", "name", "avatar", "team")} for p in v.get("players") or []],
            "embed": f"{_base(request)}/embed/tournament", "stream": f"{_base(request)}/api/v1/stream"}


class PlayerIn(BaseModel):
    steamid: str = Field(pattern=SID)
    name: str | None = Field(None, max_length=40)
    avatar: str | None = Field(None, max_length=300)


def _open(d: dict) -> None:
    if d.get("status") != "setup" or not d.get("registration"):
        raise HTTPException(409, "Anmeldung ist geschlossen")


@router.get("/tournament/player/{steamid}", dependencies=[Depends(auth("tournament", read=True))])
async def v1_player(steamid: str, request: Request):
    """Status eines Spielers: angemeldet? Team? Nächstes/laufendes Spiel mit Server-Adresse und Zuschauen-Link."""
    if not re.match(SID, steamid):
        raise HTTPException(400, "SteamID64 erwartet")
    M = _M()
    d = M.tour.load()
    t = M.tour.player_team(d, steamid)
    out = {"steamid": steamid, "registered": any(p["steamid"] == steamid for p in d["players"]),
           "team": {"id": t["id"], "name": t["name"], "players": t["players"]} if t else None,
           "registration_open": d.get("status") == "setup" and bool(d.get("registration")), "status": d.get("status")}
    if t:
        mine = [m for m in d["matches"] if t["id"] in (m.get("t1"), m.get("t2")) and m["status"] in ("ready", "live", "wait")]
        mine.sort(key=lambda m: (m["status"] != "live", m.get("planned") or 9e18))
        if mine:
            m = mine[0]
            s = next((x for x in M.load_servers() if x["id"] == m.get("server")), None)
            p = M.playerdb.get(steamid)
            lan = bool(p and M.playerdb.connects_from_lan(p))
            out["next_match"] = {"id": m["id"], "label": m["label"], "status": m["status"], "planned": m.get("planned"), "map": m.get("map"),
                                 "opponent": M.tour.team_name(d, m["t2"] if m["t1"] == t["id"] else m["t1"]),
                                 "server": s.get("name") if s else None,
                                 "join": (await M.invite_join_text(s, lan)).strip() if s else None}
    return out


@router.post("/tournament/register", dependencies=[Depends(auth("tournament"))])
async def v1_register(data: PlayerIn):
    M = _M()
    d = M.tour.load()
    _open(d)
    p = next((x for x in d["players"] if x["steamid"] == data.steamid), None)
    if p:
        if data.name:
            p["name"] = data.name.strip()[:40]
    else:
        pl = M.playerdb.get(data.steamid)
        d["players"].append({"steamid": data.steamid, "name": (data.name or (M.playerdb.display(pl) if pl else data.steamid)).strip()[:40],
                             "avatar": data.avatar or (pl or {}).get("avatar"), "t": time.time(), "via": "homepage"})
    M.tour.save(d)
    return {"ok": True}


class SteamIn(BaseModel):
    steamid: str = Field(pattern=SID)


@router.post("/tournament/unregister", dependencies=[Depends(auth("tournament"))])
async def v1_unregister(data: SteamIn):
    M = _M()
    d = M.tour.load()
    _open(d)
    d["players"] = [p for p in d["players"] if p["steamid"] != data.steamid]
    for t in d["teams"]:
        t["players"] = [x for x in t["players"] if x != data.steamid]
    d["teams"] = [t for t in d["teams"] if t["players"]]
    M.tour.save(d)
    return {"ok": True}


class TeamIn(BaseModel):
    steamid: str = Field(pattern=SID)
    name: str = Field(min_length=1, max_length=24)


@router.post("/tournament/teams", dependencies=[Depends(auth("tournament"))])
async def v1_team_create(data: TeamIn):
    """Team gründen – der Spieler muss angemeldet sein; der Partner tritt mit /teams/{id}/join bei."""
    M = _M()
    d = M.tour.load()
    _open(d)
    if not any(p["steamid"] == data.steamid for p in d["players"]):
        raise HTTPException(400, "Spieler ist nicht angemeldet")
    if M.tour.player_team(d, data.steamid):
        raise HTTPException(400, "Spieler ist schon in einem Team")
    name = M._clean_team_name(data.name)
    if any(t["name"].lower() == name.lower() for t in d["teams"]):
        raise HTTPException(400, "Den Teamnamen gibt es schon")
    tid = M.tour.new_team_id()
    d["teams"].append({"id": tid, "name": name, "players": [data.steamid]})
    M.tour.save(d)
    return {"ok": True, "id": tid}


@router.post("/tournament/teams/{tid}/join", dependencies=[Depends(auth("tournament"))])
async def v1_team_join(tid: str, data: SteamIn):
    M = _M()
    d = M.tour.load()
    _open(d)
    if not any(p["steamid"] == data.steamid for p in d["players"]):
        raise HTTPException(400, "Spieler ist nicht angemeldet")
    if M.tour.player_team(d, data.steamid):
        raise HTTPException(400, "Spieler ist schon in einem Team")
    t = M.tour.team(d, tid)
    if not t or len(t["players"]) >= 2:
        raise HTTPException(400, "Team voll oder nicht gefunden")
    t["players"].append(data.steamid)
    M.tour.save(d)
    return {"ok": True}


@router.post("/tournament/teams/leave", dependencies=[Depends(auth("tournament"))])
async def v1_team_leave(data: SteamIn):
    M = _M()
    d = M.tour.load()
    _open(d)
    for t in d["teams"]:
        t["players"] = [x for x in t["players"] if x != data.steamid]
    d["teams"] = [t for t in d["teams"] if t["players"]]
    M.tour.save(d)
    return {"ok": True}


# ---------------------------------------------------------------- Zuschauen / Stream
@router.get("/stream", dependencies=[Depends(auth("stream", read=True))])
async def v1_stream(request: Request):
    """Live-Stream: läuft er, was wird gezeigt, HLS-Adresse und fertige Einbett-Seite (iframe)."""
    M = _M()
    st = await M.public_stream()
    b = _base(request)
    if st.get("enabled"):
        st["hls"] = b + st["hls"]
    st["embed"] = f"{b}/embed/stream"
    st.pop("server", None)
    return st


@router.get("/halloffame", dependencies=[Depends(auth("tournament", read=True))])
async def v1_hof():
    """Hall of Fame: tournaments (Sieger, Finalist, Finale, MVP, alle Spielerwerte) und players (ewige Wertung)."""
    return await _M().public_hof()


@router.get("/deathmatch", dependencies=[Depends(auth("tournament", read=True))])
async def v1_deathmatch():
    """Deathmatch-Bestenliste von CS #1: day (heute, ab 6 Uhr) und total."""
    return await _M().public_dm()


@router.get("/servers", dependencies=[Depends(auth("tournament", read=True))])
async def v1_servers():
    """Server mit Status, Spielern und Beitritts-/Zuschauen-Adresse (öffentliche Adresse)."""
    M = _M()
    out = []
    wan = await M.wan_host()
    for s in M.load_servers():
        st = M._state.get(s["id"]) or {}
        j = st.get("join") or {}
        host = M._join_host(s)
        rep = (lambda v: v.replace(host, wan) if (v and wan) else v)
        out.append({"id": s["id"], "name": st.get("hostname") or s.get("name"), "game": M.game_of(s), "online": bool(st.get("online")),
                    "players": st.get("humans"), "max": st.get("max_players"), "map": st.get("map"),
                    "address": rep(j.get("address")), "tv_address": rep(j.get("tv_address"))})
    return {"servers": out}


# ---------------------------------------------------------------- Steam-Bot
@router.get("/bot", dependencies=[Depends(auth("bot"))])
async def v1_bot():
    M = _M()
    st = await M.steambot_ctl.status()
    b = st.get("bot") or {}
    return {"enabled": M.steambot_ctl.settings().get("enabled"), "state": b.get("state"), "steamid": b.get("steamid"),
            "name": b.get("name"), "can_invite": b.get("can_invite"), "friends": len([f for f in b.get("friends") or [] if f.get("rel") == "Friend"]),
            "error": st.get("error")}


@router.get("/bot/friends", dependencies=[Depends(auth("bot"))])
async def v1_bot_friends():
    M = _M()
    st = await M.steambot_ctl.status()
    return {"friends": (st.get("bot") or {}).get("friends") or []}


@router.post("/bot/friend", dependencies=[Depends(auth("bot"))])
async def v1_bot_friend(data: SteamIn):
    """Freundschaftsanfrage vom Bot (Nachrichten gehen nur an bestätigte Freunde – Steam-Regel)."""
    M = _M()
    try:
        return await M.steambot_ctl.api("POST", "/add", {"steamid": data.steamid})
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, str(e)[:200])


class MsgIn(BaseModel):
    steamids: list[str] = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=2000)


async def _send(steamids: list[str], text: str) -> dict:
    M = _M()
    ids = [x for x in steamids if re.match(SID, x)]
    st = await M.steambot_ctl.status()
    friends = {f["steamid"] for f in ((st.get("bot") or {}).get("friends") or []) if f.get("rel") == "Friend"}
    send, not_friend = [x for x in ids if x in friends], [x for x in ids if x not in friends]
    res = {"done": [], "failed": []}
    if send:
        try:
            res = await M.steambot_ctl.api("POST", "/msg", {"steamids": send, "text": text}, timeout=max(30, len(send)))
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, str(e)[:200])
    return {"sent": res.get("done") or [], "failed": res.get("failed") or [], "not_friends": not_friend}


@router.post("/bot/message", dependencies=[Depends(auth("bot"))])
async def v1_bot_message(data: MsgIn):
    """Nachricht an Spieler (nur Freunde des Bots; die anderen kommen in „not_friends“ zurück)."""
    return await _send(data.steamids, data.text)


class InviteIn(BaseModel):
    steamids: list[str] = Field(min_length=1, max_length=200)
    text: str = Field("", max_length=1500)
    server_id: str | None = None        # einer unserer Server: Adresse LAN/WAN je Spieler + Klick-Link
    address: str | None = Field(None, max_length=120)   # oder eine fremde Adresse (z. B. Finalturnier-Server)
    password: str | None = Field(None, max_length=60)


@router.post("/bot/invite", dependencies=[Depends(auth("bot"))])
async def v1_bot_invite(data: InviteIn):
    """Einladung zu einem Spiel: Text + Adresse. Bei server_id bekommt jeder die passende Adresse (LAN/Internet)
    und einen klickbaren Beitritts-Link; bei address wird die Adresse (und ggf. Passwort) angehängt."""
    M = _M()
    if not data.server_id and not data.address:
        raise HTTPException(400, "server_id oder address angeben")
    head = data.text.strip()
    if data.server_id:
        s = next((x for x in M.load_servers() if x["id"] == data.server_id), None)
        if not s:
            raise HTTPException(404, "Server nicht gefunden")
        out = {"sent": [], "failed": [], "not_friends": []}
        for lan, group in M._split_lan(data.steamids).items():
            if group:
                r = await _send(group, (head + "\n" if head else "") + (await M.invite_join_text(s, lan)).strip())
                for k in out:
                    out[k] += r[k]
        return out
    addr = re.sub(r"[^\w.\-:\[\]]", "", data.address or "")
    txt = (head + "\n" if head else "") + f"Verbinden: {addr}" + (f"\nPasswort: {data.password}" if data.password else "") + \
        f"\nIn der CS2-Konsole: connect {addr}" + (f"; password {data.password}" if data.password else "")
    return await _send(data.steamids, txt)


# ---------------------------------------------------------------- Turniere anlegen und einstellen (Recht „organize“)
class TourSetIn(BaseModel):
    name: str | None = Field(None, max_length=60)
    mode: str | None = Field(None, description="ko | double | groups | rr")
    start: float | None = Field(None, description="geplanter Start (Unix-Sekunden)")
    registration: bool | None = None
    maps: list[str] | None = Field(None, max_length=20)
    match_min: int | None = Field(None, ge=10, le=180)
    pause_min: int | None = Field(None, ge=0, le=60)


class TourCreateIn(TourSetIn):
    template: str | None = Field(None, max_length=40, description="ID einer Turniervorlage aus GET /tournament/options")


def _tour_apply(M, d: dict, data: TourSetIn) -> None:
    for k, v in data.model_dump(exclude_none=True).items():
        if k not in TourSetIn.model_fields:            # nur Einstellungen – Teams, IDs usw. behandelt der Aufrufer
            continue
        if k == "mode" and v not in M.tour.MODES:
            raise HTTPException(400, "Unbekannter Modus – erlaubt: " + ", ".join(M.tour.MODES))
        if k == "maps":
            v = [re.sub(r"[^\w\-/]", "", x) for x in v if x.strip()][:20] or M.tour.WINGMAN_MAPS
        if k == "name":
            v = re.sub(r'["\\;]', "", v).strip()[:60] or d.get("name")
        d[k] = v


@router.get("/tournament/options", dependencies=[Depends(auth("organize"))])
async def v1_tour_options():
    """Modi, Vorlagen und Standard-Maps – für das Formular „Turnier anlegen“ auf der Homepage."""
    M = _M()
    return {"modes": M.tour.MODES, "maps_default": M.tour.WINGMAN_MAPS,
            "templates": [{"id": t["id"], "name": t.get("name")} for t in M.tour.templates()]}


@router.post("/tournament/new", dependencies=[Depends(auth("organize"))])
async def v1_tour_new(data: TourCreateIn):
    """Neues Turnier anlegen (das bisherige wird im Archiv gespeichert). Spielplan und Start macht die Turnierleitung."""
    M = _M()
    d = M.tour.load()
    if M._tour_busy(d) or M._tour_test(d):
        raise HTTPException(409, "Das aktuelle Turnier läuft – erst im Spielservermanager anhalten")
    if data.template and not any(t["id"] == data.template for t in M.tour.templates()):
        raise HTTPException(400, "Vorlage nicht gefunden")
    if M._tour_has_content(d):
        M.tour.lib_save(d)
    new = M.tour.new_from(data.template)
    new["name"] = f"{M.automation.brand()} Wingman-Turnier" if not data.name and not data.template else new["name"]
    _tour_apply(M, new, data)
    new["via"] = "homepage"
    M._tour_names.clear()
    M.tour.save(new)
    return {"ok": True, "tournament": {k: new.get(k) for k in ("name", "mode", "start", "registration", "maps", "match_min", "pause_min", "status")}}


@router.put("/tournament", dependencies=[Depends(auth("organize"))])
async def v1_tour_set(data: TourSetIn):
    """Einstellungen des aktuellen Turniers ändern (z. B. Anmeldung öffnen/schließen, Startzeit, Maps)."""
    M = _M()
    d = M.tour.load()
    if d.get("status") == "running" and (data.mode or data.maps):
        raise HTTPException(409, "Modus und Maps lassen sich während des Turniers nicht ändern")
    _tour_apply(M, d, data)
    if d["matches"] and d["status"] != "done":
        M.tour.plan(d)
    M.tour.save(d)
    return {"ok": True, "tournament": {k: d.get(k) for k in ("name", "mode", "start", "registration", "maps", "match_min", "pause_min", "status")}}


# ---------------------------------------------------------------- Benutzerkonten von der Homepage (Recht „users“)
class UserSyncIn(BaseModel):
    external_id: str = Field(min_length=1, max_length=64, pattern=r"^[\w.@:+-]+$", description="eindeutige Nutzer-ID der Homepage")
    username: str | None = Field(None, max_length=32, description="gewünschter Benutzername (a–z, 0–9, . _ -), sonst aus nick")
    nick: str | None = Field(None, max_length=64, description="Anzeigename / Nickname")
    email: str | None = Field(None, max_length=120, pattern=r"^$|^[^@\s]+@[^@\s]+\.[^@\s]+$")
    steamid: str | None = Field(None, pattern=r"^$|^\d{17}$", description="SteamID64 – damit klappt auch „Mit Steam anmelden“")
    avatar: str | None = Field(None, max_length=300, pattern=r"^$|^https://")
    password: str | None = Field(None, min_length=8, max_length=128, description="optional: Login mit Benutzername + Passwort")
    note: str | None = Field(None, max_length=80)


class UserBulkIn(BaseModel):
    users: list[UserSyncIn] = Field(max_length=500)


def _user_out(M, u: dict, created: bool | None = None) -> dict:
    out = {"external_id": u.get("external_id"), "username": u["username"], "nick": u.get("nick"), "email": u.get("email"),
           "steamid": u.get("steamid"), "public_only": M.users.public_only(u), "profiles": M.users.user_profiles(u),
           "role": u.get("role"), "created_at": u.get("created"), "last_login": u.get("last_login")}
    if created is not None:
        out["created"] = created
    return out


def _sync_user(M, data: UserSyncIn) -> dict:
    try:
        u, created = M.users.upsert_external(data.model_dump())
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(409, str(e))
    if data.steamid:                                          # Spieler-Eintrag (Name, Bild, Admin je Spiel) verknüpfen
        p = M.playerdb.get(data.steamid)
        if p is None:
            p = M.playerdb.add_manual(data.steamid, data.nick or "", data.avatar or "")
        if not p.get("user") or not M.users.find(p["user"]):
            M.playerdb.update(p["id"], {"user": u["username"]})
    return _user_out(M, u, created)


@router.post("/users", dependencies=[Depends(auth("users"))])
async def v1_user_sync(data: UserSyncIn):
    """Konto anlegen oder aktualisieren. Neue Konten sehen nur die öffentliche Seite, bis ein Admin Rechte vergibt."""
    return _sync_user(_M(), data)


@router.post("/users/bulk", dependencies=[Depends(auth("users"))])
async def v1_user_bulk(data: UserBulkIn):
    """Viele Konten auf einmal (max. 500) – Fehler einzelner Einträge brechen den Rest nicht ab."""
    M, res = _M(), []
    for x in data.users:
        try:
            res.append({"ok": True, **_sync_user(M, x)})
        except HTTPException as e:
            res.append({"ok": False, "external_id": x.external_id, "error": e.detail})
    return {"results": res, "created": sum(1 for r in res if r.get("created")), "failed": sum(1 for r in res if not r["ok"])}


@router.get("/users/{external_id}", dependencies=[Depends(auth("users"))])
async def v1_user_get(external_id: str):
    M = _M()
    u = M.users.find_external(external_id)
    if not u or u.get("source") != "homepage":
        raise HTTPException(404, "Kein über die Homepage angelegtes Konto mit dieser external_id")
    return _user_out(M, u)


@router.delete("/users/{external_id}", dependencies=[Depends(auth("users"))])
async def v1_user_delete(external_id: str):
    """Konto löschen (z. B. wenn es auf der Homepage gelöscht wurde). Administratoren sind geschützt."""
    M = _M()
    try:
        name = M.users.delete_external(external_id)
    except ValueError as e:
        raise HTTPException(403, str(e))
    if not name:
        raise HTTPException(404, "Kein Konto mit dieser external_id")
    for p in M.playerdb.all_players():
        if p.get("user") == name:
            M.playerdb.update(p["id"], {"user": ""})
    return {"ok": True, "username": name}


# ---------------------------------------------------------------- Turnier von der Homepage übernehmen + Ergebnisse
class ImportPlayer(BaseModel):
    steamid: str = Field(pattern=SID)
    name: str | None = Field(None, max_length=40)
    avatar: str | None = Field(None, max_length=300, pattern=r"^$|^https://")


class ImportTeam(BaseModel):
    external_id: str = Field(min_length=1, max_length=64, pattern=r"^[\w.@:+-]+$")
    name: str = Field(min_length=1, max_length=24)
    players: list[ImportPlayer] = Field(min_length=1, max_length=10)


class TourImportIn(TourSetIn):
    external_id: str = Field(min_length=1, max_length=64, pattern=r"^[\w.@:+-]+$", description="Turnier-ID der Homepage")
    teams: list[ImportTeam] = Field(max_length=128)
    seeding: str = Field("random", pattern="^(random|given)$", description="given = Reihenfolge der Teams ist die Setzliste")
    generate: bool = Field(True, description="Spielplan sofort erzeugen")


@router.put("/tournament/import", dependencies=[Depends(auth("organize"))])
async def v1_tour_import(data: TourImportIn):
    """Turnier mit Teams von der Homepage übernehmen (anlegen oder – solange noch nicht gespielt wird – ersetzen).
    Anmeldung und Teams verwaltet die Homepage; gespielt, gewertet und gestartet wird im Spielservermanager."""
    M = _M()
    d = M.tour.load()
    if M._tour_busy(d) or M._tour_test(d):
        raise HTTPException(409, "Das aktuelle Turnier läuft – erst im Spielservermanager anhalten")
    same = d.get("external_id") == data.external_id
    played = [m for m in d.get("matches") or [] if m.get("status") == "live" or (m.get("status") == "done" and m.get("s1") is not None)]
    if same and played:
        raise HTTPException(409, "In diesem Turnier wurde schon gespielt – Teams und Spielplan lassen sich nicht mehr ersetzen")
    if not same:
        if M._tour_has_content(d):
            M.tour.lib_save(d)
        d = M.tour.new_from(None)
        d["name"] = data.name or f"{M.automation.brand()} Turnier"
    sids = [p.steamid for t in data.teams for p in t.players]
    if len(sids) != len(set(sids)):
        raise HTTPException(400, "Ein Spieler steht in mehreren Teams")
    names = [t.name.strip().lower() for t in data.teams]
    if len(names) != len(set(names)):
        raise HTTPException(400, "Teamnamen müssen eindeutig sein")
    if len({t.external_id for t in data.teams}) != len(data.teams):
        raise HTTPException(400, "external_id der Teams muss eindeutig sein")
    _tour_apply(M, d, data)
    keep = {t.get("ext_id"): t["id"] for t in d.get("teams") or [] if t.get("ext_id")}
    d["teams"], d["players"] = [], []
    for t in data.teams:
        d["teams"].append({"id": keep.get(t.external_id) or M.tour.new_team_id(), "ext_id": t.external_id,
                           "name": re.sub(r'["\\;]', "", t.name).strip()[:24], "players": [p.steamid for p in t.players]})
        for p in t.players:
            pl = M.playerdb.get(p.steamid) or M.playerdb.add_manual(p.steamid, p.name or "", p.avatar or "")
            d["players"].append({"steamid": p.steamid, "name": (p.name or M.playerdb.display(pl) or p.steamid).strip()[:40],
                                 "avatar": p.avatar or pl.get("avatar"), "t": time.time(), "via": "homepage"})
    d.update(external_id=data.external_id, via="homepage", registration=False, status="setup")
    d["matches"], d["groups"] = [], {}
    if data.generate and len(d["teams"]) >= 2:
        try:
            M.tour.generate(d, shuffle=data.seeding == "random")
        except ValueError as e:
            raise HTTPException(400, str(e))
        d["servers"] = [s["id"] for s in M._tour_pool()]
        M.tour.plan(d)
    M._tour_names.clear()
    M.tour.save(d)
    return {"ok": True, "external_id": d["external_id"], "name": d["name"], "teams": len(d["teams"]),
            "matches": len(d["matches"]), "servers_needed": M.tour.needed_servers(d) if d["matches"] else 0,
            "team_ids": {t["ext_id"]: t["id"] for t in d["teams"]}}


def _champion(d: dict, M) -> str | None:
    if d.get("status") != "done" or not d.get("matches"):
        return None
    if d.get("mode") == "rr":
        tab = M.tour.rr_table(d)
        return tab[0]["team"] if tab else None
    ko = [m for m in d["matches"] if m["stage"] in ("W", "K", "F")]
    last = max(ko, key=lambda m: (m["stage"] == "F", m["round"])) if ko else None
    return (last or {}).get("winner")


@router.get("/tournament/results", dependencies=[Depends(auth("tournament", read=True))])
async def v1_tour_results():
    """Alle Ergebnisse für die eigene Darstellung auf der Homepage: Spiele mit Teams (inkl. external_id), Stand, Sieger,
    Spielerwerte je Match, Gruppentabellen, Bestenliste und Turniersieger."""
    M = _M()
    d = M.tour.load()
    v = M._tour_out(d)
    ext = {t["id"]: t.get("ext_id") for t in d["teams"]}

    def team(tid):
        if not tid:
            return None
        if tid == M.tour.BYE:
            return {"id": None, "external_id": None, "name": "Freilos", "bye": True}
        return {"id": tid, "external_id": ext.get(tid), "name": M.tour.team_name(d, tid)}

    raw = {m["id"]: m for m in d["matches"]}
    matches = []
    for m in v["matches"]:
        r = raw.get(m["id"]) or {}
        matches.append({"id": m["id"], "no": m.get("no"), "stage": m["stage"], "round": m["round"], "label": m["label"],
                        "group": m.get("group"), "team1": team(r.get("t1")), "team2": team(r.get("t2")),
                        "placeholder1": m.get("p1"), "placeholder2": m.get("p2"), "score1": m.get("s1"), "score2": m.get("s2"),
                        "status": m["status"], "winner": team(r.get("winner")), "walkover": bool(m.get("walkover")),
                        "map": m.get("map"), "planned": m.get("planned"), "started": m.get("started"), "ended": m.get("ended"),
                        "server": m.get("server_name"), "tv_url": m.get("tv_url"), "stats": r.get("stats") or []})
    groups = {g: [{**row, "team": team(row["team"])} for row in rows] for g, rows in (v.get("groups") or {}).items()}
    out = {"external_id": d.get("external_id"), "name": d.get("name"), "mode": d.get("mode"), "status": d.get("status"),
           "start": d.get("start"), "updated": time.time(),
           "teams": [{"id": t["id"], "external_id": t.get("ext_id"), "name": t["name"], "players": t["players"]} for t in d["teams"]],
           "matches": matches, "groups": groups, "leaders": v.get("leaders") or [], "champion": team(_champion(d, M))}
    if v.get("table"):
        out["table"] = [{**row, "team": team(row["team"])} for row in v["table"]]
    return out

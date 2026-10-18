"""Steam-Gameserver-Tokens (GSLT) speichern, bei Steam abfragen/anlegen und Servern zuordnen.

Mit einem Steam-Web-API-Schlüssel (steamcommunity.com/dev/apikey) nutzt das Tool den Dienst IGameServersService:
GetAccountList (alle Tokens des Kontos), CreateAccount (neuen Token anlegen), ResetLoginToken (abgelaufenen erneuern).
Ohne Schlüssel lassen sich Tokens von Hand eintragen. Gespeichert wird alles in /data/gslt.json (nur für Admins sichtbar).
"""
import secrets
import time

import httpx

from . import store

FILE = "gslt.json"
API = "https://api.steampowered.com/IGameServersService"
APPS = {"cs2": 730, "tf2": 440}
APP_LABEL = {730: "CS2", 440: "TF2"}


class GsltError(Exception):
    pass


def _load() -> dict:
    d = store.load(FILE, {})
    d.setdefault("key", "")
    d.setdefault("tokens", [])
    return d


def _save(d: dict) -> None:
    store.save(FILE, d)


def has_key() -> bool:
    return bool(_load()["key"])


def set_key(key: str) -> None:
    d = _load()
    d["key"] = (key or "").strip()
    _save(d)


def tokens() -> list[dict]:
    return _load()["tokens"]


def public_list() -> list[dict]:
    """Für die Oberfläche: Token nur gekürzt."""
    out = []
    for t in tokens():
        tok = t.get("token") or ""
        out.append({**{k: t.get(k) for k in ("steamid", "appid", "memo", "assigned", "expired", "deleted", "last_logon", "source")},
                    "id": t.get("id") or t.get("steamid"),
                    "token_short": (tok[:4] + "…" + tok[-4:]) if len(tok) > 10 else tok, "app": APP_LABEL.get(t.get("appid"), str(t.get("appid")))})
    return out


def _upsert(entry: dict) -> None:
    d = _load()
    for t in d["tokens"]:
        if (entry.get("steamid") and t.get("steamid") == entry["steamid"]) or (entry.get("token") and t.get("token") == entry["token"]):
            t.update({k: v for k, v in entry.items() if v is not None})
            _save(d)
            return
    entry.setdefault("id", entry.get("steamid") or secrets.token_hex(6))
    d["tokens"].append(entry)
    _save(d)


def add_manual(token: str, appid: int, memo: str = "") -> None:
    token = (token or "").strip()
    if len(token) < 20 or not token.isalnum():
        raise GsltError("Das sieht nicht nach einem Steam-Token aus (32 Zeichen, nur Buchstaben/Ziffern)")
    _upsert({"token": token, "appid": int(appid), "memo": memo, "source": "manuell", "expired": False})


async def _call(method: str, verb: str = "GET", **params) -> dict:
    key = _load()["key"]
    if not key:
        raise GsltError("Kein Steam-Web-API-Schlüssel hinterlegt")
    try:
        async with httpx.AsyncClient(timeout=15) as cl:
            if verb == "GET":
                r = await cl.get(f"{API}/{method}/v1/", params={"key": key, **params})
            else:
                r = await cl.post(f"{API}/{method}/v1/", data={"key": key, **params})
    except httpx.HTTPError as e:
        raise GsltError(f"Steam nicht erreichbar ({e.__class__.__name__})") from e
    if r.status_code in (401, 403):
        raise GsltError("Steam lehnt den API-Schlüssel ab (falsch oder Konto ohne Berechtigung)")
    if r.status_code >= 400:
        raise GsltError(f"Steam-Fehler {r.status_code}")
    try:
        return r.json().get("response") or {}
    except ValueError as e:
        raise GsltError("Unerwartete Antwort von Steam") from e


async def sync() -> int:
    """Alle Tokens des Kontos von Steam holen."""
    resp = await _call("GetAccountList")
    n = 0
    for sv in resp.get("servers") or []:
        _upsert({"steamid": sv.get("steamid"), "appid": sv.get("appid"), "token": sv.get("login_token"), "memo": sv.get("memo") or "",
                 "expired": bool(sv.get("is_expired")), "deleted": bool(sv.get("is_deleted")), "last_logon": sv.get("rt_last_logon"),
                 "source": "steam"})
        n += 1
    d = _load()
    d["synced"] = time.time()
    _save(d)
    return n


async def create(appid: int, memo: str) -> dict:
    resp = await _call("CreateAccount", "POST", appid=int(appid), memo=memo[:32])
    if not resp.get("login_token"):
        raise GsltError("Steam hat keinen Token geliefert (Konto braucht das Spiel, eine Telefonnummer und darf max. 1000 Tokens haben)")
    e = {"steamid": resp.get("steamid"), "appid": int(appid), "token": resp["login_token"], "memo": memo, "expired": False, "source": "steam"}
    _upsert(e)
    return e


async def renew(steamid: str) -> dict:
    resp = await _call("ResetLoginToken", "POST", steamid=steamid)
    if not resp.get("login_token"):
        raise GsltError("Steam hat den Token nicht erneuert")
    _upsert({"steamid": steamid, "token": resp["login_token"], "expired": False})
    return next(t for t in tokens() if t.get("steamid") == steamid)


def assign(token: str, target: str | None) -> None:
    d = _load()
    for t in d["tokens"]:
        if t.get("token") == token:
            t["assigned"] = target
        elif target and t.get("assigned") == target:
            t["assigned"] = None
    _save(d)


def free_token(appid: int, used: set[str]) -> dict | None:
    for t in tokens():
        if t.get("appid") == appid and not t.get("expired") and not t.get("deleted") and t.get("token") \
                and t["token"] not in used and not t.get("assigned"):
            return t
    return None


async def get_or_create(appid: int, memo: str, used: set[str]) -> dict | None:
    """Freien Token nehmen – sonst (mit API-Schlüssel) bei Steam einen neuen anlegen."""
    t = free_token(appid, used)
    if t:
        return t
    if has_key():
        try:
            await sync()
        except GsltError:
            pass
        t = free_token(appid, used)
        if t:
            return t
        return await create(appid, memo)
    return None


def remove(token_or_steamid: str) -> None:
    d = _load()
    d["tokens"] = [t for t in d["tokens"] if token_or_steamid not in (t.get("id"), t.get("steamid"))]
    _save(d)

"""Spieler-Datenbank: jeder, der jemals auf einem Server war – automatisch aus Server-Logs, Status und TeamSpeak.

Quellen
- CS2/TF2/Source (Container-Log):  "Name<2><[U:1:123]><>" connected, address "1.2.3.4:27005"  -> SteamID, Name, IP
- Minecraft (Container-Log):       Name[/1.2.3.4:5678] logged in with entity id …        -> Name, IP
- Valheim (Container-Log):         Got connection SteamID 7656…  /  Got character ZDOID from Name : …
- TeamSpeak (ServerQuery):         Nickname, eindeutige ID, IP                             -> TS-Name über die IP zugeordnet
- alle anderen Spiele:             Namen aus dem Status

IP-Adressen: je Spieler wird eine lokale (LAN) und eine öffentliche IP gespeichert – beide werden mit der neuesten
Sichtung aktualisiert. Anzeigename: eigener Nickname > TeamSpeak-Name > zuletzt gesehener Spielname > SteamID.
Gespeichert in /data/players.json (gleiche Datei wie die manuell gepflegten Spieler).
"""
import ipaddress
import re
import time

from . import store

FILE = "players.json"
STEAMID64_BASE = 76561197960265728
_cache: list | None = None
_dirty = {"v": False, "t": 0.0}


def _load() -> list[dict]:
    global _cache
    if _cache is None:
        _cache = store.load(FILE, [])
        for p in _cache:                         # alte, von Hand angelegte Einträge: Name = Nickname
            if "id" not in p:
                p["id"] = p.get("steamid") or f"n:{p.get('name', '')}"
                if not p.get("auto") and p.get("name") and "nick" not in p:
                    p["nick"] = p["name"]
    return _cache


def all_players() -> list[dict]:
    return _load()


def save(force: bool = False) -> None:
    if _dirty["v"] and (force or time.time() - _dirty["t"] > 20):
        store.save(FILE, _load())
        _dirty.update(v=False, t=time.time())


def _mark():
    _dirty["v"] = True


def is_private(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip)
        return a.is_private or a.is_loopback or a.is_link_local
    except ValueError:
        return False


def _ip_only(addr: str | None) -> str:
    a = (addr or "").strip()
    if not a or a.lower() in ("loopback", "bot"):
        return ""
    if a.count(":") == 1:          # IPv4:Port
        a = a.split(":")[0]
    a = a.strip("[]/")
    try:
        ipaddress.ip_address(a)
        return a
    except ValueError:
        return ""


def display(p: dict) -> str:
    return p.get("nick") or p.get("ts_name") or (p.get("names") or [None])[-1] or p.get("steamid") or p.get("id")


def _refresh_name(p: dict) -> None:
    n = display(p)
    if n and p.get("name") != n:
        p["name"] = n


def _find(steamid: str = "", name: str = "", ip: str = "", ts_uid: str = "", game: str = "") -> dict | None:
    lst = _load()
    if steamid:
        hit = next((p for p in lst if p.get("steamid") == steamid), None)
        if hit:
            return hit
    if ts_uid:
        hit = next((p for p in lst if p.get("ts_uid") == ts_uid), None)
        if hit:
            return hit
    if ip and is_private(ip):        # LAN-IP ist pro Person eindeutig genug
        cand = [p for p in lst if p.get("lan_ip") == ip]
        if len(cand) == 1:
            return cand[0]
        if cand and name:
            hit = next((p for p in cand if name in (p.get("names") or []) or name == p.get("ts_name")), None)
            if hit:
                return hit
        if cand:
            return max(cand, key=lambda p: p.get("last_seen") or 0)
    if name:
        low = name.lower()
        cand = [p for p in lst if low in [x.lower() for x in (p.get("names") or [])] or low == (p.get("nick") or "").lower()
                or low == (p.get("ts_name") or "").lower()]
        if ip and not is_private(ip):
            same = [p for p in cand if p.get("wan_ip") == ip]
            if same:
                return same[0]
        if len(cand) == 1:
            return cand[0]
        if cand and game:
            hit = next((p for p in cand if game in (p.get("games") or [])), None)
            if hit:
                return hit
        if cand:
            return cand[0]
    return None


def seen(*, steamid: str = "", name: str = "", ip: str = "", sid: str = "", server: str = "", game: str = "",
         ts_uid: str = "", ts_name: str = "", t: float | None = None) -> dict | None:
    """Sichtung eintragen (legt den Spieler bei Bedarf an)."""
    name = (name or "").strip()[:64]
    if name in ("", "?", "(verbindet …)", "(lädt …)") and not steamid and not ts_uid:
        return None
    ip = _ip_only(ip)
    t = t or time.time()
    p = _find(steamid, "" if ts_uid else name, ip, ts_uid, game)
    if p is not None and ((steamid and p.get("steamid") and p["steamid"] != steamid)
                          or (ts_uid and p.get("ts_uid") and p["ts_uid"] != ts_uid)):
        p = None                                     # andere Person mit gleicher IP/Name
    if p is None:
        pid = steamid or (f"ts:{ts_uid}" if ts_uid else f"n:{game}:{name}")
        p = {"id": re.sub(r"[/\\?#%]", "_", pid), "steamid": steamid or "", "names": [],
             "first_seen": t, "added": int(t), "auto": True, "servers": {}, "games": []}
        _load().append(p)
    if steamid and not p.get("steamid"):
        p["steamid"] = steamid
        p["id"] = steamid
    if ts_uid:
        p["ts_uid"] = ts_uid
        if ts_name:
            p["ts_name"] = ts_name[:64]
    elif name:
        names = [x for x in (p.get("names") or []) if x != name] + [name]
        p["names"] = names[-8:]
    if ip:
        p["lan_ip" if is_private(ip) else "wan_ip"] = ip
    if sid:
        p.setdefault("servers", {})[sid] = {"name": server, "game": game, "last": t}
    if game and game not in (p.get("games") or []):
        p["games"] = (p.get("games") or []) + [game]
    p["last_seen"] = max(t, p.get("last_seen") or 0)
    p.setdefault("first_seen", t)
    _refresh_name(p)
    _mark()
    return p


def link_ts(ts_uid: str, ts_name: str, ip: str, t: float | None = None) -> None:
    """TeamSpeak-Client: über die IP einem Spieler zuordnen, sonst eigener Eintrag."""
    ip = _ip_only(ip)
    lst = _load()
    target = next((p for p in lst if p.get("ts_uid") == ts_uid), None)
    if target is None and ip:
        if is_private(ip):
            cand = [p for p in lst if p.get("lan_ip") == ip and not p.get("ts_uid")]
        else:
            cand = [p for p in lst if p.get("wan_ip") == ip and not p.get("ts_uid")]
        if len(cand) == 1:
            target = cand[0]
    if target is not None:
        target["ts_uid"], target["ts_name"] = ts_uid, ts_name[:64]
        if ip:
            target["lan_ip" if is_private(ip) else "wan_ip"] = ip
        target["last_seen"] = max(t or time.time(), target.get("last_seen") or 0)
        _refresh_name(target)
        _mark()
    else:
        seen(ts_uid=ts_uid, ts_name=ts_name, ip=ip, t=t)


def merge(keep_id: str, other_id: str) -> None:
    lst = _load()
    a = next((p for p in lst if p["id"] == keep_id), None)
    b = next((p for p in lst if p["id"] == other_id), None)
    if not a or not b or a is b:
        raise ValueError("Spieler nicht gefunden")
    for k in ("steamid", "ts_uid", "ts_name", "lan_ip", "wan_ip", "avatar", "nick"):
        if not a.get(k) and b.get(k):
            a[k] = b[k]
    a["names"] = list(dict.fromkeys((a.get("names") or []) + (b.get("names") or [])))[-8:]
    a["games"] = list(dict.fromkeys((a.get("games") or []) + (b.get("games") or [])))
    a["servers"] = {**(b.get("servers") or {}), **(a.get("servers") or {})}
    a["first_seen"] = min(x for x in (a.get("first_seen"), b.get("first_seen"), time.time()) if x)
    a["last_seen"] = max(a.get("last_seen") or 0, b.get("last_seen") or 0)
    if a.get("steamid"):
        a["id"] = a["steamid"]
    lst.remove(b)
    _refresh_name(a)
    _mark()
    save(True)


def set_nick(pid: str, nick: str) -> dict:
    p = next((x for x in _load() if x["id"] == pid or x.get("steamid") == pid), None)
    if not p:
        raise ValueError("Spieler nicht gefunden")
    p["nick"] = nick.strip()[:64]
    _refresh_name(p)
    _mark()
    save(True)
    return p


def remove(pid: str) -> None:
    global _cache
    _cache = [x for x in _load() if x["id"] != pid and x.get("steamid") != pid]
    _mark()
    save(True)


def add_manual(steamid: str, name: str, avatar: str) -> dict:
    p = next((x for x in _load() if x.get("steamid") == steamid), None)
    if p is None:
        p = {"id": steamid, "steamid": steamid, "names": [], "added": int(time.time()), "servers": {}, "games": []}
        _load().append(p)
    if name:
        p["nick"] = name
    if avatar:
        p["avatar"] = avatar
    _refresh_name(p)
    _mark()
    save(True)
    return p


# ---------------------------------------------------------------- Log-Auswertung
RE_SRC_CONNECT = re.compile(r'"(.{1,64}?)<\d+><(\[U:1:\d+\]|STEAM_[0-5]:[01]:\d+|7656119\d{10})><[^>]*>" connected, address "([^"]*)"')
RE_SRC_ENTERED = re.compile(r'"(.{1,64}?)<\d+><(\[U:1:\d+\]|STEAM_[0-5]:[01]:\d+)><[^>]*>" (?:entered the game|STEAM USERID validated)')
RE_MC_LOGIN = re.compile(r"\]: ([A-Za-z0-9_]{2,16})\[/([0-9a-fA-F.:]+):\d+\] logged in")
RE_VH_STEAM = re.compile(r"Got connection SteamID (7656119\d{10})")
RE_VH_CHAR = re.compile(r"Got character ZDOID from (.{1,40}?) : ")


def _sid64(raw: str) -> str:
    m = re.match(r"\[U:1:(\d+)\]", raw)
    if m:
        return str(STEAMID64_BASE + int(m.group(1)))
    m = re.match(r"STEAM_[0-5]:([01]):(\d+)", raw)
    if m:
        return str(STEAMID64_BASE + int(m.group(2)) * 2 + int(m.group(1)))
    return raw if raw.startswith("7656119") else ""


def parse_log(text: str, game: str, sid: str, server: str) -> int:
    n = 0
    last_vh = ""
    for line in text.splitlines():
        if game == "minecraft":
            m = RE_MC_LOGIN.search(line)
            if m:
                seen(name=m.group(1), ip=m.group(2), sid=sid, server=server, game=game)
                n += 1
            continue
        if game == "valheim":
            m = RE_VH_STEAM.search(line)
            if m:
                last_vh = m.group(1)
                seen(steamid=last_vh, sid=sid, server=server, game=game)
                n += 1
                continue
            m = RE_VH_CHAR.search(line)
            if m and last_vh:
                seen(steamid=last_vh, name=m.group(1), sid=sid, server=server, game=game)
            continue
        m = RE_SRC_CONNECT.search(line)
        if m:
            st = _sid64(m.group(2))
            if st:
                seen(steamid=st, name=m.group(1), ip=m.group(3), sid=sid, server=server, game=game)
                n += 1
            continue
        m = RE_SRC_ENTERED.search(line)
        if m:
            st = _sid64(m.group(2))
            if st:
                seen(steamid=st, name=m.group(1), sid=sid, server=server, game=game)
                n += 1
    return n


def online_index(servers: list[dict], states: dict, game_of) -> dict[str, list[dict]]:
    """Spieler-ID -> Liste der Server, auf denen er gerade ist (aus dem aktuellen Status)."""
    out: dict[str, list[dict]] = {}
    for s in servers:
        st = states.get(s["id"]) or {}
        if not st.get("online"):
            continue
        g = game_of(s)
        for pl in st.get("players") or []:
            if not isinstance(pl, dict) or pl.get("bot"):
                continue
            if g == "teamspeak":
                p = _find(ts_uid=pl.get("uid") or "", name="" if pl.get("uid") else pl.get("name") or "")
            else:
                p = _find(name=pl.get("name") or "", ip=_ip_only(pl.get("address")), game=g)
            if p:
                out.setdefault(p["id"], []).append({"sid": s["id"], "server": st.get("hostname") or s.get("name"), "game": g})
    return out

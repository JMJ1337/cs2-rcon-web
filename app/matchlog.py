"""Letzte Matches von MatchZy (Remote-Log): MatchZy schickt Ereignisse per HTTP an das Tool.

CS2-Server bekommen per RCON: matchzy_remote_log_url "<tool>/api/matchzy/events/<server>" sowie einen geheimen Header.
Ausgewertet werden series_start, going_live, round_end, map_result und series_end (Get5-kompatibles Format):
Teams, Spielstand, Map und Spielerwerte (Kills/Tode/Assists/Schaden) – gespeichert in /data/matchlog.json (die letzten 40).
"""
import hashlib
import hmac
import time

from . import store

FILE = "matchlog.json"
KEEP = 40


def secret(sid: str, key: bytes) -> str:
    return hmac.new(key, f"matchzy:{sid}".encode(), hashlib.sha256).hexdigest()[:32]


def _load() -> list[dict]:
    return store.load(FILE, [])


def _players(team: dict) -> list[dict]:
    out = []
    for p in (team or {}).get("players") or []:
        st = p.get("stats") or {}
        out.append({"name": p.get("name") or "?", "kills": st.get("kills"), "deaths": st.get("deaths"),
                    "assists": st.get("assists"), "damage": st.get("damage"), "mvp": st.get("mvp"),
                    "hs": st.get("headshot_kills")})
    out.sort(key=lambda x: -(x["kills"] or 0))
    return out


def ingest(sid: str, server_name: str, ev: dict) -> None:
    name = (ev.get("event") or "").lower()
    if not name:
        return
    mid = str(ev.get("matchid") or ev.get("match_id") or "")
    lst = _load()
    m = next((x for x in lst if x["sid"] == sid and x["matchid"] == mid and not x.get("finished")), None) if mid else None
    if m is None and name in ("series_start", "going_live", "round_end", "map_result"):
        m = {"sid": sid, "server": server_name, "matchid": mid or str(int(time.time())), "started": time.time(),
             "team1": {"name": "Team 1", "score": 0, "players": []}, "team2": {"name": "Team 2", "score": 0, "players": []},
             "maps": [], "map": None, "finished": False, "live": False}
        lst.append(m)
    if m is None:
        return
    m["updated"] = time.time()
    for k in ("team1", "team2"):
        t = ev.get(k)
        if isinstance(t, dict):
            if t.get("name"):
                m[k]["name"] = t["name"]
            if t.get("score") is not None:
                m[k]["score"] = t["score"]
            pl = _players(t)
            if pl:
                m[k]["players"] = pl
    if ev.get("map_name"):
        m["map"] = ev["map_name"]
    if name == "going_live":
        m["live"] = True
    if name == "map_result":
        m["maps"].append({"map": ev.get("map_name") or m.get("map"), "t1": (ev.get("team1") or {}).get("score"),
                          "t2": (ev.get("team2") or {}).get("score"), "winner": (ev.get("winner") or {}).get("team")})
    if name == "series_end":
        m["finished"] = True
        m["live"] = False
        m["ended"] = time.time()
        if ev.get("team1_series_score") is not None:
            m["series"] = [ev.get("team1_series_score"), ev.get("team2_series_score")]
    store.save(FILE, lst[-KEEP:])


def recent(sid: str | None = None, n: int = 5) -> list[dict]:
    lst = [x for x in _load() if sid is None or x["sid"] == sid]
    lst.sort(key=lambda x: -(x.get("updated") or x.get("started") or 0))
    return lst[:n]


# ---------------------------------------------------------------- Matches aus dem Server-Log (logaddress_add_http)
# Funktioniert auch ohne MatchZy-Match: jede Map von Match-Start bis „Game Over“ wird mit Spielstand und K/D/A gespeichert.
import re as _re

_live: dict[str, dict] = {}
_P = r'"(?P<{n}>.{{1,64}}?)<\d+><(?P<{n}id>\[U:1:\d+\]|BOT|STEAM_[0-5]:[01]:\d+)><(?P<{n}team>[A-Za-z]*)>"'
RE_KILL = _re.compile(_P.format(n="a") + r" \[[^\]]*\] killed " + _P.format(n="v") + r".*?with \"(?P<w>[^\"]+)\"(?P<hs>.*headshot)?")
RE_ASSIST = _re.compile(_P.format(n="a") + r" assisted killing " + _P.format(n="v"))
RE_START = _re.compile(r'World triggered "Match_Start" on "(?P<map>[^"]+)"')
RE_SCORE = _re.compile(r'Team "(?P<t>CT|TERRORIST)" scored "(?P<s>\d+)" with "\d+" players')
RE_OVER = _re.compile(r'Game Over: \S+ \S+ (?P<map>\S+) score (?P<a>\d+):(?P<b>\d+) after (?P<min>\d+) min')
RE_SWITCH = _re.compile(_P.format(n="a") + r' (?:switched from team <\w+> to <(?P<to>\w+)>|joined team "(?P<to2>\w+)")')
TEAM_NAME = {"CT": "Counter-Terroristen", "TERRORIST": "Terroristen"}


def _pl(m: dict, key: str, name: str, team: str) -> dict:
    p = m["pl"].setdefault(key, {"name": name, "kills": 0, "deaths": 0, "assists": 0, "hs": 0, "team": team})
    p["name"] = name
    if team in ("CT", "TERRORIST"):
        p["team"] = team
    return p


def _save_live(sid: str, server_name: str, m: dict, finished: bool) -> None:
    lst = _load()
    teams = {}
    for t in ("CT", "TERRORIST"):
        pls = sorted(({k: v for k, v in p.items() if k != "team"} for p in m["pl"].values() if p.get("team") == t),
                     key=lambda x: -x["kills"])
        teams[t] = {"name": TEAM_NAME[t], "score": m["score"].get(t, 0), "players": pls}
    entry = {"sid": sid, "server": server_name, "matchid": m["id"], "started": m["started"], "updated": time.time(),
             "team1": teams["CT"], "team2": teams["TERRORIST"], "maps": [], "map": m["map"], "finished": finished,
             "live": not finished, "source": "log"}
    if finished:
        entry["ended"] = time.time()
    lst = [x for x in lst if not (x["sid"] == sid and x.get("matchid") == m["id"])]
    # Läuft parallel ein MatchZy-Match auf dem Server, hat das Vorrang (dort gibt es echte Teamnamen)
    if any(x["sid"] == sid and x.get("source") != "log" and abs((x.get("started") or 0) - m["started"]) < 1800 for x in lst):
        return
    lst.append(entry)
    store.save(FILE, lst[-KEEP:])


def ingest_log(sid: str, server_name: str, text: str) -> int:
    n = 0
    for line in text.splitlines():
        m = _live.get(sid)
        if (x := RE_START.search(line)):
            _live[sid] = {"id": f"log-{int(time.time())}", "map": x.group("map"), "started": time.time(), "pl": {}, "score": {}, "dirty": True}
            n += 1
            continue
        if not m:
            continue
        if (x := RE_KILL.search(line)):
            if x.group("aid") != "BOT":
                a = _pl(m, x.group("aid"), x.group("a"), x.group("ateam"))
                if x.group("ateam") != x.group("vteam"):
                    a["kills"] += 1
                    if x.group("hs"):
                        a["hs"] += 1
            if x.group("vid") != "BOT":
                _pl(m, x.group("vid"), x.group("v"), x.group("vteam"))["deaths"] += 1
            m["dirty"] = True
        elif (x := RE_ASSIST.search(line)):
            if x.group("aid") != "BOT":
                _pl(m, x.group("aid"), x.group("a"), x.group("ateam"))["assists"] += 1
        elif (x := RE_SCORE.search(line)):
            m["score"][x.group("t")] = int(x.group("s"))
            m["dirty"] = True
        elif (x := RE_SWITCH.search(line)):
            if x.group("aid") != "BOT":
                _pl(m, x.group("aid"), x.group("a"), x.group("to") or x.group("to2") or "")
        elif (x := RE_OVER.search(line)):
            if m["pl"]:
                _save_live(sid, server_name, m, True)
            _live.pop(sid, None)
            n += 1
            continue
    m = _live.get(sid)
    if m and m.get("dirty") and m["pl"]:
        _save_live(sid, server_name, m, False)
        m["dirty"] = False
    return n

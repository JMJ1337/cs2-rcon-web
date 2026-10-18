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

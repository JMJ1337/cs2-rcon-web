"""Hall of Fame: abgeschlossene Turniere (Sieger, Finalist, MVP) und ewige Spielerwertung über alle Turniere."""
import secrets
import time

from . import store
from . import tournament as tour

FILE = "hall_of_fame.json"


def load() -> list[dict]:
    return store.load(FILE, [])


def _final(d: dict) -> dict | None:
    done = [m for m in tour.ordered(d) if m["status"] == "done" and not m.get("walkover")]
    ko = [m for m in done if m["stage"] in ("W", "K", "F")]
    return (ko or done)[-1] if (ko or done) else None


def entry(d: dict) -> dict | None:
    """Eintrag für ein fertiges Turnier bauen (None, wenn es keinen Sieger gibt)."""
    def team(tid):
        t = tour.team(d, tid)
        if not t:
            return None
        return {"name": t["name"], "players": [{"steamid": None if tour.is_bot(x) else x, "name": tour._pname(d, x)} for x in t["players"]]}
    if d.get("mode") == "rr":
        tab = tour.rr_table(d)
        if not tab:
            return None
        win, second = tab[0]["team"], (tab[1]["team"] if len(tab) > 1 else None)
        final = None
    else:
        final = _final(d)
        if not final or not final.get("winner"):
            return None
        win = final["winner"]
        second = final["t2"] if final["t1"] == win else final["t1"]
    lead = tour.leaderboard(d)
    mvp = next((r for r in lead if r.get("steamid")), lead[0] if lead else None)
    return {"id": secrets.token_hex(4), "name": d.get("name") or "Turnier", "date": d.get("start") or time.time(),
            "saved": time.time(), "mode": tour.MODES.get(d.get("mode"), d.get("mode")), "teams": len(d.get("teams") or []),
            "winner": team(win), "second": team(second) if second else None,
            "final": {"s1": final.get("s1"), "s2": final.get("s2"), "map": final.get("map"),
                      "t1": tour.team_name(d, final["t1"]), "t2": tour.team_name(d, final["t2"])} if final else None,
            "mvp": {k: mvp.get(k) for k in ("steamid", "name", "team", "rating", "kd", "kills", "adr")} if mvp else None,
            "players": [{k: r.get(k) for k in ("steamid", "name", "team", "rating", "kills", "deaths", "matches", "wins", "rounds")}
                        for r in lead]}


def add(d: dict) -> dict | None:
    e = entry(d)
    if not e:
        return None
    lst = load()
    lst.append(e)
    store.save(FILE, lst)
    return e


def delete(eid: str) -> None:
    store.save(FILE, [e for e in load() if e["id"] != eid])


def alltime(names: dict | None = None) -> list[dict]:
    """Ewige Tabelle: Titel, Finals, Turniere, Siege, Kills, Ø-Rating (gewichtet nach Runden) – nur echte Spieler."""
    tab: dict[str, dict] = {}
    for e in load():
        champs = {p["steamid"] for p in ((e.get("winner") or {}).get("players") or []) if p.get("steamid")}
        seconds = {p["steamid"] for p in ((e.get("second") or {}).get("players") or []) if p.get("steamid")}
        mvp = (e.get("mvp") or {}).get("steamid")
        for p in e.get("players") or []:
            sid = p.get("steamid")
            if not sid:
                continue
            r = tab.setdefault(sid, {"steamid": sid, "name": p.get("name"), "titles": 0, "finals": 0, "mvps": 0, "tournaments": 0,
                                     "matches": 0, "wins": 0, "kills": 0, "deaths": 0, "_rs": 0.0, "_rn": 0})
            r["name"] = (names or {}).get(sid) or p.get("name") or r["name"]
            r["tournaments"] += 1
            for k in ("matches", "wins", "kills", "deaths"):
                r[k] += p.get(k) or 0
            n = p.get("rounds") or 0
            if p.get("rating") is not None:
                r["_rs"] += (p["rating"] or 0) * max(1, n)
                r["_rn"] += max(1, n)
        for sid in champs:
            if sid in tab:
                tab[sid]["titles"] += 1
                tab[sid]["finals"] += 1
        for sid in seconds:
            if sid in tab:
                tab[sid]["finals"] += 1
        if mvp in tab:
            tab[mvp]["mvps"] += 1
    out = []
    for r in tab.values():
        r["rating"] = round(r.pop("_rs") / r["_rn"], 2) if r["_rn"] else None
        r.pop("_rn")
        r["kd"] = round(r["kills"] / max(1, r["deaths"]), 2)
        out.append(r)
    return sorted(out, key=lambda r: (-r["titles"], -r["finals"], -r["mvps"], -(r["rating"] or 0)))

"""CS2-Wingman-Turnier: Teams, Spielplan (K.-o., Doppel-K.-o., Gruppen + K.-o., Jeder gegen jeden), Zeitplan, Ergebnisse.

Reine Logik + Speicherung. Server, MatchZy und Steam-Bot hängt main.py daran.
Ein Match: {id, stage, round, label, t1, t2, src1, src2, winner, loser, s1, s2, status, server, planned, ...}
  t1/t2 = Team-ID, None (noch offen) oder "BYE" (Freilos)
  src = {"m": Match-ID, "r": "W"|"L"}  oder  {"g": Gruppe, "pos": Platz}
  status: wait (Gegner offen) · ready · live · done
"""
import itertools
import math
import random
import secrets
import time

from . import store

FILE = "tournament.json"
BYE = "BYE"
WINGMAN_MAPS = ["de_inferno", "de_nuke", "de_overpass", "de_vertigo"]
MODES = {"ko": "K.-o.-System", "double": "Doppel-K.-o.", "groups": "Gruppen + K.-o.", "rr": "Jeder gegen jeden"}

DEFAULTS = {"active": False, "name": "Groh LAN Wingman-Turnier", "mode": "groups", "start": None, "match_min": 35,
            "pause_min": 10, "maps": WINGMAN_MAPS, "status": "setup", "registration": True, "auto_servers": True,
            "invite": True, "par_qf": True, "par_sf": False, "players": [], "teams": [], "matches": [], "groups": {}, "servers": [], "created": None}


def load() -> dict:
    d = {**DEFAULTS, **store.load(FILE, {})}
    for k in ("players", "teams", "matches", "servers", "maps"):
        d[k] = list(d.get(k) or [])
    return d


def save(d: dict) -> dict:
    store.save(FILE, d)
    return d


def team(d: dict, tid):
    return next((t for t in d["teams"] if t["id"] == tid), None)


def team_name(d: dict, tid) -> str:
    if tid == BYE:
        return "Freilos"
    t = team(d, tid)
    return t["name"] if t else "?"


def player_team(d: dict, steamid: str):
    return next((t for t in d["teams"] if steamid in t["players"]), None)


# ---------------------------------------------------------------- Spielplan erzeugen
def _m(d: dict, stage: str, rnd: int, label: str, t1=None, t2=None, src1=None, src2=None, group=None) -> dict:
    m = {"id": f"m{len(d['matches']) + 1}", "stage": stage, "round": rnd, "label": label, "t1": t1, "t2": t2,
         "src1": src1, "src2": src2, "group": group, "winner": None, "loser": None, "s1": None, "s2": None,
         "status": "wait", "server": None, "planned": None, "started": None, "ended": None, "map": None}
    d["matches"].append(m)
    return m


def _seed_order(n: int) -> list[int]:
    """Setzliste für einen K.-o.-Baum der Größe n (1 gegen n, 2 gegen n-1 …, Beste treffen sich spät)."""
    order = [1]
    while len(order) < n:
        size = len(order) * 2
        order = list(itertools.chain.from_iterable((s, size + 1 - s) for s in order))
    return order


def _ko(d: dict, entrants: list, stage="W", label="K.-o.") -> list[dict]:
    """entrants: Team-IDs oder Quellen ({"g":..}). Gibt die Runden (Listen von Matches) zurück."""
    size = 1 << max(1, math.ceil(math.log2(max(2, len(entrants)))))
    seeds = list(entrants) + [BYE] * (size - len(entrants))
    order = _seed_order(size)
    slots = [seeds[i - 1] for i in order]
    rounds, prev = [], []
    names = {1: "Finale", 2: "Halbfinale", 4: "Viertelfinale", 8: "Achtelfinale"}
    r = 1
    while True:
        cur = []
        n_match = (len(slots) // 2) if r == 1 else len(prev) // 2
        rname = names.get(n_match, f"Runde {r}")
        for i in range(n_match):
            if r == 1:
                a, b = slots[2 * i], slots[2 * i + 1]
                kw = {}
                for k, v in (("1", a), ("2", b)):
                    if isinstance(v, dict):
                        kw["src" + k] = v
                    else:
                        kw["t" + k] = v
                cur.append(_m(d, stage, r, f"{label} · {rname}", **kw))
            else:
                cur.append(_m(d, stage, r, f"{label} · {rname}", src1={"m": prev[2 * i]["id"], "r": "W"},
                              src2={"m": prev[2 * i + 1]["id"], "r": "W"}))
        rounds.append(cur)
        prev = cur
        if n_match == 1:
            return rounds
        r += 1


def _rr_rounds(ids: list) -> list[list[tuple]]:
    """Jeder gegen jeden (Kreis-Verfahren)."""
    lst = list(ids) + ([None] if len(ids) % 2 else [])
    n = len(lst)
    out = []
    for r in range(n - 1):
        pairs = [(lst[i], lst[n - 1 - i]) for i in range(n // 2)]
        out.append([p for p in pairs if None not in p])
        lst = [lst[0]] + [lst[-1]] + lst[1:-1]
    return out


def generate(d: dict) -> dict:
    """Spielplan neu erzeugen (löscht alte Matches). Reihenfolge der Teams = Setzliste (zufällig gemischt)."""
    teams = [t["id"] for t in d["teams"] if len(t["players"]) == 2]
    if len(teams) < 2:
        raise ValueError("Mindestens 2 vollständige Teams (je 2 Spieler) nötig")
    random.shuffle(teams)
    d["matches"], d["groups"] = [], {}
    mode = d.get("mode") or "ko"
    if mode == "rr":
        for r, pairs in enumerate(_rr_rounds(teams), 1):
            for a, b in pairs:
                _m(d, "R", r, f"Runde {r}", a, b)
    elif mode == "groups":
        ng = max(1, round(len(teams) / 4)) if len(teams) >= 6 else 1
        if ng == 1:                               # zu wenige Teams für Gruppen -> eine Gruppe, die Top 2 ins Finale
            groups = {"A": teams}
        else:
            groups = {chr(65 + i): teams[i::ng] for i in range(ng)}
        d["groups"] = groups
        for g, ids in groups.items():
            for r, pairs in enumerate(_rr_rounds(ids), 1):
                for a, b in pairs:
                    _m(d, "G", r, f"Gruppe {g} · Runde {r}", a, b, group=g)
        adv = []
        gs = sorted(groups)
        if len(gs) == 1:
            adv = [{"g": "A", "pos": 1}, {"g": "A", "pos": 2}] + ([{"g": "A", "pos": 3}, {"g": "A", "pos": 4}] if len(teams) >= 5 else [])
        else:
            firsts = [{"g": g, "pos": 1} for g in gs]
            seconds = [{"g": g, "pos": 2} for g in reversed(gs)]
            adv = firsts + seconds
        rounds = _ko(d, adv, "K", "K.-o.")
        base = max([m["round"] for m in d["matches"] if m["stage"] == "G"] or [0])
        for rnd in rounds:
            for m in rnd:
                m["round"] += base
    elif mode == "double" and len(teams) >= 3:
        wb = _ko(d, teams, "W", "Winner")
        lb_prev = None
        lr = 1
        # Loser-Bracket: 1. Runde = Verlierer der WB-Runde 1 gegeneinander, danach abwechselnd
        losers = [{"m": m["id"], "r": "L"} for m in wb[0]]
        cur = [_m(d, "L", lr, f"Loser · Runde {lr}", src1=losers[2 * i], src2=losers[2 * i + 1]) for i in range(len(losers) // 2)]
        lb_prev = cur
        for wr in range(1, len(wb)):
            lr += 1
            drop = [{"m": m["id"], "r": "L"} for m in wb[wr]]
            cur = [_m(d, "L", lr, f"Loser · Runde {lr}", src1={"m": lb_prev[i]["id"], "r": "W"}, src2=drop[i])
                   for i in range(len(drop))]
            lb_prev = cur
            if len(cur) > 1:
                lr += 1
                cur = [_m(d, "L", lr, f"Loser · Runde {lr}", src1={"m": lb_prev[2 * i]["id"], "r": "W"},
                          src2={"m": lb_prev[2 * i + 1]["id"], "r": "W"}) for i in range(len(lb_prev) // 2)]
                lb_prev = cur
        gf = _m(d, "F", 1, "Großes Finale", src1={"m": wb[-1][0]["id"], "r": "W"}, src2={"m": lb_prev[0]["id"], "r": "W"})
        # Runden fürs Timing durchnummerieren: WB und LB laufen parallel
        for m in d["matches"]:
            if m["stage"] == "L":
                m["round"] = m["round"] + 1
        gf["round"] = max(m["round"] for m in d["matches"]) + 1
    else:
        _ko(d, teams, "W", "K.-o.")
    maps = d.get("maps") or WINGMAN_MAPS
    for i, m in enumerate(d["matches"]):
        m["map"] = maps[i % len(maps)]
    resolve(d)
    return d


# ---------------------------------------------------------------- Ergebnisse weiterreichen
def standings(d: dict, g: str) -> list[dict]:
    """Gruppentabelle: Siege, dann Rundendifferenz."""
    ids = d["groups"].get(g) or []
    tab = {t: {"team": t, "name": team_name(d, t), "played": 0, "won": 0, "lost": 0, "rf": 0, "ra": 0} for t in ids}
    for m in d["matches"]:
        if m["stage"] != "G" or m["group"] != g or m["status"] != "done":
            continue
        for me, other, sm, so in ((m["t1"], m["t2"], m["s1"], m["s2"]), (m["t2"], m["t1"], m["s2"], m["s1"])):
            if me in tab:
                r = tab[me]
                r["played"] += 1
                r["rf"] += sm or 0
                r["ra"] += so or 0
                if m["winner"] == me:
                    r["won"] += 1
                else:
                    r["lost"] += 1
    return sorted(tab.values(), key=lambda r: (-r["won"], -(r["rf"] - r["ra"]), -r["rf"], r["name"]))


def rr_table(d: dict) -> list[dict]:
    d2 = {**d, "groups": {"_": [t["id"] for t in d["teams"] if len(t["players"]) == 2]}}
    ms = [{**m, "stage": "G", "group": "_"} for m in d["matches"] if m["stage"] == "R"]
    return standings({**d2, "matches": ms}, "_")


def _src_value(d: dict, src: dict):
    if not src:
        return None
    if "g" in src:
        gm = [m for m in d["matches"] if m["stage"] == "G" and m["group"] == src["g"]]
        if not gm or any(m["status"] != "done" for m in gm):
            return None
        tab = standings(d, src["g"])
        return tab[src["pos"] - 1]["team"] if len(tab) >= src["pos"] else BYE
    m = next((x for x in d["matches"] if x["id"] == src["m"]), None)
    if not m or m["status"] != "done":
        return None
    return m["winner"] if src["r"] == "W" else (m["loser"] or BYE)


def resolve(d: dict) -> None:
    """Teams aus fertigen Matches in die nächsten eintragen, Freilose automatisch weiterschalten."""
    changed = True
    while changed:
        changed = False
        for m in d["matches"]:
            if m["status"] == "done":
                continue
            for k in ("1", "2"):
                if m["t" + k] is None and m["src" + k]:
                    v = _src_value(d, m["src" + k])
                    if v is not None:
                        m["t" + k] = v
                        changed = True
            a, b = m["t1"], m["t2"]
            if a is not None and b is not None:
                if a == BYE or b == BYE:
                    m.update(status="done", winner=b if a == BYE else a, loser=BYE, s1=None, s2=None, walkover=True)
                    changed = True
                elif m["status"] == "wait":
                    m["status"] = "ready"
                    changed = True


def set_result(d: dict, mid: str, s1: int, s2: int) -> dict:
    m = next((x for x in d["matches"] if x["id"] == mid), None)
    if not m:
        raise ValueError("Match nicht gefunden")
    if m["t1"] in (None, BYE) or m["t2"] in (None, BYE):
        raise ValueError("Gegner stehen noch nicht fest")
    if s1 == s2 and m["stage"] != "G" and m["stage"] != "R":
        raise ValueError("Unentschieden geht im K.-o. nicht")
    m.update(s1=s1, s2=s2, status="done", ended=m.get("ended") or time.time())
    m["winner"], m["loser"] = (m["t1"], m["t2"]) if s1 >= s2 else (m["t2"], m["t1"])
    resolve(d)
    if all(x["status"] == "done" for x in d["matches"]):
        d["status"] = "done"
    return m


def reset_match(d: dict, mid: str) -> None:
    m = next((x for x in d["matches"] if x["id"] == mid), None)
    if m:
        m.update(s1=None, s2=None, winner=None, loser=None, status="ready" if m["t1"] and m["t2"] else "wait",
                 started=None, ended=None, live_matchid=None)


# ---------------------------------------------------------------- Zeitplan
def plan(d: dict) -> None:
    """Startzeit und Server für jedes offene Match: frühestens nach Ende der Vorgänger, auf dem Server, der als
    Erstes frei ist. Laufende/fertige Matches behalten ihre Zeiten. Einzel-Spiele (Finale, je nach Einstellung auch
    Halb-/Viertelfinale) laufen allein: erst wenn alles davor fertig ist, und nichts parallel dazu."""
    servers = list(d.get("servers") or [])[:max_servers(d)]
    dur = (int(d.get("match_min") or 35) + int(d.get("pause_min") or 10)) * 60
    start = d.get("start") or time.time()
    free = {s: start for s in servers}
    ends: dict[str, float] = {}
    for m in d["matches"]:
        if m["status"] in ("live", "done"):
            t_end = (m.get("ended") or ((m.get("started") or m.get("planned") or start) + dur))
            if m["status"] == "live" and m.get("server") in free:
                free[m["server"]] = max(free[m["server"]], t_end)
            ends[m["id"]] = t_end
    order = sorted(d["matches"], key=lambda m: (m["round"], {"G": 0, "R": 0, "L": 0, "W": 1, "K": 1, "F": 2}.get(m["stage"], 0), m["id"]))
    block, all_end = 0.0, 0.0
    now = time.time() if d.get("status") == "running" else start
    for m in order:
        one = solo(d, m)
        if m["status"] in ("done", "live"):
            e = ends.get(m["id"]) or start
            all_end = max(all_end, e)
            if one:
                block = max(block, e)
            continue
        m["seq"] = one
        dep = []
        for s in (m.get("src1"), m.get("src2")):
            if s and "m" in s:
                dep.append(ends.get(s["m"], start))
            elif s and "g" in s:
                dep += [ends.get(x["id"], start) for x in d["matches"] if x["stage"] == "G" and x["group"] == s["g"]]
        earliest = max([start, now, block, all_end if one else 0] + dep)
        if not servers:
            m["planned"], m["server"] = earliest, None
            ends[m["id"]] = earliest + dur
        else:
            srv = min(servers, key=lambda s: max(free[s], earliest))
            t0 = max(free[srv], earliest)
            m["planned"], m["server"] = t0, srv
            free[srv] = t0 + dur
            ends[m["id"]] = t0 + dur
        all_end = max(all_end, ends[m["id"]])
        if one:
            block = ends[m["id"]]


def solo(d: dict, m: dict) -> bool:
    """Läuft dieses Spiel allein (alle können zuschauen)? Finale immer; Halb-/Viertelfinale je nach Einstellung."""
    if m.get("stage") not in ("W", "K", "F"):
        return False
    lab = (m.get("label") or "").split(" · ")[-1]
    if lab in ("Finale", "Großes Finale"):
        return True
    if lab == "Halbfinale":
        return not d.get("par_sf", False)
    if lab == "Viertelfinale":
        return not d.get("par_qf", True)
    return False


def is_late(m: dict) -> bool:
    return solo({}, m)


def max_servers(d: dict) -> int:
    """Höchstens Teams / 4 Server (aufgerundet) – mehr braucht kein Turnier."""
    n = sum(1 for t in d.get("teams") or [] if len(t.get("players") or []) == 2)
    return max(1, -(-n // 4))


def needed_servers(d: dict) -> int:
    """Wie viele Server sollen gleichzeitig laufen? Spiele der ersten Runde, höchstens Teams / 4."""
    first = min([m["round"] for m in d["matches"]] or [1])
    n = sum(1 for m in d["matches"] if m["round"] == first and m["t1"] != BYE and m["t2"] != BYE) or 1
    return min(n, max_servers(d))


def public_view(d: dict) -> dict:
    """Für die Übersicht: ohne interne Felder, mit Teamnamen."""
    def tn(t):
        return team_name(d, t) if t else None
    out = {k: d.get(k) for k in ("active", "name", "mode", "start", "match_min", "pause_min", "status", "registration")}
    out["mode_label"] = MODES.get(d.get("mode"), d.get("mode"))
    out["teams"] = [{"id": t["id"], "name": t["name"], "players": [_pname(d, p) for p in t["players"]],
                     "steamids": t["players"]} for t in d["teams"]]
    out["players"] = [{"steamid": p["steamid"], "name": p["name"], "avatar": p.get("avatar"),
                       "team": (player_team(d, p["steamid"]) or {}).get("id")} for p in d["players"]]
    out["matches"] = [{**{k: m.get(k) for k in ("id", "stage", "round", "label", "group", "s1", "s2", "status", "planned",
                                                 "started", "ended", "map", "server", "walkover")},
                       "t1": tn(m["t1"]), "t2": tn(m["t2"]), "winner": tn(m["winner"]), "t1_id": m["t1"], "t2_id": m["t2"],
                       "p1": _ph(m.get("src1")), "p2": _ph(m.get("src2")), "no": int(m["id"][1:]) if m["id"][1:].isdigit() else None}
                      for m in d["matches"]]
    out["groups"] = {g: standings(d, g) for g in (d.get("groups") or {})}
    if d.get("mode") == "rr" and d["matches"]:
        out["table"] = rr_table(d)
    return out


def _ph(src) -> str | None:
    """Platzhalter, solange ein Team noch nicht feststeht: „Sieger #3“, „1. Gruppe A“."""
    if not isinstance(src, dict):
        return None
    if "g" in src:
        return f"{src.get('pos')}. Gruppe {src['g']}"
    if "m" in src:
        return f"{'Sieger' if src.get('r') == 'W' else 'Verlierer'} #{str(src['m'])[1:]}"
    return None


def _pname(d: dict, sid: str) -> str:
    p = next((x for x in d["players"] if x["steamid"] == sid), None)
    return p["name"] if p else sid


def new_team_id() -> str:
    return "t" + secrets.token_hex(3)

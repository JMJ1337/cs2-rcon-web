"""Wreckfest: Strecken, Spielmodi und Event-Loop (Rotation) in server_config.cfg.

Strecken-IDs nach der Liste von Pingperfect (Wreckfest-Server-Doku); „derby“ = Arena für Derby-Modi.
"""
import re

TRACKS = [
    ("speedway2_classic_arena", "Big Valley Speedway – Classic Arena", "derby"),
    ("speedway2_demolition_arena", "Big Valley Speedway – Demolition Arena", "derby"),
    ("speedway2_figure_8", "Big Valley Speedway – Figure 8", "race"),
    ("speedway2_inner_oval", "Big Valley Speedway – Inner Oval", "race"),
    ("speedway2_outer_oval", "Big Valley Speedway – Outer Oval", "race"),
    ("speedway2_oval_loop", "Big Valley Speedway – Oval Loop", "race"),
    ("dirt_speedway_dirt_oval", "Bloomfield Speedway – Dirt Oval", "race"),
    ("dirt_speedway_figure_8", "Bloomfield Speedway – Figure 8", "race"),
    ("bonebreaker_valley_main_circuit", "Bonebreaker Valley", "race"),
    ("sandpit3_long_loop", "Boulder Bank Circuit – Long", "race"),
    ("sandpit3_long_loop_rev", "Boulder Bank Circuit – Long (rückwärts)", "race"),
    ("sandpit3_short_loop", "Boulder Bank Circuit – Short", "race"),
    ("sandpit3_short_loop_rev", "Boulder Bank Circuit – Short (rückwärts)", "race"),
    ("mixed9_r1", "Clayridge Circuit", "race"),
    ("mixed9_r1_rev", "Clayridge Circuit (rückwärts)", "race"),
    ("crash_canyon_main_circuit", "Crash Canyon", "race"),
    ("loop", "Deathloop", "race"),
    ("triangle_r1", "Dirt Devil Stadium – 1", "race"),
    ("triangle_r2", "Dirt Devil Stadium – 2", "race"),
    ("fields08_1", "Drytown Desert", "race"),
    ("fields08_1_rev", "Drytown Desert (rückwärts)", "race"),
    ("tarmac3_main_circuit", "Espedalen Raceway", "race"),
    ("tarmac3_main_circuit_rev", "Espedalen Raceway (rückwärts)", "race"),
    ("tarmac3_short_circuit", "Espedalen Raceway – Short", "race"),
    ("tarmac3_short_circuit_rev", "Espedalen Raceway – Short (rückwärts)", "race"),
    ("smallstadium_demolition_arena", "Fairfield County – Arena", "derby"),
    ("mudpit_demolition_arena", "Fairfield Mudpit", "derby"),
    ("grass_arena_demolition_arena", "Fairfield Grass Arena", "derby"),
    ("mixed1_main_circuit", "Finncross Circuit", "race"),
    ("mixed1_main_circuit_rev", "Finncross Circuit (rückwärts)", "race"),
    ("tarmac1_main_circuit", "Fire Rock Raceway", "race"),
    ("tarmac1_main_circuit_rev", "Fire Rock Raceway (rückwärts)", "race"),
    ("tarmac1_short_circuit", "Fire Rock Raceway – Short", "race"),
    ("tarmac1_short_circuit_rev", "Fire Rock Raceway – Short (rückwärts)", "race"),
    ("mixed7_r1", "Firwood Motorcenter – 1", "race"),
    ("mixed7_r1_rev", "Firwood Motorcenter – 1 (rückwärts)", "race"),
    ("mixed7_r3", "Firwood Motorcenter – 3", "race"),
    ("mixed7_r3_rev", "Firwood Motorcenter – 3 (rückwärts)", "race"),
    ("field_derby_arena", "Glendale Countryside – Arena", "derby"),
    ("urban06", "Hellride", "race"),
    ("speedway1_figure_8", "Hilltop Stadium – Figure 8", "race"),
    ("speedway1_oval", "Hilltop Stadium – Oval", "race"),
    ("fields12_1", "Kingston Raceway – 1", "race"),
    ("fields12_1_rev", "Kingston Raceway – 1 (rückwärts)", "race"),
    ("fields12_2", "Kingston Raceway – 2", "race"),
    ("mixed2_main_circuit", "Maasten Motorcenter", "race"),
    ("mixed2_main_circuit_rev", "Maasten Motorcenter (rückwärts)", "race"),
    ("bigstadium_demolition_arena", "Madman Stadium – Arena", "derby"),
    ("bigstadium_figure_8", "Madman Stadium – Figure 8", "race"),
    ("gravel1_main_loop", "Midwest Motocenter", "race"),
    ("gravel1_main_loop_rev", "Midwest Motocenter (rückwärts)", "race"),
    ("tarmac2_main_circuit", "Motorcity Circuit", "race"),
    ("tarmac2_main_circuit_rev", "Motorcity Circuit (rückwärts)", "race"),
    ("fields10_1", "Mudford Motorpark – 1", "race"),
    ("fields10_2", "Mudford Motorpark – 2", "race"),
    ("mixed8_r1", "Northfolk Ring – 1", "race"),
    ("mixed8_r2", "Northfolk Ring – 2", "race"),
    ("mixed8_r3", "Northfolk Ring – 3", "race"),
    ("mixed5_outer_loop", "Northland Raceway – Outer", "race"),
    ("mixed5_outer_loop_rev", "Northland Raceway – Outer (rückwärts)", "race"),
    ("mixed5_inner_loop", "Northland Raceway – Inner", "race"),
    ("mixed5_inner_loop_rev", "Northland Raceway – Inner (rückwärts)", "race"),
    ("mixed5_free_route", "Northland Raceway – Free Route", "race"),
    ("mixed3_long_loop", "Pinehills Raceway – Long", "race"),
    ("mixed3_long_loop_rev", "Pinehills Raceway – Long (rückwärts)", "race"),
    ("mixed3_short_loop", "Pinehills Raceway – Short", "race"),
    ("mixed3_short_loop_rev", "Pinehills Raceway – Short (rückwärts)", "race"),
    ("fields09_1", "Rockfield Roughspot", "race"),
    ("mixed4_main_circuit", "Rosenheim Raceway", "race"),
    ("mixed4_main_circuit_rev", "Rosenheim Raceway (rückwärts)", "race"),
    ("sandpit1_long_loop", "Sandstone Raceway – Long", "race"),
    ("sandpit1_long_loop_rev", "Sandstone Raceway – Long (rückwärts)", "race"),
    ("sandpit1_short_loop", "Sandstone Raceway – Short", "race"),
    ("sandpit1_short_loop_rev", "Sandstone Raceway – Short (rückwärts)", "race"),
    ("sandpit1_alt_loop", "Sandstone Raceway – Alternate", "race"),
    ("sandpit1_alt_loop_rev", "Sandstone Raceway – Alternate (rückwärts)", "race"),
    ("sandpit2_2", "Savolax Sandpit", "race"),
    ("sandpit2_2_rev", "Savolax Sandpit (rückwärts)", "race"),
    ("sandpit2_full_circuit", "Savolax Sandpit – Full", "race"),
    ("sandpit2_full_circuit_rev", "Savolax Sandpit – Full (rückwärts)", "race"),
    ("fields11_1", "The Maw", "race"),
    ("urban07", "Thunderbowl", "race"),
    ("forest12_1", "Tribend Raceway – 1", "race"),
    ("forest12_1_rev", "Tribend Raceway – 1 (rückwärts)", "race"),
    ("forest12_2", "Tribend Raceway – 2", "race"),
    ("forest11_1", "Vale Falls – 1", "race"),
    ("forest11_1_rev", "Vale Falls – 1 (rückwärts)", "race"),
    ("forest11_2", "Vale Falls – 2", "race"),
    ("forest11_2_rev", "Vale Falls – 2 (rückwärts)", "race"),
    ("fields13_1", "Eagles Park Speedway – 1", "race"),
    ("fields13_1_rev", "Eagles Park Speedway – 1 (rückwärts)", "race"),
    ("fields13_2", "Eagles Park Speedway – 2", "race"),
]
TRACK_NAMES = {k: n for k, n, _ in TRACKS}

GAMEMODES = [("racing", "Rennen"), ("derby", "Derby (Last Man Standing)"), ("derby deathmatch", "Derby Deathmatch"),
             ("team race", "Team-Rennen"), ("team derby", "Team-Derby"), ("elimination race", "Ausscheidungsrennen")]
MODE_NAMES = dict(GAMEMODES)
CAR_CLASSES = ["", "a", "b", "c", "d"]

# Felder eines Events (Reihenfolge wie in der Doku)
EL_FIELDS = ["gamemode", "num_teams", "laps", "bots", "car_class_restriction", "car_restriction",
             "car_reset_disabled", "wrong_way_limiter_disabled", "weather"]
# globale Einstellungen rund um die Rotation
GLOBAL_KEYS = {"enable_track_vote": "Streckenabstimmung (0/1)", "admin_control": "Admin startet Countdown (0/1)",
               "lobby_countdown": "Lobby-Countdown (30–127 s)", "ready_players_required": "Bereit-Quote (%)",
               "vehicle_damage": "Schaden (normal/intense/realistic)", "elimination_interval": "Ausscheiden alle … s (0 = jede Runde)",
               "time_limit": "Zeitlimit Deathmatch (Min.)", "car_reset_delay": "Reset-Verzögerung (0–20 s)",
               "special_vehicles_disabled": "Spezialfahrzeuge aus (0/1)"}

MARK = "# --- Event-Loop (Spielservermanager) ---"


def track_name(tid: str | None) -> str:
    return TRACK_NAMES.get(tid or "", tid or "")


def parse_events(text: str) -> list[dict]:
    """el_add=… beginnt ein Event, folgende el_*-Zeilen gehören dazu."""
    events: list[dict] = []
    for line in text.splitlines():
        m = re.match(r"^\s*el_([a-z_]+)\s*=\s*(.*?)\s*$", line)
        if not m:
            continue
        k, v = m.group(1), m.group(2).strip().strip('"')
        if k == "add":
            events.append({"track": v})
        elif events and k in EL_FIELDS:
            events[-1][k] = v
    return events


def _clean(v) -> str:
    return re.sub(r'[\r\n"]', "", str(v if v is not None else "")).strip()


def render_events(text: str, events: list[dict]) -> str:
    """Alle aktiven el_*-Zeilen ersetzen und die neue Rotation ans Ende schreiben."""
    lines = [ln for ln in text.splitlines() if not re.match(r"^\s*el_[a-z_]+\s*=", ln) and ln.strip() != MARK]
    while lines and not lines[-1].strip():
        lines.pop()
    if events:
        lines += ["", MARK]
        for e in events:
            t = _clean(e.get("track"))
            if not re.fullmatch(r"[A-Za-z0-9_\-]+", t):
                continue
            lines.append(f"el_add={t}")
            for k in EL_FIELDS:
                v = _clean(e.get(k))
                if v == "":
                    continue
                lines.append(f'el_{k}="{v}"' if k in ("gamemode", "weather") else f"el_{k}={v}")
    return "\n".join(lines) + "\n"

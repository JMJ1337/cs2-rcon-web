"""Spieleranzahl automatisch nach Modus und Map setzen (sv_visiblemaxplayers)."""
import fnmatch
import re

from . import store

SETTINGS_FILE = "settings.json"

# (game_type, game_mode) -> Modus
DEFAULT_MODES = [
    {"key": "competitive", "label": "Competitive (5v5)", "game_type": 0, "game_mode": 1, "players": 10},
    {"key": "wingman", "label": "Wingman (2v2)", "game_type": 0, "game_mode": 2, "players": 4},   # +1 CSTV automatisch
    {"key": "casual", "label": "Casual", "game_type": 0, "game_mode": 0, "players": 20},
    {"key": "deathmatch", "label": "Deathmatch", "game_type": 1, "game_mode": 2, "players": 16},
    {"key": "armsrace", "label": "Arms Race", "game_type": 1, "game_mode": 0, "players": 10},
    {"key": "custom", "label": "Custom", "game_type": 3, "game_mode": 0, "players": 10},
]

# Map-Regeln haben Vorrang vor dem Modus (erste passende gewinnt)
DEFAULT_MAP_RULES = [
    {"pattern": "aim_*", "players": 2, "label": "Aim-Maps (1v1)"},
    {"pattern": "*1v1*", "players": 2, "label": "1v1-Maps"},
    {"pattern": "awp_*", "players": 4, "label": "AWP-Maps (2v2)"},
    {"pattern": "surf_*", "players": 16, "label": "Surf"},
    {"pattern": "bhop_*", "players": 16, "label": "Bhop"},
    {"pattern": "kz_*", "players": 16, "label": "KZ"},
]

DEFAULT_SETTINGS = {
    "modes": DEFAULT_MODES,
    "map_rules": DEFAULT_MAP_RULES,
    "public_url": "",          # Adresse, unter der die CS2-Server dieses Tool erreichen (für MatchZy)
    "internet_host": "",       # öffentliche IP/DNS-Name für Besucher aus dem Internet (leer = automatisch ermitteln)
    "watch_interval": 10,
    "scan_interval": 15,        # Minuten, 0 = aus
    "scan_subnets": "",         # zusätzliche Netze, z. B. "192.168.200.0/24"
    "games_base": "/mnt/grohlan",   # Basisordner für neue Spielserver (NAS-Mount auf dem Docker-Host)
    "cache_container": "",      # Lancache-Container (leer = automatisch erkennen)
    "hostname_pattern": "Groh CS #{nr} {mode}",       # CS2-Servername nach Modus (leer = aus)
    "names_pattern": "Groh {game} #{nr} {mode}",      # alle anderen Spiele, z. B. „TF2 #1 Payload“, „Valheim #1“ (leer = aus)
    "container_dns": "",        # DNS für neue Spielserver-Container (leer = Lancache-DNS automatisch)
    "auto_bots": True,          # CS2: allein auf dem Server -> Bots (nicht in Competitive/Wingman)
    "auto_matchzy": True,       # CS2: MatchZy nur in Competitive/Wingman geladen
    "port_range": "27000-27100",    # im Router weitergeleiteter Portbereich – neue Server bekommen ihre Internet-Ports von hier
}


def get_settings() -> dict:
    s = store.load(SETTINGS_FILE, {})
    out = {**DEFAULT_SETTINGS, **s}
    # alte Standard-Muster auf das einheitliche Schema „CS #1 Modus“ umstellen
    if out.get("hostname_pattern") in ("CS#{nr} {mode}", "Groh {mode} {nr}", "CS #{nr} {mode}", "Groh CS {nr} {mode}"):
        out["hostname_pattern"] = DEFAULT_SETTINGS["hostname_pattern"]
    if out.get("names_pattern") in ("{game}#{nr} {mode}", "Groh {mode} {nr}", "{game} #{nr} {mode}", "Groh {game} {nr} {mode}"):
        out["names_pattern"] = DEFAULT_SETTINGS["names_pattern"]
    if not out.get("modes"):
        out["modes"] = DEFAULT_MODES
    if not s.get("_wingman5"):                 # einmalig: Wingman braucht 5 Plätze (der CSTV-Zuschauer belegt einen)
        for m in out["modes"]:
            if m.get("key") == "wingman" and int(m.get("players") or 0) == 4:
                m["players"] = 5
        s["modes"], s["_wingman5"] = out["modes"], True
    if not s.get("_tvslot"):                   # einmalig: CSTV-Platz wird jetzt automatisch addiert -> Wingman wieder 4
        for m in out["modes"]:
            if m.get("key") == "wingman" and int(m.get("players") or 0) == 5:
                m["players"] = 4
        s["modes"], s["_tvslot"] = out["modes"], True
        store.save(SETTINGS_FILE, s)
    return out


def save_settings(data: dict) -> dict:
    cur = get_settings()
    for k in ("modes", "map_rules", "public_url", "internet_host", "watch_interval", "scan_interval", "scan_subnets",
              "games_base", "cache_container", "cache_dir", "default_join_pw", "default_admin_pw", "cs2_template_src", "hostname_pattern", "names_pattern", "container_dns", "auto_bots", "auto_matchzy", "port_range"):
        if k in data:
            cur[k] = data[k]
    store.save(SETTINGS_FILE, cur)
    return cur


def mode_for(game_type, game_mode, settings=None):
    settings = settings or get_settings()
    for m in settings["modes"]:
        if str(m["game_type"]) == str(game_type) and str(m["game_mode"]) == str(game_mode):
            return m
    return None


def map_basename(map_name: str | None) -> str:
    if not map_name:
        return ""
    return map_name.replace("\\", "/").rstrip("/").split("/")[-1].lower()


def target_players(map_name, game_type, game_mode, settings=None):
    """Liefert (anzahl, begründung) oder (None, grund)."""
    settings = settings or get_settings()
    base = map_basename(map_name)
    for r in settings.get("map_rules", []):
        pat = (r.get("pattern") or "").lower().strip()
        if pat and base and fnmatch.fnmatch(base, pat):
            return int(r["players"]), f"Map-Regel „{r.get('label') or pat}“"
    m = mode_for(game_type, game_mode, settings)
    if m:
        return int(m["players"]), f"Modus {m['label']}"
    return None, "kein passender Modus"


def parse_cvars(raw: str, names: list[str]) -> dict:
    values = {n: None for n in names}
    for n in names:
        # nach „=“ nur Leerzeichen/Tabs – sonst greift ein leerer Wert die nächste Zeile ab (z. B. sv_password -> „bot_quota“)
        m = re.search(rf"(?m)^[ \t]*\"?{re.escape(n)}\"?[ \t]*=[ \t]*(\"([^\"\n]*)\"|([^\s]+))", raw)
        if m:
            values[n] = m.group(2) if m.group(2) is not None else m.group(3)
    return values

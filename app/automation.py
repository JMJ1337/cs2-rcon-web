"""Spieleranzahl automatisch nach Modus und Map setzen (sv_visiblemaxplayers)."""
import fnmatch
import re

from . import store

SETTINGS_FILE = "settings.json"

# (game_type, game_mode) -> Modus
DEFAULT_MODES = [
    {"key": "competitive", "label": "Competitive (5v5)", "game_type": 0, "game_mode": 1, "players": 10},
    {"key": "wingman", "label": "Wingman (2v2)", "game_type": 0, "game_mode": 2, "players": 4},
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
    "watch_interval": 10,
}


def get_settings() -> dict:
    s = store.load(SETTINGS_FILE, {})
    out = {**DEFAULT_SETTINGS, **s}
    if not out.get("modes"):
        out["modes"] = DEFAULT_MODES
    return out


def save_settings(data: dict) -> dict:
    cur = get_settings()
    for k in ("modes", "map_rules", "public_url", "watch_interval"):
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
        m = re.search(rf"(?m)^\s*{re.escape(n)}\s*=\s*(\"([^\"]*)\"|(\S+))", raw)
        if m:
            values[n] = m.group(2) if m.group(2) is not None else m.group(3)
    return values

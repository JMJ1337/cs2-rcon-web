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
    "scan_subnets": "",         # zusätzliche Netze, z. B. "192.168.1.0/24"
    "brand": "LAN",             # Name der Veranstaltung – erscheint in Servernamen, Titeln, Benachrichtigungen ({brand})
    "games_base": "/srv/gameserver",   # Basisordner für neue Spielserver (z. B. NAS-Mount auf dem Docker-Host)
    "cache_container": "",      # Lancache-Container (leer = automatisch erkennen)
    "hostname_pattern": "{brand} CS #{nr} {mode}",       # CS2-Servername nach Modus (leer = aus)
    "names_pattern": "{brand} {game} #{nr} {mode}",      # alle anderen Spiele, z. B. „LAN TF2 #1 Payload“ (leer = aus)
    "container_dns": "",        # DNS für neue Spielserver-Container (leer = Lancache-DNS automatisch)
    "auto_bots": True,          # CS2: allein auf dem Server -> Bots (nicht in Competitive/Wingman)
    "auto_matchzy": True,       # CS2: MatchZy nur in Competitive/Wingman geladen
    "port_range": "27000-27100",    # im Router weitergeleiteter Portbereich – neue Server bekommen ihre Internet-Ports von hier
}


# Bestehende Installationen aus der Zeit vor der einstellbaren Veranstaltung: deren bisherige Standardwerte
# werden beim ersten Start einmalig fest gespeichert, damit sich dort nichts ändert.
_LEGACY = {"brand": "GrohLAN", "games_base": "/mnt/grohlan", "tpl_dns_default": "192.168.200.27",
           "hostname_pattern": "Groh CS #{nr} {mode}", "names_pattern": "Groh {game} #{nr} {mode}"}
_LEGACY_OLD_CS = ("CS#{nr} {mode}", "Groh {mode} {nr}", "CS #{nr} {mode}", "Groh CS {nr} {mode}")
_LEGACY_OLD_NAMES = ("{game}#{nr} {mode}", "Groh {mode} {nr}", "{game} #{nr} {mode}", "Groh {game} {nr} {mode}")
_LEGACY_STORES = {"steambot.json": {"bot_name": "GrohLan"},
                  "apikeys.json": {"origins": ["https://www.groh-lan.de", "https://groh-lan.de"]},
                  "tournament.json": {"name": "Groh LAN Wingman-Turnier"},
                  "notify.json": {"title": "Groh LAN"}}

# Neuinstallation: Standard-Beitritts- und RCON-Passwort für neue Spielserver (in den Einstellungen änderbar)
FRESH_DEFAULTS = {"default_join_pw": "123456789", "default_admin_pw": "123456789"}


def _migrate_brand(s: dict) -> dict:
    if "brand" in s:
        return s
    if s or (store.DATA_DIR / SETTINGS_FILE).exists():   # bestehende Installation (auch wenn die Datei gerade nicht lesbar ist)
        if not s:
            return s                                      # nichts überschreiben – beim nächsten Lesen erneut versuchen
        for k in ("brand", "games_base", "tpl_dns_default"):
            s.setdefault(k, _LEGACY[k])
        hp = s.get("hostname_pattern", _LEGACY["hostname_pattern"])
        s["hostname_pattern"] = _LEGACY["hostname_pattern"] if hp in _LEGACY_OLD_CS else hp
        np_ = s.get("names_pattern", _LEGACY["names_pattern"])
        s["names_pattern"] = _LEGACY["names_pattern"] if np_ in _LEGACY_OLD_NAMES else np_
        for fn, vals in _LEGACY_STORES.items():
            d = store.load(fn, {})
            if isinstance(d, dict):
                missing = {k: v for k, v in vals.items() if k not in d}
                if missing:
                    store.save(fn, {**d, **missing})
    else:   # Neuinstallation
        s.update(brand=DEFAULT_SETTINGS["brand"], **FRESH_DEFAULTS)
    store.save(SETTINGS_FILE, s)
    return s


def brand() -> str:
    return (get_settings().get("brand") or "").strip() or "LAN"


def get_settings() -> dict:
    s = _migrate_brand(store.load(SETTINGS_FILE, {}))
    out = {**DEFAULT_SETTINGS, **s}
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
              "games_base", "brand", "cache_container", "cache_dir", "default_join_pw", "default_admin_pw", "cs2_template_src", "hostname_pattern", "names_pattern", "container_dns", "auto_bots", "auto_matchzy", "port_range"):
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

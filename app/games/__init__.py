"""Unterstützte Spiele und ihre Fähigkeiten."""

GAMES = {
    "cs2": {
        "label": "Counter-Strike 2", "short": "CS2", "color": "#f0a43a",
        "port_label": "Spielport (RCON, TCP)", "default_port": 27015,
        "password_label": "RCON-Passwort", "console": True,
        "features": ["maps", "match", "cvars", "auto_slots"],
    },
    "factorio": {
        "label": "Factorio", "short": "Factorio", "color": "#e39827",
        "port_label": "RCON-Port (TCP)", "default_port": 27100,
        "password_label": "RCON-Passwort (config/rconpw)", "console": True,
        "features": ["save"],
    },
    "satisfactory": {
        "label": "Satisfactory", "short": "Satisfactory", "color": "#f2b134",
        "port_label": "API-/Spielport (TCP)", "default_port": 7777,
        "password_label": "Admin-Passwort", "console": True,
        "features": ["save", "claim"],
    },
    "valheim": {
        "label": "Valheim", "short": "Valheim", "color": "#6fa8dc",
        "port_label": "Query-Port (UDP, Spielport + 1)", "default_port": 2457,
        "password_label": "– (nicht nötig)", "console": False,
        "features": [],
    },
    "wreckfest": {
        "label": "Wreckfest", "short": "Wreckfest", "color": "#e5534b",
        "port_label": "Query-Port (UDP, Standard 27016)", "default_port": 27016,
        "password_label": "– (nicht nötig)", "console": False,
        "features": ["webconsole"],
    },
    "tf2": {
        "label": "Team Fortress 2", "short": "TF2", "color": "#cf6a32",
        "port_label": "Spielport (RCON, TCP+UDP)", "default_port": 27045,
        "password_label": "RCON-Passwort", "console": True,
        "features": [],
    },
    "minecraft": {
        "label": "Minecraft", "short": "Minecraft", "color": "#62b04a",
        "port_label": "Spielport (TCP)", "default_port": 25565,
        "password_label": "– (Konsole läuft über den Container)", "console": True,
        "features": [],
    },
    "teamspeak": {
        "label": "TeamSpeak 3", "short": "TS3", "color": "#2580c3",
        "port_label": "ServerQuery-Port (TCP)", "default_port": 10011,
        "password_label": "ServerQuery-Passwort (serveradmin)", "console": True,
        "features": [],
    },
}


from .catalog import CATALOG as _CAT  # noqa: E402

for _k, _c in _CAT.items():
    _st = _c["status"]
    GAMES[_k] = {
        "label": _c["label"], "short": _c["short"], "color": _c["color"], "appid": _c.get("appid"),
        "port_label": "Abfrage-Port" if _st[0] != "container" else "Spielport",
        "default_port": next((p[2] for p in _c["ports"] if p[0] == (_st[1] if len(_st) > 1 else "port")), _c["ports"][0][2]),
        "password_label": "– (nicht nötig)", "console": False,
        "features": ["webconsole"] if _c.get("web") else [], "catalog": True,
    }
for _k, _a in {"cs2": 730, "tf2": 440, "factorio": 427520, "satisfactory": 526870, "valheim": 892970, "wreckfest": 228380}.items():
    GAMES[_k]["appid"] = _a


def game_of(server: dict) -> str:
    g = server.get("game") or "cs2"
    return g if g in GAMES else "cs2"

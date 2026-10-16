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
}


def game_of(server: dict) -> str:
    g = server.get("game") or "cs2"
    return g if g in GAMES else "cs2"

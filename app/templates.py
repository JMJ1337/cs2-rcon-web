"""Vorlagen zum Anlegen neuer Spielserver-Container."""
import re

# Felder: key, label, type (text/number/password/select), default, hint
TEMPLATES = {
    "cs2": {
        "label": "Counter-Strike 2 (MatchZy)", "image": "xbird/cs2-matchzy:latest", "uid": 1000,
        "data_default": "{base}/cs/server{n}",
        "fields": [
            ["name", "Container-Name", "text", "cs2-dedicated-CS{n}", ""],
            ["server_name", "Servername", "text", "GROH LAN CS{n}", ""],
            ["port", "Spielport (TCP+UDP, auch RCON)", "number", "{port}", "Server 1 = 27015, 2 = 27016 …"],
            ["tv_port", "CSTV-Port (UDP)", "number", "{tvport}", ""],
            ["token", "Steam-Token (GSLT)", "password", "", "steamcommunity.com/dev/managegameservers"],
            ["rcon_pw", "RCON-Passwort", "password", "", ""],
            ["server_pw", "Server-Passwort (optional)", "text", "", ""],
            ["mode", "Modus", "select", "wingman", "competitive,wingman,casual,deathmatch"],
            ["map", "Startmap", "text", "de_inferno", ""],
            ["slots", "Max. Slots", "number", "20", "Obergrenze, sichtbare Slots setzt die Automatik"],
            ["dns", "DNS (Lancache, optional)", "text", "192.168.200.27", ""],
        ],
    },
    "factorio": {
        "label": "Factorio", "image": "factoriotools/factorio:stable", "uid": 845,
        "data_default": "{base}/factorio/{name}",
        "fields": [
            ["name", "Container-Name", "text", "factorio-{n}", ""],
            ["port", "Spielport (UDP)", "number", "34197", ""],
            ["rcon_port", "RCON-Port (TCP)", "number", "27100", "nicht 27015–27019 (CS2)"],
            ["save_name", "Spielstand-Name", "text", "lan", "wird beim ersten Start erzeugt"],
        ],
    },
    "satisfactory": {
        "label": "Satisfactory", "image": "wolveix/satisfactory-server:latest", "uid": 1000,
        "data_default": "{base}/satisfactory/{name}",
        "fields": [
            ["name", "Container-Name", "text", "satisfactory-{n}", ""],
            ["port", "Spiel-/API-Port (TCP+UDP)", "number", "7777", ""],
            ["msg_port", "Messaging-Port (TCP)", "number", "8888", ""],
            ["max_players", "Max. Spieler", "number", "8", ""],
            ["server_name", "Servername (beim Beanspruchen)", "text", "GROH LAN Satisfactory", ""],
            ["admin_pw", "Admin-Passwort (beim Beanspruchen)", "password", "", "wird nach dem Start automatisch gesetzt"],
        ],
    },
    "valheim": {
        "label": "Valheim", "image": "lloesche/valheim-server:latest", "uid": 0,
        "data_default": "{base}/valheim/{name}",
        "fields": [
            ["name", "Container-Name", "text", "valheim-{n}", ""],
            ["server_name", "Servername", "text", "GROH LAN Valheim", ""],
            ["world", "Weltname", "text", "Dedicated", ""],
            ["password", "Server-Passwort (min. 5 Zeichen)", "password", "", ""],
            ["port", "Spielport (UDP, +1 = Query)", "number", "2456", ""],
        ],
    },
    "wreckfest": {
        "label": "Wreckfest", "image": "ghcr.io/ich777/steamcmd:wreckfest", "uid": 99, "gid": 100,
        "data_default": "{base}/wreckfest/{name}",
        "fields": [
            ["name", "Container-Name", "text", "wreckfest-{n}", ""],
            ["port", "Spielport (UDP)", "number", "33540", ""],
            ["query_port", "Query-Port auf dem Host (UDP)", "number", "27116", "intern 27016 – außen verschoben, damit es nicht mit CS2 kollidiert"],
            ["steam_port", "Steam-Port auf dem Host (UDP)", "number", "27115", "intern 27015"],
            ["web_port", "Webkonsole (TCP)", "number", "9028", "Server-Konsole im Browser"],
        ],
    },
}

MODES = {"competitive": (0, 1), "wingman": (0, 2), "casual": (0, 0), "deathmatch": (1, 2)}


def _port(v, label):
    try:
        p = int(v)
    except (TypeError, ValueError):
        raise ValueError(f"{label}: ungültiger Port")
    if not 1 <= p <= 65535:
        raise ValueError(f"{label}: ungültiger Port")
    return p


def build(game: str, v: dict, data_dir: str) -> dict:
    """Liefert {name, image, spec, uid, data_dir, server: {...für die Serverliste...}}."""
    t = TEMPLATES[game]
    name = re.sub(r"[^a-zA-Z0-9_.\-]", "-", (v.get("name") or "").strip()) or f"{game}-server"
    data_dir = data_dir.rstrip("/")
    if not data_dir.startswith("/"):
        raise ValueError("Datenordner muss ein absoluter Pfad auf dem Docker-Host sein")
    labels = {"gsm.managed": "1", "gsm.game": game}
    host = {"RestartPolicy": {"Name": "unless-stopped"}, "Binds": [], "PortBindings": {}}
    exposed, env, srv = {}, [], {}

    def pub(port, proto):
        exposed[f"{port}/{proto}"] = {}
        host["PortBindings"][f"{port}/{proto}"] = [{"HostPort": str(port)}]

    if game == "cs2":
        port, tv = _port(v.get("port"), "Spielport"), _port(v.get("tv_port"), "CSTV-Port")
        if not v.get("token") or not v.get("rcon_pw"):
            raise ValueError("Steam-Token und RCON-Passwort sind Pflicht")
        gt, gm = MODES.get(v.get("mode") or "wingman", (0, 2))
        env = [f"SRCDS_TOKEN={v['token']}", f"CS2_SERVERNAME={v.get('server_name') or name}",
               f"CS2_GAMEALIAS={v.get('mode') or 'wingman'}", f"CS2_STARTMAP={v.get('map') or 'de_inferno'}",
               f"CS2_MAXPLAYERS={int(v.get('slots') or 20)}", f"CS2_PORT={port}", f"TV_PORT={tv}",
               f"CS2_RCONPW={v['rcon_pw']}", f"CS2_PW={v.get('server_pw') or ''}", "CS2_MAPGROUP=mg_active",
               "CS2_BOT_QUOTA=0", "STEAMAPPVALIDATE=0", "CS2_CHEATS=0", "CS2_SERVER_HIBERNATE=0", "CS2_LAN=0",
               "TV_ENABLE=0", "CS2_LOG=on", f"CS2_ADDITIONAL_ARGS=+game_type {gt} +game_mode {gm}"]
        pub(port, "tcp"); pub(port, "udp"); pub(tv, "udp")
        host["Binds"].append(f"{data_dir}:/home/steam/cs2-dedicated/")
        if v.get("dns"):
            host["Dns"] = [v["dns"]]
        spec_extra = {"Tty": True, "OpenStdin": True}
        srv = {"port": port, "password": v["rcon_pw"]}
    elif game == "factorio":
        port, rport = _port(v.get("port"), "Spielport"), _port(v.get("rcon_port"), "RCON-Port")
        env = [f"PORT={port}", f"RCON_PORT={rport}", f"SAVE_NAME={v.get('save_name') or 'lan'}",
               "GENERATE_NEW_SAVE=true", "LOAD_LATEST_SAVE=true"]
        pub(port, "udp"); pub(rport, "tcp")
        host["Binds"].append(f"{data_dir}:/factorio")
        spec_extra = {}
        srv = {"port": rport, "password": "", "game_port": port}  # Passwort wird nach dem Start aus config/rconpw gelesen
    elif game == "satisfactory":
        port, mport = _port(v.get("port"), "Spielport"), _port(v.get("msg_port"), "Messaging-Port")
        env = [f"MAXPLAYERS={int(v.get('max_players') or 8)}", "PUID=1000", "PGID=1000", "STEAMBETA=false",
               f"SERVERGAMEPORT={port}", f"SERVERMESSAGINGPORT={mport}"]
        pub(port, "tcp"); pub(port, "udp"); pub(mport, "tcp")
        host["Binds"].append(f"{data_dir}:/config")
        spec_extra = {}
        srv = {"port": port, "password": "", "claim": {"name": v.get("server_name") or name,
                                                       "password": v.get("admin_pw") or ""}}
    elif game == "valheim":
        port = _port(v.get("port"), "Spielport")
        pw = v.get("password") or ""
        if len(pw) < 5:
            raise ValueError("Valheim-Passwort muss mindestens 5 Zeichen haben")
        env = [f"SERVER_NAME={v.get('server_name') or name}", f"WORLD_NAME={v.get('world') or 'Dedicated'}",
               f"SERVER_PASS={pw}", f"SERVER_PORT={port}", "SERVER_PUBLIC=false", "TZ=Europe/Berlin"]
        pub(port, "udp"); pub(port + 1, "udp")
        host["Binds"] += [f"{data_dir}/config:/config", f"{data_dir}/server:/opt/valheim"]
        host["CapAdd"] = ["SYS_NICE"]
        spec_extra = {}
        srv = {"port": port + 1, "password": ""}
    elif game == "wreckfest":
        port = _port(v.get("port"), "Spielport")
        qport, sport = _port(v.get("query_port"), "Query-Port"), _port(v.get("steam_port"), "Steam-Port")
        wport = _port(v.get("web_port"), "Webkonsole")
        env = ["GAME_ID=361580", "VALIDATE=", "UID=99", "GID=100", "GAME_PARAMS="]
        exposed.update({f"{port}/udp": {}, "27016/udp": {}, "27015/udp": {}, "8080/tcp": {}})
        host["PortBindings"].update({f"{port}/udp": [{"HostPort": str(port)}], "27016/udp": [{"HostPort": str(qport)}],
                                     "27015/udp": [{"HostPort": str(sport)}], "8080/tcp": [{"HostPort": str(wport)}]})
        host["Binds"] += [f"{data_dir}/steamcmd:/serverdata/steamcmd", f"{data_dir}/serverfiles:/serverdata/serverfiles"]
        spec_extra = {}
        srv = {"port": qport, "password": "", "web_url": f"http://{{host}}:{wport}"}
    else:
        raise ValueError("Unbekanntes Spiel")
    spec = {"Image": t["image"], "Env": env, "ExposedPorts": exposed, "HostConfig": host, "Labels": labels, **spec_extra}
    dirs = [b.split(":")[0] for b in host["Binds"]]
    return {"name": name, "image": t["image"], "spec": spec, "uid": t["uid"], "gid": t.get("gid", t["uid"]), "dirs": dirs, "server": srv}

"""Vorlagen zum Anlegen neuer Spielserver-Container."""
import re

# Felder: key, label, type (text/number/password/select), default, hint
TEMPLATES = {
    "cs2": {
        "label": "Counter-Strike 2 (MatchZy)", "image": "xbird/cs2-matchzy:latest", "uid": 1000,
        "data_default": "{base}/cs/server{n}",
        "fields": [
            ["name", "Container-Name", "text", "cs2-dedicated-CS{n}", ""],
            ["server_name", "Servername", "text", "Groh CS {n} Wettkampf", ""],
            ["port", "Spielport (TCP+UDP, auch RCON)", "number", "{port}", "CS #1 = 27031, #2 = 27032 … (27015/27016 sind für Wreckfest frei)"],
            ["tv_port", "CSTV-Port (UDP)", "number", "{tvport}", ""],
            ["token", "Steam-Token (GSLT)", "password", "", "leer = automatisch aus der Token-Liste (Einstellungen → Steam-Tokens)"],
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
            ["server_name", "Servername (beim Beanspruchen)", "text", "Groh Satisfactory {n}", ""],
            ["admin_pw", "Admin-Passwort (beim Beanspruchen)", "password", "", "wird nach dem Start automatisch gesetzt"],
        ],
    },
    "valheim": {
        "label": "Valheim", "image": "lloesche/valheim-server:latest", "uid": 0,
        "data_default": "{base}/valheim/{name}",
        "fields": [
            ["name", "Container-Name", "text", "valheim-{n}", ""],
            ["server_name", "Servername", "text", "Groh Valheim {n}", ""],
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
            ["server_name", "Servername", "text", "Groh Wreckfest {n}", "so erscheint er im Server-Browser"],
            ["password", "Server-Passwort (optional)", "text", "", ""],
            ["max_players", "Max. Spieler", "number", "24", ""],
            ["admin_steam_ids", "Admin-SteamIDs (SteamID64, kommagetrennt, optional)", "text", "", "werden automatisch Admin"],
            ["port", "Spielport (UDP)", "number", "33540", ""],
            ["query_port", "Query-Port (UDP)", "number", "27016", "Original 27016 – die LAN-Suche schaut auf 26900–26905 und 27015–27020"],
            ["steam_port", "Steam-Port (UDP)", "number", "27015", "Original 27015"],
            ["web_port", "Webkonsole (TCP)", "number", "9028", "Server-Konsole im Browser"],
        ],
    },
    "tf2": {
        "label": "Team Fortress 2", "image": "cm2network/tf2:latest", "uid": 1000,
        "data_default": "{base}/tf2/{name}",
        "fields": [
            ["name", "Container-Name", "text", "tf2-{n}", ""],
            ["server_name", "Servername", "text", "Groh TF2 {n}", ""],
            ["port", "Spielport (TCP+UDP, auch RCON)", "number", "27045", "nicht 27015–27019 (CS2)"],
            ["tv_port", "SourceTV-Port (UDP)", "number", "27055", ""],
            ["token", "Steam-Token (GSLT, App 440)", "password", "", "leer = automatisch aus der Token-Liste – für LAN optional"],
            ["rcon_pw", "RCON-Passwort", "password", "", ""],
            ["server_pw", "Server-Passwort (optional)", "text", "", ""],
            ["map", "Startmap", "text", "ctf_2fort", "z. B. ctf_2fort, cp_dustbowl, pl_badwater, koth_harvest_final"],
            ["slots", "Max. Spieler", "number", "24", ""],
        ],
    },
    "minecraft": {
        "label": "Minecraft (Java)", "image": "itzg/minecraft-server:latest", "uid": 1000,
        "data_default": "{base}/minecraft/{name}",
        "fields": [
            ["name", "Container-Name", "text", "minecraft-{n}", ""],
            ["motd", "Servername (MOTD)", "text", "Groh Minecraft {n}", ""],
            ["port", "Spielport (TCP)", "number", "25565", ""],
            ["type", "Server-Typ", "select", "PAPER", "PAPER,VANILLA,FABRIC,FORGE,NEOFORGE,PURPUR"],
            ["version", "Version", "text", "LATEST", "z. B. LATEST oder 1.21.4"],
            ["memory", "Arbeitsspeicher", "text", "4G", ""],
            ["max_players", "Max. Spieler", "number", "20", ""],
            ["mode", "Spielmodus", "select", "survival", "survival,creative,adventure"],
            ["difficulty", "Schwierigkeit", "select", "normal", "peaceful,easy,normal,hard"],
            ["online_mode", "Nur echte Accounts (online-mode)", "select", "TRUE", "TRUE,FALSE"],
            ["ops", "Operatoren (Spielernamen, kommagetrennt)", "text", "", ""],
        ],
    },
    "teamspeak": {
        "label": "TeamSpeak 3", "image": "teamspeak:latest", "uid": 9987,
        "data_default": "{base}/teamspeak/{name}",
        "fields": [
            ["name", "Container-Name", "text", "teamspeak-{n}", ""],
            ["port", "Sprach-Port (UDP)", "number", "9987", "Standard für Clients ohne Portangabe"],
            ["query_port", "ServerQuery-Port (TCP)", "number", "10011", "für dieses Tool"],
            ["file_port", "Dateiübertragung (TCP)", "number", "30033", ""],
        ],
    },
}

from .games import catalog as _catalog  # noqa: E402

for _k, _c in _catalog.CATALOG.items():
    TEMPLATES[_k] = {"label": _c["label"], "image": _c["image"], "uid": _c["uid"], "gid": _c.get("gid", _c["uid"]),
                     "data_default": "{base}/" + _k + "/{name}", "fields": _catalog.fields(_k), "hint": _c.get("hint", "")}

# Port-Vergabe: (Feld, Startport, Schrittweite, belegte Ports pro Server)
PORT_PLAN = {
    "cs2": [("port", 27031, 1, 1), ("tv_port", 27021, 1, 1)],   # CS #n: 2703n / CSTV 2702n (27015/27016 bleiben für Wreckfest)
    "factorio": [("port", 34197, 1, 1), ("rcon_port", 27100, 1, 1)],
    "satisfactory": [("port", 7777, 1, 1), ("msg_port", 8888, 1, 1)],
    "valheim": [("port", 2456, 2, 2)],                       # Spielport + Query-Port (+1)
    "tf2": [("port", 27045, 1, 1), ("tv_port", 27055, 1, 1)],
    "minecraft": [("port", 25565, 1, 1)],
    "teamspeak": [("port", 9987, 1, 1), ("query_port", 10011, 1, 1), ("file_port", 30033, 1, 1)],
    "wreckfest": [("port", 33540, 1, 1), ("steam_port", 27015, 1, 1), ("query_port", 27016, 1, 1), ("web_port", 9028, 1, 1)],   # Originalports
}


for _k in _catalog.CATALOG:
    PORT_PLAN[_k] = _catalog.port_plan(_k)

# Standard-Passwörter (Groh LAN): Beitritt „hinkel“, RCON/Admin „groh6671“ – im Formular vorausgefüllt, änderbar
DEFAULT_JOIN_PW, DEFAULT_ADMIN_PW = "hinkel", "groh6671"
for _t in TEMPLATES.values():
    for _f in _t["fields"]:
        if _f[3] == "" and _f[0] in ("rcon_pw", "admin_pw", "rcon_password"):
            _f[3] = DEFAULT_ADMIN_PW
        elif _f[3] == "" and _f[0] in ("password", "server_pw", "join_pw", "server_password"):
            _f[3] = DEFAULT_JOIN_PW


def suggest_ports(game: str, used: set[int]) -> dict:
    taken = set(used)
    out = {}
    for field, base, step, span in PORT_PLAN.get(game, []):
        p = base
        while any((p + i) in taken for i in range(span)) and p < 65000:
            p += step
        for i in range(span):
            taken.add(p + i)
        out[field] = p
    return out


def host_ports(spec: dict) -> list[int]:
    ports = []
    for lst in (spec.get("HostConfig", {}).get("PortBindings") or {}).values():
        for b in lst:
            if str(b.get("HostPort", "")).isdigit():
                ports.append(int(b["HostPort"]))
    return sorted(set(ports))


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
            raise ValueError("RCON-Passwort fehlt" if v.get("token") else
                             "Kein Steam-Token frei – unter Automatik & Einstellungen → Steam-Tokens einen eintragen oder den Steam-API-Schlüssel hinterlegen")
        gt, gm = MODES.get(v.get("mode") or "wingman", (0, 2))
        env = [f"SRCDS_TOKEN={v.get('token') or ''}", f"CS2_SERVERNAME={v.get('server_name') or name}",
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
    elif game == "tf2":
        port, tv = _port(v.get("port"), "Spielport"), _port(v.get("tv_port"), "SourceTV-Port")
        rcon = (v.get("rcon_pw") or "").strip()
        if not rcon:
            raise ValueError("RCON-Passwort fehlt")
        env = [f"SRCDS_PORT={port}", f"SRCDS_TV_PORT={tv}", f"SRCDS_CLIENT_PORT={port + 1000}",
               f"SRCDS_RCONPW={rcon}", f"SRCDS_PW={v.get('server_pw') or ''}", f"SRCDS_TOKEN={v.get('token') or ''}",
               f"SRCDS_HOSTNAME={v.get('server_name') or name}", f"SRCDS_STARTMAP={v.get('map') or 'ctf_2fort'}",
               f"SRCDS_MAXPLAYERS={int(v.get('slots') or 24)}", "SRCDS_REGION=3", "SRCDS_FPSMAX=300", "SRCDS_TICKRATE=66"]
        pub(port, "tcp"); pub(port, "udp"); pub(tv, "udp")
        host["Binds"].append(f"{data_dir}:/home/steam/tf-dedicated")
        spec_extra = {}
        srv = {"port": port, "password": rcon}
    elif game == "minecraft":
        port = _port(v.get("port"), "Spielport")
        env = ["EULA=TRUE", f"TYPE={v.get('type') or 'PAPER'}", f"VERSION={v.get('version') or 'LATEST'}",
               f"MEMORY={v.get('memory') or '4G'}", f"MOTD={v.get('motd') or name}",
               f"MAX_PLAYERS={int(v.get('max_players') or 20)}", f"MODE={v.get('mode') or 'survival'}",
               f"DIFFICULTY={v.get('difficulty') or 'normal'}", f"ONLINE_MODE={v.get('online_mode') or 'TRUE'}",
               "ENABLE_RCON=true", "TZ=Europe/Berlin", "UID=1000", "GID=1000"]
        if (v.get("ops") or "").strip():
            env.append("OPS=" + re.sub(r"[^\w,]", "", v["ops"]))
        pub(port, "tcp")
        env.append("SERVER_PORT=25565")
        host["PortBindings"] = {f"25565/tcp": [{"HostPort": str(port)}]}
        exposed.clear(); exposed["25565/tcp"] = {}
        host["Binds"].append(f"{data_dir}:/data")
        spec_extra = {"Tty": True, "OpenStdin": True}
        srv = {"port": port, "password": ""}
    elif game == "teamspeak":
        port, qport, fport = _port(v.get("port"), "Sprach-Port"), _port(v.get("query_port"), "Query-Port"), _port(v.get("file_port"), "Dateiport")
        env = ["TS3SERVER_LICENSE=accept", f"TS3SERVER_DEFAULT_VOICE_PORT={port}", f"TS3SERVER_QUERY_PORT={qport}",
               f"TS3SERVER_FILETRANSFER_PORT={fport}", "TS3SERVER_QUERY_PROTOCOLS=raw"]
        pub(port, "udp"); pub(qport, "tcp"); pub(fport, "tcp")
        host["Binds"].append(f"{data_dir}:/var/ts3server")
        spec_extra = {}
        srv = {"port": qport, "password": "", "game_port": port}
    elif game in _catalog.CATALOG:
        c = _catalog.CATALOG[game]
        vals = {f: _port(v.get(f), lbl) for f, lbl, *_ in c["ports"]}
        sub = {"data": data_dir, "params": (v.get("params") if v.get("params") is not None else c.get("params", "")),
               "steam_user": v.get("steam_user") or "", "steam_pw": v.get("steam_pw") or "", "host": v.get("_host") or "",
               "port": vals.get("port", ""), **{f[0]: v.get(f[0]) or "" for f in c.get("fields", [])}}
        env = [e.format(**sub) for e in c["env"]]
        for f, _lbl, _d, protos, cport in c["ports"]:
            for proto in protos.split(","):
                exposed[f"{cport}/{proto}"] = {}
                host["PortBindings"][f"{cport}/{proto}"] = [{"HostPort": str(vals[f])}]
        if c.get("web"):
            wport = _port(v.get("web_port"), "Webkonsole")
            exposed["8080/tcp"] = {}
            host["PortBindings"]["8080/tcp"] = [{"HostPort": str(wport)}]
        host["Binds"] += [b.format(data=data_dir) for b in c["binds"]]
        spec_extra = {}
        if c.get("cmd"):
            spec_extra["Cmd"] = c["cmd"]
        if c.get("tty"):
            spec_extra.update(Tty=True, OpenStdin=True)
        st = c["status"]
        sp = vals.get(st[1]) if len(st) > 1 and st[1] in vals else vals.get("port")
        jp = vals.get(c["join"][1]) or vals.get("port")
        srv = {"port": sp, "password": "", "game_port": jp}
        if c.get("web"):
            srv["web_url"] = f"http://{{host}}:{wport}"
    elif game == "wreckfest":
        port = _port(v.get("port"), "Spielport")
        qport, sport = _port(v.get("query_port"), "Query-Port"), _port(v.get("steam_port"), "Steam-Port")
        wport = _port(v.get("web_port"), "Webkonsole")
        env = ["GAME_ID=361580", "VALIDATE=", "UID=99", "GID=100", "GAME_PARAMS="]
        # Ports innen = außen, damit die Werte in server_config.cfg stimmen (werden nach der Installation eingetragen)
        pub(port, "udp"); pub(qport, "udp"); pub(sport, "udp")
        exposed["8080/tcp"] = {}
        host["PortBindings"]["8080/tcp"] = [{"HostPort": str(wport)}]
        host["Binds"] += [f"{data_dir}/steamcmd:/serverdata/steamcmd", f"{data_dir}/serverfiles:/serverdata/serverfiles"]
        spec_extra = {}
        srv = {"port": qport, "password": "", "web_url": f"http://{{host}}:{wport}", "game_port": port,
               "wf_config": {"game_port": port, "query_port": qport, "steam_port": sport,
                             "server_name": v.get("server_name") or name, "password": v.get("password") or "",
                             "max_players": str(int(v.get("max_players") or 24)),
                             "admin_steam_ids": re.sub(r"[^0-9,]", "", v.get("admin_steam_ids") or "")}}
    else:
        raise ValueError("Unbekanntes Spiel")
    spec = {"Image": t["image"], "Env": env, "ExposedPorts": exposed, "HostConfig": host, "Labels": labels, **spec_extra}
    dirs = [b.split(":")[0] for b in host["Binds"]]
    return {"name": name, "image": t["image"], "spec": spec, "uid": t["uid"], "gid": t.get("gid", t["uid"]), "dirs": dirs, "server": srv}

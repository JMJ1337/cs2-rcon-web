"""Weitere LAN-Spieleserver, datengetrieben.

Jeder Eintrag beschreibt Image, Ports (Host-Port frei wählbar, Container-Port fest), Umgebung, Statusabfrage und Beitreten.
Die meisten nutzen die SteamCMD-Images von ich777 (gleiches Schema: /serverdata/serverfiles, UID 99/GID 100, Webkonsole 8080).
Status: ("a2s", feld) = Steam-Serverabfrage · ("tcp", feld) = Port erreichbar · ("ac", feld) = Assetto-Corsa-HTTP · ("container",) = nur Containerzustand
Beitreten: ("steam", feld) = steam://connect · ("addr", feld) = Adresse kopieren
"""

def _ich(tag):
    return f"ghcr.io/ich777/steamcmd:{tag}"


ICH_ENV = ["UID=99", "GID=100", "VALIDATE=", "GAME_PARAMS={params}", "USERNAME={steam_user}", "PASSWRD={steam_pw}"]
ICH_BINDS = ["{data}/steamcmd:/serverdata/steamcmd", "{data}/serverfiles:/serverdata/serverfiles"]

# Port: [Feld, Bezeichnung, Standard-Host-Port, Protokolle, Container-Port]
CATALOG = {
    "l4d2": {
        "label": "Left 4 Dead 2", "short": "L4D2", "color": "#b5402f", "appid": 550, "image": _ich("l4d2"), "uid": 99, "gid": 100,
        "env": ICH_ENV + ["GAME_ID=222860"], "binds": ICH_BINDS, "params": "+map c1m1_hotel +sv_lan 1",
        "ports": [["port", "Spielport (TCP+UDP)", 27060, "tcp,udp", 27015]], "web": True,
        "status": ("a2s", "port"), "join": ("steam", "port"),
    },
    "garrysmod": {
        "label": "Garry's Mod", "short": "GMod", "color": "#1d8fe0", "appid": 4000, "image": _ich("garrysmod"), "uid": 99, "gid": 100,
        "env": ICH_ENV + ["GAME_ID=4020"], "binds": ICH_BINDS, "params": "+gamemode sandbox +map gm_construct +maxplayers 16",
        "ports": [["port", "Spielport (TCP+UDP)", 27065, "tcp,udp", 27015]], "web": True,
        "status": ("a2s", "port"), "join": ("steam", "port"),
    },
    "insurgency": {
        "label": "Insurgency: Sandstorm", "short": "Sandstorm", "color": "#8a7a52", "appid": 581320, "image": _ich("insurgencysandstorm"),
        "uid": 99, "gid": 100, "env": ICH_ENV + ["GAME_ID=581330"], "binds": ICH_BINDS,
        "params": "Oilfield?Scenario=Scenario_Refinery_Push_Security?MaxPlayers=16 -log",
        "ports": [["port", "Spielport (UDP)", 27102, "udp", 27102], ["query_port", "Query-Port (UDP)", 27131, "udp", 27131]], "web": True,
        "status": ("a2s", "query_port"), "join": ("addr", "port"),
    },
    "quakelive": {
        "label": "Quake Live", "short": "Quake", "color": "#c23b22", "appid": 282440, "image": _ich("quakelive"), "uid": 99, "gid": 100,
        "env": ICH_ENV + ["GAME_ID=349090"], "binds": ICH_BINDS, "params": "+set sv_hostname GROH-LAN +set g_gametype 0",
        "ports": [["port", "Spielport (UDP)", 27960, "udp", 27960], ["rcon_port", "ZMQ-RCON (TCP)", 28960, "tcp", 28960]], "web": True,
        "status": ("a2s", "port"), "join": ("steam", "port"),
    },
    "killingfloor2": {
        "label": "Killing Floor 2", "short": "KF2", "color": "#9e1b1b", "appid": 232090, "image": _ich("killingfloor2"), "uid": 99, "gid": 100,
        "env": ICH_ENV + ["GAME_ID=232130"], "binds": ICH_BINDS, "params": "KF-BioticsLab",
        "ports": [["port", "Spielport (UDP)", 7797, "udp", 7777], ["query_port", "Query-Port (UDP)", 27115 + 60, "udp", 27015],
                  ["admin_port", "Web-Admin (TCP)", 8090 + 10, "tcp", 8080]], "web": False,
        "status": ("a2s", "query_port"), "join": ("addr", "port"),
    },
    "7dtd": {
        "label": "7 Days to Die", "short": "7DTD", "color": "#a33c1f", "appid": 251570, "image": _ich("7dtd"), "uid": 99, "gid": 100,
        "env": ICH_ENV + ["GAME_ID=294420"], "binds": ICH_BINDS, "params": "-logfile /serverdata/serverfiles/output_log.txt -quit -batchmode -nographics -dedicated -configfile=serverconfig.xml",
        "ports": [["port", "Spielport (TCP+UDP, +1/+2 UDP)", 26910, "tcp,udp", 26900], ["port1", "UDP +1", 26911, "udp", 26901],
                  ["port2", "UDP +2", 26912, "udp", 26902]], "web": True,
        "status": ("a2s", "port"), "join": ("addr", "port"),
    },
    "projectzomboid": {
        "label": "Project Zomboid", "short": "Zomboid", "color": "#7b8b2c", "appid": 108600, "image": _ich("projectzomboid"), "uid": 99, "gid": 100,
        "env": ICH_ENV + ["GAME_ID=380870", "ADMIN_PWD={admin_pw}", "SRV_NAME={server_name}"], "binds": ICH_BINDS, "params": "",
        "ports": [["port", "Spielport (UDP)", 16261, "udp", 16261], ["port2", "Direktverbindung (UDP)", 16262, "udp", 16262]], "web": True,
        "fields": [["server_name", "Servername", "text", "GROHLAN", ""], ["admin_pw", "Admin-Passwort", "password", "", ""]],
        "status": ("a2s", "port"), "join": ("addr", "port"),
    },
    "palworld": {
        "label": "Palworld", "short": "Palworld", "color": "#3aa7d6", "appid": 1623730, "image": _ich("palworld"), "uid": 99, "gid": 100,
        "env": ICH_ENV + ["GAME_ID=2394010"], "binds": ICH_BINDS, "params": "-useperfthreads -NoAsyncLoadingThread -UseMultithreadForDS",
        "ports": [["port", "Spielport (UDP)", 8211, "udp", 8211], ["query_port", "Query-Port (UDP)", 27215, "udp", 27015]], "web": True,
        "status": ("a2s", "query_port"), "join": ("addr", "port"),
    },
    "vrising": {
        "label": "V Rising", "short": "V Rising", "color": "#8c1f2f", "appid": 1604030, "image": _ich("vrising"), "uid": 99, "gid": 100,
        "env": ICH_ENV + ["GAME_ID=1829350", "SERVER_NAME={server_name}", "WORLD_NAME=world1"], "binds": ICH_BINDS, "params": "",
        "ports": [["port", "Spielport (UDP)", 9876, "udp", 9876], ["query_port", "Query-Port (UDP)", 9877, "udp", 9877]], "web": True,
        "fields": [["server_name", "Servername", "text", "GROH LAN V Rising", ""]],
        "status": ("a2s", "query_port"), "join": ("addr", "port"),
    },
    "abioticfactor": {
        "label": "Abiotic Factor", "short": "Abiotic", "color": "#4f8f6b", "appid": 427410, "image": _ich("abioticfactor"), "uid": 99, "gid": 100,
        "env": ICH_ENV + ["GAME_ID=2857200"], "binds": ICH_BINDS, "params": "-SteamServerName=GROHLAN -MaxServerPlayers=6",
        "ports": [["port", "Spielport (UDP)", 7787, "udp", 7777], ["query_port", "Query-Port (UDP)", 27225, "udp", 27015]], "web": True,
        "status": ("a2s", "query_port"), "join": ("addr", "port"),
    },
    "dontstarve": {
        "label": "Don't Starve Together", "short": "DST", "color": "#7a5c3a", "appid": 322330, "image": _ich("dontstarve"), "uid": 99, "gid": 100,
        "env": ICH_ENV + ["GAME_ID=343050", "CLUSTER_TOKEN={cluster_token}"], "binds": ICH_BINDS, "params": "",
        "ports": [["port", "Spielport (UDP)", 10999, "udp", 10999], ["port2", "Höhlen-Shard (UDP)", 11000, "udp", 11000]], "web": True,
        "fields": [["cluster_token", "Klei-Server-Token", "password", "", "accounts.klei.com → Spiele → Server erstellen"]],
        "status": ("container",), "join": ("addr", "port"),
    },
    "enshrouded": {
        "label": "Enshrouded", "short": "Enshrouded", "color": "#3e6fa8", "appid": 1203620, "image": "sknnr/enshrouded-dedicated-server:latest",
        "uid": 10000, "gid": 10000, "env": ["SERVER_NAME={server_name}", "SERVER_PASSWORD={password}", "GAME_PORT=15636", "QUERY_PORT=15637",
                                            "SERVER_SLOTS=16"],
        "binds": ["{data}:/home/steam/enshrouded/savegame"], "params": "",
        "ports": [["port", "Spielport (UDP)", 15636, "udp", 15636], ["query_port", "Query-Port (UDP)", 15637, "udp", 15637]], "web": False,
        "fields": [["server_name", "Servername", "text", "GROH LAN Enshrouded", ""], ["password", "Passwort", "text", "", ""]],
        "status": ("a2s", "query_port"), "join": ("addr", "port"),
    },
    "assettocorsa": {
        "label": "Assetto Corsa", "short": "AC", "color": "#c8102e", "appid": 244210, "image": _ich("assettocorsa"), "uid": 99, "gid": 100,
        "env": ICH_ENV + ["GAME_ID=302550"], "binds": ICH_BINDS, "params": "",
        "ports": [["port", "Spielport (TCP+UDP)", 9600, "tcp,udp", 9600], ["http_port", "HTTP-Port (TCP)", 8081, "tcp", 8081]], "web": True,
        "steam_login": True, "status": ("ac", "http_port"), "join": ("addr", "port"),
    },
    "terraria": {
        "label": "Terraria (TShock)", "short": "Terraria", "color": "#5b8f2a", "appid": 105600, "image": "ryshe/terraria:latest",
        "uid": 0, "gid": 0, "env": ["WORLD_FILENAME=lan.wld"], "binds": ["{data}:/root/.local/share/Terraria/Worlds"],
        "cmd": ["-autocreate", "2", "-world", "/root/.local/share/Terraria/Worlds/lan.wld", "-maxplayers", "16"], "params": "",
        "ports": [["port", "Spielport (TCP)", 7790, "tcp", 7777]], "web": False, "tty": True,
        "status": ("tcp", "port"), "join": ("addr", "port"),
    },
    "openttd": {
        "label": "OpenTTD", "short": "OpenTTD", "color": "#5a7d9a", "appid": 1536610, "image": "bateau/openttd:latest",
        "uid": 1000, "gid": 1000, "env": ["loadgame=last-autosave"], "binds": ["{data}:/home/openttd/.openttd"], "params": "",
        "ports": [["port", "Spielport (TCP+UDP)", 3979, "tcp,udp", 3979]], "web": False,
        "status": ("tcp", "port"), "join": ("addr", "port"),
    },
    "amongus": {
        "label": "Among Us (Impostor)", "short": "Among Us", "color": "#c51111", "appid": 945360, "image": "aeonlucid/impostor:nightly",
        "uid": 0, "gid": 0, "env": ["IMPOSTOR_Server__PublicIp={host}", "IMPOSTOR_Server__PublicPort={port}"], "binds": [], "params": "",
        "ports": [["port", "Spielport (UDP)", 22023, "udp", 22023]], "web": False,
        "status": ("container",), "join": ("addr", "port"),
        "hint": "Im Spiel einen eigenen Server mit dieser Adresse hinzufügen (z. B. über impostor.github.io/Impostor).",
    },
}


def fields(key: str) -> list:
    c = CATALOG[key]
    out = [["name", "Container-Name", "text", f"{key}-{{n}}", ""]]
    out += [list(f) for f in c.get("fields", [])]
    for f, label, default, proto, _ in c["ports"]:
        out.append([f, label, "number", str(default), ""])
    if c.get("web"):
        out.append(["web_port", "Webkonsole (TCP)", "number", "9040", "Server-Konsole im Browser"])
    if "{params}" in " ".join(c["env"]):
        out.append(["params", "Startparameter", "text", c.get("params", ""), "werden an den Server übergeben"])
    if c.get("steam_login"):
        out.append(["steam_user", "Steam-Benutzer (Spiel muss im Konto sein)", "text", "", "Steam Guard muss aus sein"])
        out.append(["steam_pw", "Steam-Passwort", "password", "", ""])
    return out


def port_plan(key: str) -> list:
    c = CATALOG[key]
    plan = [(f, d, 1, 1) for f, _, d, _, _ in c["ports"]]
    if c.get("web"):
        plan.append(("web_port", 9040, 1, 1))
    return plan

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
        "env": ICH_ENV + ["GAME_ID=349090"], "binds": ICH_BINDS, "params": "+set net_strict 1 +set sv_hostname Quake#1 +set g_gametype 0 +set sv_maxClients 16 +map campgrounds ffa",
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
        "fields": [["server_name", "Servername", "text", "Zomboid #{n}", ""], ["admin_pw", "Admin-Passwort", "password", "", ""]],
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
        "fields": [["server_name", "Servername", "text", "V Rising #{n}", ""]],
        "status": ("a2s", "query_port"), "join": ("addr", "port"),
    },
    "abioticfactor": {
        "label": "Abiotic Factor", "short": "Abiotic", "color": "#4f8f6b", "appid": 427410, "image": _ich("abioticfactor"), "uid": 99, "gid": 100,
        "env": ICH_ENV + ["GAME_ID=2857200"], "binds": ICH_BINDS, "params": "-SteamServerName=Abiotic#1 -MaxServerPlayers=6",
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
        "fields": [["server_name", "Servername", "text", "Enshrouded #{n}", ""], ["password", "Passwort", "text", "", ""]],
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



def _src(label, short, color, appid, tag, game_id, params, host_port, hint=""):
    """Source-/GoldSrc-Server von ich777: ein Port (TCP+UDP), Status per A2S, Beitreten per steam://connect."""
    e = {"label": label, "short": short, "color": color, "appid": appid, "image": _ich(tag), "uid": 99, "gid": 100,
         "env": ICH_ENV + [f"GAME_ID={game_id}"], "binds": ICH_BINDS, "params": params,
         "ports": [["port", "Spielport (TCP+UDP)", host_port, "tcp,udp", 27015]], "web": True,
         "status": ("a2s", "port"), "join": ("steam", "port")}
    if hint:
        e["hint"] = hint
    return e


def _ue(label, short, color, appid, tag, game_id, params, ports, status_port="query_port", join_port="port", **extra):
    """Andere ich777-SteamCMD-Server (Unreal/Unity …): mehrere Ports, Status per A2S am Query-Port, Adresse kopieren."""
    e = {"label": label, "short": short, "color": color, "appid": appid, "image": _ich(tag), "uid": 99, "gid": 100,
         "env": ICH_ENV + [f"GAME_ID={game_id}"], "binds": ICH_BINDS, "params": params, "ports": ports, "web": True,
         "status": ("a2s", status_port) if status_port else ("container",), "join": ("addr", join_port)}
    e.update(extra)
    return e


# Zusätzliche Spiele – Auswahl nach den AMP-Templates (CubeCoders/AMPTemplates), umgesetzt mit den
# SteamCMD-Images von ich777 (Standardwerte aus ich777/docker-templates).
CATALOG.update({
    # --- Klassiker (GoldSrc / Source) ---
    "cs16": _src("Counter-Strike 1.6", "CS 1.6", "#d9a441", 10, "cstrike1.6", "90", "+maxplayers 16 +map de_dust2 +sv_lan 1", 27070),
    "czero": _src("Counter-Strike: Condition Zero", "CS:CZ", "#c98b2e", 80, "cstrikeczero", "90 +app_set_config '90 mod czero'",
                  "+maxplayers 16 +map de_dust2_cz +sv_lan 1", 27071),
    "dod": _src("Day of Defeat", "DoD", "#6b7a3a", 30, "dodclassic", "90 +app_set_config '90 mod dod'",
                "+maxplayers 24 +map dod_avalanche +sv_lan 1", 27073),
    "dods": _src("Day of Defeat: Source", "DoD:S", "#7d8b3f", 300, "dods", "232290", "+maxplayers 24 +map dod_avalanche +sv_lan 1", 27074),
    "tfc": _src("Team Fortress Classic", "TFC", "#b5562b", 20, "tf", "90 +app_set_config '90 mod tfc'", "+maxplayers 24 +map 2fort +sv_lan 1", 27075),
    "hldm": _src("Half-Life Deathmatch", "HLDM", "#e07b1a", 70, "hldm", "90", "+maxplayers 16 +map crossfire +sv_lan 1", 27076),
    "hl2dm": _src("Half-Life 2: Deathmatch", "HL2DM", "#f08c1a", 320, "hl2dm", "232370", "+maxplayers 16 +map dm_lockdown +sv_lan 1", 27077),
    "svencoop": _src("Sven Co-op", "Sven", "#4a7fb5", 225840, "svencoop", "276060",
                     "+maxplayers 16 +map hl_c00.bsp +servercfgfile servers/server.cfg", 27078),
    "l4d": _src("Left 4 Dead", "L4D", "#8f2f24", 500, "l4d", "222840", "+map l4d_hospital01_apartment +sv_lan 1", 27079),
    "nmrih": _src("No More Room in Hell", "NMRiH", "#7a1f1f", 224260, "nomoreroominhell", "317670", "+map nmo_broadway -maxplayers 8 +sv_lan 1", 27080),
    "zps": _src("Zombie Panic! Source", "ZPS", "#5e7d2e", 17500, "zombiepanic", "17505", "+maxplayers 16 +map zpo_biotec +sv_lan 1", 27081),
    "fof": _src("Fistful of Frags", "FoF", "#a0743c", 265630, "fistfuloffrags", "295230", "+maxplayers 16 +map fof_fistful +sv_lan 1", 27082),
    "pvkii": _src("Pirates, Vikings & Knights II", "PVKII", "#3c6e8f", 17570, "pvkii", "17575", "+maxplayers 16 +map bt_island +sv_lan 1", 27083),
    "asrd": _src("Alien Swarm: Reactive Drop", "AS:RD", "#3f8f8f", 563560, "alienswarmreactivedrop", "563560",
                 "+map lobby -maxplayers 4 +exec server.cfg", 27084),
    # --- Koop & Survival ---
    "killingfloor": _ue("Killing Floor", "KF", "#8a1515", 1250, "killingfloor", "215360",
                        "KF-bioticslab.rom?game=KFmod.KFGameType?VACSecured=true?MaxPlayers=6",
                        [["port", "Spielport (UDP)", 7707, "udp", 7707], ["query_port", "Query-Port (UDP)", 7708, "udp", 7708],
                         ["port3", "GameSpy (UDP)", 7717, "udp", 7717], ["port4", "Master (TCP+UDP)", 28852, "tcp,udp", 28852],
                         ["admin_port", "Web-Admin (TCP)", 8075, "tcp", 8075]]),
    "unturned": _ue("Unturned", "Unturned", "#6b8f3a", 304930, "unturned", "1110390", "-pei -normal -nosync -pve",
                    [["port", "Spielport (TCP+UDP)", 27085, "tcp,udp", 27015], ["query_port", "Query-Port (TCP+UDP)", 27086, "tcp,udp", 27016],
                     ["port3", "Port +2 (TCP+UDP)", 27087, "tcp,udp", 27017]]),
    "barotrauma": _ue("Barotrauma", "Barotrauma", "#2f6f8f", 602960, "barotrauma", "1026340", "",
                      [["port", "Spielport (UDP)", 27090, "udp", 27015], ["query_port", "Query-Port (UDP)", 27091, "udp", 27016]]),
    "sotf": _ue("Sons of the Forest", "SotF", "#3a5f3a", 1326470, "sonsoftheforest", "2465200", "",
                [["port", "Spielport (UDP)", 8766, "udp", 8766], ["query_port", "Query-Port (UDP)", 27216, "udp", 27016],
                 ["port3", "Blob-Sync (UDP)", 9700, "udp", 9700]]),
    "theforest": _ue("The Forest", "Forest", "#4a6b3a", 242760, "theforest", "556450", "",
                     [["port", "Spielport (UDP)", 8776, "udp", 8766], ["query_port", "Query-Port (UDP)", 27235, "udp", 27015],
                      ["port3", "Steam (UDP)", 27236, "udp", 27016]]),
    "conanexiles": _ue("Conan Exiles", "Conan", "#a8742f", 440900, "conanexiles", "443030", "",
                       [["port", "Spielport (TCP+UDP)", 7807, "tcp,udp", 7777], ["port2", "Port +1 (UDP)", 7808, "udp", 7778],
                        ["query_port", "Query-Port (UDP)", 27245, "udp", 27015]]),
    "icarus": _ue("Icarus", "Icarus", "#c46a2b", 1149460, "icarus", "2089300", '-SteamServerName="Icarus #1" -Port=17777 -QueryPort=27015',
                  [["port", "Spielport (UDP)", 17777, "udp", 17777], ["query_port", "Query-Port (UDP)", 27255, "udp", 27015]]),
    "soulmask": _ue("Soulmask", "Soulmask", "#8f6a3a", 2646460, "soulmask", "3017300",
                    '-SteamServerName="Soulmask #1" -MaxPlayers=20 -pve -Port=8777 -QueryPort=27015 -EchoPort=18888',
                    [["port", "Spielport (UDP)", 8777, "udp", 8777], ["query_port", "Query-Port (UDP)", 27265, "udp", 27015]]),
    "rust": _ue("Rust", "Rust", "#ce422b", 252490, "rust", "258550", "+server.maxplayers 16 +server.worldsize 3000",
                [["port", "Spielport (UDP)", 28015, "udp", 28015], ["query_port", "Query-Port (UDP)", 28016, "udp", 28016],
                 ["rcon_port", "Web-RCON (TCP)", 28017, "tcp", 28017], ["app_port", "Rust+ App (TCP)", 28018, "tcp", 28018]],
                hint="Braucht viel RAM (8–12 GB) und lädt beim ersten Start lange."),
    "mordhau": _ue("Mordhau", "Mordhau", "#7a2f2f", 629760, "mordhau", "629800", "",
                   [["port", "Spielport (UDP)", 7797, "udp", 7777], ["query_port", "Query-Port (UDP)", 27275, "udp", 27015],
                    ["port3", "Beacon (UDP)", 15000, "udp", 15000]]),
    "avorion": _ue("Avorion", "Avorion", "#4a5f8f", 445220, "avorion", "565060", "",
                   [["port", "Spielport (TCP+UDP)", 27000, "tcp,udp", 27000], ["port2", "Port 27003 (UDP)", 27003, "udp", 27003],
                    ["query_port", "Query-Port (UDP)", 27020, "udp", 27020], ["port4", "Port 27021 (UDP)", 27021, "udp", 27021]]),
    "starbound": _ue("Starbound", "Starbound", "#5a4f8f", 211820, "starbound", "533830", "",
                     [["port", "Spielport (TCP)", 21025, "tcp", 21025]], status_port=None, steam_login=True,
                     hint="Der Server wird über deinen Steam-Account geladen (Spiel muss im Konto sein)."),
    "scpsl": _ue("SCP: Secret Laboratory", "SCP:SL", "#5a5a5a", 700330, "scp-secretlaboratory", "996560", "",
                 [["port", "Spielport (TCP+UDP)", 7817, "tcp,udp", 7777]], status_port=None),
    "craftopia": _ue("Craftopia", "Craftopia", "#4fa86b", 1307550, "craftopia", "1670340", "",
                     [["port", "Spielport (TCP+UDP)", 8787, "tcp,udp", 8787]], status_port=None),
    "eco": _ue("Eco", "Eco", "#3f8f5a", 382310, "eco", "739590", "",
               [["port", "Spielport (UDP)", 3000, "udp", 3000], ["web_ui", "Web-Oberfläche (TCP)", 3001, "tcp", 3001]], status_port=None),
    "necesse": _ue("Necesse", "Necesse", "#6b8fa8", 1169040, "necesse", "1169370", "",
                   [["port", "Spielport (UDP)", 14159, "udp", 14159]], status_port=None),
    "corekeeper": _ue("Core Keeper", "Core Keeper", "#a8853f", 1621690, "corekeeper", "1963720", "",
                      [["port", "Spielport (UDP, nur Direkt-IP)", 27095, "udp", 27015]], status_port=None,
                      hint="Beitreten per Game-ID: Die ID steht nach dem Start im Container-Log bzw. in GameID.txt."),
})

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

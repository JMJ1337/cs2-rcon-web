"""Bekannte Fehler in den Container-Logs erkennen und eine Lösung vorschlagen."""
import re
import time
from datetime import datetime

from . import docker_api

# (Spiele oder None = alle, Muster, Titel, Lösung)
RULES = [
    (("cs2", "tf2"), r"(token is already in use|already in use by another|GSLT.*in use|sv_setsteamaccount.*in use)",
     "Steam-Token wird schon benutzt",
     "Jeder Server braucht einen eigenen Token (GSLT). Im Container-Tab „Steam-Token tauschen“ klicken (nimmt einen freien aus Einstellungen → Steam-Tokens oder erstellt einen) – bei Portainer-Stacks dort TOKEN ändern."),
    (("cs2", "tf2"), r"(Invalid token|token.*(expired|invalid|banned)|Login Failure: Invalid|STEAM_LOGON_.*(INVALID|BANNED))",
     "Steam-Token ungültig oder abgelaufen",
     "Unter Einstellungen → Steam-Tokens „Erneuern“ bzw. im Container-Tab „Steam-Token tauschen“ – oder auf steamcommunity.com/dev/managegameservers neu erzeugen (App 730 CS2, 440 TF2)."),
    (None, r"(No space left on device|disk write failure|state is 0x202|state is 0x212)",
     "Speicherplatz voll",
     "Auf dem NAS/Datenträger Platz schaffen (alte Server, Lancache-Limit verkleinern) und den Container neu starten."),
    (None, r"(state is 0x602|state is 0x206|Permission denied|EACCES|Operation not permitted|Access to the path .* is denied)",
     "Keine Schreibrechte im Datenordner (oder Schreibfehler auf dem NAS)",
     "SteamCMD meldet 0x602 auch bei Schreibproblemen auf NFS. Rechte des Datenordners für den Container-Benutzer setzen (z. B. chown -R 1000:1000 <Ordner>; Wreckfest 99:100, TeamSpeak 9987) bzw. auf dem NAS Schreibrechte vergeben."),
    (None, r"(Address already in use|bind\(\) failed|Failed to bind|couldn't allocate any server IP port|Could not bind|EADDRINUSE|port is already allocated)",
     "Port ist schon belegt",
     "Ein anderer Server/Container nutzt denselben Port. Ports beim Anlegen nicht doppelt vergeben – Server mit freiem Port neu anlegen oder den anderen stoppen."),
    (None, r"(java\.lang\.OutOfMemoryError|Out of memory|Cannot allocate memory|std::bad_alloc|Killed process)",
     "Zu wenig Arbeitsspeicher",
     "Dem Server mehr RAM geben (Minecraft: MEMORY erhöhen) oder andere Server stoppen."),
    (None, r"Failed to install app '\d+' \(Invalid platform\)",
     "SteamCMD: „Invalid platform“",
     "Bekannter SteamCMD-Fehler (z. B. Left 4 Dead 2). Im Container-Tab „Steam-Installation reparieren“ klicken – lädt einmal als Windows und dann als Linux."),
    (None, r"(Error! App '\d+' state is 0x[0-9a-f]+ after update job|Failed to install app|ERROR! Failed to install)",
     "Installation/Update über Steam fehlgeschlagen",
     "Container neu starten; bleibt der Fehler, Speicherplatz und Rechte prüfen bzw. mit VALIDATE/validate neu prüfen lassen."),
    (None, r"(Login Failure: No Connection|Connection to Steam servers failed|Failed to connect to Steam|Steam connection timed out)",
     "Keine Verbindung zu Steam",
     "Internet/DNS des Docker-Hosts prüfen (Lancache-DNS erreichbar?). Danach Container neu starten."),
    (("minecraft",), r"(You need to agree to the EULA|EULA.*not accepted)",
     "Minecraft-EULA nicht akzeptiert", "Umgebungsvariable EULA=TRUE setzen und Container neu starten."),
    (("minecraft",), r"(UnsupportedClassVersionError|requires running the server with Java|has been compiled by a more recent version of the Java)",
     "Falsche Java-Version", "Passendes Image-Tag wählen (z. B. itzg/minecraft-server:java21 bzw. :java17 für alte Versionen/Mods)."),
    (("minecraft",), r"(Failed to start the minecraft server|Encountered an unexpected exception|Mod .* requires|Missing mods?(?![.\w]))",
     "Minecraft startet nicht (Mods/Welt)", "Log im Container-Tab prüfen: fehlende oder unpassende Mods entfernen bzw. Version/Loader angleichen."),
    (("teamspeak",), r"(license.*(not accepted|accept)|TS3SERVER_LICENSE)",
     "TeamSpeak-Lizenz nicht akzeptiert", "Umgebungsvariable TS3SERVER_LICENSE=accept setzen."),
    (("valheim",), r"(password.*(too short|at least 5)|Password matches server name)",
     "Valheim-Passwort ungültig", "Passwort mit mindestens 5 Zeichen, das nicht im Servernamen vorkommt."),
    (("factorio",), r"(Couldn't acquire exclusive lock|Error .*MapDeserialiser|Map version .* cannot be loaded)",
     "Factorio-Spielstand kann nicht geladen werden", "Spielstand passt nicht zur Version oder ist gesperrt – Container neu starten oder passende Version wählen."),
    (("satisfactory",), r"(Failed to bind to|LogNet: Error)",
     "Satisfactory-Netzwerkfehler", "Ports 7777 TCP+UDP und 8888 TCP prüfen (nicht doppelt belegt) und Container neu starten."),
]
IGNORE = re.compile(r"(GU resource .* version mismatch|\[S_API FAIL\]|flock /sys/devices|SteamAPI_Init|breakpad|ConVarRef|Unknown command)", re.I)
_COMPILED = [(g, re.compile(p, re.I), t, s) for g, p, t, s in RULES]

state: dict[str, dict] = {}     # Container -> {"problems": [...], "checked": t}


def _ts(line: str):
    m = re.match(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.\d+)?Z?\s(.*)$", line)
    if not m:
        return None, line
    try:
        return datetime.fromisoformat(m.group(1) + "+00:00").timestamp(), m.group(2)
    except ValueError:
        return None, m.group(2)


def analyze(text: str, game: str, since: float | None = None) -> list[dict]:
    found: dict[str, dict] = {}
    for raw in text.splitlines():
        t, line = _ts(raw)
        if since and t and t < since:
            continue
        line = re.sub(r"\x1b\[[0-9;]*m", "", line).strip()
        if not line or IGNORE.search(line):
            continue
        for games, rx, title, sol in _COMPILED:
            if games and game not in games:
                continue
            if rx.search(line):
                found[title] = {"title": title, "solution": sol, "line": line[:240], "t": t}
                break           # pro Zeile nur die genaueste Erklärung
    return sorted(found.values(), key=lambda x: -(x["t"] or 0))


def _hexip(h: str) -> str:
    return ".".join(str(int(h[k:k + 2], 16)) for k in (6, 4, 2, 0))


async def connections(container: str) -> dict:
    """Aktive TCP-Verbindungen des Containers: {ip:port: anzahl}."""
    out = await docker_api.exec_cmd(container, ["sh", "-c", "cat /proc/net/tcp 2>/dev/null"], timeout=10)
    res: dict[str, int] = {}
    for line in out.splitlines()[1:]:
        p = line.split()
        if len(p) > 3 and p[3] == "01" and ":" in p[2]:
            h, port = p[2].split(":")
            k = f"{_hexip(h)}:{int(port, 16)}"
            res[k] = res.get(k, 0) + 1
    return res


async def check(container: str, game: str, downloading: bool = False, cache_ips: list[str] | None = None) -> dict:
    try:
        info = await docker_api.inspect(container)
        st = info.get("State") or {}
        started = None
        if st.get("StartedAt") and not st["StartedAt"].startswith("0001"):
            started = datetime.fromisoformat(st["StartedAt"][:19] + "+00:00").timestamp()
        r = await docker_api._req("GET", f"/containers/{container}/logs",
                                  params={"stdout": "1", "stderr": "1", "tail": "800", "timestamps": "1"})
        raw = r.content
        text = raw.decode("utf-8", "replace") if info.get("Config", {}).get("Tty") else docker_api._demux(raw)
        # Fehler seit dem letzten Start; bei Neustart-Schleife auch die davor
        restarts = info.get("RestartCount") or 0
        probs = analyze(text, game, None if restarts and st.get("Restarting") else (started - 5 if started else None))
        if st.get("OOMKilled"):
            probs.insert(0, {"title": "Vom System wegen RAM beendet (OOM)", "line": "OOMKilled",
                             "solution": "Mehr Arbeitsspeicher freigeben bzw. dem Server weniger RAM zuweisen (Minecraft: MEMORY).", "t": None})
        if st.get("Restarting") or (restarts >= 3 and started and time.time() - started < 600):
            probs.append({"title": f"Container startet ständig neu ({restarts}×)", "line": st.get("Error") or "",
                          "solution": "Siehe Fehler oben bzw. Log im Container-Tab – meist Port, Rechte oder Konfiguration.", "t": None})
        if downloading and cache_ips and st.get("Running"):
            try:
                conns = await connections(container)
                via_cache = sum(n for k, n in conns.items() if k.split(":")[0] in cache_ips and k.endswith(":80"))
                direct = sum(n for k, n in conns.items() if k.endswith(":443") and k.split(":")[0] not in cache_ips)
                if direct >= 3 and via_cache == 0:
                    probs.append({"title": "Update lädt am Lancache vorbei",
                                  "solution": f"SteamCMD holt die Daten verschlüsselt direkt von Steam ({direct} HTTPS-Verbindungen, keine zum Cache) – "
                                              "das wird nicht gecacht und zählt nicht im Lancache-Durchsatz.",
                                  "line": ", ".join(sorted(conns)[:4]), "t": None, "level": "info"})
            except docker_api.DockerError:
                pass
        res = {"problems": probs[:4], "checked": time.time()}
    except docker_api.DockerError as e:
        res = {"problems": [], "checked": time.time(), "error": str(e)}
    state[container] = res
    return res


def status_hints(game: str, st: dict) -> list[dict]:
    """Hinweise aus dem Spielstatus (z. B. RCON-'status')."""
    raw = st.get("raw") or ""
    out = []
    if game in ("cs2", "tf2") and re.search(r"account\s*:\s*not logged in", raw):
        out.append({"title": "Kein Steam-Token eingetragen",
                    "solution": "Server läuft ohne Login – im LAN beitretbar, aber nicht in der Internet-Serverliste. Für öffentliche Sichtbarkeit Token (GSLT) eintragen.",
                    "line": "account : not logged in", "t": None, "level": "info"})
    return out

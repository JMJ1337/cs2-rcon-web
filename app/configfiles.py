"""Konfigurationsdateien der Spielserver lesen/schreiben (im Container, als Besitzer der Datei).

Je Spiel: bekannte Dateien (Pfad im Container) und – wo sinnvoll – ein Formular mit beschrifteten Feldern.
"""
import base64
import json
import re
import shlex

from . import docker_api

SF = "/serverdata/serverfiles"

# Spiel -> Liste von {path, label, fmt: properties|ini|json|xml|text, fields: [[key, label, type, opts]]}
FILES = {
    "cs2": [{"path": "/home/steam/cs2-dedicated/game/csgo/cfg/server.cfg", "label": "server.cfg", "fmt": "text"},
            {"path": "/home/steam/cs2-dedicated/game/csgo/cfg/gamemode_competitive_server.cfg", "label": "gamemode_competitive_server.cfg", "fmt": "text"}],
    "tf2": [{"path": "/home/steam/tf-dedicated/tf/cfg/server.cfg", "label": "server.cfg", "fmt": "text"},
            {"path": "/home/steam/tf-dedicated/tf/cfg/mapcycle.txt", "label": "mapcycle.txt (Map-Rotation)", "fmt": "text"},
            {"path": "/home/steam/tf-dedicated/tf/cfg/motd.txt", "label": "motd.txt (Begrüßung)", "fmt": "text"}],
    "minecraft": [{"path": "/data/server.properties", "label": "server.properties", "fmt": "properties", "fields": [
        ["motd", "Servername (MOTD)", "text"], ["max-players", "Max. Spieler", "number"],
        ["gamemode", "Spielmodus", "select", ["survival", "creative", "adventure", "spectator"]],
        ["difficulty", "Schwierigkeit", "select", ["peaceful", "easy", "normal", "hard"]],
        ["hardcore", "Hardcore", "bool"], ["pvp", "PvP", "bool"], ["white-list", "Whitelist aktiv", "bool"],
        ["online-mode", "Nur echte Accounts (online-mode)", "bool"], ["allow-flight", "Fliegen erlauben (Mods)", "bool"],
        ["view-distance", "Sichtweite (Chunks)", "number"], ["simulation-distance", "Simulationsweite (Chunks)", "number"],
        ["spawn-protection", "Spawn-Schutz (Blöcke)", "number"], ["level-seed", "Welt-Seed (neue Welt)", "text"],
        ["enable-command-block", "Befehlsblöcke", "bool"], ["max-world-size", "Max. Weltgröße", "number"]]},
        {"path": "/data/whitelist.json", "label": "whitelist.json", "fmt": "json"}, {"path": "/data/ops.json", "label": "ops.json", "fmt": "json"}],
    "factorio": [{"path": "/factorio/config/server-settings.json", "label": "server-settings.json", "fmt": "json", "fields": [
        ["name", "Servername", "text"], ["description", "Beschreibung", "text"], ["max_players", "Max. Spieler (0 = ∞)", "number"],
        ["game_password", "Spiel-Passwort", "text"], ["visibility.lan", "Im LAN sichtbar", "bool"], ["visibility.public", "Öffentlich gelistet", "bool"],
        ["require_user_verification", "Factorio-Login nötig", "bool"], ["autosave_interval", "Autosave alle (Min.)", "number"],
        ["autosave_slots", "Autosave-Plätze", "number"], ["afk_autokick_interval", "AFK-Kick nach (Min., 0 = aus)", "number"],
        ["auto_pause", "Pausieren ohne Spieler", "bool"], ["only_admins_can_pause_the_game", "Nur Admins dürfen pausieren", "bool"],
        ["max_upload_in_kilobytes_per_second", "Upload-Limit (KB/s, 0 = ∞)", "number"]]},
        {"path": "/factorio/config/server-adminlist.json", "label": "server-adminlist.json (Admins)", "fmt": "json"},
        {"path": "/factorio/config/map-settings.json", "label": "map-settings.json", "fmt": "json"}],
    "valheim": [{"path": "/config/adminlist.txt", "label": "adminlist.txt (SteamIDs)", "fmt": "text"},
                {"path": "/config/permittedlist.txt", "label": "permittedlist.txt (Whitelist)", "fmt": "text"},
                {"path": "/config/bannedlist.txt", "label": "bannedlist.txt", "fmt": "text"}],
    "satisfactory": [{"path": "/config/gamefiles/FactoryGame/Saved/Config/LinuxServer/Game.ini", "label": "Game.ini", "fmt": "text"},
                     {"path": "/config/gamefiles/FactoryGame/Saved/Config/LinuxServer/Engine.ini", "label": "Engine.ini", "fmt": "text"}],
    "teamspeak": [{"path": "/var/ts3server/query_ip_allowlist.txt", "label": "query_ip_allowlist.txt", "fmt": "text"}],
    "l4d2": [{"path": f"{SF}/left4dead2/cfg/server.cfg", "label": "server.cfg", "fmt": "text"}],
    "garrysmod": [{"path": f"{SF}/garrysmod/cfg/server.cfg", "label": "server.cfg", "fmt": "text"}],
    "insurgency": [{"path": f"{SF}/Insurgency/Saved/Config/LinuxServer/Game.ini", "label": "Game.ini", "fmt": "text"},
                   {"path": f"{SF}/Insurgency/Config/Server/MapCycle.txt", "label": "MapCycle.txt", "fmt": "text"}],
    "quakelive": [{"path": f"{SF}/baseq3/server.cfg", "label": "server.cfg", "fmt": "text"},
                  {"path": f"{SF}/baseq3/mappool.txt", "label": "mappool.txt", "fmt": "text"}],
    "killingfloor2": [{"path": f"{SF}/KFGame/Config/PCServer-KFGame.ini", "label": "PCServer-KFGame.ini", "fmt": "text"},
                      {"path": f"{SF}/KFGame/Config/KFWeb.ini", "label": "KFWeb.ini (Web-Admin)", "fmt": "text"}],
    "7dtd": [{"path": f"{SF}/serverconfig.xml", "label": "serverconfig.xml", "fmt": "xml", "fields": [
        ["ServerName", "Servername", "text"], ["ServerPassword", "Passwort", "text"], ["ServerMaxPlayerCount", "Max. Spieler", "number"],
        ["GameWorld", "Welt", "text"], ["WorldGenSeed", "Seed", "text"], ["GameDifficulty", "Schwierigkeit (0–5)", "number"],
        ["DayNightLength", "Tageslänge (Min.)", "number"], ["BloodMoonFrequency", "Blutmond alle (Tage)", "number"],
        ["LootAbundance", "Loot (%)", "number"], ["XPMultiplier", "XP (%)", "number"], ["ServerVisibility", "Sichtbarkeit (0 = privat, 1 = Freunde, 2 = öffentlich)", "number"],
        ["EACEnabled", "Easy Anti-Cheat", "bool"]]}],
    "projectzomboid": [{"path": "/serverdata/Zomboid/Server/servertest.ini", "label": "servertest.ini", "fmt": "properties", "fields": [
        ["PublicName", "Servername", "text"], ["Password", "Passwort", "text"], ["MaxPlayers", "Max. Spieler", "number"],
        ["PVP", "PvP", "bool"], ["PauseEmpty", "Pausieren ohne Spieler", "bool"], ["Public", "Öffentlich", "bool"],
        ["Mods", "Mods (Mod-IDs, ;-getrennt)", "text"], ["WorkshopItems", "Workshop-IDs (;-getrennt)", "text"]]},
        {"path": "/serverdata/Zomboid/Server/servertest_SandboxVars.lua", "label": "SandboxVars.lua", "fmt": "text"}],
    "palworld": [{"path": f"{SF}/Pal/Saved/Config/LinuxServer/PalWorldSettings.ini", "label": "PalWorldSettings.ini", "fmt": "text"}],
    "vrising": [{"path": f"{SF}/save-data/Settings/ServerHostSettings.json", "label": "ServerHostSettings.json", "fmt": "json", "fields": [
        ["Name", "Servername", "text"], ["Description", "Beschreibung", "text"], ["Password", "Passwort", "text"],
        ["MaxConnectedUsers", "Max. Spieler", "number"], ["MaxConnectedAdmins", "Max. Admins", "number"],
        ["AutoSaveInterval", "Autosave (s)", "number"], ["ListOnSteam", "In Steam gelistet", "bool"], ["ListOnEOS", "Auf EOS gelistet", "bool"],
        ["Secure", "VAC/sicher", "bool"], ["LanMode", "LAN-Modus", "bool"]]},
        {"path": f"{SF}/save-data/Settings/ServerGameSettings.json", "label": "ServerGameSettings.json", "fmt": "json"}],
    "abioticfactor": [{"path": f"{SF}/AbioticFactor/Saved/SaveGames/Server/Admin.ini", "label": "Admin.ini", "fmt": "text"}],
    "dontstarve": [{"path": "/serverdata/.klei/DoNotStarveTogether/Cluster_1/cluster.ini", "label": "cluster.ini", "fmt": "text"}],
    "enshrouded": [{"path": "/home/steam/enshrouded/enshrouded_server.json", "label": "enshrouded_server.json", "fmt": "json", "fields": [
        ["name", "Servername", "text"], ["slotCount", "Max. Spieler", "number"]]}],
    "assettocorsa": [{"path": f"{SF}/cfg/server_cfg.ini", "label": "server_cfg.ini (Strecke, Autos, Regeln)", "fmt": "text"},
                     {"path": f"{SF}/cfg/entry_list.ini", "label": "entry_list.ini (Startplätze)", "fmt": "text"}],
    "openttd": [{"path": "/home/openttd/.openttd/openttd.cfg", "label": "openttd.cfg", "fmt": "text"}],
    "wreckfest": [{"path": f"{SF}/server_config.cfg", "label": "server_config.cfg", "fmt": "text"}],
}


class ConfigError(Exception):
    pass


def files_for(game: str) -> list[dict]:
    return FILES.get(game, [])


def _spec(game: str, path: str) -> dict:
    for f in FILES.get(game, []):
        if f["path"] == path:
            return f
    raise ConfigError("Diese Datei ist für dieses Spiel nicht freigegeben")


async def read(container: str, game: str, path: str) -> dict:
    spec = _spec(game, path)
    q = shlex.quote(path)
    out = await docker_api.exec_cmd(container, ["sh", "-c", f"if [ -f {q} ]; then stat -c '%u:%g' {q}; echo '#--'; cat {q}; else echo '#MISSING'; fi"], timeout=20)
    if out.startswith("#MISSING"):
        return {"exists": False, "content": "", "values": {}, "spec": spec}
    owner, _, content = out.partition("#--\n")
    return {"exists": True, "owner": owner.strip(), "content": content, "values": parse(spec, content), "spec": spec}


async def write(container: str, game: str, path: str, content: str) -> None:
    spec = _spec(game, path)
    if spec["fmt"] == "json":
        try:
            json.loads(content)
        except ValueError as e:
            raise ConfigError(f"Kein gültiges JSON: {e}") from e
    q = shlex.quote(path)
    owner = (await docker_api.exec_cmd(container, ["sh", "-c", f"[ -f {q} ] && stat -c '%u:%g' {q} || stat -c '%u:%g' $(dirname {q})"], timeout=20)).strip()
    b64 = base64.b64encode(content.encode()).decode()
    script = f"[ -f {q} ] && cp {q} {q}.bak 2>/dev/null; echo {b64} | base64 -d > {q}.tmp && mv {q}.tmp {q} && echo OK"
    user = owner if re.fullmatch(r"\d+:\d+", owner or "") else ""
    out = await docker_api.exec_cmd(container, ["sh", "-c", script], timeout=30, user=user)
    if "OK" not in out:
        # Fallback als root (z. B. wenn der Besitzer im Container keine Shell hat)
        out = await docker_api.exec_cmd(container, ["sh", "-c", script], timeout=30)
        if "OK" not in out:
            raise ConfigError(f"Schreiben fehlgeschlagen: {out.strip()[:200]}")


# ---------------------------------------------------------------- Formulare
def _get(d, dotted):
    for k in dotted.split("."):
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def _set(d, dotted, v):
    ks = dotted.split(".")
    for k in ks[:-1]:
        d = d.setdefault(k, {})
    d[ks[-1]] = v


def parse(spec: dict, content: str) -> dict:
    fields = spec.get("fields") or []
    if not fields:
        return {}
    keys = [f[0] for f in fields]
    vals = {}
    if spec["fmt"] in ("properties", "ini"):
        for line in content.splitlines():
            m = re.match(r"^\s*([A-Za-z0-9_.\-]+)\s*=\s*(.*?)\s*$", line)
            if m and m.group(1) in keys:
                vals[m.group(1)] = m.group(2)
    elif spec["fmt"] == "json":
        try:
            j = json.loads(content)
        except ValueError:
            return {}
        for k in keys:
            v = _get(j, k)
            if v is not None:
                vals[k] = v
    elif spec["fmt"] == "xml":
        for k in keys:
            m = re.search(rf'<property\s+name="{re.escape(k)}"\s+value="([^"]*)"', content)
            if m:
                vals[k] = m.group(1)
    return vals


def apply(spec: dict, content: str, changes: dict) -> str:
    fields = {f[0]: f for f in spec.get("fields") or []}
    changes = {k: v for k, v in changes.items() if k in fields}

    def conv(k, v):
        t = fields[k][2]
        if t == "bool":
            return bool(v) if spec["fmt"] == "json" else ("true" if v in (True, "true", "1", 1) else "false")
        if t == "number":
            try:
                n = float(v)
                return (int(n) if n == int(n) else n) if spec["fmt"] == "json" else str(int(n) if n == int(n) else n)
            except (TypeError, ValueError):
                raise ConfigError(f"{fields[k][1]}: Zahl erwartet") from None
        return str(v).replace("\n", " ")

    if spec["fmt"] in ("properties", "ini"):
        lines = content.splitlines()
        for k, v in changes.items():
            val = conv(k, v)
            for i, line in enumerate(lines):
                if re.match(rf"^\s*{re.escape(k)}\s*=", line):
                    lines[i] = f"{k}={val}"
                    break
            else:
                lines.append(f"{k}={val}")
        return "\n".join(lines) + "\n"
    if spec["fmt"] == "json":
        j = json.loads(content) if content.strip() else {}
        for k, v in changes.items():
            _set(j, k, conv(k, v))
        return json.dumps(j, indent=2, ensure_ascii=False) + "\n"
    if spec["fmt"] == "xml":
        out = content
        for k, v in changes.items():
            val = conv(k, v).replace('"', "&quot;")
            out, n = re.subn(rf'(<property\s+name="{re.escape(k)}"\s+value=")[^"]*(")', rf"\g<1>{val}\g<2>", out)
            if not n:
                out = out.replace("</ServerSettings>", f'\t<property name="{k}" value="{val}"/>\n</ServerSettings>')
        return out
    raise ConfigError("Für diese Datei gibt es kein Formular")

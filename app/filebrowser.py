"""Datei-Browser für Spielserver-Container und Spielstände.

Erlaubt sind nur die eingebundenen Datenordner des Containers (Binds/Volumes), damit niemand im Container-System herumschreibt.
Lesen/Schreiben per docker exec (als Besitzer der Datei), Herunterladen/Hochladen per Docker-Archiv-API (tar).
"""
import base64
import io
import posixpath
import re
import shlex
import tarfile
import time

from . import docker_api

MAX_EDIT = 2 * 1024 * 1024
TEXT_EXT = re.compile(r"\.(cfg|ini|txt|json|xml|properties|yml|yaml|lua|conf|log|sh|toml|csv|md|js|vdf|acf)$", re.I)

SF = "/serverdata/serverfiles"
SAVES = {
    "satisfactory": ["/config/saved/server", "/config/gamefiles/FactoryGame/Saved/SaveGames"],
    "factorio": ["/factorio/saves"],
    "valheim": ["/config/worlds_local", "/config/backups"],
    "minecraft": ["/data/world", "/data/world_nether", "/data/world_the_end"],
    "terraria": ["/root/.local/share/Terraria/Worlds"],
    "7dtd": ["/serverdata/.local/share/7DaysToDie/Saves", f"{SF}/Saves"],
    "projectzomboid": ["/serverdata/Zomboid/Saves", "/serverdata/Zomboid/backups"],
    "palworld": [f"{SF}/Pal/Saved/SaveGames"],
    "vrising": [f"{SF}/save-data/Saves"],
    "enshrouded": ["/home/steam/enshrouded/savegame"],
    "openttd": ["/home/openttd/.openttd/save"],
    "dontstarve": ["/serverdata/.klei/DoNotStarveTogether"],
    "abioticfactor": [f"{SF}/AbioticFactor/Saved/SaveGames"],
    "wreckfest": [],
}


class FileError(Exception):
    pass


async def roots(container: str) -> list[str]:
    info = await docker_api.inspect(container)
    out = []
    for m in info.get("Mounts") or []:
        d = m.get("Destination") or ""
        if d and not d.startswith(("/var/run", "/etc", "/proc", "/sys", "/dev")) and d not in ("/", "/tmp"):
            out.append(d.rstrip("/") or "/")
    return sorted(set(out))


def _norm(path: str) -> str:
    p = posixpath.normpath("/" + (path or "").lstrip("/"))
    if "\x00" in p:
        raise FileError("Ungültiger Pfad")
    return p


async def check(container: str, path: str) -> str:
    p = _norm(path)
    rs = await roots(container)
    if not any(p == r or p.startswith(r.rstrip("/") + "/") for r in rs):
        raise FileError("Nur innerhalb der Datenordner des Servers erlaubt: " + ", ".join(rs))
    return p


async def listdir(container: str, path: str) -> dict:
    p = await check(container, path)
    q = shlex.quote(p)
    out = await docker_api.exec_cmd(container, ["sh", "-c",
        f"[ -d {q} ] || {{ echo '#NODIR'; exit 0; }}; cd {q} && for f in .* *; do [ \"$f\" = . ] || [ \"$f\" = .. ] || [ ! -e \"$f\" ] && continue; "
        f"if [ -d \"$f\" ]; then t=d; else t=f; fi; printf '%s\\t%s\\t%s\\t%s\\n' \"$t\" \"$(stat -c %s \"$f\" 2>/dev/null)\" \"$(stat -c %Y \"$f\" 2>/dev/null)\" \"$f\"; done"],
        timeout=20)
    if out.startswith("#NODIR"):
        raise FileError("Ordner gibt es nicht")
    items = []
    for line in out.splitlines():
        parts = line.split("\t", 3)
        if len(parts) == 4:
            t, size, mt, name = parts
            items.append({"name": name, "dir": t == "d", "size": int(size) if size.isdigit() else None,
                          "mtime": int(mt) if mt.isdigit() else None,
                          "text": t == "f" and bool(TEXT_EXT.search(name))})
    items.sort(key=lambda x: (not x["dir"], x["name"].lower()))
    return {"path": p, "items": items}


async def read_text(container: str, path: str) -> dict:
    p = await check(container, path)
    q = shlex.quote(p)
    size = (await docker_api.exec_cmd(container, ["sh", "-c", f"stat -c %s {q} 2>/dev/null || echo -1"], timeout=10)).strip()
    if not size.lstrip("-").isdigit() or int(size) < 0:
        raise FileError("Datei gibt es nicht")
    if int(size) > MAX_EDIT:
        raise FileError("Datei zu groß zum Bearbeiten – bitte herunterladen")
    out = await docker_api.exec_cmd(container, ["sh", "-c", f"base64 {q} | tr -d '\\n'"], timeout=20)
    try:
        raw = base64.b64decode(out.strip())
    except ValueError as e:
        raise FileError("Datei konnte nicht gelesen werden") from e
    if b"\x00" in raw[:4096]:
        raise FileError("Binärdatei – bitte herunterladen")
    return {"path": p, "content": raw.decode("utf-8", "replace"), "size": int(size)}


async def write_text(container: str, path: str, content: str) -> None:
    p = await check(container, path)
    q = shlex.quote(p)
    owner = (await docker_api.exec_cmd(container, ["sh", "-c", f"stat -c '%u:%g' {q} 2>/dev/null || stat -c '%u:%g' $(dirname {q})"], timeout=10)).strip()
    b64 = base64.b64encode(content.encode()).decode()
    script = f"[ -f {q} ] && cp {q} {q}.bak 2>/dev/null; echo {b64} | base64 -d > {q}.tmp && mv {q}.tmp {q} && echo OK"
    user = owner if re.fullmatch(r"\d+:\d+", owner) else ""
    out = await docker_api.exec_cmd(container, ["sh", "-c", script], timeout=30, user=user)
    if "OK" not in out:
        out = await docker_api.exec_cmd(container, ["sh", "-c", script], timeout=30)
        if "OK" not in out:
            raise FileError("Schreiben fehlgeschlagen: " + out.strip()[:200])


async def download(container: str, path: str):
    """Datei (roh) oder Ordner (tar.gz) – gibt (dateiname, bytes, mediatype) zurück."""
    p = await check(container, path)
    r = await docker_api._req("GET", f"/containers/{container}/archive", params={"path": p}, timeout=600)
    data = r.content
    tf = tarfile.open(fileobj=io.BytesIO(data))
    members = tf.getmembers()
    if len(members) == 1 and members[0].isfile():
        return posixpath.basename(p), tf.extractfile(members[0]).read(), "application/octet-stream"
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as out:
        for m in members:
            out.addfile(m, tf.extractfile(m) if m.isfile() else None)
    return posixpath.basename(p.rstrip("/")) + ".tar.gz", buf.getvalue(), "application/gzip"


async def upload(container: str, dirpath: str, filename: str, data: bytes) -> str:
    d = await check(container, dirpath)
    name = posixpath.basename(filename.replace("\\", "/"))
    if not name or name in (".", ".."):
        raise FileError("Ungültiger Dateiname")
    owner = (await docker_api.exec_cmd(container, ["sh", "-c", f"stat -c '%u:%g' {shlex.quote(d)}"], timeout=10)).strip()
    uid, gid = (int(x) for x in owner.split(":")) if re.fullmatch(r"\d+:\d+", owner) else (0, 0)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        ti = tarfile.TarInfo(name)
        ti.size, ti.mtime, ti.uid, ti.gid, ti.mode = len(data), int(time.time()), uid, gid, 0o664
        tf.addfile(ti, io.BytesIO(data))
    await docker_api._req("PUT", f"/containers/{container}/archive", params={"path": d}, content=buf.getvalue(),
                          headers={"Content-Type": "application/x-tar"}, timeout=600)
    return posixpath.join(d, name)


async def delete(container: str, path: str) -> None:
    p = await check(container, path)
    if p in await roots(container):
        raise FileError("Den Datenordner selbst kann man nicht löschen")
    q = shlex.quote(p)
    out = await docker_api.exec_cmd(container, ["sh", "-c", f"rm -rf -- {q} && echo OK"], timeout=60)
    if "OK" not in out:
        raise FileError("Löschen fehlgeschlagen: " + out.strip()[:200])


async def saves(container: str, game: str) -> list[dict]:
    """Spielstände/Welten in den bekannten Ordnern des Spiels."""
    out = []
    for d in SAVES.get(game, []):
        try:
            ls = await listdir(container, d)
        except (FileError, docker_api.DockerError):
            continue
        for it in ls["items"]:
            if it["name"].endswith((".bak", ".tmp")) or it["name"].startswith("."):
                continue
            out.append({**it, "path": posixpath.join(d, it["name"]), "dirpath": d})
    out.sort(key=lambda x: -(x["mtime"] or 0))
    return out

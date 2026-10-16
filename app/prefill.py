"""SteamPrefill (tpill90/steam-lancache-prefill): Spiele vorab in den Lancache laden.

Jeder Lauf ist ein eigener Container „steamprefill“ (Tty + offenes stdin). Eingaben für den Steam-Login
(Benutzer, Passwort, Steam-Guard-Code) gehen über einen Docker-attach-Stream an den Container.
"""
import asyncio
import base64
import json
import re
import time

import httpx

from . import automation, docker_api, store

IMAGE = "tpill90/steam-lancache-prefill:latest"
NAME = "steamprefill"
SETTINGS = "prefill.json"
DEFAULTS = {"schedule": "", "flags": {"recent": False, "recently_purchased": False, "top": 0, "all": False,
                                      "force": False, "verbose": False, "os": "windows"},
            "apps": [], "last_run": None, "last_scheduled": ""}

_stdin: dict = {"writer": None, "container": None}
job: dict = {"running": False, "step": None, "error": None}


def settings() -> dict:
    s = {**DEFAULTS, **store.load(SETTINGS, {})}
    s["flags"] = {**DEFAULTS["flags"], **(s.get("flags") or {})}
    return s


def save_settings(data: dict) -> dict:
    s = settings()
    for k in ("schedule", "flags", "apps", "last_run", "last_scheduled"):
        if k in data:
            s[k] = data[k]
    store.save(SETTINGS, s)
    return s


def config_dir() -> str:
    base = (automation.get_settings().get("games_base") or "/mnt/grohlan").rstrip("/")
    return f"{base}/steamprefill/Config"


async def _attach_stdin(name: str):
    """Docker-attach (hijacked HTTP) nur für stdin öffnen."""
    r, w = await asyncio.open_unix_connection(docker_api.SOCK)
    w.write((f"POST /containers/{name}/attach?stream=1&stdin=1&stdout=0&stderr=0 HTTP/1.1\r\n"
             "Host: docker\r\nUpgrade: tcp\r\nConnection: Upgrade\r\nContent-Length: 0\r\n\r\n").encode())
    await w.drain()
    head = b""
    while b"\r\n\r\n" not in head:
        chunk = await asyncio.wait_for(r.read(1024), 10)
        if not chunk:
            break
        head += chunk
    if b" 101 " not in head.split(b"\r\n", 1)[0] and b" 200 " not in head.split(b"\r\n", 1)[0]:
        w.close()
        raise docker_api.DockerError("attach fehlgeschlagen: " + head.split(b"\r\n", 1)[0].decode(errors="replace"))
    return r, w


async def container_state() -> dict | None:
    try:
        info = await docker_api.inspect(NAME)
    except docker_api.DockerError:
        return None
    st = info.get("State") or {}
    return {"running": st.get("Running"), "status": st.get("Status"), "exit": st.get("ExitCode"),
            "started": st.get("StartedAt"), "finished": st.get("FinishedAt"), "cmd": info.get("Config", {}).get("Cmd")}


async def config_files() -> list[str]:
    try:
        out = await docker_api.run_helper([f"{config_dir()}:/target"], ["sh", "-c", "mkdir -p /target && ls -1A /target"], timeout=60)
        return [x.strip() for x in out.splitlines() if x.strip()]
    except docker_api.DockerError:
        return []


async def write_apps(apps: list[int]) -> None:
    data = base64.b64encode(json.dumps(sorted(set(int(a) for a in apps))).encode()).decode()
    await docker_api.run_helper([f"{config_dir()}:/target"],
                                ["sh", "-c", f"mkdir -p /target && echo {data} | base64 -d > /target/selectedAppsToPrefill.json && echo ok"],
                                timeout=60)


async def start(cmd: list[str], dns: list[str] | None) -> None:
    """Alten Lauf entfernen, neuen Container starten, stdin verbinden."""
    if not await docker_api.image_exists(IMAGE):
        job["step"] = "Image wird geladen …"
        await docker_api.pull(IMAGE)
    try:
        await docker_api.remove_container(NAME)
    except docker_api.DockerError:
        pass
    await docker_api.run_helper([f"{config_dir()}:/target"], ["sh", "-c", "mkdir -p /target && echo ok"], timeout=60)
    hc = {"Binds": [f"{config_dir()}:/Config"], "RestartPolicy": {"Name": "no"}}
    if dns:
        hc["Dns"] = dns
    spec = {"Image": IMAGE, "Cmd": cmd, "Tty": True, "OpenStdin": True, "StdinOnce": False, "AttachStdin": True,
            "Env": ["TERM=dumb"], "Labels": {"gsm.helper": "prefill"}, "HostConfig": hc}
    await docker_api._req("POST", "/containers/create", params={"name": NAME}, json=spec, timeout=60)
    # erst verbinden, dann starten -> keine Eingabeaufforderung geht verloren
    if _stdin["writer"]:
        try:
            _stdin["writer"].close()
        except Exception:  # noqa: BLE001
            pass
    _, w = await _attach_stdin(NAME)
    _stdin.update(writer=w, container=NAME)
    await docker_api._req("POST", f"/containers/{NAME}/start", timeout=60)


async def send(text: str) -> None:
    w = _stdin.get("writer")
    if not w or w.is_closing():
        try:
            _, w = await _attach_stdin(NAME)
            _stdin.update(writer=w)
        except (OSError, docker_api.DockerError, asyncio.TimeoutError) as e:
            raise docker_api.DockerError(f"Keine Verbindung zur Eingabe: {e}") from e
    w.write((text + "\r").encode())
    await w.drain()


async def stop() -> None:
    await docker_api._req("POST", f"/containers/{NAME}/stop", params={"t": "5"}, timeout=30)


async def log(tail: int = 400) -> str:
    try:
        txt = await docker_api.logs(NAME, tail)
    except docker_api.DockerError:
        return ""
    txt = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", txt)
    lines = []
    for raw in txt.split("\n"):
        line = raw.split("\r")[-1] if "\r" in raw.rstrip("\r") else raw.rstrip("\r")   # Fortschrittszeilen überschreiben sich
        lines.append(line)
    return "\n".join(lines)


def prompt_of(text: str) -> str | None:
    """Wartet SteamPrefill gerade auf eine Eingabe?"""
    tail = [x for x in text.strip().splitlines() if x.strip()][-3:]
    last = " ".join(tail).lower()
    if re.search(r"(account name|username|benutzername)\s*:?\s*$", last):
        return "user"
    if re.search(r"password.*:\s*$", last):
        return "password"
    if re.search(r"(steam ?guard|2fa|two.factor|auth(entication)? code|code from|enter the code)", last):
        return "code"
    if re.search(r"\?\s*\[?y/n\]?", last):
        return "yesno"
    return None


def build_cmd(mode: str, flags: dict) -> list[str]:
    if mode == "select-apps":
        return ["select-apps", "--no-ansi"]
    cmd = ["prefill", "--no-ansi"]
    if flags.get("all"):
        cmd.append("--all")
    if flags.get("recent"):
        cmd.append("--recent")
    if flags.get("recently_purchased"):
        cmd.append("--recently-purchased")
    if int(flags.get("top") or 0) > 0:
        cmd += ["--top", str(min(100, int(flags["top"])))]
    if flags.get("force"):
        cmd.append("--force")
    if flags.get("verbose"):
        cmd.append("--verbose")
    if flags.get("os") in ("linux", "macos"):
        cmd += ["--os", flags["os"]]
    return cmd


async def search(q: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=10) as cl:
        r = await cl.get("https://store.steampowered.com/api/storesearch/", params={"term": q, "l": "german", "cc": "DE"})
        items = (r.json() or {}).get("items") or []
    return [{"id": it.get("id"), "name": it.get("name"), "img": it.get("tiny_image")} for it in items if it.get("type") == "app"][:15]


def due(schedule: str, last: str) -> bool:
    """Zeitplan 'HH:MM' täglich."""
    if not re.fullmatch(r"\d\d:\d\d", schedule or ""):
        return False
    now = time.localtime()
    today = time.strftime("%Y-%m-%d", now)
    return time.strftime("%H:%M", now) >= schedule and last != today


def parse_progress(text: str) -> dict:
    """Fortschritt je Spiel aus der SteamPrefill-Ausgabe."""
    apps, cur = [], None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = re.search(r"\]\s*Starting (.+?)\s*$", line)
        if m:
            cur = {"name": m.group(1), "state": "läuft", "pct": 0.0, "info": ""}
            apps.append(cur)
            continue
        if cur is None:
            continue
        m = re.match(r"^Downloading\.*:?\s*(\d{1,3}(?:[.,]\d+)?)\s*%", line)
        if m:
            cur["pct"] = float(m.group(1).replace(",", "."))
            continue
        if re.search(r"up to date|already been prefilled|nothing to download", line, re.I):
            cur.update(state="aktuell", pct=100.0, info=line[:120]); cur = None
            continue
        if re.search(r"\b(Finished|Completed|Done)\b", line):
            cur.update(state="fertig", pct=100.0, info=re.sub(r"^\[[^\]]*\]\s*", "", line)[:120]); cur = None
            continue
        if re.search(r"(error|failed|exception|unable)", line, re.I):
            cur.update(state="Fehler", info=line[:160])
    return {"apps": apps, "current": next((a for a in reversed(apps) if a["state"] == "läuft"), None)}

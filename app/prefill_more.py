"""Prefill für weitere Dienste (tpill90): Battle.net und Epic Games – gleiche Technik wie SteamPrefill.

Jeder Lauf ist ein Container mit TTY und offenem stdin; Eingaben (z. B. Epic-Anmeldecode) gehen per Docker-attach hinein.
- Battle.net: kein Konto nötig, Spiele über Produktcodes (prefill --products wow pro …).
- Epic Games: einmalige Anmeldung im Browser, danach Code eingeben; prefill --all lädt alle eigenen Spiele.
"""
import asyncio
import re
import time

from . import automation, docker_api, store
from . import prefill as steam_prefill

SERVICES = {
    "battlenet": {"label": "Battle.net", "image": "tpill90/battlenet-lancache-prefill:latest", "name": "bnetprefill",
                  "dir": "battlenetprefill"},
    "epic": {"label": "Epic Games", "image": "tpill90/epic-lancache-prefill:latest", "name": "epicprefill",
             "dir": "epicprefill"},
}
# Battle.net-Produktcodes (Auswahl der bekannten Spiele)
BNET_PRODUCTS = [
    ("wow", "World of Warcraft"), ("wow_classic", "WoW Classic"), ("wow_classic_era", "WoW Classic Era"),
    ("pro", "Overwatch 2"), ("fenris", "Diablo IV"), ("osi", "Diablo II: Resurrected"), ("d3", "Diablo III"),
    ("hs", "Hearthstone"), ("s2", "StarCraft II"), ("s1", "StarCraft Remastered"), ("hero", "Heroes of the Storm"),
    ("w3", "Warcraft III: Reforged"), ("anbs", "Diablo Immortal"), ("wlby", "Crash Bandicoot 4"),
]
SETTINGS = "prefill_more.json"
_pulled: dict = {}
_stdin: dict = {}
_last: dict = {}


def settings() -> dict:
    d = store.load(SETTINGS, {})
    d.setdefault("battlenet", {"products": ["wow", "pro"], "schedule": "", "last_scheduled": ""})
    d.setdefault("epic", {"mode": "all", "schedule": "", "last_scheduled": ""})
    return d


def save_settings(svc: str, data: dict) -> dict:
    d = settings()
    cur = d.get(svc) or {}
    for k in ("products", "mode", "schedule", "last_scheduled"):
        if k in data:
            cur[k] = data[k]
    d[svc] = cur
    store.save(SETTINGS, d)
    return d


def config_dir(svc: str) -> str:
    base = (automation.get_settings().get("games_base") or "/mnt/grohlan").rstrip("/")
    return f"{base}/{SERVICES[svc]['dir']}/Config"


def build_cmd(svc: str, opts: dict) -> list[str]:
    cmd = ["prefill", "--no-ansi"]
    if svc == "battlenet":
        if opts.get("mode") == "all":
            cmd.append("--all")
        elif not [p for p in (opts.get("products") or []) if re.fullmatch(r"[a-z0-9_]{1,24}", p)]:
            raise ValueError("Mindestens ein Spiel auswählen")
    elif opts.get("mode") != "selected":
        cmd.append("--all")                 # Epic: alle Spiele des Kontos
    if opts.get("force"):
        cmd.append("--force")
    return cmd


async def write_selection(svc: str, products: list[str]) -> None:
    """Battle.net: Auswahl wie bei „select-apps“ speichern (selectedAppsToPrefill.json im Config-Ordner)."""
    import base64
    import json
    prods = [p for p in products if re.fullmatch(r"[a-z0-9_]{1,24}", p)]
    b64 = base64.b64encode(json.dumps(prods).encode()).decode()
    await docker_api.run_helper([f"{config_dir(svc)}:/target"],
                                ["sh", "-c", f"mkdir -p /target && echo {b64} | base64 -d > /target/selectedAppsToPrefill.json && echo ok"], timeout=60)


async def state(svc: str) -> dict | None:
    try:
        info = await docker_api.inspect(SERVICES[svc]["name"])
    except docker_api.DockerError:
        return None
    st = info.get("State") or {}
    return {"running": st.get("Running"), "status": st.get("Status"), "exit": st.get("ExitCode"),
            "started": st.get("StartedAt"), "finished": st.get("FinishedAt"), "cmd": (info.get("Config") or {}).get("Cmd")}


async def start(svc: str, cmd: list[str], dns: list[str] | None) -> None:
    sv = SERVICES[svc]
    if not await docker_api.image_exists(sv["image"]) or time.time() - _pulled.get(svc, 0) > 6 * 3600:
        try:
            await docker_api.pull(sv["image"])
            _pulled[svc] = time.time()
        except docker_api.DockerError:
            if not await docker_api.image_exists(sv["image"]):
                raise
    try:
        await docker_api.remove_container(sv["name"])
    except docker_api.DockerError:
        pass
    await docker_api.run_helper([f"{config_dir(svc)}:/target"], ["sh", "-c", "mkdir -p /target && echo ok"], timeout=60)
    hc = {"Binds": [f"{config_dir(svc)}:/Config"], "RestartPolicy": {"Name": "no"}}
    if dns:
        hc["Dns"] = dns
    spec = {"Image": sv["image"], "Cmd": cmd, "Tty": True, "OpenStdin": True, "StdinOnce": False, "AttachStdin": True,
            "Env": ["TERM=dumb"], "Labels": {"gsm.helper": "prefill"}, "HostConfig": hc}
    await docker_api._req("POST", "/containers/create", params={"name": sv["name"]}, json=spec, timeout=60)
    w = _stdin.get(svc)
    if w:
        try:
            w.close()
        except Exception:  # noqa: BLE001
            pass
    _, w = await steam_prefill._attach_stdin(sv["name"])
    _stdin[svc] = w
    await docker_api._req("POST", f"/containers/{sv['name']}/start", timeout=60)
    _last[svc] = time.time()


async def send(svc: str, text: str) -> None:
    w = _stdin.get(svc)
    if not w or w.is_closing():
        _, w = await steam_prefill._attach_stdin(SERVICES[svc]["name"])
        _stdin[svc] = w
    w.write((text + "\r").encode())
    await w.drain()


async def stop(svc: str) -> None:
    await docker_api._req("POST", f"/containers/{SERVICES[svc]['name']}/stop", params={"t": "5"}, timeout=30)


async def log(svc: str, tail: int = 300) -> str:
    try:
        raw = await docker_api.logs(SERVICES[svc]["name"], tail)
    except docker_api.DockerError:
        return ""
    return re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", raw).replace("\r", "\n")


def prompt_of(text: str) -> str | None:
    """Wartet der Container auf eine Eingabe (z. B. Epic-Anmeldecode)?"""
    tail = "\n".join([ln for ln in text.splitlines() if ln.strip()][-6:])
    if re.search(r"(authorization code|authorizationCode|enter.*code|paste.*code|Code:)\s*$", tail, re.I | re.M):
        return "code"
    if re.search(r"(https://\S*epicgames\.com\S*)", tail) and re.search(r"code", tail, re.I):
        return "code"
    return None


def login_url(text: str) -> str | None:
    m = re.findall(r"(https://\S*(?:epicgames\.com|battle\.net)\S*)", text)
    return m[-1].rstrip(".,)") if m else None


async def run_scheduled(dns: list[str] | None) -> None:
    d = settings()
    for svc in SERVICES:
        cfg = d.get(svc) or {}
        if steam_prefill.due(cfg.get("schedule") or "", cfg.get("last_scheduled") or ""):
            st = await state(svc)
            if st and st.get("running"):
                continue
            save_settings(svc, {"last_scheduled": time.strftime("%Y-%m-%d")})
            try:
                if svc == "battlenet" and cfg.get("mode") != "all":
                    await write_selection(svc, cfg.get("products") or [])
                await start(svc, build_cmd(svc, cfg), dns)
            except (ValueError, docker_api.DockerError):
                pass

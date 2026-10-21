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
DEFAULTS = {"server_games": True, "skip_cached": True, "last_full": None, "yield": True, "yield_mbs": 2.0, "throttle_mbs": 5.0, "max_mbs": 0, "schedule": "", "flags": {"recent": False, "recently_purchased": False, "top": 0, "all": False,
                                      "force": False, "verbose": False, "os": "windows"},
            "apps": [], "last_run": None, "last_scheduled": ""}

_stdin: dict = {"writer": None, "container": None}
_pulled: dict = {"t": 0.0}
job: dict = {"running": False, "step": None, "error": None}


def settings() -> dict:
    s = {**DEFAULTS, **store.load(SETTINGS, {})}
    s["flags"] = {**DEFAULTS["flags"], **(s.get("flags") or {})}
    return s


def save_settings(data: dict) -> dict:
    s = settings()
    for k in ("schedule", "flags", "apps", "last_run", "last_scheduled", "yield", "yield_mbs", "throttle_mbs", "max_mbs",
              "server_games", "skip_cached", "last_full"):
        if k in data:
            s[k] = data[k]
    store.save(SETTINGS, s)
    return s


def config_dir() -> str:
    base = (automation.get_settings().get("games_base") or "/srv/gameserver").rstrip("/")
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


async def forget_depots(depot_ids: list[str]) -> int:
    """Einzelne Depots aus SteamPrefills Liste „schon geladen“ streichen – dann lädt er diese Spiele beim nächsten Lauf neu.
    Nötig, wenn der Cache die Daten nicht mehr hat (neuer Cache, Platz freigeräumt), SteamPrefill sie aber für erledigt hält."""
    if not depot_ids:
        return 0
    try:
        raw = await docker_api.run_helper([f"{config_dir()}:/target"], ["sh", "-c", "cat /target/successfullyDownloadedDepots.json 2>/dev/null"], timeout=60)
        data = json.loads(raw or "{}")
    except (docker_api.DockerError, ValueError):
        return 0
    drop = set(str(d) for d in depot_ids)
    if isinstance(data, dict):
        new = {k: v for k, v in data.items() if str(k) not in drop}
    elif isinstance(data, list):
        new = [x for x in data if str(x.get("DepotId", x) if isinstance(x, dict) else x) not in drop]
    else:
        return 0
    removed = len(data) - len(new)
    if removed:
        b64 = base64.b64encode(json.dumps(new).encode()).decode()
        await docker_api.run_helper([f"{config_dir()}:/target"],
                                    ["sh", "-c", f"echo {b64} | base64 -d > /target/successfullyDownloadedDepots.json && echo ok"], timeout=60)
    return removed


async def forget_downloaded() -> None:
    """Neuer/geleerter Cache: SteamPrefills Liste „schon geladen“ löschen, sonst überspringt er Spiele, die nicht mehr im Cache sind."""
    await docker_api.run_helper([f"{config_dir()}:/target"], ["sh", "-c", "rm -f /target/successfullyDownloadedDepots.json; echo ok"], timeout=60)


async def write_apps(apps: list[int]) -> None:
    data = base64.b64encode(json.dumps(sorted(set(int(a) for a in apps))).encode()).decode()
    await docker_api.run_helper([f"{config_dir()}:/target"],
                                ["sh", "-c", f"mkdir -p /target && echo {data} | base64 -d > /target/selectedAppsToPrefill.json && echo ok"],
                                timeout=60)


async def start(cmd: list[str], dns: list[str] | None) -> None:
    """Alten Lauf entfernen, neuen Container starten, stdin verbinden."""
    # SteamPrefill automatisch aktuell halten (höchstens alle 6 h prüfen)
    if not await docker_api.image_exists(IMAGE) or time.time() - _pulled.get("t", 0) > 6 * 3600:
        job["step"] = "SteamPrefill wird aktualisiert …"
        try:
            await docker_api.pull(IMAGE)
            _pulled["t"] = time.time()
        except docker_api.DockerError:
            if not await docker_api.image_exists(IMAGE):
                raise
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
    try:
        await pause(False)
    except docker_api.DockerError:
        pass
    auto.update(paused=False, manual=False, since=None, reason=None)
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
        if m and m.group(1).lower().rstrip("!") != "login":
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


auto = {"paused": False, "manual": False, "since": None, "reason": None, "busy": 0, "quiet": 0}


async def manual_pause(on: bool) -> None:
    await pause(on)
    auto.update(paused=on, manual=on, since=time.time() if on else None, reason="von Hand pausiert" if on else None,
                busy=0, quiet=0)


EXTRA_NAMES: list[str] = []      # weitere Prefill-Container (Battle.net, Epic) – werden zusammen pausiert


async def _running_names() -> list[str]:
    out = []
    for n in [NAME] + EXTRA_NAMES:
        try:
            st = (await docker_api.inspect(n)).get("State") or {}
        except docker_api.DockerError:
            continue
        if st.get("Running"):
            out.append(n)
    return out


async def pause(on: bool) -> None:
    for n in await _running_names():
        try:
            await docker_api._req("POST", f"/containers/{n}/{'pause' if on else 'unpause'}", timeout=30)
        except docker_api.DockerError:
            pass


# ---- Drosseln statt Pausieren: Download-Rate des Prefill-Containers per tc (Ingress-Policer) im eigenen Netz-Namespace ----
_rate: dict[str, tuple] = {}          # Container -> (StartedAt, angewendete Rate in Bytes/s oder 0 = frei)
throttle_ok: bool | None = None        # None = noch nicht probiert, False = geht nicht (dann wie früher pausieren)


async def _apply_rate(name: str, bps: float) -> bool:
    """bps = 0 -> keine Grenze. Hilfs-Container teilt sich das Netz mit dem Prefill (NET_ADMIN nur dort, nicht am Host)."""
    global throttle_ok
    if bps:
        kbit = max(800, int(bps * 8 / 1000))
        burst = max(256, int(bps / 10 / 1024))           # ~100 ms Puffer
        tc = (f"tc qdisc add dev eth0 handle ffff: ingress && tc filter add dev eth0 parent ffff: protocol all prio 1 "
              f"u32 match u32 0 0 police rate {kbit}kbit burst {burst}k drop flowid :1")
    else:
        tc = "true"
    sh = (f"(command -v tc >/dev/null || apk add -q --no-cache iproute2 >/dev/null 2>&1) && "
          f"(tc qdisc del dev eth0 ingress 2>/dev/null; true) && {tc} && echo ok")
    try:
        out = await docker_api.run_helper([], ["sh", "-c", sh], timeout=90,
                                          host_extra={"NetworkMode": f"container:{name}", "CapAdd": ["NET_ADMIN"]})
        throttle_ok = "ok" in out
    except docker_api.DockerError:
        throttle_ok = False
    return bool(throttle_ok)


async def set_rate(bps: float) -> bool:
    ok = True
    for n in await _running_names():
        try:
            started = ((await docker_api.inspect(n)).get("State") or {}).get("StartedAt")
        except docker_api.DockerError:
            continue
        if _rate.get(n) == (started, bps):
            continue
        if await _apply_rate(n, bps):
            _rate[n] = (started, bps)
        else:
            ok = False
    return ok


async def yield_check(cache_tx: float | None, prefill_rx: float | None, others_downloading: list[str],
                      lan_tx: float | None = None) -> None:
    """Alle 5 s: Prefill drosseln, solange andere über den Cache laden (oder Server-Updates laufen), danach wieder
    auf volle (bzw. die eingestellte Höchst-)Geschwindigkeit. Geht Drosseln nicht, wird wie früher pausiert."""
    s = settings()
    names = await _running_names()
    running = bool(names)
    is_paused = False
    for n in names:
        try:
            if ((await docker_api.inspect(n)).get("State") or {}).get("Paused"):
                is_paused = True
        except docker_api.DockerError:
            pass
    if not running:
        auto.update(paused=False, throttled=False, manual=False, disk_full=False, since=None, reason=None, busy=0, quiet=0)
        return
    if auto.get("manual"):
        return
    # Cache-Platte voll -> Prefill sinnlos (nichts wird mehr gespeichert): pausieren, bis wieder Platz ist
    from . import cache_stats, notify
    fs = cache_stats.storage.get("fs") or {}
    if fs.get("total") and time.time() - (fs.get("t") or 0) < 900:
        low = fs["free"] < max(10e9, fs["total"] * 0.01)
        if low and not auto.get("disk_full"):
            await pause(True)
            auto.update(paused=True, throttled=False, disk_full=True, since=time.time(),
                        reason=f"Cache-Platte voll ({fs['free'] / 1e9:.1f} GB frei) – nichts würde gespeichert")
            notify.fire("💾 Lancache-Platte voll – Prefill angehalten, bis der Cache wieder Platz hat.", event="disk", key="cache-full-prefill")
            return
        if auto.get("disk_full"):
            if fs["free"] > max(30e9, fs["total"] * 0.03):
                await pause(False)
                auto.update(paused=False, disk_full=False, since=None, reason=None, busy=0, quiet=0)
            else:
                return
    max_bps = float(s.get("max_mbs") or 0) * 1e6
    thr_bps = float(s.get("throttle_mbs") or 5) * 1e6
    if max_bps:
        thr_bps = min(thr_bps, max_bps)
    if not s.get("yield"):
        if is_paused and auto.get("paused"):
            await pause(False)
        auto.update(paused=False, throttled=False, since=None, reason=None)
        await set_rate(max_bps)
        return
    limit = float(s.get("yield_mbs") or 2.0) * 1e6
    # Traffic an andere Clients = alles, was der Cache sendet, minus das, was Prefill selbst empfängt
    pr = 0 if is_paused else (prefill_rx or 0)
    others = max(0.0, (cache_tx or 0) - pr)
    lan_busy = lan_tx is not None and lan_tx > limit
    busy = others > max(limit, 0.3 * pr) or bool(others_downloading) or lan_busy
    if busy:
        auto["busy"] += 1; auto["quiet"] = 0
    else:
        auto["quiet"] += 1; auto["busy"] = 0
    need = 4 if lan_busy and not (others > max(limit, 0.3 * pr) or others_downloading) else 2
    active = auto.get("paused") or auto.get("throttled")
    if not active and auto["busy"] >= need:
        why = ("Server-Update: " + ", ".join(others_downloading)) if others_downloading else \
            (f"LAN-Clients laden {lan_tx / 1e6:.1f} MB/s" if lan_tx and lan_tx > limit else f"andere laden {others / 1e6:.1f} MB/s über den Cache")
        if await set_rate(thr_bps):
            auto.update(throttled=True, paused=False, since=time.time(), reason=why, rate=thr_bps)
        else:                                   # Drosseln nicht möglich -> pausieren wie bisher
            await pause(True)
            auto.update(paused=True, throttled=False, since=time.time(), reason=why)
    elif active and auto["quiet"] >= 6:         # 30 s Ruhe
        if auto.get("paused") and is_paused:
            await pause(False)
        await set_rate(max_bps)
        auto.update(paused=False, throttled=False, since=None, reason=None, rate=max_bps or None)
    elif not active:
        await set_rate(max_bps)                 # Höchstgeschwindigkeit (auch nach Neustart des Prefills) halten
        auto["rate"] = max_bps or None
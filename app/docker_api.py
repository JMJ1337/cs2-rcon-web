"""Docker-Engine-API über den Unix-Socket (Container steuern, Logs, neue Server anlegen)."""
import json
import os
import struct

import httpx

SOCK = os.getenv("DOCKER_SOCK", "/var/run/docker.sock")
HELPER_IMAGE = os.getenv("HELPER_IMAGE", "alpine:3.20")


class DockerError(Exception):
    pass


def available() -> bool:
    return os.path.exists(SOCK)


def _client(timeout=15.0):
    if not available():
        raise DockerError("Docker-Socket nicht eingebunden (/var/run/docker.sock im Stack mounten)")
    return httpx.AsyncClient(transport=httpx.AsyncHTTPTransport(uds=SOCK), base_url="http://docker", timeout=timeout)


async def _req(method, path, timeout=15.0, **kw):
    async with _client(timeout) as cl:
        try:
            r = await cl.request(method, path, **kw)
        except httpx.HTTPError as e:
            raise DockerError(f"Docker nicht erreichbar ({e.__class__.__name__})") from e
    if r.status_code >= 400:
        try:
            msg = r.json().get("message")
        except ValueError:
            msg = r.text[:200]
        raise DockerError(msg or f"Docker-Fehler {r.status_code}")
    return r


def _demux(raw: bytes) -> str:
    """Docker-Multiplex-Stream (ohne TTY) in Text umwandeln."""
    out, i = [], 0
    while i + 8 <= len(raw) and raw[i] in (0, 1, 2) and raw[i + 1:i + 4] == b"\x00\x00\x00":
        size = struct.unpack(">I", raw[i + 4:i + 8])[0]
        out.append(raw[i + 8:i + 8 + size])
        i += 8 + size
    if not out:
        return raw.decode("utf-8", "replace")
    return b"".join(out).decode("utf-8", "replace")


async def list_containers() -> list[dict]:
    r = await _req("GET", "/containers/json", params={"all": "1"})
    out = []
    for c in r.json():
        out.append({
            "id": c["Id"][:12], "name": (c.get("Names") or ["/?"])[0].lstrip("/"), "image": c.get("Image"),
            "state": c.get("State"), "status": c.get("Status"), "labels": c.get("Labels") or {},
            "ports": sorted({f"{p.get('PublicPort')}/{p.get('Type')}" for p in c.get("Ports", []) if p.get("PublicPort")}),
        })
    return sorted(out, key=lambda x: x["name"])


async def inspect(name: str) -> dict:
    return (await _req("GET", f"/containers/{name}/json")).json()


async def action(name: str, act: str) -> None:
    if act not in ("start", "stop", "restart"):
        raise DockerError("Unbekannte Aktion")
    await _req("POST", f"/containers/{name}/{act}", params={"t": "20"} if act != "start" else None, timeout=60)


async def logs(name: str, tail: int = 200) -> str:
    info = await inspect(name)
    r = await _req("GET", f"/containers/{name}/logs",
                   params={"stdout": "1", "stderr": "1", "tail": str(max(10, min(tail, 2000))), "timestamps": "0"})
    raw = r.content
    return raw.decode("utf-8", "replace") if info.get("Config", {}).get("Tty") else _demux(raw)


async def stats(name: str) -> dict:
    s = (await _req("GET", f"/containers/{name}/stats", params={"stream": "false"}, timeout=20)).json()
    cpu = s.get("cpu_stats", {})
    pre = s.get("precpu_stats", {})
    try:
        d_cpu = cpu["cpu_usage"]["total_usage"] - pre["cpu_usage"]["total_usage"]
        d_sys = cpu["system_cpu_usage"] - pre["system_cpu_usage"]
        ncpu = cpu.get("online_cpus") or len(cpu["cpu_usage"].get("percpu_usage") or [1])
        cpu_pct = round(d_cpu / d_sys * ncpu * 100, 1) if d_sys > 0 else 0.0
    except (KeyError, TypeError, ZeroDivisionError):
        cpu_pct = None
    mem = s.get("memory_stats", {})
    usage = mem.get("usage", 0) - (mem.get("stats", {}).get("inactive_file") or 0)
    nets = s.get("networks") or {}
    rx = sum((n or {}).get("rx_bytes", 0) for n in nets.values()) if nets else None
    tx = sum((n or {}).get("tx_bytes", 0) for n in nets.values()) if nets else None
    return {"cpu": cpu_pct, "mem_mb": round(usage / 1048576) if usage else None,
            "mem_limit_mb": round(mem.get("limit", 0) / 1048576) or None, "net_rx": rx, "net_tx": tx}


async def exec_cmd(name: str, cmd: list[str], timeout: float = 30, user: str = "") -> str:
    body = {"Cmd": cmd, "AttachStdout": True, "AttachStderr": True, "Tty": False}
    if user:
        body["User"] = user
    e = (await _req("POST", f"/containers/{name}/exec", json=body)).json()
    r = await _req("POST", f"/exec/{e['Id']}/start", json={"Detach": False, "Tty": False}, timeout=timeout)
    return _demux(r.content)


async def pull(image: str, progress=None) -> None:
    repo, _, tag = image.rpartition(":") if ":" in image.split("/")[-1] else (image, "", "latest")
    async with _client(timeout=None) as cl:
        async with cl.stream("POST", "/images/create", params={"fromImage": repo, "tag": tag}) as r:
            if r.status_code >= 400:
                raise DockerError(f"Image {image} konnte nicht geladen werden ({r.status_code})")
            async for line in r.aiter_lines():
                if not line.strip():
                    continue
                try:
                    j = json.loads(line)
                except ValueError:
                    continue
                if j.get("error"):
                    raise DockerError(j["error"])
                if progress and j.get("status"):
                    progress(f"{j['status']} {j.get('progress', '')}".strip())


async def image_exists(image: str) -> bool:
    try:
        await _req("GET", f"/images/{image}/json")
        return True
    except DockerError:
        return False


async def run_helper(binds: list[str], cmd: list[str], timeout: float = 120, host_extra: dict | None = None) -> str:
    """Kurzlebigen Hilfs-Container starten (z. B. Ordner auf dem NAS anlegen und Rechte setzen)."""
    if not await image_exists(HELPER_IMAGE):
        await pull(HELPER_IMAGE)  # klein (~4 MB), nur beim ersten Mal
    c = (await _req("POST", "/containers/create", json={
        "Image": HELPER_IMAGE, "Cmd": cmd, "HostConfig": {"Binds": binds, "AutoRemove": False, **(host_extra or {})},
        "Labels": {"gsm.helper": "1"}})).json()
    cid = c["Id"]
    try:
        await _req("POST", f"/containers/{cid}/start")
        w = (await _req("POST", f"/containers/{cid}/wait", timeout=timeout)).json()
        out = _demux((await _req("GET", f"/containers/{cid}/logs", params={"stdout": "1", "stderr": "1"})).content)
        if w.get("StatusCode", 0) != 0:
            raise DockerError(f"Hilfs-Container fehlgeschlagen: {out.strip()[:300]}")
        return out
    finally:
        try:
            await _req("DELETE", f"/containers/{cid}", params={"force": "1"})
        except DockerError:
            pass


async def create_container(name: str, spec: dict) -> str:
    r = await _req("POST", "/containers/create", params={"name": name}, json=spec, timeout=60)
    cid = r.json()["Id"]
    await _req("POST", f"/containers/{cid}/start", timeout=60)
    return cid[:12]


async def used_host_ports() -> dict[int, str]:
    """Alle Host-Ports, die Container belegen (auch gestoppte) -> Containername."""
    used: dict[int, str] = {}
    r = await _req("GET", "/containers/json", params={"all": "1"})
    for c in r.json():
        name = (c.get("Names") or ["/?"])[0].lstrip("/")
        try:
            info = await inspect(c["Id"])
        except DockerError:
            continue
        binds = (info.get("HostConfig") or {}).get("PortBindings") or {}
        for _, lst in binds.items():
            for b in lst or []:
                hp = (b or {}).get("HostPort") or ""
                if "-" in hp:
                    a, z = hp.split("-", 1)
                    for p in range(int(a), int(z) + 1):
                        used[p] = name
                elif hp.isdigit():
                    used[int(hp)] = name
        if (info.get("HostConfig") or {}).get("NetworkMode") == "host":
            for p in (info.get("Config") or {}).get("ExposedPorts") or {}:
                num = p.split("/")[0]
                if num.isdigit():
                    used[int(num)] = name
    return used


async def mounts(name: str) -> list[dict]:
    info = await inspect(name)
    return [{"type": m.get("Type"), "source": m.get("Source"), "name": m.get("Name"), "dest": m.get("Destination")}
            for m in info.get("Mounts") or []]


async def all_mounts() -> dict[str, list[dict]]:
    out = {}
    r = await _req("GET", "/containers/json", params={"all": "1"})
    for c in r.json():
        n = (c.get("Names") or ["/?"])[0].lstrip("/")
        out[n] = [{"type": m.get("Type"), "source": m.get("Source"), "name": m.get("Name")} for m in c.get("Mounts") or []]
    return out


async def remove_container(name: str) -> None:
    await _req("DELETE", f"/containers/{name}", params={"force": "1", "v": "1"}, timeout=60)


async def remove_volume(name: str) -> None:
    await _req("DELETE", f"/volumes/{name}", timeout=60)


async def recreate(name: str, mutate) -> None:
    """Container mit geänderter Konfiguration neu erstellen (Binds/Daten bleiben). mutate(cfg, hostconfig) ändert in-place."""
    info = await inspect(name)
    cfg, hc = dict(info["Config"]), dict(info["HostConfig"])
    mutate(cfg, hc)
    spec = {k: cfg.get(k) for k in ("Image", "Env", "Cmd", "Entrypoint", "ExposedPorts", "Labels", "WorkingDir",
                                     "User", "Tty", "OpenStdin", "StopSignal", "Volumes") if cfg.get(k) is not None}
    spec["HostConfig"] = hc
    tmp = f"{name}-alt-{int(__import__('time').time())}"
    if info.get("State", {}).get("Running"):
        await _req("POST", f"/containers/{name}/stop", params={"t": "30"}, timeout=60)
    await _req("POST", f"/containers/{name}/rename", params={"name": tmp})
    try:
        await create_container(name, spec)
    except DockerError:
        await _req("POST", f"/containers/{tmp}/rename", params={"name": name})
        await _req("POST", f"/containers/{name}/start", timeout=60)
        raise
    await _req("DELETE", f"/containers/{tmp}", params={"force": "1"}, timeout=60)


async def run_once(image: str, script: str, binds: list[str], user: str = "", env: list[str] | None = None,
                   timeout: float = 3600) -> tuple[int, str]:
    """Einmaligen Container aus einem Spiel-Image starten (z. B. SteamCMD-Reparatur), Ausgabe zurückgeben."""
    c = (await _req("POST", "/containers/create", json={
        "Image": image, "Entrypoint": ["/bin/bash", "-c"], "Cmd": [script], "User": user or "", "Env": env or [],
        "HostConfig": {"Binds": binds, "AutoRemove": False}, "Labels": {"gsm.helper": "steamfix"}})).json()
    cid = c["Id"]
    try:
        await _req("POST", f"/containers/{cid}/start")
        w = (await _req("POST", f"/containers/{cid}/wait", timeout=timeout)).json()
        out = _demux((await _req("GET", f"/containers/{cid}/logs", params={"stdout": "1", "stderr": "1", "tail": "60"})).content)
        return int(w.get("StatusCode", 0)), out
    finally:
        try:
            await _req("DELETE", f"/containers/{cid}", params={"force": "1"})
        except DockerError:
            pass

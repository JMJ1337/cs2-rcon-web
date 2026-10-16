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
    return {"cpu": cpu_pct, "mem_mb": round(usage / 1048576) if usage else None,
            "mem_limit_mb": round(mem.get("limit", 0) / 1048576) or None}


async def exec_cmd(name: str, cmd: list[str]) -> str:
    e = (await _req("POST", f"/containers/{name}/exec",
                    json={"Cmd": cmd, "AttachStdout": True, "AttachStderr": True, "Tty": False})).json()
    r = await _req("POST", f"/exec/{e['Id']}/start", json={"Detach": False, "Tty": False}, timeout=30)
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


async def run_helper(binds: list[str], cmd: list[str]) -> str:
    """Kurzlebigen Hilfs-Container starten (z. B. Ordner auf dem NAS anlegen und Rechte setzen)."""
    if not await image_exists(HELPER_IMAGE):
        await pull(HELPER_IMAGE)  # klein (~4 MB), nur beim ersten Mal
    c = (await _req("POST", "/containers/create", json={
        "Image": HELPER_IMAGE, "Cmd": cmd, "HostConfig": {"Binds": binds, "AutoRemove": False},
        "Labels": {"gsm.helper": "1"}})).json()
    cid = c["Id"]
    try:
        await _req("POST", f"/containers/{cid}/start")
        w = (await _req("POST", f"/containers/{cid}/wait", timeout=120)).json()
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

"""Live-Stream im Browser: kleiner Stream-Server (MediaMTX) als eigener Container.

Ablauf: Ein Stream-PC mit CS2 hängt als CSTV-Zuschauer am laufenden Match (Kamera: Auto-Director), OBS schickt das
Bild per RTMP an diesen Server, der Browser spielt es als HLS über das Tool ab (nur Port 8090 nötig).
Ein Hilfsskript auf dem Stream-PC verbindet CS2 automatisch mit dem jeweils laufenden Turnierspiel.
"""
import secrets
import socket

import httpx

from . import docker_api, store

NAME = "gsm-stream"
IMAGE = "bluenviron/mediamtx:1.9.3"
VOLUME = "gsm-stream"
RTMP_PORT = 1935
HLS = f"http://{NAME}:8888"
FILE = "stream.json"
PATH = "live"

DEFAULTS = {"enabled": False, "key": "", "title": "", "netcon_port": 2121, "server": ""}


def settings() -> dict:
    d = {**DEFAULTS, **store.load(FILE, {})}
    if not d.get("key"):
        d["key"] = secrets.token_urlsafe(10).replace("-", "x").replace("_", "y")
        store.save(FILE, d)
    return d


def save(new: dict) -> dict:
    d = settings()
    for k in ("enabled", "title", "netcon_port", "server"):
        if k in new and new[k] is not None:
            d[k] = new[k]
    if new.get("new_key"):
        d["key"] = secrets.token_urlsafe(10).replace("-", "x").replace("_", "y")
    store.save(FILE, d)
    return d


def _config(key: str) -> str:
    return f"""logLevel: warn
api: no
rtsp: no
srt: no
webrtc: no
rtmp: yes
rtmpAddress: :1935
hls: yes
hlsAddress: :8888
hlsAlwaysRemux: yes
hlsVariant: fmp4
hlsSegmentCount: 7
hlsSegmentDuration: 1s
hlsAllowOrigin: '*'
authMethod: internal
authInternalUsers:
  - user: any
    pass:
    ips: []
    permissions:
      - action: read
  - user: obs
    pass: "{key}"
    ips: []
    permissions:
      - action: publish
paths:
  {PATH}:
"""


async def _own_network() -> str | None:
    try:
        info = await docker_api.inspect(socket.gethostname())
        nets = list(((info.get("NetworkSettings") or {}).get("Networks") or {}).keys())
        return next((n for n in nets if n not in ("host", "none")), None)
    except docker_api.DockerError:
        return None


async def state() -> dict | None:
    try:
        info = await docker_api.inspect(NAME)
    except docker_api.DockerError:
        return None
    s = info.get("State") or {}
    return {"running": s.get("Running"), "status": s.get("Status"), "started": s.get("StartedAt")}


async def start() -> None:
    d = settings()
    import base64
    cfg = base64.b64encode(_config(d["key"]).encode()).decode()
    await docker_api.run_helper([f"{VOLUME}:/t"], ["sh", "-c", f"echo {cfg} | base64 -d > /t/mediamtx.yml && echo ok"], timeout=60)
    try:
        await docker_api.remove_container(NAME)
    except docker_api.DockerError:
        pass
    used = await docker_api.used_host_ports()
    if RTMP_PORT in used:
        raise docker_api.DockerError(f"Port {RTMP_PORT} (RTMP) ist schon belegt von {used[RTMP_PORT]}")
    if not await docker_api.image_exists(IMAGE):
        await docker_api.pull(IMAGE)
    net = await _own_network()
    spec = {"Image": IMAGE, "Cmd": ["/cfg/mediamtx.yml"], "Labels": {"gsm.helper": "stream"},
            "ExposedPorts": {f"{RTMP_PORT}/tcp": {}},
            "HostConfig": {"Binds": [f"{VOLUME}:/cfg:ro"], "RestartPolicy": {"Name": "unless-stopped"},
                           "PortBindings": {f"{RTMP_PORT}/tcp": [{"HostPort": str(RTMP_PORT)}]},
                           **({"NetworkMode": net} if net else {})}}
    if net:
        spec["NetworkingConfig"] = {"EndpointsConfig": {net: {"Aliases": [NAME]}}}
    await docker_api.create_container(NAME, spec)


async def stop() -> None:
    try:
        await docker_api._req("POST", f"/containers/{NAME}/stop", params={"t": "3"}, timeout=30)
    except docker_api.DockerError:
        pass


async def on_air() -> bool:
    """Sendet OBS gerade? (dann gibt es die Playlist)"""
    try:
        async with httpx.AsyncClient(timeout=3) as cl:
            r = await cl.get(f"{HLS}/{PATH}/index.m3u8")
        return r.status_code == 200
    except httpx.HTTPError:
        return False


HELPER_PS1 = r'''# Stream-PC: verbindet CS2 automatisch mit dem laufenden Turnierspiel (CSTV) und schaltet die Auto-Kamera ein.
# CS2 mit Startoption  -netconport {port}  starten (Steam > CS2 > Eigenschaften > Startoptionen), OBS sendet an den Stream-Server.
$api = "{api}"
$last = ""
Write-Host "Stream-Helfer läuft – Strg+C beendet."
while ($true) {{
  try {{
    $s = Invoke-RestMethod -Uri $api -TimeoutSec 5
    $tv = $s.tv
    $key = "$tv|$($s.id)"
    if ($tv -and $key -ne $last) {{
      Write-Host (Get-Date -Format HH:mm:ss) "-> $($s.match)  ($tv)"
      $c = New-Object System.Net.Sockets.TcpClient("127.0.0.1", {port})
      $w = New-Object System.IO.StreamWriter($c.GetStream()); $w.AutoFlush = $true
      $w.WriteLine("disconnect"); Start-Sleep -Seconds 2
      $w.WriteLine("password `"`"; connect $tv"); Start-Sleep -Seconds 15
      $w.WriteLine("spec_autodirector 1; spec_autodirector_cameraman 0; cl_draw_only_deathnotices 0")
      $c.Close(); $last = $key
    }}
  }} catch {{ Write-Host "warte …" $_.Exception.Message }}
  Start-Sleep -Seconds 10
}}
'''


def helper_script(api_url: str) -> str:
    return HELPER_PS1.format(api=api_url, port=int(settings().get("netcon_port") or 2121))

"""Was liegt WIRKLICH im Lancache? – Stichprobe der Cache-Dateien.

Jede Datei im nginx-Cache beginnt mit einem Kopf, in dem der Schlüssel steht („KEY: steam/depot/123/chunk/…“).
Statt alle ~1 Mio. Dateien zu lesen (Stunden), wird eine gleichmäßig verteilte Stichprobe gelesen (Standard 1/256 der
Unterordner – der Cache verteilt die Dateien zufällig über die Ordner). Hochgerechnet auf die gemessene Belegung
ergibt das, wie viel von jedem Spiel im Cache liegt. Das Ergebnis ersetzt in der Statistik die Schätzung.

Läuft losgelöst im Lancache-Container (übersteht Neustarts des Tools), Fortschritt in OUT.
"""
import time

from . import cache_stats, docker_api, store

OUT = "/tmp/gsm_cache_inv.out"
FILE = "cache_inventory.json"
SAMPLE = 256          # so viele Unterordner (von 65536) werden gelesen

SH = (
    "cd /data/cache/cache 2>/dev/null || cd /data/cache || exit 1; "
    "set -- */*/; D=$#; echo \"DIRS $D\"; N=%d; K=$((D / N)); [ $K -lt 1 ] && K=1; i=0; n=0; "
    "for d in \"$@\"; do i=$((i+1)); [ $((i %% K)) -ne 0 ] && continue; n=$((n+1)); [ $n -gt $N ] && break; "
    "echo \"S $n\"; for f in \"$d\"*; do [ -f \"$f\" ] || continue; "
    "s=$(stat -c %%s \"$f\" 2>/dev/null); k=$(head -c 2048 \"$f\" 2>/dev/null | grep -a -m1 '^KEY: ' | cut -c6-120); "
    "echo \"F ${s:-0} $k\"; done; done; echo \"END $n\""
) % SAMPLE

state: dict = {"running": False, "done": 0, "total": SAMPLE, "started": None, "error": None}


def saved() -> dict:
    return store.load(FILE, {})


def _key_to_depot(key: str) -> str | None:
    """'steam/depot/123/chunk/…bytes=…' -> Depot-Schlüssel wie in der Statistik."""
    svc, _, rest = key.partition("/")
    if not rest:
        return None
    return cache_stats.depot_of(f'"GET /{rest}', svc)


async def start() -> None:
    name = cache_stats.state.get("container")
    if not name:
        raise docker_api.DockerError("Kein Lancache-Container")
    try:
        await docker_api.exec_cmd(name, ["sh", "-c", "for p in $(ps -eo pid,args | awk '/gsm_cache_in[v]/{print $1}'); "
                                                     f"do kill $p 2>/dev/null; done; rm -f {OUT}.tmp; true"], timeout=15)
    except docker_api.DockerError:
        pass
    body = {"Cmd": ["sh", "-c", f"( {SH} ) > {OUT}.tmp 2>&1; mv {OUT}.tmp {OUT}"], "AttachStdout": False, "AttachStderr": False}
    e = (await docker_api._req("POST", f"/containers/{name}/exec", json=body)).json()
    await docker_api._req("POST", f"/exec/{e['Id']}/start", json={"Detach": True, "Tty": False})
    state.update(running=True, done=0, started=time.time(), error=None)


async def poll() -> dict:
    """Fortschritt lesen; ist die Stichprobe fertig, auswerten und speichern."""
    name = cache_stats.state.get("container")
    if not name:
        return state
    try:
        out = await docker_api.exec_cmd(name, ["sh", "-c", f"if [ -f {OUT}.tmp ]; then echo '#RUN'; grep -c '^S ' {OUT}.tmp; "
                                                          f"head -1 {OUT}.tmp; elif [ -f {OUT} ]; then echo '#FINAL'; cat {OUT}; fi"], timeout=60)
    except docker_api.DockerError as e:
        state["error"] = str(e)[:200]
        return state
    lines = [ln for ln in out.splitlines() if ln.strip()]
    if not lines:
        state["running"] = False
        return state
    if lines[0] == "#RUN":
        state.update(running=True, done=int(lines[1]) if len(lines) > 1 and lines[1].isdigit() else 0)
        if not state.get("started"):
            state["started"] = time.time()
        return state
    if lines[0] == "#FINAL":
        _evaluate(lines[1:])
        try:
            await docker_api.exec_cmd(name, ["rm", "-f", OUT], timeout=15)
        except docker_api.DockerError:
            pass
        state.update(running=False, done=state.get("total"))
    return state


def _evaluate(lines: list[str]) -> None:
    dirs = next((int(x.split()[1]) for x in lines if x.startswith("DIRS ") and x.split()[1].isdigit()), 0)
    n = next((int(x.split()[1]) for x in lines if x.startswith("END ") and x.split()[1].isdigit()), 0)
    per: dict[str, float] = {}
    files = total = unknown = 0
    for x in lines:
        if not x.startswith("F "):
            continue
        p = x.split(" ", 2)
        size = int(p[1]) if len(p) > 1 and p[1].isdigit() else 0
        key = p[2] if len(p) > 2 else ""
        files += 1
        total += size
        d = _key_to_depot(key) if key else None
        if d:
            per[d] = per.get(d, 0) + size
        else:
            unknown += size
    if not files or not n or not dirs:
        state["error"] = "Stichprobe leer – Cache-Ordner nicht lesbar?"
        return
    used = cache_stats.storage.get("cache_bytes") or total * dirs / n
    scale = used / total if total else dirs / n          # auf die gemessene Belegung hochrechnen
    data = {"t": time.time(), "dirs": dirs, "sample_dirs": n, "files": files, "sample_bytes": total, "used": used,
            "depots": {d: round(v * scale) for d, v in per.items()}, "unknown": round(unknown * scale)}
    store.save(FILE, data)
    state["error"] = None

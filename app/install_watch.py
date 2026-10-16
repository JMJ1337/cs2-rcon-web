"""Installations-/Update-Fortschritt und Fehler aus den Container-Logs lesen (SteamCMD & Co.)."""
import re
import time
from datetime import datetime

from . import docker_api

RE_PROGRESS = re.compile(r"Update state \(0x[0-9a-fA-F]+\) ([a-zA-Z][a-zA-Z ]*?), progress: ([\d.]+) \((\d+) / (\d+)\)")
RE_SUCCESS = re.compile(r"Success! App '?\d+'? (fully installed|already up to date)|fully installed|already up to date", re.I)
RE_STEAM_ERR = re.compile(r"Error! App '?(\d+)'? state is (0x[0-9a-fA-F]+)")
RE_ERROR = re.compile(r"(Error!|\bERROR\b|\bFATAL\b|Fatal error|Segmentation fault|No space left on device|"
                      r"Permission denied|Traceback \(most recent call last\)|failed to|Failed to|panic:)")
RE_IGNORE = re.compile(r"(0 errors|no error|error_log|ERROR_SUCCESS|errors: 0|Failed to load .*steamclient|"
                       r"\[S_API FAIL\]|SteamAPI_Init|ConVarRef|ignoring|deprecated)", re.I)

PHASES = {"downloading": "Lädt herunter", "verifying install": "Prüft Dateien", "verifying update": "Prüft Update",
          "preallocating": "Reserviert Speicher", "committing": "Installiert", "reconfiguring": "Konfiguriert",
          "staging": "Bereitet vor", "validating": "Prüft Dateien"}

STEAM_STATES = {"0x202": "Nicht genug Speicherplatz auf dem Datenträger", "0x206": "Update-Fehler (Datenträger/Rechte)",
                "0x212": "Nicht genug Speicherplatz", "0x402": "Netzwerk-/Downloadfehler",
                "0x602": "Update fehlgeschlagen – meist Schreibrechte im Datenordner oder Datenträger voll",
                "0x606": "Datenträgerfehler", "0x6": "Keine Verbindung zu Steam", "0x10e": "Update abgebrochen"}

state: dict[str, dict] = {}       # Containername -> Status
_dismissed: dict[str, float] = {}  # Containername -> Fehler bis zu diesem Zeitpunkt ausblenden


def _ts(line: str):
    """Docker-Zeitstempel am Zeilenanfang (logs?timestamps=1)."""
    m = re.match(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.\d+)?Z?\s(.*)$", line)
    if not m:
        return None, line
    try:
        t = datetime.fromisoformat(m.group(1) + "+00:00").timestamp()   # Docker liefert UTC
    except ValueError:
        t = None
    return t, m.group(2)


def parse(text: str, container: str) -> dict:
    lines = [ln for ln in re.split(r"[\r\n]+", text) if ln.strip()]
    progress, success_t, errors = None, None, []
    for raw in lines:
        t, line = _ts(raw)
        line = re.sub(r"\x1b\[[0-9;]*m", "", line).strip()
        m = RE_PROGRESS.search(line)
        if m:
            phase = m.group(1).strip().lower()
            progress = {"phase": phase, "label": PHASES.get(phase, phase.capitalize()), "pct": float(m.group(2)),
                        "done": int(m.group(3)), "total": int(m.group(4)), "t": t or time.time()}
            continue
        if RE_SUCCESS.search(line):
            success_t = t or time.time()
            progress = None
            continue
        m = RE_STEAM_ERR.search(line)
        if m:
            errors.append({"t": t, "text": STEAM_STATES.get(m.group(2).lower(), "Steam-Update-Fehler")
                           + f" ({m.group(2)})", "line": line[:300]})
            progress = None
            continue
        if RE_ERROR.search(line) and not RE_IGNORE.search(line):
            errors.append({"t": t, "text": line[:200], "line": line[:300]})
    prev = state.get(container, {})
    now = time.time()
    rate = None
    if progress:
        pp = prev.get("progress")
        if pp and pp.get("phase") == progress["phase"] and progress["t"] > pp["t"] and progress["done"] >= pp["done"]:
            rate = (progress["done"] - pp["done"]) / max(1, progress["t"] - pp["t"])
            if rate == 0 and pp.get("rate"):
                rate = pp["rate"] * 0.5
        elif pp and pp.get("rate") and pp.get("phase") == progress["phase"]:
            rate = pp["rate"]
        progress["rate"] = round(rate) if rate else None
        left = progress["total"] - progress["done"]
        progress["eta"] = round(left / rate) if rate and rate > 0 and progress["phase"] == "downloading" else None
        # veraltet? (letzte Fortschrittszeile älter als 3 Min. und keine neue)
        progress["stale"] = now - progress["t"] > 180
    cut = max(_dismissed.get(container, 0), now - 3600)
    errors = [e for e in errors if (e["t"] or now) >= cut and (success_t is None or (e["t"] or now) >= success_t)]
    uniq, seen = [], set()
    for e in reversed(errors):
        if e["text"] not in seen:
            seen.add(e["text"])
            uniq.append(e)
    st = {"progress": progress if progress and not progress["stale"] else None, "errors": uniq[:3],
          "last_success": success_t or prev.get("last_success"), "updated": now}
    state[container] = st
    return st


async def poll(container: str) -> dict:
    try:
        r = await docker_api._req("GET", f"/containers/{container}/logs",
                                  params={"stdout": "1", "stderr": "1", "tail": "300", "timestamps": "1"})
        info = await docker_api.inspect(container)
        raw = r.content
        text = raw.decode("utf-8", "replace") if info.get("Config", {}).get("Tty") else docker_api._demux(raw)
        return parse(text, container)
    except docker_api.DockerError as e:
        return state.setdefault(container, {"progress": None, "errors": [], "error_poll": str(e)})


def dismiss(container: str) -> None:
    _dismissed[container] = time.time()
    if container in state:
        state[container]["errors"] = []

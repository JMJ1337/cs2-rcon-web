"""Kleine JSON-Dateispeicher unter DATA_DIR."""
import json
import logging
import os
import threading
from pathlib import Path

log = logging.getLogger("cs2rcon.store")
DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
_lock = threading.Lock()


def load(name: str, default):
    path = DATA_DIR / name
    with _lock:
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            log.exception("%s konnte nicht gelesen werden", name)
            return default


def save(name: str, data) -> None:
    path = DATA_DIR / name
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with _lock:
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)

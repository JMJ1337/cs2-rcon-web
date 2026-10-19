"""Wie lange haben Vorgänge gedauert? (Server anlegen, Spieldateien kopieren, Installation, Vorlage, Prefill, Updates …)

Je Vorgang und Schlüssel (z. B. Spiel) die letzten 10 Läufe – daraus „zuletzt“ und „Durchschnitt“ als Vorschau vor dem Start.
"""
import statistics
import time

from . import store

FILE = "timings.json"
KEEP = 10
_data: dict | None = None


def _load() -> dict:
    global _data
    if _data is None:
        _data = store.load(FILE, {})
    return _data


def record(op: str, key: str, seconds: float, ok: bool = True, info: str = "") -> None:
    if seconds is None or seconds < 1:
        return
    d = _load()
    lst = d.setdefault(f"{op}:{key or '-'}", [])
    lst.append({"t": time.time(), "s": round(seconds), "ok": ok, "info": info[:120]})
    del lst[:-KEEP]
    store.save(FILE, d)


def summary() -> dict:
    """{ "op:key": {last, avg, n, when, info} } – Durchschnitt nur über erfolgreiche Läufe."""
    out = {}
    for k, lst in _load().items():
        good = [x for x in lst if x.get("ok", True)] or lst
        if not good:
            continue
        la = good[-1]
        out[k] = {"last": la["s"], "avg": round(statistics.mean(x["s"] for x in good)), "n": len(good), "when": la["t"],
                  "info": la.get("info") or ""}
    return out


class Timer:
    """with timings.Timer("copy", "cs2"): …  – misst und speichert (Fehler -> ok=False)."""

    def __init__(self, op: str, key: str = "", info: str = ""):
        self.op, self.key, self.info = op, key, info

    def __enter__(self):
        self.t0 = time.time()
        return self

    def __exit__(self, et, ev, tb):
        record(self.op, self.key, time.time() - self.t0, ok=et is None, info=self.info)
        return False

"""Benachrichtigungen per WhatsApp (CallMeBot), optional zusätzlich ntfy (Push-App) oder Telegram.

WhatsApp über CallMeBot (kostenlos, ohne eigenes WhatsApp-Business-Konto):
  1. Die Nummer +34 644 51 95 23 im Handy als Kontakt speichern (CallMeBot).
  2. Per WhatsApp an diesen Kontakt schreiben:  I allow callmebot to send me messages
  3. Die Antwort enthält den API-Key -> hier mit der eigenen Nummer (+49…) eintragen.
Mehrere Empfänger: Nummer;Key je Zeile.

Gleiche Meldungen werden höchstens alle `repeat_min` Minuten wiederholt, maximal `max_per_hour` Nachrichten pro Stunde.
"""
import asyncio
import logging
import time
import urllib.parse

import httpx

from . import store

log = logging.getLogger("cs2rcon")
FILE = "notify.json"
EVENTS = {
    "server_down": "Server ausgefallen / wieder da",
    "problem": "Fehler im Server-Log erkannt",
    "install_done": "Installation / Anlegen fertig",
    "token": "Steam-Token abgelaufen / erneuert",
    "disk": "Speicher fast voll (Cache, NAS)",
    "cache_down": "Lancache läuft nicht",
    "backup": "Sicherung fehlgeschlagen",
    "players": "Erster Spieler auf einem leeren Server",
}
DEFAULTS = {"enabled": False, "whatsapp": "", "ntfy_url": "", "telegram_token": "", "telegram_chat": "",
            "events": {k: k != "players" for k in EVENTS}, "repeat_min": 360, "max_per_hour": 12,
            "quiet_from": "", "quiet_to": ""}
_sent: dict[str, float] = {}
_hour: list[float] = []
history: list[dict] = []


def settings() -> dict:
    d = {**DEFAULTS, **store.load(FILE, {})}
    d["events"] = {**DEFAULTS["events"], **(d.get("events") or {})}
    return d


def public_settings() -> dict:
    d = settings()
    wa = []
    for line in (d.get("whatsapp") or "").splitlines():
        if ";" in line:
            ph, _, key = line.partition(";")
            wa.append(f"{ph.strip()};{'••••' if key.strip() else ''}")
    return {**d, "whatsapp": "\n".join(wa), "telegram_token": "••••" if d.get("telegram_token") else "",
            "event_labels": EVENTS, "history": history[-20:]}


def save(new: dict) -> dict:
    d = settings()
    for k in ("enabled", "ntfy_url", "telegram_chat", "repeat_min", "max_per_hour", "quiet_from", "quiet_to"):
        if k in new and new[k] is not None:
            d[k] = new[k]
    if isinstance(new.get("events"), dict):
        d["events"] = {k: bool(new["events"].get(k, d["events"].get(k))) for k in EVENTS}
    if new.get("telegram_token") not in (None, "••••"):
        d["telegram_token"] = new["telegram_token"].strip()
    if new.get("whatsapp") is not None:              # maskierte Keys aus der alten Liste übernehmen
        old = {ln.partition(";")[0].strip(): ln.partition(";")[2].strip() for ln in (d.get("whatsapp") or "").splitlines() if ";" in ln}
        out = []
        for ln in new["whatsapp"].splitlines():
            ph, _, key = ln.partition(";")
            ph, key = ph.strip().replace(" ", ""), key.strip()
            if not ph:
                continue
            if key in ("", "••••"):
                key = old.get(ph, "")
            out.append(f"{ph};{key}")
        d["whatsapp"] = "\n".join(out)
    store.save(FILE, d)
    return public_settings()


def _quiet(d: dict) -> bool:
    a, b = d.get("quiet_from") or "", d.get("quiet_to") or ""
    if not (a and b):
        return False
    now = time.strftime("%H:%M")
    return (a <= now < b) if a < b else (now >= a or now < b)


async def _send_whatsapp(cl: httpx.AsyncClient, phone: str, key: str, text: str) -> str | None:
    url = "https://api.callmebot.com/whatsapp.php?" + urllib.parse.urlencode({"phone": phone, "text": text, "apikey": key})
    r = await cl.get(url)
    body = r.text[:200]
    if r.status_code >= 400 or "ERROR" in body.upper() and "queued" not in body.lower():
        return f"WhatsApp {phone}: {r.status_code} {body.strip()[:120]}"
    return None


async def send(text: str, *, event: str = "", key: str = "", force: bool = False) -> list[str]:
    """Nachricht an alle Kanäle. key = Dedupe-Schlüssel (gleiche Meldung nicht dauernd wiederholen)."""
    d = settings()
    if not force:
        if not d.get("enabled") or (event and not d["events"].get(event, True)) or _quiet(d):
            return []
        k = key or text
        if time.time() - _sent.get(k, 0) < int(d.get("repeat_min") or 360) * 60:
            return []
        now = time.time()
        _hour[:] = [t for t in _hour if now - t < 3600]
        if len(_hour) >= int(d.get("max_per_hour") or 12):
            return ["Limit pro Stunde erreicht"]
        _sent[k] = now
        _hour.append(now)
    from . import automation
    title = (d.get("title") or "").strip() or automation.brand()
    msg = f"🎮 {title}: {text}"
    errors = []
    async with httpx.AsyncClient(timeout=20) as cl:
        for line in (d.get("whatsapp") or "").splitlines():
            ph, _, apikey = line.partition(";")
            if ph.strip() and apikey.strip():
                try:
                    e = await _send_whatsapp(cl, ph.strip(), apikey.strip(), msg)
                    if e:
                        errors.append(e)
                except httpx.HTTPError as ex:
                    errors.append(f"WhatsApp {ph}: {ex.__class__.__name__}")
                await asyncio.sleep(1)       # CallMeBot mag keine Salven
        if d.get("ntfy_url"):
            try:
                r = await cl.post(d["ntfy_url"], content=msg.encode(), headers={"Title": title.encode("ascii", "ignore").decode() or "LAN"})
                if r.status_code >= 400:
                    errors.append(f"ntfy: {r.status_code}")
            except httpx.HTTPError as ex:
                errors.append(f"ntfy: {ex.__class__.__name__}")
        if d.get("telegram_token") and d.get("telegram_chat"):
            try:
                r = await cl.post(f"https://api.telegram.org/bot{d['telegram_token']}/sendMessage",
                                  data={"chat_id": d["telegram_chat"], "text": msg})
                if r.status_code >= 400:
                    errors.append(f"Telegram: {r.status_code}")
            except httpx.HTTPError as ex:
                errors.append(f"Telegram: {ex.__class__.__name__}")
    history.append({"t": time.time(), "text": text, "event": event, "errors": errors})
    del history[:-50]
    if errors:
        log.warning("Benachrichtigung: %s", "; ".join(errors))
    return errors


def fire(text: str, *, event: str = "", key: str = "") -> None:
    """Ohne zu warten senden (aus Schleifen heraus)."""
    try:
        asyncio.get_running_loop().create_task(send(text, event=event, key=key))
    except RuntimeError:
        pass

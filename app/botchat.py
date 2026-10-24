"""Steam-Bot im Gespräch: versteht ein paar einfache Wünsche per Chat-Nachricht.

- „stop“ / „keine Nachrichten mehr“ → keine Rundnachrichten und Ankündigungen mehr (mit „start“ wieder an)
- „Vorschlag: …“ / „Idee …“ / „Verbesserung …“ → landet im Posteingang der Verwaltung (Steam-Bot)
- „Server …“ / „Kannst du einen Valheim-Server anlegen?“ → Serverwunsch im Posteingang
- „hilfe“ → kurze Übersicht; alles, was er nicht versteht, beantwortet er ebenfalls mit der Übersicht

Die Antworten gehen sofort zurück; Posteingang-Einträge lösen zusätzlich eine Benachrichtigung aus (wenn eingerichtet).
"""
import asyncio
import logging
import re
import secrets
import time

from . import automation, notify, playerdb, steambot_ctl, store

log = logging.getLogger("cs2rcon")
INBOX = "botinbox.json"
_help_sent: dict[str, list[float]] = {}

RX_STOP = re.compile(r"\b(stop+|abmelden|abbestellen|unsubscribe|keine\s+(nachricht|nachrichten|infos?|werbung|rundmails?|mails?)"
                     r"|nicht\s+mehr\s+(an)?schreiben|schreib\s+mir\s+nicht|lass\s+mich\s+in\s+ruhe)\b", re.I)
RX_START = re.compile(r"^\s*(start|wieder\s+(nachrichten|schreiben|an)|nachrichten\s+(wieder\s+)?an|anmelden)\b", re.I)
RX_IDEA = re.compile(r"^\s*(vorschlag|vorschläge|idee|verbesserung|verbesserungsvorschlag|feedback|wunsch|anregung)\b[\s:,.\-–]*", re.I)
RX_SERVER = re.compile(r"\bserver\b", re.I)
RX_SERVER_ASK = re.compile(r"\b(anlegen|erstellen|aufmachen|aufsetzen|starten|einrichten|bitte|brauch|hätte|haette|wünsch|wuensch|gern|möchte|moechte|können|kannst|könnt)\w*", re.I)
RX_HELP = re.compile(r"^\s*(hilfe|help|\?|befehle|commands|was\s+kannst\s+du)\b", re.I)

HELP = ("Hallo, ich bin der Bot von {brand} 🤖 – das verstehe ich:\n"
        "• „stop“ – ich schicke dir keine Rundnachrichten mehr („start“ = wieder an)\n"
        "• „Vorschlag: …“ – deine Idee oder Verbesserung geht an die Orga\n"
        "• „Server: …“ – Wunsch nach einem Server, z. B. „Server: Valheim für 6 Leute heute Abend“\n"
        "• „hilfe“ – diese Übersicht")


# ---------------------------------------------------------------- Abmeldungen (keine Rundnachrichten)
def optouts() -> dict:
    return steambot_ctl.settings().get("optout") or {}


def opted_out(steamid: str) -> bool:
    return str(steamid) in optouts()


def without_optouts(steamids: list[str]) -> tuple[list[str], list[str]]:
    """(senden, ausgelassen) – für Rundnachrichten, Ankündigungen und Einladungen über die API."""
    o = optouts()
    keep = [s for s in steamids if str(s) not in o]
    return keep, [s for s in steamids if str(s) in o]


def set_optout(steamid: str, on: bool) -> None:
    o = dict(optouts())
    if on:
        o[str(steamid)] = time.time()
    else:
        o.pop(str(steamid), None)
    steambot_ctl.save({"optout": o})


# ---------------------------------------------------------------- Posteingang
def inbox() -> list[dict]:
    return store.load(INBOX, [])


def inbox_set(eid: str, status: str | None = None, delete: bool = False, game: str | None = None) -> None:
    lst = inbox()
    if delete:
        lst = [x for x in lst if x["id"] != eid]
    else:
        for x in lst:
            if x["id"] == eid:
                if status:
                    x["status"] = status
                if game is not None:
                    x["game"] = game or None
    store.save(INBOX, lst)


def _guess_game(text: str) -> str | None:
    from .games import GAMES
    t = text.lower()
    best = None
    for k, g in GAMES.items():
        for name in {k, (g.get("label") or "").lower(), (g.get("short") or "").lower()}:
            if name and len(name) >= 3 and re.search(r"(?<![a-z0-9])" + re.escape(name) + r"(?![a-z0-9])", t):
                if not best or len(name) > best[1]:
                    best = (k, len(name))
    return best[0] if best else None


def _M():
    from . import main as M
    return M


def _tool_user(steamid: str) -> dict | None:
    """Benutzerkonto zur SteamID (direkt oder über den verknüpften Spieler)."""
    M = _M()
    u = M.users.find_by_steam(steamid)
    if not u:
        p = playerdb.get(steamid)
        u = M.users.find(p["user"]) if p and p.get("user") else None
    return None if not u or u.get("pending") else u


async def _say(steamid: str, text: str) -> None:
    try:
        await steambot_ctl.api("POST", "/msg", {"steamids": [steamid], "text": text}, timeout=20)
    except Exception as e:  # noqa: BLE001
        log.info("Steam-Bot an %s: %s", steamid, e)


async def _notify_admin(e: dict) -> None:
    label = "Serverwunsch" if e["kind"] == "server" else "Vorschlag"
    try:
        await notify.send(f"Steam-Bot – {label} von {e['name']}: {e['text'][:300]}", event="bot_inbox", key=e["id"])
    except Exception:  # noqa: BLE001
        pass


async def approve(eid: str, game: str | None, by: str = "Orga") -> tuple[bool, str]:
    """Serverwunsch annehmen: Server mit Standardwerten anlegen, Spieler informieren, bei Fertigstellung Adresse schicken."""
    from .games import GAMES
    M = _M()
    lst = inbox()
    e = next((x for x in lst if x["id"] == eid), None)
    if not e or e["kind"] != "server":
        return False, "Eintrag nicht gefunden"
    if e.get("status") not in ("offen", "fehler"):
        return False, f"Schon entschieden ({e.get('status')})"
    g = game or e.get("game")
    if not g or g not in M.templates.TEMPLATES:
        return False, "Bitte erst das Spiel auswählen"
    try:
        job = await M.create_default_server(g)
    except Exception as ex:  # noqa: BLE001
        msg = getattr(ex, "detail", None) or str(ex)
        e.update(status="fehler", note=str(msg)[:200])
        store.save(INBOX, lst)
        return False, str(msg)
    label = (GAMES.get(g) or {}).get("label") or g
    e.update(status="angelegt", game=g, job=job.get("id"), by=by, decided=time.time())
    store.save(INBOX, lst)
    asyncio.create_task(_watch_job(e["id"], e["steamid"], job.get("id"), label))
    msg = f"✅ Dein {label}-Server wird jetzt angelegt. Ich schicke dir die Adresse, sobald er läuft (kann ein paar Minuten dauern)."
    if not by.endswith("(eigenes Recht)"):
        await _say(e["steamid"], msg)
    return True, msg


async def deny(eid: str, reason: str = "") -> bool:
    lst = inbox()
    e = next((x for x in lst if x["id"] == eid), None)
    if not e:
        return False
    e.update(status="abgelehnt", decided=time.time(), note=reason[:200])
    store.save(INBOX, lst)
    if e["kind"] == "server":
        await _say(e["steamid"], "🙁 Dein Serverwunsch wurde leider abgelehnt" + (f": {reason}" if reason else " – sprich gern die Orga direkt an."))
    return True


async def _watch_job(eid: str, steamid: str, jid: str | None, label: str) -> None:
    """Auf den Anlege-Auftrag warten und dem Spieler die Adresse schicken, sobald der Server online ist."""
    M = _M()
    for _ in range(4 * 3600 // 20):
        await asyncio.sleep(20)
        job = M._jobs.get(jid or "") or {}
        if job.get("error"):
            await _say(steamid, f"⚠️ Dein {label}-Server konnte leider nicht angelegt werden – die Orga schaut sich das an.")
            inbox_set(eid, "fehler")
            await _notify_admin({"kind": "server", "name": label, "text": f"Anlegen fehlgeschlagen: {job['error']}", "id": eid + "f"})
            return
        sid = job.get("server_id")
        if sid and (M._state.get(sid) or {}).get("online"):
            s = next((x for x in M.load_servers() if x["id"] == sid), None)
            if not s:
                return
            p = playerdb.get(steamid)
            lan = bool(p and playerdb.connects_from_lan(p))
            await _say(steamid, f"🎮 Dein {label}-Server „{s['name']}“ läuft!\n" + (await M.invite_join_text(s, lan)).strip())
            inbox_set(eid, "fertig")
            return


async def _add_inbox(kind: str, steamid: str, text: str, notify_admin: bool = True) -> dict:
    p = playerdb.get(steamid)
    name = playerdb.display(p) if p else steamid
    e = {"id": secrets.token_hex(4), "t": time.time(), "kind": kind, "steamid": steamid, "name": name,
         "text": text.strip()[:1000], "status": "offen"}
    if kind == "server":
        e["game"] = _guess_game(text)
    lst = inbox()
    lst.append(e)
    store.save(INBOX, lst[-300:])
    if notify_admin:
        await _notify_admin(e)
    return e


# ---------------------------------------------------------------- Nachrichten verarbeiten
async def handle(steamid: str, text: str) -> str | None:
    """Antwort auf eine eingehende Nachricht (None = nichts antworten)."""
    t = (text or "").strip()
    if not t:
        return None
    if RX_START.search(t) and opted_out(steamid):
        set_optout(steamid, False)
        return "👍 Alles klar – du bekommst wieder Infos und Rundnachrichten von der LAN. Mit „stop“ kannst du sie jederzeit abbestellen."
    if RX_STOP.search(t) and not RX_IDEA.match(t):
        if opted_out(steamid):
            return "Du bist schon abgemeldet – ich schicke dir keine Rundnachrichten. Mit „start“ bekommst du sie wieder."
        set_optout(steamid, True)
        return ("✅ Verstanden – ich schicke dir keine Rundnachrichten und Ankündigungen mehr. "
                "Einladungen zu deinen eigenen Turnier-Matches kommen weiterhin. Mit „start“ ist alles wieder an.")
    m = RX_IDEA.match(t)
    if m:
        body = t[m.end():].strip()
        if len(body) < 3:
            return "Gern! Schreib deinen Vorschlag einfach dahinter, z. B. „Vorschlag: mehr Aim-Maps am Freitag“."
        await _add_inbox("idee", steamid, body)
        return "💡 Danke für deinen Vorschlag – ich habe ihn an die Orga weitergegeben!"
    if RX_SERVER.search(t) and (RX_SERVER_ASK.search(t) or re.match(r"^\s*server\b", t, re.I)):
        body = re.sub(r"^\s*server\b[\s:,.\-–]*", "", t, flags=re.I).strip() or t
        e = await _add_inbox("server", steamid, body, notify_admin=False)
        from .games import GAMES
        g = (GAMES.get(e.get("game") or "") or {}).get("label")
        u = _tool_user(steamid)
        if g and u and _M().users.level(u, e["game"]) >= 4:          # darf selbst anlegen -> sofort
            recent = [x for x in inbox() if x.get("steamid") == steamid and x.get("status") == "angelegt" and time.time() - x["t"] < 1800]
            if recent:
                inbox_set(e["id"], "offen")
                await _notify_admin(e)
                return "⏳ Du hast gerade erst einen Server angelegt – dein neuer Wunsch liegt jetzt bei der Orga."
            ok, msg = await approve(e["id"], None, by=f"{u['username']} (eigenes Recht)")
            return msg if ok else f"⚠️ Anlegen hat nicht geklappt: {msg} – ich gebe es an die Orga weiter."
        await _notify_admin(e)
        return (f"🖥️ Danke – dein Wunsch nach einem {g}-Server ist bei der Orga angekommen. Du bekommst Bescheid, sobald sie entschieden hat."
                if g else "🖥️ Danke – dein Serverwunsch ist bei der Orga angekommen. Schreib gern dazu, welches Spiel und für wie viele Leute.")
    # „hilfe“ oder nicht verstanden: immer die Übersicht – nur gegen Endlos-Pingpong (z. B. mit einem anderen Bot)
    # höchstens 6 Antworten in 10 Minuten pro Person
    now = time.time()
    recent = [x for x in _help_sent.get(steamid, []) if now - x < 600]
    if len(recent) >= 6:
        return None
    _help_sent[steamid] = recent + [now]
    intro = "" if RX_HELP.match(t) else "🤔 Das habe ich leider nicht verstanden.\n\n"
    return intro + HELP.format(brand=automation.brand())


async def tick() -> None:
    """Alle paar Sekunden: neue eingehende Nachrichten beantworten."""
    d = steambot_ctl.settings()
    if not d.get("enabled") or d.get("chat") is False:
        return
    st = await steambot_ctl.status()
    bot = st.get("bot") or {}
    if bot.get("state") != "angemeldet":
        return
    msgs = [m for m in bot.get("messages") or [] if m.get("dir") == "in" and m.get("from")]
    seen = d.get("chat_seen")
    if seen is None:                                         # erster Lauf: alte Nachrichten nicht mehr beantworten
        steambot_ctl.save({"chat_seen": max([m["t"] for m in msgs] + [time.time()])})
        return
    new = sorted((m for m in msgs if m["t"] > seen), key=lambda m: m["t"])
    if not new:
        return
    for m in new:
        try:
            reply = await handle(m["from"], m.get("text") or "")
            if reply:
                await steambot_ctl.api("POST", "/msg", {"steamids": [m["from"]], "text": reply}, timeout=20)
        except Exception as e:  # noqa: BLE001
            log.info("Steam-Bot-Chat: %s", e)
    steambot_ctl.save({"chat_seen": new[-1]["t"]})

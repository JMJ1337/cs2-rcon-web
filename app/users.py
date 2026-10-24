"""Benutzerverwaltung (liegt in /data/users.json und übersteht damit jedes Update)."""
import hashlib
import hmac
import secrets
import time

from . import store

FILE = "users.json"
ROLES = {"admin": 3, "user": 2, "viewer": 1}
ROLE_LABELS = {"admin": "Administrator", "user": "Benutzer (Rechte pro Spiel)", "viewer": "Nur ansehen"}
# Rechte pro Spiel: 0 = kein Zugriff, 1 = sehen, 2 = bedienen, 3 = verwalten, 4 = anlegen/löschen
LEVELS = {0: "Kein Zugriff", 1: "Sehen", 2: "Bedienen", 3: "Verwalten", 4: "Anlegen"}
LEVEL_HINTS = {1: "Status, Spieler, Verlauf und Log ansehen",
               2: "zusätzlich Start/Stopp/Neustart, Konsole/RCON, Map & Modus, Spielstand speichern",
               3: "zusätzlich Konfiguration, Dateien, Spielstände laden, Container-Einstellungen, Server bearbeiten",
               4: "zusätzlich neue Server dieses Spiels anlegen und löschen"}
ROLE_DEFAULT = {"user": 2, "viewer": 1}
# Sonderrechte (zusätzlich zu den Spiel-Rechten)
RIGHTS = {"tournament": "Turniere anlegen/bearbeiten (inkl. Live-Stream)"}


# ---------------------------------------------------------------- Profile (Rechte-Vorlagen)
PROFILES_FILE = "user_profiles.json"
DEFAULT_PROFILES = [
    {"id": "zuschauer", "name": "Zuschauer", "color": "#6b7a8f", "desc": "sieht alle Server, Spieler und Logs", "perms": {"*": 1}, "rights": []},
    {"id": "spielleiter", "name": "Spielleiter", "color": "#3e8f5a", "desc": "bedient alle Server (Start/Stopp, Konsole, Maps, Bots)",
     "perms": {"*": 2}, "rights": []},
    {"id": "turnierorga", "name": "Turnier-Orga", "color": "#d9a441", "desc": "Turniere + Stream, CS2 bedienen",
     "perms": {"*": 1, "cs2": 2}, "rights": ["tournament"]},
    {"id": "betreuer", "name": "Server-Betreuer", "color": "#3e6fa8", "desc": "verwaltet alle Server (Konfiguration, Dateien, Spielstände)",
     "perms": {"*": 3}, "rights": ["tournament"]},
    {"id": "techniker", "name": "Techniker", "color": "#b5562b", "desc": "darf zusätzlich Server anlegen und löschen",
     "perms": {"*": 4}, "rights": ["tournament"]},
]


PUBLIC_PROFILE = {"id": "oeffentlich", "name": "Nur öffentliche Seite", "color": "#6b7a8f",
                  "desc": "kein Zugriff auf die Verwaltung – sieht nach dem Login nur die öffentliche Übersicht",
                  "perms": {"*": 0}, "rights": []}


def profiles() -> list[dict]:
    p = store.load(PROFILES_FILE, None)
    if p is None:
        p = [PUBLIC_PROFILE] + DEFAULT_PROFILES
        store.save(PROFILES_FILE, p)
        store.save("user_profiles_meta.json", {"public_added": True})
    elif not store.load("user_profiles_meta.json", {}).get("public_added"):     # einmalig nachrüsten
        if not any(x["id"] == PUBLIC_PROFILE["id"] for x in p):
            p = [PUBLIC_PROFILE] + p
            store.save(PROFILES_FILE, p)
        store.save("user_profiles_meta.json", {"public_added": True})
    return p


def profile(pid: str | None) -> dict | None:
    return next((p for p in profiles() if p["id"] == pid), None) if pid else None


def save_profile(data: dict) -> dict:
    name = str(data.get("name") or "").strip()[:40]
    if not name:
        raise ValueError("Name fehlt")
    allp = profiles()
    pid = data.get("id") or ""
    cur = next((p for p in allp if p["id"] == pid), None)
    if cur is None:
        base = "".join(ch for ch in name.lower().replace(" ", "-") if ch.isalnum() or ch == "-")[:24] or "profil"
        pid, n = base, 2
        while any(p["id"] == pid for p in allp):
            pid, n = f"{base}-{n}", n + 1
        cur = {"id": pid}
        allp.append(cur)
    cur.update(name=name, color=str(data.get("color") or "#6b7a8f")[:9], desc=str(data.get("desc") or "")[:120],
               perms=clean_perms(data.get("perms")) or {"*": 1}, rights=[r for r in (data.get("rights") or []) if r in RIGHTS])
    store.save(PROFILES_FILE, allp)
    return cur


def delete_profile(pid: str) -> None:
    store.save(PROFILES_FILE, [p for p in profiles() if p["id"] != pid])
    users = load()
    for u in users:
        if u.get("profile") == pid:
            u.pop("profile", None)
        if pid in (u.get("profiles") or []):
            u["profiles"] = [x for x in u["profiles"] if x != pid]
    store.save(FILE, users)


def user_profiles(u: dict) -> list[str]:
    """Profile des Benutzers (mehrere möglich; altes Feld „profile“ wird mitgelesen)."""
    ids = list(u.get("profiles") or [])
    if u.get("profile") and u["profile"] not in ids:
        ids.insert(0, u["profile"])
    return [i for i in ids if profile(i)]


def effective_perms(u: dict) -> dict:
    """Mehrere Profile: je Spiel gilt die höchste Stufe; danach eigene Abweichungen des Benutzers."""
    prs = [profile(i) for i in user_profiles(u)]
    if not prs:
        base = {"*": ROLE_DEFAULT.get(u.get("role"), 0)}
    else:
        star = max(int(p["perms"].get("*", 0)) for p in prs)
        keys = {k for p in prs for k in p["perms"] if k != "*"}
        base = {"*": star} | {k: max(int(p["perms"].get(k, p["perms"].get("*", 0))) for p in prs) for k in keys}
        base = {k: v for k, v in base.items() if k == "*" or v != star}
    return base | (u.get("perms") or {})


def effective_rights(u: dict) -> list[str]:
    if u.get("role") == "admin":
        return list(RIGHTS)
    prs = [profile(i) for i in user_profiles(u)]
    return [r for r in RIGHTS if r in (u.get("rights") or []) or any(r in p.get("rights", []) for p in prs)]


def public_only(u: dict | None) -> bool:
    """Wartet auf Freigabe, Profil „Nur öffentliche Seite“ oder ganz ohne Rechte: sieht nur die öffentliche Seite."""
    if not u or u.get("role") == "admin":
        return False
    if u.get("pending") or PUBLIC_PROFILE["id"] in user_profiles(u):
        return True
    perms = effective_perms(u)
    return max([int(v) for v in perms.values()] or [0]) <= 0 and not effective_rights(u)


def has_right(u: dict | None, right: str) -> bool:
    return bool(u) and right in effective_rights(u)


def level(u: dict | None, game: str | None) -> int:
    """Rechtestufe des Benutzers für ein Spiel (Profil + eigene Abweichungen)."""
    if not u:
        return 0
    if u.get("role") == "admin":
        return 4
    perms = effective_perms(u)
    if game and game in perms:
        return int(perms[game])
    return int(perms.get("*", 0))


def max_level(u: dict | None, games) -> int:
    return max([level(u, g) for g in games] + [level(u, None)], default=0)


def clean_perms(perms: dict | None) -> dict:
    out = {}
    for k, v in (perms or {}).items():
        try:
            v = int(v)
        except (TypeError, ValueError):
            continue
        if 0 <= v <= 4 and isinstance(k, str) and len(k) <= 32:
            out[k] = v
    return out


def _hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000).hex()
    return f"pbkdf2${salt}${h}"


def _check(password: str, stored: str) -> bool:
    try:
        _, salt, h = stored.split("$")
    except ValueError:
        return False
    return hmac.compare_digest(_hash(password, salt).split("$")[2], h)


def load() -> list[dict]:
    return store.load(FILE, [])


def public(u: dict) -> dict:
    return {k: u.get(k) for k in ("username", "role", "created", "last_login", "note", "steamid", "pending", "steam_name")} | {"profiles": user_profiles(u),
        "rights": effective_rights(u), "own_rights": [r for r in (u.get("rights") or []) if r in RIGHTS],
        "role_label": ROLE_LABELS.get(u.get("role"), ""),
        "own_perms": u.get("perms") or {}, "public_only": public_only(u),
        "perms": {"*": 4} if u.get("role") == "admin" else effective_perms(u)}


def find(username: str) -> dict | None:
    username = (username or "").strip().lower()
    return next((u for u in load() if u["username"] == username), None)


def verify(username: str, password: str) -> dict | None:
    u = find(username)
    if u and _check(password, u["hash"]):
        users = load()
        for x in users:
            if x["username"] == u["username"]:
                x["last_login"] = int(time.time())
        store.save(FILE, users)
        return u
    return None


def upsert(username: str, password: str | None, role: str | None, perms: dict | None = None, rights: list | None = None,
           profile_ids: list | None = None, note: str | None = None) -> dict:
    username = (username or "").strip().lower()
    if not username or len(username) > 32 or not username.replace("_", "").replace("-", "").replace(".", "").isalnum():
        raise ValueError("Benutzername: 1–32 Zeichen, Buchstaben/Ziffern/._-")
    if role and role not in ROLES:
        raise ValueError("Unbekannte Rolle")
    users = load()
    u = next((x for x in users if x["username"] == username), None)
    if u is None:
        if not password:
            raise ValueError("Passwort fehlt")
        u = {"username": username, "role": role or "user", "created": int(time.time()), "last_login": None}
        if (role or "user") != "admin" and not profile_ids and not perms:
            u["perms"] = {"*": 0}          # neue Benutzer: nur öffentliche Seite, bis ein Profil/Recht vergeben ist
        users.append(u)
    if password:
        if len(password) < 6:
            raise ValueError("Passwort muss mindestens 6 Zeichen haben")
        u["hash"] = _hash(password)
        u["pw_changed"] = int(time.time())
    if role:
        if u["role"] == "admin" and role != "admin" and sum(1 for x in users if x["role"] == "admin") <= 1:
            raise ValueError("Der letzte Administrator kann nicht herabgestuft werden")
        u["role"] = role
    if perms is not None:
        u["perms"] = clean_perms(perms)
    if rights is not None:
        u["rights"] = [r for r in rights if r in RIGHTS]
    if profile_ids is not None:
        bad = [i for i in profile_ids if not profile(i)]
        if bad:
            raise ValueError("Unbekanntes Profil: " + ", ".join(bad))
        u["profiles"] = list(dict.fromkeys(profile_ids))
        u.pop("profile", None)
    if note is not None:
        u["note"] = note.strip()[:80]
    store.save(FILE, users)
    return u


def delete(username: str) -> None:
    users = load()
    u = next((x for x in users if x["username"] == username), None)
    if not u:
        return
    if u["role"] == "admin" and sum(1 for x in users if x["role"] == "admin") <= 1:
        raise ValueError("Der letzte Administrator kann nicht gelöscht werden")
    store.save(FILE, [x for x in users if x["username"] != username])


def bootstrap(admin_password: str) -> None:
    """Beim ersten Start: Benutzer 'admin' mit dem ADMIN_PASSWORD aus dem Stack anlegen."""
    if not load():
        store.save(FILE, [{"username": "admin", "role": "admin", "hash": _hash(admin_password),
                           "created": int(time.time()), "last_login": None, "pw_changed": 0}])


def restore_admin(admin_password: str) -> None:
    """Notzugang: gelöschten Benutzer „admin“ mit dem Stack-Passwort wieder anlegen."""
    lst = load()
    if any(u.get("username") == "admin" for u in lst):
        return
    lst.append({"username": "admin", "role": "admin", "hash": _hash(admin_password),
                "created": int(time.time()), "last_login": None, "pw_changed": 0})
    store.save(FILE, lst)


# ---------------------------------------------------------------- Registrierung per Steam
def find_by_steam(steamid: str) -> dict | None:
    return next((u for u in load() if steamid and u.get("steamid") == steamid), None)


def _free_name(base: str, users: list[dict]) -> str:
    import re as _re
    b = _re.sub(r"[^a-z0-9._-]", "", (base or "").lower().replace(" ", "_"))[:24] or "spieler"
    name, n = b, 2
    while any(x["username"] == name for x in users):
        name, n = f"{b}{n}", n + 1
    return name


def register_steam(steamid: str, steam_name: str) -> dict:
    """Neues Konto über Steam-Login: wartet auf Freigabe durch einen Admin (bis dahin nur öffentliche Seite)."""
    users = load()
    u = {"username": _free_name(steam_name or f"steam{steamid[-6:]}", users), "role": "user", "created": int(time.time()),
         "last_login": int(time.time()), "steamid": steamid, "steam_name": (steam_name or "")[:64], "pending": True,
         "profiles": [PUBLIC_PROFILE["id"]], "hash": _hash(secrets.token_urlsafe(24)), "pw_changed": 0}
    users.append(u)
    store.save(FILE, users)
    return u


def touch_login(username: str) -> None:
    users = load()
    for x in users:
        if x["username"] == username:
            x["last_login"] = int(time.time())
    store.save(FILE, users)


def approve(username: str, profile_ids: list[str]) -> dict:
    u = upsert(username, None, None, None, None, profile_ids=[p for p in profile_ids if p != PUBLIC_PROFILE["id"]] or [PUBLIC_PROFILE["id"]])
    users = load()
    for x in users:
        if x["username"] == u["username"]:
            x.pop("pending", None)
            u = x
    store.save(FILE, users)
    return u


def link_steam(username: str, steamid: str | None) -> None:
    users = load()
    for x in users:
        if x["username"] == username:
            if steamid:
                x["steamid"] = steamid
            else:
                x.pop("steamid", None)
    store.save(FILE, users)

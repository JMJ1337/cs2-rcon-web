"""Benutzerverwaltung (liegt in /data/users.json und übersteht damit jedes Update)."""
import hashlib
import hmac
import secrets
import time

from . import store

FILE = "users.json"
ROLES = {"admin": 3, "user": 2, "viewer": 1}
ROLE_LABELS = {"admin": "Administrator", "user": "Spielleiter", "viewer": "Nur ansehen"}


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
    return {k: u.get(k) for k in ("username", "role", "created", "last_login")} | {"role_label": ROLE_LABELS.get(u.get("role"), "")}


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


def upsert(username: str, password: str | None, role: str | None) -> dict:
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

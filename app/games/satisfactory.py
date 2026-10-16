"""Client für die offizielle Satisfactory Dedicated Server HTTPS-API (/api/v1)."""
import re
import time

import httpx


class SatisfactoryError(Exception):
    pass


class SatisfactoryClient:
    def __init__(self, host: str, port: int, password: str, timeout: float = 6.0):
        self.url = f"https://{host}:{port}/api/v1"
        self.password = password or ""
        self.timeout = timeout
        self.token: str | None = None
        self.privilege: str | None = None

    async def _call(self, function: str, data: dict | None = None, token: str | None = None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            async with httpx.AsyncClient(verify=False, timeout=self.timeout) as cl:  # selbstsigniertes Zertifikat
                r = await cl.post(self.url, json={"function": function, "data": data or {}}, headers=headers)
        except httpx.HTTPError as e:
            raise SatisfactoryError(f"Keine Verbindung zu {self.url} ({e.__class__.__name__})") from e
        if r.status_code == 204 or not r.content:
            return {}
        try:
            j = r.json()
        except ValueError:
            raise SatisfactoryError(f"Ungültige Antwort (HTTP {r.status_code})")
        if r.status_code >= 400 or "errorCode" in j:
            raise SatisfactoryError(j.get("errorMessage") or j.get("errorCode") or f"HTTP {r.status_code}")
        return j.get("data", j)

    async def login(self, force=False) -> str:
        if self.token and not force:
            return self.token
        if self.password:
            d = await self._call("PasswordLogin", {"MinimumPrivilegeLevel": "Administrator", "Password": self.password})
            self.privilege = "Administrator"
        else:
            d = await self._call("PasswordlessLogin", {"MinimumPrivilegeLevel": "Client"})
            self.privilege = "Client"
        self.token = d.get("authenticationToken")
        if not self.token:
            raise SatisfactoryError("Login fehlgeschlagen")
        return self.token

    async def call(self, function: str, data: dict | None = None):
        await self.login()
        try:
            return await self._call(function, data, self.token)
        except SatisfactoryError as e:
            if "token" in str(e).lower() or "auth" in str(e).lower():
                await self.login(force=True)
                return await self._call(function, data, self.token)
            raise

    async def unclaimed(self) -> bool:
        try:
            await self._call("PasswordlessLogin", {"MinimumPrivilegeLevel": "InitialAdmin"})
            return True
        except SatisfactoryError:
            return False

    async def claim(self, server_name: str, admin_password: str) -> str:
        d = await self._call("PasswordlessLogin", {"MinimumPrivilegeLevel": "InitialAdmin"})
        tok = d.get("authenticationToken")
        d2 = await self._call("ClaimServer", {"ServerName": server_name, "AdminPassword": admin_password}, tok)
        self.password = admin_password
        self.token = d2.get("authenticationToken") or None
        return self.token or ""

    def close(self):
        pass


def _phase(p: str | None) -> str:
    if not p:
        return ""
    m = re.search(r"GP_([A-Za-z_]+?)(?:_(\d+))?'?$", p.strip("'\""))
    if not m:
        return p
    name = m.group(1).replace("_", " ").replace("Project Assembly Phase", "Projekt-Montage Phase").strip()
    return f"{name} {m.group(2)}" if m.group(2) else name


def _duration(sec) -> str:
    try:
        s = int(sec)
    except (TypeError, ValueError):
        return ""
    h, m = divmod(s // 60, 60)
    return f"{h} h {m} min"


async def status(c: SatisfactoryClient) -> dict:
    unclaimed = False
    try:
        d = await c.call("QueryServerState")
    except SatisfactoryError:
        if await c.unclaimed():
            unclaimed = True
            d = {}
        else:
            raise
    st = d.get("serverGameState", {}) if d else {}
    tick = st.get("averageTickRate")
    extra = {
        "Session": st.get("activeSessionName") or "–",
        "Tech-Stufe": st.get("techTier"),
        "Phase": _phase(st.get("gamePhase")),
        "Spielzeit": _duration(st.get("totalGameDuration")),
        "Tickrate": f"{tick:.1f}/s" if isinstance(tick, (int, float)) else None,
        "Status": "pausiert" if st.get("isGamePaused") else ("läuft" if st.get("isGameRunning") else "keine Session geladen"),
    }
    return {
        "map": st.get("activeSessionName") or ("nicht beansprucht" if unclaimed else "–"),
        "humans": st.get("numConnectedPlayers"), "bots": 0, "max_players": st.get("playerLimit"),
        "players": [], "version": None, "hostname": None,
        "mode": {"key": "satisfactory", "label": "Satisfactory"},
        "extra": {k: v for k, v in extra.items() if v not in (None, "")},
        "unclaimed": unclaimed, "privilege": c.privilege,
        "updated": time.time(),
    }

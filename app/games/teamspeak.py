"""TeamSpeak 3: ServerQuery (raw, TCP 10011)."""
import asyncio
import re
import time

ESC = [("\\\\", "\\"), ("\\/", "/"), ("\\s", " "), ("\\p", "|"), ("\\a", "\a"), ("\\b", "\b"), ("\\f", "\f"),
       ("\\n", "\n"), ("\\r", "\r"), ("\\t", "\t"), ("\\v", "\v")]


class TeamSpeakError(Exception):
    pass


def unescape(s: str) -> str:
    out, i = [], 0
    while i < len(s):
        for a, b in ESC:
            if s.startswith(a, i):
                out.append(b)
                i += len(a)
                break
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


def escape(s: str) -> str:
    s = s.replace("\\", "\\\\")
    for a, b in ESC[1:]:
        s = s.replace(b, a)
    return s


def parse(body: str) -> list[dict]:
    rows = []
    for item in body.strip().split("|"):
        d = {}
        for kv in item.split(" "):
            if not kv:
                continue
            k, _, v = kv.partition("=")
            d[k] = unescape(v)
        rows.append(d)
    return rows


class Query:
    def __init__(self, host: str, port: int, password: str, voice_port: int | None = None, timeout: float = 5.0):
        self.host, self.port, self.password, self.voice_port, self.timeout = host, port, password, voice_port, timeout

    async def _cmd(self, r, w, cmd: str) -> str:
        w.write((cmd + "\n").encode())
        await w.drain()
        lines = []
        while True:
            line = (await asyncio.wait_for(r.readline(), self.timeout)).decode("utf-8", "replace").strip("\r\n")
            if line.startswith("error "):
                e = parse(line[6:])[0]
                if e.get("id") != "0":
                    raise TeamSpeakError(f"{e.get('msg', 'Fehler')} (id {e.get('id')})")
                return "\n".join(lines)
            lines.append(line)

    async def run(self, *cmds: str) -> list[str]:
        try:
            r, w = await asyncio.wait_for(asyncio.open_connection(self.host, self.port), self.timeout)
        except (OSError, asyncio.TimeoutError) as e:
            raise TeamSpeakError(f"ServerQuery {self.host}:{self.port} nicht erreichbar") from e
        try:
            await asyncio.wait_for(r.readline(), self.timeout)       # "TS3"
            await asyncio.wait_for(r.readline(), self.timeout)       # Willkommenstext
            if self.password:
                await self._cmd(r, w, f"login serveradmin {escape(self.password)}")
            await self._cmd(r, w, f"use port={self.voice_port}" if self.voice_port else "use sid=1")
            out = [await self._cmd(r, w, c) for c in cmds]
            w.write(b"quit\n")
            return out
        except asyncio.TimeoutError as e:
            raise TeamSpeakError("ServerQuery antwortet nicht") from e
        finally:
            w.close()


async def status(q: Query) -> dict:
    info_raw, clients_raw = await q.run("serverinfo", "clientlist -times")
    info = parse(info_raw)[0]
    clients = [c for c in parse(clients_raw) if c.get("client_type") == "0"]
    up = int(info.get("virtualserver_uptime") or 0)
    name = info.get("virtualserver_name")
    return {
        "map": name or "–", "humans": len(clients), "bots": 0,
        "max_players": int(info.get("virtualserver_maxclients") or 0),
        "players": [{"name": c.get("client_nickname", "?"),
                     "time": f"{int(c.get('client_idle_time') or 0) // 60000} min inaktiv"} for c in clients],
        "version": re.sub(r"\s*\[.*", "", info.get("virtualserver_version") or ""), "hostname": name,
        "mode": {"key": "teamspeak", "label": "TeamSpeak 3"},
        "extra": {k: v for k, v in {"Kanäle": info.get("virtualserver_channelsonline"),
                                    "Uptime": f"{up // 3600} h {up % 3600 // 60} min" if up else None,
                                    "Passwort": "ja" if info.get("virtualserver_flag_password") == "1" else "nein",
                                    "Ping Ø": f"{float(info.get('virtualserver_total_ping') or 0):.0f} ms"}.items() if v},
        "updated": time.time(),
    }

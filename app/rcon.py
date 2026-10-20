"""Minimaler asynchroner Source-RCON-Client (kompatibel mit CS2)."""
import asyncio
import struct

SERVERDATA_AUTH = 3
SERVERDATA_AUTH_RESPONSE = 2
SERVERDATA_EXECCOMMAND = 2
SERVERDATA_RESPONSE_VALUE = 0

MAX_PACKET = 1024 * 64


class RconError(Exception):
    pass


class RconAuthError(RconError):
    pass


class RconClient:
    def __init__(self, host: str, port: int, password: str, timeout: float = 4.0):
        self.host = host
        self.port = port
        self.password = password
        self.timeout = timeout
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.lock = asyncio.Lock()
        self._id = 0

    def _next_id(self) -> int:
        self._id = (self._id % 2_000_000_000) + 1
        return self._id

    async def _send(self, req_id: int, ptype: int, body: str) -> None:
        payload = struct.pack("<ii", req_id, ptype) + body.encode("utf-8") + b"\x00\x00"
        self.writer.write(struct.pack("<i", len(payload)) + payload)
        await self.writer.drain()

    async def _read(self, first_timeout: float):
        # Header nur mit (evtl. kurzem) Timeout lesen – bricht sauber ab, ohne Bytes zu verlieren.
        size_b = await asyncio.wait_for(self.reader.readexactly(4), first_timeout)
        size = struct.unpack("<i", size_b)[0]
        if size < 10 or size > MAX_PACKET:
            raise RconError(f"Ungültige Paketgröße: {size}")
        data = await asyncio.wait_for(self.reader.readexactly(size), self.timeout)
        req_id, ptype = struct.unpack("<ii", data[:8])
        body = data[8:-2].decode("utf-8", "replace")
        return req_id, ptype, body

    def close(self) -> None:
        if self.writer:
            try:
                self.writer.close()
            except Exception:
                pass
        self.reader = self.writer = None

    async def _connect(self) -> None:
        self.close()
        try:
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), self.timeout
            )
        except (OSError, asyncio.TimeoutError) as e:
            raise RconError(f"Keine Verbindung zu {self.host}:{self.port} ({e.__class__.__name__})") from e

        rid = self._next_id()
        await self._send(rid, SERVERDATA_AUTH, self.password)
        try:
            while True:
                pid, ptype, _ = await self._read(self.timeout)
                if ptype == SERVERDATA_AUTH_RESPONSE:
                    if pid == -1:
                        self.close()
                        raise RconAuthError("RCON-Passwort falsch")
                    return
        except (asyncio.IncompleteReadError, asyncio.TimeoutError, OSError) as e:
            self.close()
            raise RconError("Server hat die Authentifizierung nicht beantwortet "
                            "(läuft der Server mit -usercon und ist rcon_password gesetzt?)") from e

    async def _exec(self, command: str, gap: float) -> str:
        rid = self._next_id()
        await self._send(rid, SERVERDATA_EXECCOMMAND, command)
        chunks: list[str] = []
        # Erstes Antwortpaket mit unserer ID abwarten
        while True:
            try:
                pid, ptype, body = await self._read(self.timeout)
            except asyncio.TimeoutError:
                return ""  # manche Befehle liefern keine Antwort
            if pid == rid:
                chunks.append(body)
                break
        # Weitere Pakete einsammeln, bis kurz nichts mehr kommt (mehrteilige Antworten)
        while True:
            try:
                pid, ptype, body = await self._read(gap)
            except asyncio.TimeoutError:
                break
            if pid == rid:
                chunks.append(body)
        return "".join(chunks)

    async def execute(self, command: str, gap: float = 0.2) -> str:
        async with self.lock:
            for attempt in (0, 1):
                try:
                    if self.writer is None or self.reader is None or self.reader.at_eof():
                        await self._connect()
                    return await self._exec(command, gap)
                except RconAuthError:
                    raise
                except (asyncio.IncompleteReadError, ConnectionError, OSError) as e:
                    # Verbindung war tot (z. B. Server-Restart) -> einmal neu verbinden
                    self.close()
                    if attempt:
                        raise RconError(f"Verbindung verloren: {e.__class__.__name__}") from e
            return ""


class _UdpProto(asyncio.DatagramProtocol):
    def __init__(self):
        self.queue: asyncio.Queue = asyncio.Queue()

    def datagram_received(self, data, addr):
        self.queue.put_nowait(data)

    def error_received(self, exc):
        self.queue.put_nowait(exc)


class GoldSrcRcon:
    """RCON für GoldSrc-Server (CS 1.6, DoD, TFC, HLDM, Sven Co-op): UDP mit Challenge."""

    def __init__(self, host: str, port: int, password: str, timeout: float = 4.0):
        self.host, self.port, self.password, self.timeout = host, port, password, timeout
        self.lock = asyncio.Lock()

    def close(self) -> None:
        pass

    async def execute(self, command: str, gap: float = 0.3) -> str:
        async with self.lock:
            loop = asyncio.get_running_loop()
            try:
                tr, pr = await loop.create_datagram_endpoint(_UdpProto, remote_addr=(self.host, self.port))
            except OSError as e:
                raise RconError(f"Keine Verbindung zu {self.host}:{self.port} ({e.__class__.__name__})") from e
            try:
                async def recv(t):
                    d = await asyncio.wait_for(pr.queue.get(), t)
                    if isinstance(d, Exception):
                        raise RconError(str(d))
                    return d
                tr.sendto(b"\xff\xff\xff\xffchallenge rcon\n")
                try:
                    d = await recv(self.timeout)
                except asyncio.TimeoutError as e:
                    raise RconError(f"Keine Antwort von {self.host}:{self.port} (UDP-RCON)") from e
                txt = d[4:].decode("latin-1", "replace")
                parts = txt.split()
                if len(parts) < 3 or parts[0] != "challenge":
                    raise RconError("Unerwartete Challenge-Antwort: " + txt[:60])
                ch = parts[2]
                pw = self.password.replace('"', "")
                tr.sendto(b"\xff\xff\xff\xff" + f'rcon {ch} "{pw}" {command}\n'.encode("utf-8", "replace"))
                out = []
                t = self.timeout
                while True:
                    try:
                        d = await recv(t)
                    except asyncio.TimeoutError:
                        break
                    body = d[4:]
                    if body[:1] == b"l":
                        body = body[1:]
                    out.append(body.rstrip(b"\x00").decode("utf-8", "replace"))
                    t = gap
                res = "".join(out)
                if "Bad rcon_password" in res:
                    raise RconAuthError("RCON-Passwort falsch")
                if "No password set" in res:
                    raise RconAuthError("Auf dem Server ist kein rcon_password gesetzt")
                return res
            finally:
                tr.close()

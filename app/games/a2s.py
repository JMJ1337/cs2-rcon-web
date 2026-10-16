"""Steam A2S-Abfrage (UDP) – für Valheim & Co. ohne RCON."""
import asyncio
import struct

HEADER = b"\xFF\xFF\xFF\xFF"


class A2SError(Exception):
    pass


class _Proto(asyncio.DatagramProtocol):
    def __init__(self):
        self.queue: asyncio.Queue = asyncio.Queue()

    def datagram_received(self, data, addr):
        self.queue.put_nowait(data)

    def error_received(self, exc):
        self.queue.put_nowait(exc)


async def _request(host: str, port: int, payload: bytes, timeout: float, challenge_ok=True) -> bytes:
    loop = asyncio.get_running_loop()
    transport, proto = await loop.create_datagram_endpoint(_Proto, remote_addr=(host, port))
    try:
        transport.sendto(HEADER + payload)
        for _ in range(3):
            data = await asyncio.wait_for(proto.queue.get(), timeout)
            if isinstance(data, Exception):
                raise A2SError(str(data))
            if data[:4] != HEADER:
                raise A2SError("Mehrteilige A2S-Antworten werden nicht unterstützt")
            body = data[4:]
            if body[:1] == b"A" and challenge_ok:  # Challenge -> erneut mit Challenge senden
                ch = body[1:5]
                if payload.startswith(b"T"):
                    transport.sendto(HEADER + payload + ch)
                else:
                    transport.sendto(HEADER + payload[:1] + ch)
                continue
            return body
        raise A2SError("Keine gültige Antwort")
    except asyncio.TimeoutError as e:
        raise A2SError(f"Keine Antwort von {host}:{port} (UDP)") from e
    finally:
        transport.close()


def _cstr(b: bytes, i: int):
    j = b.index(b"\x00", i)
    return b[i:j].decode("utf-8", "replace"), j + 1


async def info(host: str, port: int, timeout: float = 3.0) -> dict:
    b = await _request(host, port, b"TSource Engine Query\x00", timeout)
    if b[:1] != b"I":
        raise A2SError("Unerwartete A2S_INFO-Antwort")
    i = 2
    name, i = _cstr(b, i)
    map_, i = _cstr(b, i)
    folder, i = _cstr(b, i)
    game, i = _cstr(b, i)
    appid = struct.unpack_from("<H", b, i)[0]
    players, max_players, bots = b[i + 2], b[i + 3], b[i + 4]
    i += 5
    server_type, os_, visibility, vac = chr(b[i]), chr(b[i + 1]), b[i + 2], b[i + 3]
    i += 4
    version, i = _cstr(b, i)
    keywords = ""
    if i < len(b):
        edf = b[i]
        i += 1
        if edf & 0x80:
            i += 2
        if edf & 0x10:
            i += 8
        if edf & 0x40:
            i += 2
            _, i = _cstr(b, i)
        if edf & 0x20:
            keywords, i = _cstr(b, i)
    return {"name": name, "map": map_, "folder": folder, "game": game, "appid": appid,
            "players": players, "max_players": max_players, "bots": bots,
            "password": bool(visibility), "version": version, "keywords": keywords}


async def players(host: str, port: int, timeout: float = 3.0) -> list[dict]:
    b = await _request(host, port, b"U\xFF\xFF\xFF\xFF", timeout)
    if b[:1] != b"D":
        return []
    n, i, out = b[1], 2, []
    for _ in range(n):
        i += 1
        name, i = _cstr(b, i)
        score, dur = struct.unpack_from("<lf", b, i)
        i += 8
        out.append({"name": name, "score": score, "time": int(dur)})
    return out

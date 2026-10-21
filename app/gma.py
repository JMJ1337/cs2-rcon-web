"""Garry's-Mod-Addons (.gma, alt: LZMA-gepacktes .bin) auspacken.

Viele HL2DM-Community-Maps liegen heute nur noch im Garry's-Mod-Workshop. Ein .gma ist ein einfaches Archiv:
Kopf (Magic „GMAD“, Version, SteamID, Zeit, ggf. Liste benötigter Inhalte, Name, Beschreibung, Autor, Version),
danach die Dateiliste (Nr, Name, Größe, CRC) und anschließend die Dateiinhalte hintereinander.
"""
import lzma
import struct


class GmaError(Exception):
    pass


def _cstr(b: bytes, i: int) -> tuple[str, int]:
    j = b.index(b"\x00", i)
    return b[i:j].decode("utf-8", "replace"), j + 1


def unpack(data: bytes) -> dict[str, bytes]:
    """Liefert {pfad: inhalt}. Erkennt auch die alte LZMA-gepackte Form."""
    if data[:4] != b"GMAD":
        try:
            data = lzma.decompress(data, format=lzma.FORMAT_ALONE)
        except lzma.LZMAError as e:
            raise GmaError("Kein Garry's-Mod-Addon (.gma)") from e
        if data[:4] != b"GMAD":
            raise GmaError("Kein Garry's-Mod-Addon (.gma)")
    ver = data[4]
    i = 5 + 8 + 8                                    # Version, SteamID, Zeitstempel
    if ver > 1:
        while True:                                  # benötigte Inhalte (leer = Ende)
            s, i = _cstr(data, i)
            if not s:
                break
    _name, i = _cstr(data, i)
    _desc, i = _cstr(data, i)
    _author, i = _cstr(data, i)
    i += 4                                           # Addon-Version
    entries = []
    while True:
        (num,) = struct.unpack_from("<I", data, i)
        i += 4
        if num == 0:
            break
        name, i = _cstr(data, i)
        (size,) = struct.unpack_from("<q", data, i)
        i += 8 + 4                                   # Größe + CRC
        entries.append((name, size))
    out = {}
    for name, size in entries:
        out[name] = data[i:i + size]
        i += size
    return out

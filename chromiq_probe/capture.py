"""Reading and writing capture files (pcap and pcapng).

The readers are ported from the ChromIQ X-Rite probe 1.6.6
(`_read_pcap`, `_read_pcapng`, `_write_pcap`), with one change: a pcapng
file may hold several interfaces with different link types, so each record
carries its interface's link type.

PRIVACY RULE P1: a file this tool writes for sending is always built with
`write_pcap` from kept records only. Nothing of the source file's header,
section or interface options, comments, name resolution or statistics blocks
is ever copied; those can hold the computer's name, its operating system,
adapter names and comments.
"""

from __future__ import annotations

import os
import struct

LINKTYPE_ETHERNET = 1
LINKTYPE_RAW = 101
LINKTYPE_LINUX_SLL = 113
LINKTYPE_USB_LINUX = 189
LINKTYPE_USB_LINUX_MMAPPED = 220
LINKTYPE_IPV4 = 228
LINKTYPE_IPV6 = 229
LINKTYPE_USBPCAP = 249
LINKTYPE_USB_DARWIN = 266
LINKTYPE_LINUX_SLL2 = 276

USB_LINKTYPES = (LINKTYPE_USB_LINUX, LINKTYPE_USB_LINUX_MMAPPED, LINKTYPE_USBPCAP,
                 LINKTYPE_USB_DARWIN)
NET_LINKTYPES = (LINKTYPE_ETHERNET, LINKTYPE_RAW, LINKTYPE_LINUX_SLL, LINKTYPE_IPV4,
                 LINKTYPE_IPV6, LINKTYPE_LINUX_SLL2)

LINKTYPE_NAMES = {
    LINKTYPE_ETHERNET: "Ethernet",
    LINKTYPE_RAW: "raw IP",
    LINKTYPE_LINUX_SLL: "Linux cooked",
    LINKTYPE_LINUX_SLL2: "Linux cooked v2",
    LINKTYPE_IPV4: "raw IPv4",
    LINKTYPE_IPV6: "raw IPv6",
    LINKTYPE_USB_LINUX: "Linux usbmon",
    LINKTYPE_USB_LINUX_MMAPPED: "Linux usbmon",
    LINKTYPE_USBPCAP: "Windows USBPcap",
    LINKTYPE_USB_DARWIN: "macOS USB",
}


MAX_RECORD = 1 << 20        # larger records are skipped (a real one is at most 256 KiB)


class Capture:
    """A capture in memory: one link type, records as (time, bytes). Only for
    small files (the zip's own recordings, tests); full recordings are read
    with CaptureFile, record by record."""

    def __init__(self, linktype: int, records: list, skipped: int = 0):
        self.linktype = linktype
        self.records = records          # [(ts float seconds, bytes)]
        self.skipped = skipped

    def __len__(self):
        return len(self.records)


def _read_exact(fh, n: int) -> bytes:
    b = fh.read(n)
    return b if len(b) == n else b""


def _pcapng_records(fh, want=None, stats=None):
    """Stream a pcapng file: yields (linktype, ts, data). `want` is the link
    type to yield (others are counted in stats["skipped"])."""
    endian = "<"
    interfaces = []
    while True:
        head = _read_exact(fh, 8)
        if not head:
            return
        btype = struct.unpack(endian + "I", head[:4])[0]
        if btype == 0x0A0D0D0A:
            bom = _read_exact(fh, 4)
            if not bom:
                return
            endian = "<" if bom == b"\x4d\x3c\x2b\x1a" else ">"
            blen = struct.unpack(endian + "I", head[4:8])[0]
            interfaces = []
            if blen < 16:
                return
            fh.seek(blen - 12, 1)
            continue
        blen = struct.unpack(endian + "I", head[4:8])[0]
        if blen < 12:
            return
        body_len = blen - 12
        if btype == 6 and body_len >= 20:
            hdr = _read_exact(fh, 20)
            if not hdr:
                return
            ifid, ts_hi, ts_lo, cap, _orig = struct.unpack(endian + "IIIII", hdr)
            rest = body_len - 20
            if cap > rest or cap > MAX_RECORD or ifid >= len(interfaces):
                if stats is not None:
                    stats["skipped"] = stats.get("skipped", 0) + 1
                fh.seek(rest + 4, 1)
                continue
            data = _read_exact(fh, cap)
            fh.seek(rest - cap + 4, 1)
            lt, tsdiv = interfaces[ifid]
            if want is None or lt == want:
                yield lt, ((ts_hi << 32) | ts_lo) / tsdiv, data
            elif stats is not None:
                stats["skipped"] = stats.get("skipped", 0) + 1
            continue
        if body_len > MAX_RECORD:
            fh.seek(body_len + 4, 1)
            continue
        body = _read_exact(fh, body_len)
        if len(body) != body_len:
            return
        fh.seek(4, 1)
        if btype == 1 and len(body) >= 8:
            linktype = struct.unpack(endian + "H", body[:2])[0]
            tsdiv = 1e6
            opt = 8
            while opt + 4 <= len(body):
                code, olen = struct.unpack(endian + "HH", body[opt:opt + 4])
                if code == 0:
                    break
                if code == 9 and olen >= 1:
                    res = body[opt + 4]
                    tsdiv = float(2 ** (res & 0x7f)) if res & 0x80 else float(10 ** res)
                opt += 4 + olen + ((-olen) % 4)
            interfaces.append((linktype, tsdiv))
        elif btype == 3 and len(body) >= 4 and interfaces:
            lt = interfaces[0][0]
            if want is None or lt == want:
                yield lt, 0.0, body[4:4 + min(len(body) - 4, MAX_RECORD)]


def _pcap_header(fh):
    head = _read_exact(fh, 24)
    if len(head) < 24:
        raise ValueError("file too short to be a capture")
    magic = head[:4]
    if magic in (b"\xd4\xc3\xb2\xa1", b"\x4d\x3c\xb2\xa1"):
        endian = "<"
    elif magic in (b"\xa1\xb2\xc3\xd4", b"\xa1\xb2\x3c\x4d"):
        endian = ">"
    else:
        raise ValueError("not a pcap or pcapng file")
    nano = magic in (b"\x4d\x3c\xb2\xa1", b"\xa1\xb2\x3c\x4d")
    return endian, nano, struct.unpack(endian + "I", head[20:24])[0] & 0x0FFFFFFF


def _pcap_records(fh, endian, nano, stats=None):
    while True:
        hdr = _read_exact(fh, 16)
        if not hdr:
            return
        ts_s, ts_u, incl, _orig = struct.unpack(endian + "IIII", hdr)
        if incl > MAX_RECORD:
            if stats is not None:
                stats["skipped"] = stats.get("skipped", 0) + 1
            fh.seek(incl, 1)
            continue
        data = _read_exact(fh, incl)
        if len(data) != incl:                    # truncated final record
            return
        yield ts_s + ts_u / (1e9 if nano else 1e6), data


class CaptureFile:
    """A capture on disk, read record by record (never whole). `records()`
    can be called several times: each call reads the file again."""

    def __init__(self, path: str = None, blob: bytes = None):
        self.path, self.blob = path, blob
        self.stats = {"skipped": 0}
        with self._open() as fh:
            first = fh.read(4)
            fh.seek(0)
            self.ng = first == b"\x0a\x0d\x0d\x0a"
            if self.ng:
                self.linktype = None
                types = {}
                for lt, _ts, _d in _pcapng_records(fh):
                    types[lt] = types.get(lt, 0) + 1
                    if sum(types.values()) > 2000:
                        break
                if not types:
                    fh.seek(0)
                    ifs = self._first_interface(fh)
                    if ifs is None:
                        raise ValueError("pcapng file without an interface description")
                    types = {ifs: 1}
                self.linktype = max(types, key=types.get)
            else:
                _e, _n, self.linktype = _pcap_header(fh)

    def _open(self):
        import io                                         # noqa: PLC0415
        return io.BytesIO(self.blob) if self.blob is not None else open(self.path, "rb")

    @staticmethod
    def _first_interface(fh):
        for _ in range(64):
            head = _read_exact(fh, 8)
            if not head:
                return None
            btype, blen = struct.unpack("<II", head)
            if blen < 12:
                return None
            body = _read_exact(fh, blen - 8)
            if btype == 1 and len(body) >= 2:
                return struct.unpack("<H", body[:2])[0]
        return None

    def records(self):
        self.stats["skipped"] = 0
        with self._open() as fh:
            if self.ng:
                for _lt, ts, d in _pcapng_records(fh, self.linktype, self.stats):
                    yield ts, d
            else:
                e, n, _lt = _pcap_header(fh)
                yield from _pcap_records(fh, e, n, self.stats)


def read_capture_bytes(blob: bytes) -> Capture:
    """Parse pcap or pcapng bytes held in memory (small files only)."""
    if len(blob) >= 4 and blob[:4] == b"\x0a\x0d\x0d\x0a":
        cf = CaptureFile(blob=blob)
    else:
        if len(blob) < 24:
            raise ValueError("file too short to be a capture")
        cf = CaptureFile(blob=blob)
    recs = list(cf.records())
    return Capture(cf.linktype, recs, cf.stats["skipped"])


def read_capture(path: str) -> Capture:
    with open(path, "rb") as fh:
        return read_capture_bytes(fh.read())


def open_private(path: str):
    """A new file only this user may read (0600 on macOS and Linux)."""
    if os.path.exists(path):
        os.remove(path)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
    return os.fdopen(fd, "wb")


class PcapWriter:
    """A classic pcap written record by record from kept records only (P1)."""

    def __init__(self, path: str, linktype: int):
        self.path = path
        self.fh = open_private(path)
        self.fh.write(struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 262144, linktype))
        self.count = 0

    def write(self, ts: float, data: bytes) -> None:
        sec = int(ts)
        usec = int(round((ts - sec) * 1e6))
        if usec >= 1000000:
            sec, usec = sec + 1, usec - 1000000
        self.fh.write(struct.pack("<IIII", sec, usec, len(data), len(data)))
        self.fh.write(bytes(data))
        self.count += 1

    def close(self) -> None:
        self.fh.close()


def pcap_bytes(linktype: int, records) -> bytes:
    """A classic little-endian microsecond pcap from records only (rule P1)."""
    out = [struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 262144, linktype)]
    for ts, data in records:
        sec = int(ts)
        usec = int(round((ts - sec) * 1e6))
        if usec >= 1000000:
            sec, usec = sec + 1, usec - 1000000
        out.append(struct.pack("<IIII", sec, usec, len(data), len(data)))
        out.append(bytes(data))
    return b"".join(out)


def write_pcap(path: str, linktype: int, records) -> None:
    w = PcapWriter(path, linktype)
    for ts, d in records:
        w.write(ts, d)
    w.close()

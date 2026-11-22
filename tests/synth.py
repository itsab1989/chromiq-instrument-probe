"""Synthetic recordings for the tests. Standard library only; every byte is
made up here. The USBPcap writer is ported from the X-Rite probe 1.6.6
tests (tests/synth.py); usbmon, macOS and network writers are new and follow
the formats' public descriptions (USBPcap documentation, Linux usbmon.txt,
the libpcap link-type list, the pcapng specification).
"""

from __future__ import annotations

import ipaddress
import struct

XFER_ISO, XFER_INT, XFER_CTRL, XFER_BULK = 0, 1, 2, 3

# made-up identifiers that must never survive into a zip
SERIAL = "SN7Q4X9Z2K"
HOST_MAC = bytes.fromhex("a4b1c2d3e4f5")
DEV_MAC = bytes.fromhex("00c0ee112233")
OTHER_MAC = bytes.fromhex("3c2ef9aabbcc")
ROUTER_MAC = bytes.fromhex("e8df70010203")
HOST_IP = "192.168.178.23"
DEV_IP = "192.168.178.77"
OTHER_IP = "192.168.178.99"
WEB_IP = "142.250.185.110"


def device_descriptor(vid, pid, iserial=3, dclass=0):
    return struct.pack("<BBHBBBBHHHBBBB", 18, 1, 0x0200, dclass, 0, 0, 64, vid, pid,
                       0x0100, 1, 2, iserial, 1)


def config_descriptor(endpoints, iclass=0xFF, sub=0, proto=0):
    eps = b"".join(struct.pack("<BBBBHB", 7, 5, addr, kind, 64, 1) for addr, kind in endpoints)
    itf = struct.pack("<BBBBBBBBB", 9, 4, 0, 0, len(endpoints), iclass, sub, proto, 0)
    total = 9 + len(itf) + len(eps)
    return struct.pack("<BBHBBBBB", 9, 2, total, 1, 1, 0, 0x80, 50) + itf + eps


def string_descriptor(text):
    body = text.encode("utf-16-le")
    return bytes([2 + len(body), 3]) + body


class _UsbBase:
    linktype = 0

    def __init__(self, t0=1_800_000_000.0, bus=1):
        self.t = t0
        self.bus = bus
        self.irp = 0x1000
        self.records = []

    def tick(self, seconds=0.001):
        self.t += seconds

    def describe(self, dev, vid, pid, endpoints, iclass=0xFF, sub=0, proto=0, serial=SERIAL):
        self.control(dev, 0x80, 6, value=0x0100, length=18, reply=device_descriptor(vid, pid))
        cfg = config_descriptor(endpoints, iclass, sub, proto)
        self.control(dev, 0x80, 6, value=0x0200, length=len(cfg), reply=cfg)
        if serial:
            self.control(dev, 0x80, 6, value=0x0303, index=0x0409,
                         reply=string_descriptor(serial))

    def vendor_out(self, dev, req, out=b"", value=0, index=0):
        self.control(dev, 0x40, req, value=value, index=index, out=out)

    def vendor_in(self, dev, req, reply):
        self.control(dev, 0xC0, req, reply=reply)

    def pcap(self):
        out = [struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 262144, self.linktype)]
        for ts, data in self.records:
            sec = int(ts)
            usec = int(round((ts - sec) * 1e6))
            out.append(struct.pack("<IIII", sec, usec, len(data), len(data)))
            out.append(data)
        return b"".join(out)

    def save(self, path):
        with open(path, "wb") as fh:
            fh.write(self.pcap())
        return str(path)


class UsbPcapWriter(_UsbBase):
    """Windows USBPcap, link type 249: a 27-byte header (28 with the stage
    byte for control transfers)."""
    linktype = 249

    def _rec(self, irp, dev, ep, xfer, info, data, stage=None):
        hlen = 28 if xfer == XFER_CTRL else 27
        hdr = struct.pack("<HQIHBHHBBI", hlen, irp, 0, 0, info, self.bus, dev, ep, xfer,
                          len(data))
        if xfer == XFER_CTRL:
            hdr += bytes([stage])
        self.records.append((self.t, hdr + bytes(data)))

    def control(self, dev, rt, req, value=0, index=0, out=b"", length=None, reply=b""):
        self.irp += 1
        wlen = len(out) if not rt & 0x80 else (length if length is not None else len(reply))
        setup = struct.pack("<BBHHH", rt, req, value, index, wlen)
        ep = 0x80 if rt & 0x80 else 0x00
        self._rec(self.irp, dev, ep, XFER_CTRL, 0, setup, stage=0)
        if out:
            self._rec(self.irp, dev, ep, XFER_CTRL, 0, out, stage=1)
        self.tick(0.0005)
        if rt & 0x80:
            self._rec(self.irp, dev, ep, XFER_CTRL, 1, reply, stage=1)
        self._rec(self.irp, dev, ep, XFER_CTRL, 1, b"", stage=3)
        self.tick(0.0005)

    def bulk_in(self, dev, ep, data, xfer=XFER_BULK):
        self.irp += 1
        self._rec(self.irp, dev, ep, xfer, 0, b"")
        self.tick(0.0002)
        self._rec(self.irp, dev, ep, xfer, 1, data)
        self.tick(0.0002)

    def bulk_out(self, dev, ep, data, xfer=XFER_BULK):
        self.irp += 1
        self._rec(self.irp, dev, ep, xfer, 0, data)
        self.tick(0.0002)
        self._rec(self.irp, dev, ep, xfer, 1, b"")
        self.tick(0.0002)


class UsbmonWriter(_UsbBase):
    """Linux usbmon, link type 220 (mmapped, 64-byte header) or 189 (48)."""

    def __init__(self, mmapped=True, **kw):
        super().__init__(**kw)
        self.linktype = 220 if mmapped else 189
        self.hl = 64 if mmapped else 48

    def _rec(self, uid, typ, xfer, ep, dev, setup_flag, setup, data, length=None):
        sec = int(self.t)
        usec = int((self.t - sec) * 1e6)
        hdr = struct.pack("<QcBBBHccqiiII8s", uid, typ, xfer, ep, dev, self.bus, setup_flag,
                          b"\x00" if data else b"<", sec, usec, 0,
                          len(data) if length is None else length, len(data), setup)
        hdr += b"\0" * (self.hl - len(hdr))
        self.records.append((self.t, hdr + bytes(data)))

    def control(self, dev, rt, req, value=0, index=0, out=b"", length=None, reply=b""):
        self.irp += 1
        wlen = len(out) if not rt & 0x80 else (length if length is not None else len(reply))
        setup = struct.pack("<BBHHH", rt, req, value, index, wlen)
        ep = 0x80 if rt & 0x80 else 0x00
        self._rec(self.irp, b"S", XFER_CTRL, ep, dev, b"\x00", setup, out)
        self.tick(0.0005)
        self._rec(self.irp, b"C", XFER_CTRL, ep, dev, b"-", b"\0" * 8, reply)
        self.tick(0.0005)

    def bulk_in(self, dev, ep, data, xfer=XFER_BULK):
        self.irp += 1
        self._rec(self.irp, b"S", xfer, ep, dev, b"-", b"\0" * 8, b"", length=len(data))
        self.tick(0.0002)
        self._rec(self.irp, b"C", xfer, ep, dev, b"-", b"\0" * 8, data)
        self.tick(0.0002)

    def bulk_out(self, dev, ep, data, xfer=XFER_BULK):
        self.irp += 1
        self._rec(self.irp, b"S", xfer, ep, dev, b"-", b"\0" * 8, data)
        self.tick(0.0002)
        self._rec(self.irp, b"C", xfer, ep, dev, b"-", b"\0" * 8, b"")
        self.tick(0.0002)


class DarwinWriter(_UsbBase):
    """macOS, link type 266: a 40-byte header with the vendor and product
    numbers in every record; OUT data in the completion (as measured by the
    X-Rite probe on real recordings)."""
    linktype = 266

    def __init__(self, devices, **kw):
        super().__init__(**kw)
        self.devices = devices          # dev address -> (vid, pid, location)

    def _rec(self, seq, direction, dev, ep, etype, data):
        vid, pid, loc = self.devices[dev]
        hdr = struct.pack("<HBBIIIQIBBBB", 0x0100, 40, direction, len(data), 0, 0, seq, loc,
                          3, dev, ep, etype)
        hdr += b"\0" * 4 + struct.pack("<HH", vid, pid)
        self.records.append((self.t, hdr + bytes(data)))

    def control(self, dev, rt, req, value=0, index=0, out=b"", length=None, reply=b""):
        self.irp += 1
        wlen = len(out) if not rt & 0x80 else (length if length is not None else len(reply))
        setup = struct.pack("<BBHHH", rt, req, value, index, wlen)
        self._rec(self.irp, 0, dev, 0x80 if rt & 0x80 else 0, 0, setup)
        self.tick(0.0005)
        self._rec(self.irp, 1, dev, 0x80 if rt & 0x80 else 0, 0, reply if rt & 0x80 else out)
        self.tick(0.0005)

    def bulk_in(self, dev, ep, data, xfer=XFER_BULK):
        self.irp += 1
        et = 2 if xfer == XFER_BULK else 3
        self._rec(self.irp, 0, dev, ep, et, b"")
        self.tick(0.0002)
        self._rec(self.irp, 1, dev, ep, et, data)
        self.tick(0.0002)

    def bulk_out(self, dev, ep, data, xfer=XFER_BULK):
        self.irp += 1
        et = 2 if xfer == XFER_BULK else 3
        self._rec(self.irp, 0, dev, ep, et, b"")
        self.tick(0.0002)
        self._rec(self.irp, 1, dev, ep, et, data)
        self.tick(0.0002)


# ---- network ------------------------------------------------------------

def _csum(b):
    if len(b) % 2:
        b += b"\0"
    s = sum(struct.unpack(f">{len(b) // 2}H", b))
    while s >> 16:
        s = (s & 0xFFFF) + (s >> 16)
    return (~s) & 0xFFFF


def ipv4(src, dst, proto, payload, ttl=64):
    s, d = ipaddress.ip_address(src).packed, ipaddress.ip_address(dst).packed
    hdr = struct.pack(">BBHHHBBH4s4s", 0x45, 0, 20 + len(payload), 1, 0, ttl, proto, 0, s, d)
    hdr = hdr[:10] + struct.pack(">H", _csum(hdr)) + hdr[12:]
    return hdr + payload


def tcp(src, dst, sp, dp, data, seq=1, flags=0x18):
    seg = struct.pack(">HHIIBBHHH", sp, dp, seq, 1, 5 << 4, flags, 65535, 0, 0) + data
    s, d = ipaddress.ip_address(src).packed, ipaddress.ip_address(dst).packed
    c = _csum(s + d + struct.pack(">BBH", 0, 6, len(seg)) + seg)
    seg = seg[:16] + struct.pack(">H", c) + seg[18:]
    return ipv4(src, dst, 6, seg)


def udp(src, dst, sp, dp, data):
    seg = struct.pack(">HHHH", sp, dp, 8 + len(data), 0) + data
    s, d = ipaddress.ip_address(src).packed, ipaddress.ip_address(dst).packed
    c = _csum(s + d + struct.pack(">BBH", 0, 17, len(seg)) + seg) or 0xFFFF
    seg = seg[:6] + struct.pack(">H", c) + seg[8:]
    return ipv4(src, dst, 17, seg)


def eth(dst_mac, src_mac, ethertype, payload):
    return dst_mac + src_mac + struct.pack(">H", ethertype) + payload


def arp(op, smac, sip, tmac, tip):
    return struct.pack(">HHBBH6s4s6s4s", 1, 0x0800, 6, 4, op, smac,
                       ipaddress.ip_address(sip).packed, tmac, ipaddress.ip_address(tip).packed)


def dhcp_discover(mac, hostname=b"SPECTRO-SN7Q4X9Z2K"):
    bootp = struct.pack(">BBBBIHH4s4s4s4s16s64s128s", 1, 1, 6, 0, 0x1234, 0, 0x8000,
                        b"\0" * 4, b"\0" * 4, b"\0" * 4, b"\0" * 4, mac + b"\0" * 10,
                        b"\0" * 64, b"\0" * 128)
    opts = b"\x63\x82\x53\x63" + bytes([53, 1, 1, 12, len(hostname)]) + hostname + b"\xff"
    return udp("0.0.0.0", "255.255.255.255", 68, 67, bootp + opts)


class NetWriter:
    def __init__(self, t0=1_800_000_000.0):
        self.t = t0
        self.records = []

    def add(self, frame, dt=0.001):
        self.records.append((self.t, frame))
        self.t += dt

    def pcap(self, linktype=1):
        out = [struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 262144, linktype)]
        for ts, data in self.records:
            sec = int(ts)
            usec = int(round((ts - sec) * 1e6))
            out.append(struct.pack("<IIII", sec, usec, len(data), len(data)))
            out.append(data)
        return b"".join(out)

    def pcapng(self, linktype=1, leak=b"\\Device\\NPF_{SECRET-ADAPTER} on MY-PC"):
        """pcapng with section and interface options and a comment that hold
        identifying text: none of it may reach a kept copy."""
        def opt(code, val):
            pad = (-len(val)) % 4
            return struct.pack("<HH", code, len(val)) + val + b"\0" * pad

        def block(btype, body):
            body += b"\0" * ((-len(body)) % 4)
            ln = 12 + len(body)
            return struct.pack("<II", btype, ln) + body + struct.pack("<I", ln)

        shb = struct.pack("<IHHq", 0x1A2B3C4D, 1, 0, -1) + opt(2, b"hw " + leak) + \
            opt(3, b"os " + leak) + opt(4, b"app " + leak) + opt(0, b"")
        idb = struct.pack("<HHI", linktype, 0, 0) + opt(2, leak) + opt(3, leak) + \
            opt(9, b"\x06") + opt(0, b"")
        out = [block(0x0A0D0D0A, shb), block(1, idb)]
        for ts, data in self.records:
            t = int(ts * 1e6)
            body = struct.pack("<IIIII", 0, t >> 32, t & 0xFFFFFFFF, len(data), len(data))
            body += data + b"\0" * ((-len(data)) % 4) + opt(1, b"comment " + leak) + opt(0, b"")
            out.append(block(6, body))
        return b"".join(out)


def tls_record(ctype, body):
    return bytes([ctype, 3, 3]) + struct.pack(">H", len(body)) + body

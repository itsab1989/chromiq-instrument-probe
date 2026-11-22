"""Network recordings (Ethernet and Wi-Fi as the computer sees it).

The instrument is the IP address (or addresses) the owner chose, and, when it
sits on the same network as the computer, its MAC address. Two passes over a
recording, record by record:

  pass 1 (NetPlan): which MAC sends from which IP addresses, which MAC carries
    traffic for other addresses (a router does), whether the chosen address
    is the computer's default gateway, and whether the instrument showed up
    at a new address (its own ARP or its own DHCP);
  pass 2 (NetPlan.decide): every record kept or dropped.

Rules:
  * A ROUTER IS NEVER THE INSTRUMENT. When the chosen address is the default
    gateway, or its MAC carries other addresses' traffic, or sends from more
    than one address, NOTHING is kept and the check says why.
  * Matching is by IP address. A MAC alone never admits traffic: ARP is kept
    only when it names the instrument's IP; frames without IP only when the
    instrument's MAC is its own (one address); DHCP only for the
    instrument's own hardware address.
  * A NEW ADDRESS IS NEVER ADOPTED HERE. It is reported, and the tool asks the
    owner after the block; only when he says yes is it used (and then for the
    whole session). A MAC seen with two addresses in use at the same time is
    not proposed at all (a Wi-Fi extender or proxy shares one MAC).
  * Look-ups and name announcements (DNS, mDNS, LLMNR, NetBIOS, SSDP,
    WS-Discovery) of any other host are dropped; the instrument's own have
    their names masked. DNS (port 53) is never kept.
  * Encrypted connections are recognised only from a real TLS / DTLS
    handshake (or an SSH banner) at the START of a connection; their record
    bodies become zeros of the same length; the headers, sizes and times stay.
"""

from __future__ import annotations

import ipaddress
import struct

from .capture import (LINKTYPE_ETHERNET, LINKTYPE_IPV4, LINKTYPE_IPV6, LINKTYPE_LINUX_SLL,
                      LINKTYPE_LINUX_SLL2, LINKTYPE_RAW)

ETH_IPV4, ETH_ARP, ETH_IPV6, ETH_VLAN = 0x0800, 0x0806, 0x86DD, 0x8100
IPV6_DROPPED = "the instrument's IPv6 traffic (this version keeps IPv4 only)"
NAME_PORTS = {5353: "mDNS", 5355: "LLMNR", 137: "NetBIOS", 138: "NetBIOS", 1900: "SSDP",
              3702: "WS-Discovery"}


def parse_mac(text: str) -> bytes:
    parts = text.replace("-", ":").split(":")
    if len(parts) != 6:
        raise ValueError(f"not a MAC address: {text}")
    return bytes(int(p, 16) for p in parts)


def mac_text(mac: bytes) -> str:
    return ":".join(f"{b:02x}" for b in mac)


class Frame:
    """Offsets into one frame: l2 (MACs, may be None), ethertype, l3 offset."""

    __slots__ = ("src_mac", "dst_mac", "ethertype", "l3", "mac_offsets")

    def __init__(self):
        self.src_mac = self.dst_mac = None
        self.ethertype = None
        self.l3 = 0
        self.mac_offsets = []       # [(offset)] of 6-byte MAC fields in the frame header


def parse_frame(linktype: int, d: bytes):
    f = Frame()
    if linktype == LINKTYPE_ETHERNET:
        if len(d) < 14:
            return None
        f.dst_mac, f.src_mac = d[0:6], d[6:12]
        f.mac_offsets = [0, 6]
        et = struct.unpack_from(">H", d, 12)[0]
        off = 14
        while et == ETH_VLAN and len(d) >= off + 4:
            et = struct.unpack_from(">H", d, off + 2)[0]
            off += 4
        f.ethertype, f.l3 = et, off
        return f
    if linktype == LINKTYPE_LINUX_SLL:
        if len(d) < 16:
            return None
        alen = struct.unpack_from(">H", d, 4)[0]
        if alen == 6:
            f.src_mac = d[6:12]
            f.mac_offsets = [6]
        f.ethertype, f.l3 = struct.unpack_from(">H", d, 14)[0], 16
        return f
    if linktype == LINKTYPE_LINUX_SLL2:
        if len(d) < 20:
            return None
        if d[11] == 6:
            f.src_mac = d[12:18]
            f.mac_offsets = [12]
        f.ethertype, f.l3 = struct.unpack_from(">H", d, 0)[0], 20
        return f
    if linktype in (LINKTYPE_RAW, LINKTYPE_IPV4, LINKTYPE_IPV6):
        if not d:
            return None
        f.ethertype = ETH_IPV6 if (d[0] >> 4) == 6 else ETH_IPV4
        f.l3 = 0
        return f
    return None


def parse_ip(d: bytes, off: int):
    """(version, src, dst, proto, l4 offset, ip header length) or None."""
    if len(d) < off + 20:
        return None
    v = d[off] >> 4
    if v == 4:
        ihl = (d[off] & 0x0F) * 4
        if ihl < 20 or len(d) < off + ihl:
            return None
        src = ipaddress.ip_address(d[off + 12:off + 16])
        dst = ipaddress.ip_address(d[off + 16:off + 20])
        return 4, src, dst, d[off + 9], off + ihl, ihl
    if v == 6 and len(d) >= off + 40:
        src = ipaddress.ip_address(d[off + 8:off + 24])
        dst = ipaddress.ip_address(d[off + 24:off + 40])
        return 6, src, dst, d[off + 6], off + 40, 40
    return None


def parse_arp(d: bytes, off: int):
    """(sender mac, sender ip, target mac, target ip) for Ethernet/IPv4 ARP."""
    if len(d) < off + 28:
        return None
    htype, ptype, hlen, plen = struct.unpack_from(">HHBB", d, off)
    if htype != 1 or ptype != 0x0800 or hlen != 6 or plen != 4:
        return None
    return (d[off + 8:off + 14], ipaddress.ip_address(d[off + 14:off + 18]),
            d[off + 18:off + 24], ipaddress.ip_address(d[off + 24:off + 28]))


def _is_dhcp(ip, d: bytes) -> bool:
    if not ip or ip[3] != 17 or len(d) < ip[4] + 8:
        return False
    sp, dp = struct.unpack_from(">HH", d, ip[4])
    return {sp, dp} <= {67, 68}


class Device:
    def __init__(self, ips=(), macs=(), ports=()):
        self.ips = {ipaddress.ip_address(i) for i in ips}
        self.macs = {parse_mac(m) if isinstance(m, str) else bytes(m) for m in macs}
        self.ports = set(int(p) for p in ports)

    @classmethod
    def from_selection(cls, sel: dict):
        return cls(sel.get("ips", ()), sel.get("macs", ()), sel.get("ports", ()))


def _special(ip) -> bool:
    return ip.is_multicast or ip.is_unspecified or str(ip) == "255.255.255.255" or \
        (ip.version == 4 and ip.packed[3] == 255)


def _dhcp_fields(d: bytes, ip):
    """(op, chaddr, yiaddr) of a DHCP message, or None."""
    l4 = ip[4]
    if len(d) < l4 + 8 + 34:
        return None
    b = l4 + 8
    return d[b], d[b + 28:b + 34], ipaddress.ip_address(d[b + 16:b + 20])


def _ports(d, ip):
    if ip[3] in (6, 17) and len(d) >= ip[4] + 4 and not _is_fragment(d, ip):
        return struct.unpack_from(">HH", d, ip[4])
    return None


def _is_fragment(d, ip) -> bool:
    if ip[0] != 4:
        return False
    l3 = ip[4] - ip[5]
    flags_off = struct.unpack_from(">H", d, l3 + 6)[0]
    return bool(flags_off & 0x2000) or bool(flags_off & 0x1FFF)


class NetPlan:
    def __init__(self, linktype: int, records, selection: dict):
        self.linktype = linktype
        self.dev = Device.from_selection(selection)
        self.ips = set(self.dev.ips)
        self.gateways = {ipaddress.ip_address(g) for g in selection.get("gateways", [])}
        self.gateway_known = "gateways" not in selection or bool(selection.get("gateways")) \
            or bool(selection.get("no_router"))
        self.gateway_macs = {parse_mac(m) for m in selection.get("gateway_macs", [])}
        self.dev_ports: set = set()      # ports the instrument's own address used
        self.talks: dict = {}            # candidate ip -> {"n": packets, "ports": set}
        self.dedupe = bool(selection.get("dedupe"))
        self.mac_srcs: dict = {}         # mac -> {ip: (first ri, last ri)}
        self.mac_hops: dict = {}         # mac -> other destination addresses sent to it
        self.ip_macs: dict = {}          # chosen ip -> macs it was sent from
        self.candidates: dict = {}       # ip -> (first ri, evidence)
        self.unproven: list = []
        self.refused = ""
        self._scan(records)
        self._decide_refusal()

    def _scan(self, records):
        for ri, (_ts, d) in enumerate(records):
            f = parse_frame(self.linktype, d)
            if f is None:
                continue
            if f.ethertype == ETH_ARP:
                arp = parse_arp(d, f.l3)
                if arp and not arp[1].is_unspecified:
                    self._src(arp[0], arp[1], ri)
                    if self.dev.macs and arp[0] in self.dev.macs and arp[1] not in self.ips:
                        self.candidates.setdefault(arp[1], (ri, "its own ARP"))
                continue
            if f.ethertype not in (ETH_IPV4, ETH_IPV6):
                continue
            ip = parse_ip(d, f.l3)
            if ip is None:
                continue
            # review 2, S-M2: the router facts come from IPv4 only (a normal
            # instrument also has link-local and global IPv6 addresses)
            if ip[0] == 4 and f.src_mac is not None and not ip[1].is_unspecified:
                self._src(f.src_mac, ip[1], ri)
                if ip[1] in self.ips:
                    self.ip_macs.setdefault(ip[1], set()).add(f.src_mac)
            if ip[0] == 4 and f.dst_mac is not None and not _special(ip[2]):
                self.mac_hops.setdefault(f.dst_mac, set()).add(ip[2])
                if ip[2] in self.ips:
                    self.ip_macs.setdefault(ip[2], set()).add(f.dst_mac)
            ports = _ports(d, ip)
            if ip[0] == 4 and ports:
                if ip[1] in self.ips:
                    self.dev_ports.add(ports[0])
                elif ip[2] in self.ips:
                    self.dev_ports.add(ports[1])
                for a, port in ((ip[1], ports[0]), (ip[2], ports[1])):
                    if a in self.candidates:
                        t = self.talks.setdefault(a, {"n": 0, "ports": set()})
                        t["n"] += 1
                        t["ports"].add(port)
            if _is_dhcp(ip, d) and self.dev.macs:
                fl = _dhcp_fields(d, ip)
                if fl and fl[0] == 2 and fl[1] in self.dev.macs and not fl[2].is_unspecified \
                        and fl[2] not in self.ips:
                    self.candidates.setdefault(fl[2], (ri, "the address the network gave it"))

    def _src(self, mac, ip, ri):
        m = self.mac_srcs.setdefault(bytes(mac), {})
        first, _last = m.get(ip, (ri, ri))
        m[ip] = (first, ri)

    def is_router(self, mac) -> bool:
        own = set(self.mac_srcs.get(mac, {}))
        others = self.mac_hops.get(mac, set()) - own - self.ips
        return len(own) > 1 or bool(others)

    def _decide_refusal(self):
        if self.ips & self.gateways:
            self.refused = ("the address you chose is this computer's router (its default "
                            "gateway), not an instrument")
            return
        if not self.gateway_known:
            self.refused = ("the tool could not find this computer's router (for example "
                            "while a VPN is connected), so it cannot make sure it is not "
                            "recording it")
            return
        for ip in self.dev.ips:
            if self.ip_macs.get(ip, set()) & self.gateway_macs:
                self.refused = ("your instrument is reached through your router, on another "
                                "network; this version records only instruments on the same "
                                "network as this computer")
                return
        macs = set(self.dev.macs)
        for ip in self.dev.ips:
            macs |= self.ip_macs.get(ip, set())
        for m in macs:
            srcs = self.mac_srcs.get(m, {})
            others = self.mac_hops.get(m, set()) - set(srcs) - self.ips
            live = [ip for ip in srcs if not ip.is_unspecified]
            if others or len(live) > 2:
                self.refused = ("the chosen device passes on traffic for other addresses, as a "
                                "router does: it is not an instrument")
                return
        self.shared = {m for m in macs if self._simultaneous(m)}

    @staticmethod
    def _sequential(srcs) -> bool:
        spans = sorted(srcs.values())
        return all(a[1] < b[0] for a, b in zip(spans, spans[1:]))

    def _simultaneous(self, mac) -> bool:
        spans = list(self.mac_srcs.get(mac, {}).values())
        for i, a in enumerate(spans):
            for b in spans[i + 1:]:
                if a[0] <= b[1] and b[0] <= a[1]:
                    return True
        return False

    def new_addresses(self) -> list:
        """Addresses the instrument may have moved to, for the owner to confirm."""
        if self.refused:
            return []
        out = []
        for ip, (ri, evidence) in sorted(self.candidates.items(), key=lambda x: x[1][0]):
            mac = next(iter(self.dev.macs), None)
            spans = self.mac_srcs.get(mac, {})
            old_active_after = any(span[1] > ri for a, span in spans.items() if a in self.dev.ips)
            if mac in getattr(self, "shared", set()) or old_active_after:
                continue
            # review 2, S-m1: only an address the computer then really talks to, on a
            # port the instrument used before; the evidence is shown to the owner
            t = self.talks.get(ip)
            if not t or not (t["ports"] & self.dev_ports):
                self.unproven.append(str(ip))
                continue
            ports = ", ".join(str(p) for p in sorted(t["ports"] & self.dev_ports))
            out.append({"ip": str(ip), "evidence": evidence,
                        "talk": f"after that, this computer exchanged {t['n']} "
                                f"packet{'s' if t['n'] != 1 else ''} with it "
                                f"on port {ports}, the port your instrument used before"})
        return out[:1]

    def decider(self):
        macs = set() if self.refused else {m for m in self.dev.macs
                                           if m not in getattr(self, "shared", set())}
        ips = set(self.ips)
        last = {}
        dev = self.dev

        def decide(ri, ts, d):
            if self.refused:
                return False, "everything (the chosen address is a router)"
            f = parse_frame(self.linktype, d)
            if f is None:
                return False, "not a network frame"
            if f.ethertype == ETH_ARP:
                arp = parse_arp(d, f.l3)
                if arp and (arp[1] in ips or arp[3] in ips):
                    return True, None
                return False, "another computer's address question (ARP)"
            if f.ethertype not in (ETH_IPV4, ETH_IPV6):
                if macs and f.src_mac in macs:
                    return True, None
                return False, "other network traffic"
            ip = parse_ip(d, f.l3)
            if ip is None:
                return False, "not a network frame"
            if ip[0] == 6 and (f.src_mac in dev.macs or f.dst_mac in dev.macs):
                return False, IPV6_DROPPED
            ports = _ports(d, ip)
            if _is_dhcp(ip, d):
                fl = _dhcp_fields(d, ip)
                if macs and fl and fl[1] in macs:
                    return True, None
                return False, "other computers' address requests (DHCP)"
            if ip[1] not in ips and ip[2] not in ips:
                if ports and (ports[0] in NAME_PORTS or ports[1] in NAME_PORTS):
                    return False, "other computers' name look-ups and announcements"
                return False, "traffic of other computers or the internet"
            if ports and 53 in ports:
                return False, "name look-ups (DNS)"
            if ports and (ports[0] in NAME_PORTS or ports[1] in NAME_PORTS) and ip[1] not in ips:
                return False, "other computers' name look-ups and announcements"
            if dev.ports and ports and ports[0] not in dev.ports and ports[1] not in dev.ports:
                return False, "the instrument's traffic on a port you did not choose"
            if self.dedupe:
                prev = last.get(d)
                last[d] = ts
                if prev is not None and abs(ts - prev) < 0.002:
                    return False, "the same frame logged twice by pktmon"
            return True, None
        return decide


def filter_net_stream(linktype: int, open_records, selection: dict, sink=None) -> dict:
    plan = NetPlan(linktype, open_records(), selection)
    decide = plan.decider()
    keep, dropped = [], {}
    for ri, (ts, d) in enumerate(open_records()):
        k, reason = decide(ri, ts, d)
        if k:
            keep.append(ri)
            if sink is not None:
                sink(ts, d, 0)
        else:
            dropped[reason] = dropped.get(reason, 0) + 1
    return {"keep": keep, "dropped": dropped, "others": {}, "refused": plan.refused,
            "router": bool(plan.refused), "new_addresses": plan.new_addresses(),
            "learned_ips": [], "shared_mac": bool(getattr(plan, "shared", set())),
            "unproven_addresses": plan.unproven,
            "ips": sorted(str(i) for i in plan.ips)}


def filter_net(linktype: int, recs, selection: dict) -> dict:
    return filter_net_stream(linktype, lambda: iter(recs), selection)


# ---- encrypted connections ---------------------------------------------------

def _tls_handshake_start(b: bytes) -> bool:
    """A TLS record carrying a ClientHello or ServerHello, with sane lengths."""
    if len(b) < 9 or b[0] != 22 or b[1] != 3 or b[2] > 4:
        return False
    rlen = struct.unpack_from(">H", b, 3)[0]
    # a handshake message may span several records, so its own length is not
    # compared with the record's
    return 4 <= rlen <= 18432 and b[5] in (1, 2)


def _dtls_handshake_start(b: bytes) -> bool:
    if len(b) < 25 or b[0] != 22 or b[1] != 0xFE or b[2] not in (0xFF, 0xFD):
        return False
    rlen = struct.unpack_from(">H", b, 11)[0]
    return 12 <= rlen <= 18432 and b[13] in (1, 2, 3)


class _Stream:
    __slots__ = ("kind", "remaining", "desync", "banner_done", "zeroed")

    def __init__(self, kind):
        self.kind = kind
        self.remaining = 0
        self.desync = False
        self.banner_done = False
        self.zeroed = 0


def _mask_tls(st: _Stream, p: bytearray) -> int:
    """Zero the record bodies, keep the 5-byte record headers. After a loss of
    step (a retransmission, a capture gap) EVERYTHING that follows in that
    direction is zeroed (review 2, S-m3: a TLS 1.2 certificate after a
    retransmission would otherwise stay readable)."""
    i, zeroed = 0, 0
    if st.desync:
        n = len(p)
        p[:] = bytes(n)
        return n
    while i < len(p) and not st.desync:
        if st.remaining:
            n = min(st.remaining, len(p) - i)
            p[i:i + n] = bytes(n)
            zeroed += n
            i += n
            st.remaining -= n
            continue
        b = bytes(p[i:i + 5])
        if len(b) < 5 or b[0] not in (20, 21, 22, 23) or b[1] != 3 or b[2] > 4:
            st.desync = True
            zeroed += len(p) - i
            p[i:] = bytes(len(p) - i)
            break
        st.remaining = struct.unpack_from(">H", b, 3)[0]
        i += 5
    return zeroed


def _mask_dtls(p: bytearray) -> int:
    i, zeroed = 0, 0
    while i + 13 <= len(p):
        if p[i] not in (20, 21, 22, 23, 25) or p[i + 1] != 0xFE:
            break
        n = struct.unpack_from(">H", p, i + 11)[0]
        end = min(len(p), i + 13 + n)
        zeroed += end - (i + 13)
        p[i + 13:end] = bytes(end - (i + 13))
        i = end
    return zeroed


def _mask_ssh(st: _Stream, p: bytearray) -> int:
    if not st.banner_done:
        nl = p.find(b"\n")
        if nl < 0:
            return 0
        st.banner_done = True
        rest = len(p) - nl - 1
        p[nl + 1:] = bytes(rest)
        return rest
    p[:] = bytes(len(p))
    return len(p)


_SSDP_KEEP = {b"nt", b"nts", b"st", b"man", b"mx", b"cache-control", b"host", b"ext",
              b"bootid.upnp.org", b"configid.upnp.org", b"searchport.upnp.org"}
_WSD_NAMES = (b"FriendlyName", b"ComputerName", b"SerialNumber", b"ModelName", b"Manufacturer",
              b"PresentationUrl", b"Location")


def mask_announcement(p: bytearray) -> int:
    """SSDP: every header value except NT, NTS, ST, MAN, MX, CACHE-CONTROL, HOST
    (and the UPnP counters) becomes 'x' of the same length (SERVER, USN,
    LOCATION and X-FRIENDLY can carry a name the owner chose or a serial).
    WS-Discovery: the content of FriendlyName, ComputerName, SerialNumber,
    ModelName, Manufacturer, PresentationUrl and Location elements."""
    n = 0
    data = bytes(p)
    if data[:6] in (b"NOTIFY", b"M-SEAR", b"HTTP/1"):
        pos = data.find(b"\r\n") + 2
        while 0 < pos < len(data):
            end = data.find(b"\r\n", pos)
            if end < 0:
                end = len(data)
            line = data[pos:end]
            colon = line.find(b":")
            if colon > 0 and line[:colon].strip().lower() not in _SSDP_KEEP:
                v0 = pos + colon + 1
                p[v0:end] = b"x" * (end - v0)
                n += 1
            pos = end + 2
        return n
    import re as _re                                      # noqa: PLC0415
    for name in _WSD_NAMES:
        for mt in _re.finditer(rb"<([A-Za-z0-9_]+:)?" + name + rb"[^>]*>([^<]*)<", data):
            a, b = mt.span(2)
            p[a:b] = b"x" * (b - a)
            n += 1
    return n


def mask_dns_names(p: bytearray) -> int:
    """mDNS / LLMNR: every name label (a length byte and that many printable
    bytes) is replaced by 'x' of the same length, except service labels
    starting with '_' and the words 'local', 'arpa', 'in-addr', 'ip6', 'tcp',
    'udp'. Returns how many labels were masked."""
    keep = {b"local", b"arpa", b"in-addr", b"ip6"}
    n, i = 0, 12
    while i < len(p):
        ln = p[i]
        if 1 <= ln <= 63 and i + 1 + ln <= len(p):
            lab = bytes(p[i + 1:i + 1 + ln])
            if all(32 < c < 127 for c in lab):
                if not lab.startswith(b"_") and lab.lower() not in keep:
                    p[i + 1:i + 1 + ln] = b"x" * ln
                    n += 1
                i += 1 + ln
                continue
        i += 1
    return n


def _csum(data: bytes) -> int:
    if len(data) % 2:
        data += b"\0"
    s = sum(struct.unpack(f">{len(data) // 2}H", data))
    while s >> 16:
        s = (s & 0xFFFF) + (s >> 16)
    return (~s) & 0xFFFF


def _fix_checksums(d: bytearray, ip) -> None:
    v, _src, _dst, proto, l4, ihl = ip
    l3 = l4 - ihl
    if v == 4:
        d[l3 + 10:l3 + 12] = b"\0\0"
        d[l3 + 10:l3 + 12] = struct.pack(">H", _csum(bytes(d[l3:l3 + ihl])))
        total = struct.unpack_from(">H", d, l3 + 2)[0]
        seg_end = min(len(d), l3 + total)
        pseudo = bytes(d[l3 + 12:l3 + 20])
    else:
        plen = struct.unpack_from(">H", d, l3 + 4)[0]
        seg_end = min(len(d), l4 + plen)
        pseudo = bytes(d[l3 + 8:l3 + 40])
    seg_len = seg_end - l4
    if proto == 6 and seg_len >= 20:
        coff = l4 + 16
    elif proto == 17 and seg_len >= 8:
        coff = l4 + 6
        if v == 4 and d[coff:coff + 2] == b"\0\0":
            return                       # UDP over IPv4 without a checksum
    else:
        return
    d[coff:coff + 2] = b"\0\0"
    if v == 4:
        pseudo += struct.pack(">BBH", 0, proto, seg_len)
    else:
        pseudo += struct.pack(">I3xB", seg_len, proto)
    c = _csum(pseudo + bytes(d[l4:seg_end]))
    if proto == 17 and c == 0:
        c = 0xFFFF
    d[coff:coff + 2] = struct.pack(">H", c)


def _payload_range(d, ip):
    v, _s, _t, proto, l4, ihl = ip
    l3 = l4 - ihl
    end = len(d)
    if v == 4 and len(d) >= l3 + 4:
        end = min(end, l3 + struct.unpack_from(">H", d, l3 + 2)[0])
    elif v == 6 and len(d) >= l3 + 6:
        end = min(end, l4 + struct.unpack_from(">H", d, l3 + 4)[0])
    if proto == 6 and len(d) >= l4 + 13:
        return l4 + (d[l4 + 12] >> 4) * 4, end
    if proto == 17:
        return l4 + 8, end
    return l4, end


def _mask_dhcp_names(d: bytearray, start: int, end: int, mapper) -> None:
    """DHCP options 12 (host name), 15 (domain), 61 (client id), 81 (FQDN):
    the values replaced by the same number of 'x' bytes."""
    i = start + 240                          # fixed BOOTP part + magic cookie
    while i + 2 <= end:
        code = d[i]
        if code == 255:
            break
        if code == 0:
            i += 1
            continue
        ln = d[i + 1]
        if code in (12, 15, 61, 81) and i + 2 + ln <= end:
            d[i + 2:i + 2 + ln] = b"x" * ln
            mapper.count("DHCP name or id")
        i += 2 + ln


class NetRewriter:
    """The privacy pass on kept frames, one at a time, in order. Call
    register() for every kept frame of the whole session first (so every
    address has its placeholder), then rewrite()."""

    def __init__(self, linktype: int, mapper, selection: dict):
        self.linktype, self.mapper = linktype, mapper
        dev = Device.from_selection(selection)
        mapper.device_macs |= dev.macs
        mapper.device_ips |= dev.ips
        self.streams = {}
        self.encrypted = {}
        self.rules = None

    def register(self, d: bytes) -> None:
        m = self.mapper
        f = parse_frame(self.linktype, d)
        if f is None:
            return
        for off in f.mac_offsets:
            m.mac(d[off:off + 6])
        if f.ethertype == ETH_ARP:
            arp = parse_arp(d, f.l3)
            if arp:
                m.mac(arp[0]), m.mac(arp[2]), m.ip(arp[1]), m.ip(arp[3])
        elif f.ethertype in (ETH_IPV4, ETH_IPV6):
            ip = parse_ip(d, f.l3)
            if ip:
                m.ip(ip[1]), m.ip(ip[2])

    def rewrite(self, raw: bytes) -> bytes:
        m = self.mapper
        if self.rules is None:
            self.rules = m.byte_rules(binary_ips=True)
        rules = self.rules
        d = bytearray(raw)
        f = parse_frame(self.linktype, raw)
        if f is None:
            return m.scrub_bytes(raw, rules)
        for off in f.mac_offsets:
            d[off:off + 6] = m.mac(raw[off:off + 6])
        if f.ethertype == ETH_ARP:
            a = f.l3
            arp = parse_arp(raw, a)
            if arp:
                d[a + 8:a + 14] = m.mac(arp[0])
                d[a + 14:a + 18] = m.ip(arp[1]).packed
                d[a + 18:a + 24] = m.mac(arp[2])
                d[a + 24:a + 28] = m.ip(arp[3]).packed
            return bytes(d)
        ip = parse_ip(raw, f.l3) if f.ethertype in (ETH_IPV4, ETH_IPV6) else None
        if ip is None:
            return bytes(d[:f.l3]) + m.scrub_bytes(bytes(d[f.l3:]), rules)
        v, src, dst, proto, l4, ihl = ip
        l3 = l4 - ihl
        if v == 4:
            d[l3 + 12:l3 + 16] = m.ip(src).packed
            d[l3 + 16:l3 + 20] = m.ip(dst).packed
        else:
            d[l3 + 8:l3 + 24] = m.ip(src).packed
            d[l3 + 24:l3 + 40] = m.ip(dst).packed
        if _is_fragment(raw, ip):
            d[l4:] = m.scrub_bytes(bytes(d[l4:]), rules)
            d[l3 + 10:l3 + 12] = b"\0\0"
            d[l3 + 10:l3 + 12] = struct.pack(">H", _csum(bytes(d[l3:l3 + ihl])))
            return bytes(d)
        ps, pe = _payload_range(d, ip)
        if proto in (6, 17) and pe > ps and len(raw) >= l4 + 4:
            sp, dp = struct.unpack_from(">HH", raw, l4)
            payload = bytearray(d[ps:pe])
            conn = (proto, frozenset(((str(src), sp), (str(dst), dp))))
            st = self.streams.get(conn)
            if st is None:
                st = self.streams[conn] = {"kind": "plain", "dirs": {}, "first": set()}
            side = (str(src), sp)
            if side not in st["first"]:
                # the first payload of EACH direction decides (a client's hello may be
                # missing from the recording; the server's answer is enough)
                st["first"].add(side)
                if st["kind"] == "plain":
                    if proto == 6 and _tls_handshake_start(bytes(payload)):
                        st["kind"] = "TLS"
                    elif proto == 17 and _dtls_handshake_start(bytes(payload)):
                        st["kind"] = "DTLS"
                    elif proto == 6 and bytes(payload[:4]) == b"SSH-":
                        st["kind"] = "SSH"
            name = f"{proto_name(proto)} {min(sp, dp)}<->{max(sp, dp)}"
            if st["kind"] != "plain":
                dstate = st["dirs"].setdefault((str(src), sp), _Stream(st["kind"]))
                if st["kind"] == "TLS":
                    n = _mask_tls(dstate, payload)
                elif st["kind"] == "DTLS":
                    n = _mask_dtls(payload)
                else:
                    n = _mask_ssh(dstate, payload)
                m.count("encrypted bytes replaced by zeros", n)
                e = self.encrypted.setdefault(name, {"kind": st["kind"], "zeroed": 0})
                e["zeroed"] += n
            elif _is_dhcp(ip, raw):
                _mask_dhcp_names(d, ps, pe, m)
                payload = bytearray(m.scrub_bytes(bytes(d[ps:pe]), rules))
            elif sp in NAME_PORTS or dp in NAME_PORTS:
                port = sp if sp in NAME_PORTS else dp
                if NAME_PORTS[port] == "NetBIOS":
                    payload[:] = bytes(len(payload))
                    m.count("NetBIOS names replaced by zeros")
                elif NAME_PORTS[port] in ("mDNS", "LLMNR"):
                    m.count("names in name announcements masked", mask_dns_names(payload))
                elif NAME_PORTS[port] in ("SSDP", "WS-Discovery"):
                    m.count("names in name announcements masked", mask_announcement(payload))
                payload = bytearray(m.scrub_bytes(bytes(payload), rules))
            else:
                payload = bytearray(m.scrub_bytes(bytes(payload), rules))
            d[ps:pe] = payload
        elif pe > ps:
            d[ps:pe] = m.scrub_bytes(bytes(d[ps:pe]), rules)
        _fix_checksums(d, ip)
        return bytes(d)


def rewrite_net(linktype: int, recs, keep: list, mapper, selection: dict) -> tuple:
    """Kept frames rewritten (tests and small files). Returns (records, encrypted)."""
    rw = NetRewriter(linktype, mapper, selection)
    for ri in keep:
        rw.register(recs[ri][1])
    out = [(recs[ri][0], rw.rewrite(recs[ri][1])) for ri in keep]
    return out, rw.encrypted


def proto_name(p: int) -> str:
    return {6: "TCP", 17: "UDP", 1: "ICMP", 58: "ICMPv6"}.get(p, f"protocol {p}")


def flows(linktype: int, recs) -> list:
    """Messages per connection for the analysis: [{t, proto, src, sp, dst, dp,
    data, conn}] (TCP payload segments and UDP datagrams; no reassembly)."""
    out = []
    for ts, d in recs:
        f = parse_frame(linktype, d)
        if not f or f.ethertype not in (ETH_IPV4, ETH_IPV6):
            continue
        ip = parse_ip(d, f.l3)
        if not ip or ip[3] not in (6, 17) or len(d) < ip[4] + 4:
            continue
        sp, dp = struct.unpack_from(">HH", d, ip[4])
        ps, pe = _payload_range(d, ip)
        data = bytes(d[ps:pe])
        flags = d[ip[4] + 13] if ip[3] == 6 and len(d) > ip[4] + 13 else 0
        out.append({"t": ts, "proto": proto_name(ip[3]), "src": str(ip[1]), "sp": sp,
                    "dst": str(ip[2]), "dp": dp, "data": data, "flags": flags,
                    "conn": f"{proto_name(ip[3])} {min(sp, dp)}<->{max(sp, dp)}"})
    return out

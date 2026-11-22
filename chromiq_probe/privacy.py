"""The privacy pass: identifiers replaced consistently.

Rules (each has a test in tests/test_privacy.py):

* The same value always gets the same placeholder within one run, so an
  analysis can still see "this is the same address again". Placeholders are
  numbered in the order values are first seen; nothing in a placeholder is
  derived from the value itself.
* The salted short code (ported from the X-Rite probe 1.6.3: a random salt
  made new for every run and never written) is used only where a report
  needs to tell two serial numbers apart without numbering them.
* Inside recorded bytes every replacement keeps the LENGTH, so length fields,
  framing and offsets of the instrument's protocol stay valid.
* Classes: the computer's and the device's MAC and IP addresses, other
  addresses in kept traffic, the computer's host name, the user name, home
  folder paths, the instrument's USB serial number (unless the owner agreed
  to keep it), and anything the owner names with --hide.
"""

from __future__ import annotations

import getpass
import hashlib
import ipaddress
import os
import re
import platform
import secrets

_SALT = [secrets.token_bytes(16)]


def new_salt() -> None:
    _SALT[0] = secrets.token_bytes(16)


def salted_code(data) -> str:
    """8 hex characters of a salted SHA-256 (X-Rite probe 1.6.3)."""
    if isinstance(data, str):
        data = data.encode("utf-8", "replace")
    return hashlib.sha256(_SALT[0] + data).hexdigest()[:8]


def same_length(tag: str, length: int, fill: str = "_") -> str:
    """A placeholder of exactly `length` characters that starts with `tag`
    where it fits. Too short a field gets only fill characters."""
    if length <= 0:
        return ""
    if len(tag) > length:
        return "#" * length
    return tag + fill * (length - len(tag))


# addresses that say nothing about a person or a place: kept as they are
def _special_ip(ip) -> bool:
    return (ip.is_multicast or ip.is_unspecified or ip.is_loopback
            or str(ip) == "255.255.255.255")


def _special_mac(mac: bytes) -> bool:
    return mac == b"\xff" * 6 or mac == b"\x00" * 6 or bool(mac[0] & 1)


DEVICE_NET = ipaddress.ip_network("198.51.100.0/24")
OTHER_NETS = [ipaddress.ip_network("192.0.2.0/24"), ipaddress.ip_network("203.0.113.0/24"),
              ipaddress.ip_network("100.64.0.0/10")]
PLACEHOLDER_NETS = [DEVICE_NET] + OTHER_NETS + [ipaddress.ip_network("2001:db8::/32")]


def placeholder_ipv4(n: int, device: bool):
    """The n-th placeholder (1-based): the instrument in 198.51.100.x (and,
    past 254, in 100.127.x.y), everything else in 192.0.2.x, 203.0.113.x,
    then 100.64.x.y. Never a real address, never the same one twice."""
    if device:
        if n <= 254:
            return ipaddress.ip_address(f"198.51.100.{n}")
        return ipaddress.ip_address(int(ipaddress.ip_address("100.127.0.0")) + n)
    if n <= 254:
        return ipaddress.ip_address(f"192.0.2.{n}")
    if n <= 508:
        return ipaddress.ip_address(f"203.0.113.{n - 254}")
    return ipaddress.ip_address(int(ipaddress.ip_address("100.64.0.0")) + n)


class Mapper:
    """Keeps the value -> placeholder tables of one run."""

    def __init__(self):
        self.macs: dict = {}          # 6 bytes -> 6 bytes
        self.ips: dict = {}           # ip_address -> ip_address
        self.texts: dict = {}         # str -> (kind, number)
        self.counts: dict = {}        # kind -> replacements made
        self.device_macs: set = set()
        self.device_ips: set = set()
        self._n = {}
        self._ip_numbers: dict = {}
        self._fake_ips: set = set()
        self._fake_macs: set = set()

    def _next(self, kind: str) -> int:
        self._n[kind] = self._n.get(kind, 0) + 1
        return self._n[kind]

    def count(self, kind: str, n: int = 1) -> None:
        if n:
            self.counts[kind] = self.counts.get(kind, 0) + n

    # -- addresses ---------------------------------------------------------
    def mac(self, mac: bytes) -> bytes:
        mac = bytes(mac)
        if _special_mac(mac) or mac in self._fake_macs:
            return mac
        if mac not in self.macs:
            dev = mac in self.device_macs
            n = self._next("devmac" if dev else "mac")
            # locally administered unicast: 02:00:00:00:<01 device / 00 other>:n
            self.macs[mac] = bytes([0x02, 0, 0, 0, 1 if dev else 0, n & 0xFF])
            self._fake_macs.add(self.macs[mac])
        return self.macs[mac]

    def ip(self, ip):
        ip = ipaddress.ip_address(ip)
        if _special_ip(ip) or ip in self._fake_ips:
            return ip
        if ip.version == 4 and (ip.packed[3] == 255 and ip.is_private):
            return ip                 # a subnet broadcast: kept, says nothing
        if ip not in self.ips:
            dev = ip in self.device_ips
            n = self._next("devip" if dev else "ip")
            if ip.version == 4:
                self.ips[ip] = placeholder_ipv4(n, dev)
            else:
                self.ips[ip] = ipaddress.ip_address(("2001:db8:1::" if dev else "2001:db8::")
                                                    + format(n, "x"))
            self._fake_ips.add(self.ips[ip])
        return self.ips[ip]

    def text(self, kind: str, value: str) -> str:
        if value not in self.texts:
            self.texts[value] = (kind, self._next(kind))
        k, n = self.texts[value]
        return f"{k}{n}"

    # -- every known identifier, in the forms it can take inside data --------
    def byte_rules(self, binary_ips: bool = False) -> list:
        """[(kind, compiled bytes regex, replacement function)], longest first.

        Forms replaced, each by a placeholder of the same byte length:
          * text values (serial numbers, names, --hide): ASCII in any upper /
            lower case, UTF-8 (as given, lower and upper case), UTF-16LE and
            UTF-16BE in any case, URL-encoded ("%5C" for "\\"), and for the user
            name its Windows 8.3 short form (MIRAND~1);
          * MAC addresses: the 6 bytes, and "aa:bb:.." / "AA-BB-.." text;
          * IP addresses seen in the traffic: their text; with binary_ips (network
            payloads) also their 4 bytes;
          * any other dotted IPv4 text whose first number is 10 or more, and any
            "aa:bb:cc:dd:ee:ff" text (version numbers like 1.2.3.4 are kept).
          * MACs also as 12 hex digits without separators; IPv6 addresses seen in
            the traffic in their short and long text forms; and in NETWORK data only,
            inside readable text, any other IPv6 text with at least 3 groups or a
            link-local, global or private prefix.
        Values shorter than 4 bytes are not replaced inside data (too likely to
        hit measurement bytes), and --check does not search for them either (a user
        name under 3 letters is not even collected)."""
        rules = []

        def add(kind, pattern: bytes, fake: bytes, flags=0, raw=False):
            if len(pattern if raw else pattern) < (1 if kind == "mac (binary)" else 4):
                return
            rx = re.compile(pattern if raw else re.escape(pattern), flags | re.DOTALL)
            rules.append((kind, rx, (lambda m, f=fake: f), len(fake)))

        for real, fake in self.macs.items():
            if real == fake:
                continue
            add("mac (binary)", real, fake)
            for sep in (":", "-", ""):
                t = sep.join(f"{b:02x}" for b in real).encode()
                f = sep.join(f"{x:02x}" for x in fake).encode()
                if sep:
                    add("mac (text)", t, f, re.I)
                else:                                     # 12 hex digits (review 2)
                    add("mac (text)", rb"(?<![0-9A-Fa-f])" + re.escape(t) + rb"(?![0-9A-Fa-f])",
                        f, re.I, raw=True)
        for real, fake in self.ips.items():
            if real == fake:
                continue
            t = str(real).encode()
            n = self._ip_numbers.setdefault(real, len(self._ip_numbers) + 1)
            add("ip (text)", rb"(?<![0-9.])" + re.escape(t) + rb"(?![0-9])",
                same_length(f"ip{n}", len(t)).encode(), raw=True)
            if binary_ips and real.version == 4:
                add("ip (binary)", real.packed, fake.packed)
            if real.version == 6:
                for form in {real.exploded, real.compressed}:
                    tb = form.encode()
                    add("ip (text)", re.escape(tb), same_length(f"ip{n}", len(tb)).encode(),
                        re.I, raw=True)
            if binary_ips and real.version == 6:
                add("ip (binary)", real.packed, fake.packed)
        for value, (kind, n) in self.texts.items():
            for pattern, fake, flags, raw in _text_forms(value, f"{kind}{n}", kind):
                add(kind, pattern, fake, flags, raw)
        rules.sort(key=lambda r: -r[3])
        mapper = self

        def any_ip(m):
            t = m.group(0)
            try:
                ip = ipaddress.ip_address(t.decode())
            except ValueError:
                return t
            if ip in mapper._fake_ips:
                return t
            n = mapper._ip_numbers.setdefault(ip, len(mapper._ip_numbers) + 1)
            mapper.count("ip (text, not seen in the traffic)")
            return same_length(f"ip{n}", len(t)).encode()

        def any_mac(m):
            t = m.group(0)
            sep = t[2:3]
            mac = bytes(int(x, 16) for x in t.decode().replace("-", ":").split(":"))
            fake = mapper.mac(mac)
            if fake == mac:
                return t
            mapper.count("mac (text, not seen in the traffic)")
            return sep.join(f"{x:02x}".encode() for x in fake)
        def any_ip6(m):
            t = m.group(0)
            try:
                ip = ipaddress.ip_address(t.decode())
            except ValueError:
                return t
            if ip.version != 6 or ip in mapper._fake_ips or ip.is_loopback or ip.is_unspecified:
                return t
            groups = [g for g in t.decode().split(":") if g]
            if len(groups) < 3 and not any(ip in n_ for n_ in _IPV6_PREFIXES):
                return t
            n = mapper._ip_numbers.setdefault(ip, len(mapper._ip_numbers) + 1)
            mapper.count("ip (text, not seen in the traffic)")
            return same_length(f"ip{n}", len(t)).encode()
        rules.append(("ip (any text)", _ANY_IPV4, any_ip, 0))
        if binary_ips:
            # review 2 re-check, R-1: the general IPv6 pattern ONLY for network data and
            # only inside readable text (8 or more printable bytes); in USB data it would
            # change binary readings ("::47", "A::5" parse as addresses). There, only the
            # known addresses (above) are replaced.
            rules.append(("ip6 (in text)", _PRINTABLE_RUN,
                          lambda m: _ANY_IPV6.sub(any_ip6, m.group(0)), 0))
        rules.append(("mac (any text)", _ANY_MAC, any_mac, 0))
        return rules

    def scrub_bytes(self, data: bytes, rules) -> bytes:
        for kind, rx, repl, _ln in rules:
            if kind in ("ip (any text)", "mac (any text)", "ip6 (in text)"):
                data = rx.sub(repl, data)
                continue
            data, n = rx.subn(repl, data)
            if n:
                self.count(kind, n)
        return data


_ANY_IPV4 = re.compile(rb"(?<![0-9.])(?:1\d|[2-9]\d|1\d\d|2[0-4]\d|25[0-5])"
                       rb"(?:\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}(?![0-9])")
_PRINTABLE_RUN = re.compile(rb"[ -~]{8,}")
_IPV6_PREFIXES = [ipaddress.ip_network(n) for n in ("fe80::/10", "2000::/3", "fc00::/7")]
_ANY_IPV6 = re.compile(rb"(?<![0-9A-Fa-f:.])[0-9A-Fa-f]{0,4}(?::[0-9A-Fa-f]{0,4}){2,7}"
                       rb"(?![0-9A-Fa-f:.])")
_ANY_MAC = re.compile(rb"(?<![0-9A-Fa-f:-])[0-9A-Fa-f]{2}([:-])(?:[0-9A-Fa-f]{2}\1){4}"
                      rb"[0-9A-Fa-f]{2}(?![0-9A-Fa-f:-])")


def _percent(value: str) -> str:
    out = []
    for ch in value:
        if ch.isalnum() and ord(ch) < 128 or ch in "-_.~":
            out.append(ch)
        else:
            out.extend(f"%{b:02X}" for b in ch.encode("utf-8"))
    return "".join(out)


def _utf16_any_case(value: str, enc: str) -> bytes:
    parts = []
    for ch in value:
        forms = {ch, ch.lower(), ch.upper()}
        alts = [re.escape(f.encode(enc)) for f in forms if len(f) == 1]
        parts.append(b"(?:" + b"|".join(sorted(alts)) + b")")
    return b"".join(parts)


def _text_forms(value: str, tag: str, kind: str):
    """(pattern, replacement, regex flags, pattern-is-a-regex) for every form."""
    out = []
    try:
        a = value.encode("ascii")
        out.append((a, same_length(tag, len(a)).encode(), re.I, False))
    except UnicodeEncodeError:
        for v in {value, value.lower(), value.upper()}:
            b = v.encode("utf-8")
            out.append((b, same_length(tag, len(b)).encode(), 0, False))
    for enc in ("utf-16-le", "utf-16-be"):
        try:
            fake = same_length(tag, len(value)).encode(enc)
            out.append((_utf16_any_case(value, enc), fake, 0, True))
        except UnicodeEncodeError:
            pass
    pct = _percent(value)
    if pct != value:
        b = pct.encode("ascii")
        out.append((b, same_length(tag, len(b)).encode(), re.I, False))
    if kind == "user":
        base = re.sub(r"[^A-Za-z0-9]", "", value).upper()
        if len(base) > 6 or len(value) > 8:
            for k in range(1, 5):
                short = f"{base[:6]}~{k}".encode()
                out.append((short, same_length(tag, len(short)).encode(), re.I, False))
    return out


# --------------------------------------------------------------------------
# this computer's own identifiers
# --------------------------------------------------------------------------

def computer_identifiers() -> dict:
    """User name, home folder and host names of this computer (to hide)."""
    ids = {}
    try:
        user = getpass.getuser()
        if user and len(user) >= 3:
            ids["user"] = user
    except Exception:                                     # noqa: BLE001
        pass
    home = os.path.expanduser("~")
    if home and home not in ("/", "~"):
        ids["home"] = home
    try:
        host = platform.node()
        if host and host.lower() not in ("localhost", ""):
            ids["host"] = host
            short = host.split(".")[0]
            if short != host and len(short) >= 3:
                ids["host_short"] = short
    except OSError:
        pass
    if platform.system() == "Darwin" and os.path.exists("/usr/sbin/scutil"):
        import subprocess                                 # noqa: PLC0415
        for key, field in (("computer_name", "ComputerName"), ("local_host", "LocalHostName")):
            try:
                out = subprocess.run(["/usr/sbin/scutil", "--get", field],
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     timeout=5).stdout.decode("utf-8", "replace").strip()
            except (OSError, subprocess.TimeoutExpired):
                out = ""
            if len(out) >= 3:
                ids[key] = out
    return ids


_MAC_TEXT = re.compile(r"\b([0-9A-Fa-f]{2})([:-])([0-9A-Fa-f]{2})\2([0-9A-Fa-f]{2})\2"
                       r"([0-9A-Fa-f]{2})\2([0-9A-Fa-f]{2})\2([0-9A-Fa-f]{2})\b")
_IPV4_TEXT = re.compile(r"\b(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})\b")
_SERIAL_TEXT = re.compile(r"(?i)((?:serial(?:[ _-]?number)?|iSerial|SerialNumber|"
                          r"USB Serial Number)\W{0,4})([A-Za-z0-9_-]{4,})")


def scrub_text(text: str, mapper: Mapper, ids: dict | None = None,
               hide=()) -> str:
    """Hide identifiers in a text written by this tool (report, notes)."""
    if not text:
        return text
    ids = computer_identifiers() if ids is None else ids
    home = ids.get("home")
    if home:
        text = text.replace(home, "~")
    text = re.sub(r"(?i)\b([A-Z]:\\+Users\\+)(?!Public\b)[^\\/\"'\r\n]+", r"\1USER", text)
    text = re.sub(r"(/Users/|/home/)(?!Shared\b)[^/\s\"']+", r"\1USER", text)
    for key in ("computer_name", "local_host", "host", "host_short", "user"):
        value = ids.get(key)
        if value:
            text = re.sub(re.escape(value), "USER" if key == "user" else
                          mapper.text("computer", value), text, flags=re.I)
    for value in hide:
        if value:
            text = re.sub(re.escape(value), mapper.text("hidden", value), text, flags=re.I)
    for value, (kind, n) in list(mapper.texts.items()):
        if kind == "serial" and value:
            text = re.sub(re.escape(value), f"{kind}{n}", text, flags=re.I)

    def mac_sub(m):
        mac = bytes(int(m.group(i), 16) for i in (1, 3, 4, 5, 6, 7))
        fake = mapper.mac(mac)
        return m.group(2).join(f"{b:02x}" for b in fake)
    text = _MAC_TEXT.sub(mac_sub, text)

    def ip_sub(m):
        try:
            ip = ipaddress.ip_address(m.group(0))
        except ValueError:
            return m.group(0)
        if not ip.is_private and not ip.is_global:
            return m.group(0)
        return str(mapper.ip(ip))
    text = _IPV4_TEXT.sub(ip_sub, text)
    text = _SERIAL_TEXT.sub(lambda m: m.group(1) + "<serial:" + salted_code(m.group(2)) + ">",
                            text)
    return text

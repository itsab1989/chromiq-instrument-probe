"""Finding the instrument: USB devices, serial ports, network neighbours.

Everything here only READS what the operating system already knows (the same
lists as Device Manager, System Information or `arp -a`). Nothing is sent to
any device and nothing on the network: no ping, no scan, no mDNS query.

The parsers are pure functions of the commands' text, so they are tested
with sample outputs; `run` is the only place a command is started.

"Before and after": the friendliest way to find a device is to take a list,
ask the owner to plug it in (or connect the maker's program to it), take the
list again, and show only what is new.
"""

from __future__ import annotations

import glob
import ipaddress
import json
import os
import platform
import re
import subprocess

from . import known


def run(cmd: list, timeout: int = 30) -> str:
    try:
        p = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=timeout)
        return p.stdout.decode("utf-8", "replace")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"[could not run {cmd[0]}: {exc}]"


class UsbDevice:
    def __init__(self, vid: int, pid: int, name: str = "", maker: str = "", serial: str = "",
                 location=None, address=None, interfaces=(), port_path: str = "",
                 instance: str = ""):
        self.vid, self.pid = vid, pid
        self.name, self.maker, self.serial = name or "", maker or "", serial or ""
        self.location = location          # macOS locationID
        self.address = address            # (bus, address) on Linux
        self.interfaces = list(interfaces)  # [(class, subclass, protocol)]
        self.port_path = port_path        # Linux: the sysfs name, e.g. "1-2.3"
        self.instance = instance          # Windows: the device instance id

    @property
    def ids(self) -> str:
        return f"{self.vid:04x}:{self.pid:04x}"

    def key(self):
        return (self.vid, self.pid, self.location, self.address, self.port_path, self.instance,
                self.serial)

    def label(self) -> str:
        name = " ".join(x for x in (self.maker, self.name) if x).strip() or "(no name)"
        return f"{name} [USB {self.ids}]"

    def verdict(self) -> str:
        return known.verdict(self.vid, self.pid, self.interfaces)

    def selection(self) -> dict:
        """One chosen device. "serial" and "port_path" bind it to this unit;
        they stay in the local session.json and never reach the zip."""
        sel = {"vid": self.vid, "pid": self.pid, "name": self.label()}
        if self.location is not None:
            sel["location"] = self.location
        if self.address:
            sel["addresses"] = [list(self.address)]
        if self.serial:
            sel["serial"] = self.serial
        if self.port_path:
            sel["port_path"] = self.port_path
        if self.interfaces:
            sel["interfaces"] = [list(x) for x in self.interfaces]
        return sel


# ---- USB, per system -------------------------------------------------------

def parse_ioreg(text: str) -> list:
    """`ioreg -p IOUSB -l -w0` on macOS."""
    devices = []
    for block in re.split(r"\n(?=[ |]*\+-o )", text or ""):
        props = dict(re.findall(r'"([^"]+)" = (.+)', block))
        if "idVendor" not in props or "idProduct" not in props:
            continue
        try:
            vid, pid = int(props["idVendor"]), int(props["idProduct"])
        except ValueError:
            continue
        if vid == 0 and pid == 0:
            continue

        def s(key):
            v = props.get(key, "").strip()
            return v[1:-1] if v.startswith('"') and v.endswith('"') else v
        loc = props.get("locationID")
        devices.append(UsbDevice(vid, pid, s("USB Product Name") or s("kUSBProductString"),
                                 s("USB Vendor Name") or s("kUSBVendorString"),
                                 s("USB Serial Number") or s("kUSBSerialNumberString"),
                                 location=int(loc) if loc and loc.isdigit() else None))
    return devices


def linux_usb_devices(root: str = "/sys/bus/usb/devices") -> list:
    devices = []
    for path in sorted(glob.glob(os.path.join(root, "*"))):
        def read(name, base=path):
            try:
                with open(os.path.join(base, name)) as fh:
                    return fh.read().strip()
            except OSError:
                return ""
        vid, pid = read("idVendor"), read("idProduct")
        if not vid or not pid:
            continue
        itfs = []
        for ipath in glob.glob(os.path.join(path, "*:*")):
            c = read("bInterfaceClass", ipath)
            if c:
                itfs.append((int(c, 16), int(read("bInterfaceSubClass", ipath) or "0", 16),
                             int(read("bInterfaceProtocol", ipath) or "0", 16)))
        bus, dev = read("busnum"), read("devnum")
        devices.append(UsbDevice(int(vid, 16), int(pid, 16), read("product"),
                                 read("manufacturer"), read("serial"),
                                 address=(int(bus), int(dev)) if bus and dev else None,
                                 interfaces=itfs, port_path=os.path.basename(path)))
    return devices


_WIN_ID = re.compile(r"USB\\VID_([0-9A-F]{4})&PID_([0-9A-F]{4})(?:&MI_\d+)?\\([^|\s]*)", re.I)


def parse_windows_pnp(text: str) -> list:
    """Lines 'InstanceId|FriendlyName|Manufacturer' from PowerShell."""
    seen, devices = set(), []
    for line in (text or "").splitlines():
        parts = line.strip().split("|")
        m = _WIN_ID.match(parts[0]) if parts else None
        if not m or "&MI_" in parts[0].upper():
            continue
        vid, pid = int(m.group(1), 16), int(m.group(2), 16)
        serial = m.group(3) if "&" not in m.group(3) else ""
        if parts[0] in seen:
            continue
        seen.add(parts[0])
        devices.append(UsbDevice(vid, pid, parts[1] if len(parts) > 1 else "",
                                 parts[2] if len(parts) > 2 else "", serial,
                                 instance=parts[0]))
    return devices


_PS_USB = ("Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | "
           "Where-Object { $_.InstanceId -like 'USB\\VID_*' } | "
           "ForEach-Object { $_.InstanceId + '|' + $_.FriendlyName + '|' + $_.Manufacturer }")


def _sys32(name: str) -> str:
    return os.path.join(os.environ.get("SystemRoot") or r"C:\Windows", "System32", name)


def _first(*paths) -> str:
    for p in paths:
        if os.path.exists(p):
            return p
    return paths[0]


def usb_devices() -> list:
    system = platform.system()
    if system == "Darwin":
        return parse_ioreg(run(["/usr/sbin/ioreg", "-p", "IOUSB", "-l", "-w0"]))
    if system == "Linux":
        return linux_usb_devices()
    if system == "Windows":
        ps = _sys32(r"WindowsPowerShell\v1.0\powershell.exe")
        if os.path.exists(ps):
            return parse_windows_pnp(run([ps, "-NoProfile", "-NonInteractive", "-Command",
                                          _PS_USB], timeout=60))
    return []


def new_devices(before: list, after: list) -> list:
    old = {d.key() for d in before}
    return [d for d in after if d.key() not in old]


# ---- serial ports ------------------------------------------------------------

def serial_ports() -> list:
    system = platform.system()
    if system == "Darwin":
        return sorted(glob.glob("/dev/cu.*"))
    if system == "Linux":
        return sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
                      + glob.glob("/dev/ttyS[0-9]"))
    if system == "Windows":
        text = run([_sys32("mode.com")], timeout=20)
        return sorted(set(re.findall(r"\b(COM\d+)\b", text)))
    return []


# ---- network -----------------------------------------------------------------

_MAC = r"([0-9a-fA-F]{1,2}(?:[:-][0-9a-fA-F]{1,2}){5})"


def _norm_mac(m: str) -> str:
    return ":".join(p.zfill(2) for p in re.split("[:-]", m.lower()))


def parse_neighbours(text: str) -> list:
    """[(ip, mac)] from `arp -a` (macOS, Windows) or `ip neigh` (Linux)."""
    out = []
    for line in (text or "").splitlines():
        ipm = re.search(r"\(?(\d{1,3}(?:\.\d{1,3}){3})\)?", line)
        macm = re.search(_MAC, line)
        if not ipm or not macm:
            continue
        mac = _norm_mac(macm.group(1))
        if mac in ("ff:ff:ff:ff:ff:ff", "00:00:00:00:00:00") or int(mac[:2], 16) & 1:
            continue
        try:
            ip = ipaddress.ip_address(ipm.group(1))
        except ValueError:
            continue
        if ip.is_multicast or str(ip).endswith(".255"):
            continue
        out.append((str(ip), mac))
    return out


def parse_connections(text: str) -> list:
    """Remote addresses of open connections from `netstat -an` (Windows,
    macOS) or `ss -tun` (Linux): [(proto, remote ip, remote port)]."""
    out = []
    for line in (text or "").splitlines():
        low = line.lower()
        if not (low.lstrip().startswith(("tcp", "udp"))):
            continue
        if "listen" in low:
            continue
        addrs = re.findall(r"(\d{1,3}(?:\.\d{1,3}){3})[.:](\d+)", line)
        if len(addrs) < 2:
            continue
        ip, port = addrs[1]
        try:
            a = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if a.is_unspecified or a.is_loopback:
            continue
        out.append(("udp" if low.lstrip().startswith("udp") else "tcp", ip, int(port)))
    return out


def neighbours() -> list:
    system = platform.system()
    if system == "Linux":
        return parse_neighbours(run([_first("/usr/sbin/ip", "/sbin/ip", "/usr/bin/ip"), "neigh"]))
    if system == "Windows":
        return parse_neighbours(run([_sys32("arp.exe"), "-a"]))
    return parse_neighbours(run(["/usr/sbin/arp", "-an"]))


def connections() -> list:
    system = platform.system()
    if system == "Linux":
        return parse_connections(run([_first("/usr/bin/ss", "/usr/sbin/ss", "/bin/ss"), "-tun"]))
    if system == "Windows":
        return parse_connections(run([_sys32("netstat.exe"), "-an"]))
    return parse_connections(run(["/usr/sbin/netstat", "-an"]))


def parse_gateways(text: str) -> list:
    """Default gateway addresses from `route -n get default` (macOS),
    `ip route show default` (Linux) or `route print -4 0.0.0.0` (Windows)."""
    out = []
    for line in (text or "").splitlines():
        low = line.strip().lower()
        m = re.search(r"gateway:\s*(\d{1,3}(?:\.\d{1,3}){3})", low) or \
            re.search(r"^default\s+(\d{1,3}(?:\.\d{1,3}){3})\s", low) or \
            re.search(r"^default via (\d{1,3}(?:\.\d{1,3}){3})", low) or \
            re.search(r"^0\.0\.0\.0\s+0\.0\.0\.0\s+(\d{1,3}(?:\.\d{1,3}){3})", low)
        if m and m.group(1) not in out:
            out.append(m.group(1))
    return out


def gateways() -> list:
    system = platform.system()
    if system == "Darwin":
        # every interface's default route (a VPN holds the first one)
        return parse_gateways(run(["/usr/sbin/netstat", "-rn", "-f", "inet"])
                              + "\n" + run(["/sbin/route", "-n", "get", "default"]))
    if system == "Linux":
        return parse_gateways(run([_first("/usr/sbin/ip", "/sbin/ip", "/usr/bin/ip"), "-4",
                                   "route", "show", "table", "all"]))
    if system == "Windows":
        return parse_gateways(run([_sys32("route.exe"), "print", "-4", "0.0.0.0"]))
    return []


def refresh_usb_selection(selection: dict) -> None:
    """Linux: before each block, find every chosen device again by its port
    and update the address the system gave it (it changes after a replug)."""
    if platform.system() != "Linux":
        return
    now = {d.port_path: d for d in linux_usb_devices()}
    for dev in selection.get("devices", []):
        d = now.get(dev.get("port_path"))
        if d and (d.vid, d.pid) == (dev["vid"], dev["pid"]) and d.address:
            dev["addresses"] = [list(d.address)]


def network_candidates(before: dict, after: dict) -> list:
    """New addresses after the owner connected the program: [(ip, mac or '',
    why)], addresses on the local network first."""
    old_n = set(before.get("neighbours", []))
    old_c = {(p, ip) for p, ip, _port in before.get("connections", [])}
    macs = dict(after.get("neighbours", []))
    found = {}
    for p, ip, port in after.get("connections", []):
        if (p, ip) not in old_c:
            found.setdefault(ip, f"a new {p.upper()} connection to port {port}")
    for ip, mac in after.get("neighbours", []):
        if (ip, mac) not in old_n:
            found.setdefault(ip, "newly seen on your local network")
    rows = [(ip, macs.get(ip, ""), why) for ip, why in found.items()]
    return sorted(rows, key=lambda r: (not ipaddress.ip_address(r[0]).is_private, r[0]))


def capture_interface_for(ip: str) -> str | None:
    """The network interface that leads to ip (macOS and Linux)."""
    system = platform.system()
    if system == "Darwin":
        m = re.search(r"interface:\s*(\S+)", run(["/sbin/route", "-n", "get", ip]))
        return m.group(1) if m else None
    if system == "Linux":
        m = re.search(r"\bdev\s+(\S+)", run([_first("/usr/sbin/ip", "/sbin/ip", "/usr/bin/ip"),
                                               "route", "get", ip]))
        return m.group(1) if m else None
    return None


def environment() -> dict:
    return {"system": platform.system(), "release": platform.release(),
            "version": platform.version(), "machine": platform.machine(),
            "python": platform.python_version()}


def devices_json(devs: list) -> str:
    return json.dumps([{"ids": d.ids, "name": d.label(), "verdict": d.verdict()} for d in devs],
                      indent=1)

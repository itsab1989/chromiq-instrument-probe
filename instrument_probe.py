#!/usr/bin/env python3
"""
instrument_probe.py — colour-instrument information collector for ChromIQ.

WHAT THIS DOES
    Works out what a colour measuring instrument (spectrophotometer,
    colorimeter, scanning table, chart reader) looks like to your computer,
    and writes it all into one plain-text file you can send back. It is meant
    for devices ChromIQ and ArgyllCMS do NOT support yet.

WHAT THIS DOES NOT DO
    It never sends a single byte to the instrument. It does not open it, does
    not calibrate it, does not take a measurement and cannot move anything. It
    only reads what the operating system already knows about connected
    hardware, and — if ArgyllCMS happens to be installed — asks it which
    instruments it recognises.

    It is safe to run at any time, with the device idle.

USAGE
        python3 instrument_probe.py

    Add --annotate to go straight to the optional advanced step (recording the
    USB traffic while the vendor's own software drives the instrument).

PRIVACY
    Serial numbers are replaced with a short stable hash by default, and your
    username and home directory are stripped out. Add --no-redact to keep the
    raw values; they are not needed for this work.

Requires: Python 3.8+ and nothing else. No pip install.

Part of the ChromIQ project — https://github.com/itsab1989/ChromIQ
"""

from __future__ import annotations

import argparse
import datetime
import getpass
import glob
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import struct
import subprocess
import sys
import tempfile
import time

PROBE_VERSION = "1.1"

# --------------------------------------------------------------------------
# what ArgyllCMS actually supports
# --------------------------------------------------------------------------
#
# Extracted from ArgyllCMS 3.5.0 `spectro/insttypes.c`, which is the authority
# on which USB instruments it can drive. If a device is in here, ChromIQ can
# very likely already use it and no new driver is needed — that alone saves an
# owner a great deal of pointless effort.

ARGYLL_USB_SUPPORTED = {
    ("04db", "005b"): "Colorimtre HCFR",
    ("0670", "0001"): "Monaco Optix / i1 Display 1",
    ("0765", "5001"): "Huey L",
    ("0765", "5010"): "Huey L",
    ("0765", "5020"): "i1 Display Pro / ColorMunki Display",
    ("0765", "6003"): "ColorMunki Smile",
    ("0765", "6008"): "ColorMunki i1Studio",
    ("0765", "6009"): "i1Pro 3",
    ("0765", "d020"): "DTP20",
    ("0765", "d092"): "DTP92Q",
    ("0765", "d094"): "DTP94",
    ("085c", "0100"): "ColorVision Spyder1",
    ("085c", "0200"): "ColorVision Spyder2",
    ("085c", "0300"): "Datacolor Spyder3",
    ("085c", "0400"): "Datacolor Spyder4",
    ("085c", "0500"): "Datacolor Spyder5",
    ("085c", "0a00"): "Datacolor SpyderX",
    ("085c", "0a0a"): "Datacolor SpyderX2",
    ("085c", "0a0b"): "Datacolor Spyder2024",
    ("0971", "2000"): "i1Pro / i1Pro 2",
    ("0971", "2001"): "i1 Monitor",
    ("0971", "2003"): "i1 Display 2",
    ("0971", "2005"): "Huey",
    ("0971", "2007"): "ColorMunki",
    ("2457", "4000"): "Image Engineering EX1",
    ("04d8", "f8da"): "Hughski ColorHug (old firmware)",
    ("273f", "1001"): "Hughski ColorHug",
    ("273f", "1004"): "Hughski ColorHug2",
}

# Instruments Argyll ships a udev rule for but has NO driver for. Argyll's own
# rules file marks both of these "(not tested)". Finding one of these is the
# most interesting outcome this tool can have.
ARGYLL_KNOWN_UNSUPPORTED = {
    ("0971", "2004"): "X-Rite i1iO scanning table",
    ("0971", "2006"): "X-Rite i1iSis chart reader",
}

# Vendors who make colour instruments. Used to flag a device as "probably an
# instrument" even when the exact model is unknown to us.
INSTRUMENT_VENDORS = {
    "0765": "X-Rite / Calibrite",
    "0971": "GretagMacbeth / X-Rite",
    "085c": "ColorVision / Datacolor",
    "0670": "Sequel Imaging",
    "04db": "HCFR",
    "2457": "Image Engineering",
    "273f": "Hughski",
    "04d8": "Microchip (ColorHug and others)",
    "132b": "Konica Minolta",
    "0a5f": "Barbieri / Zebra range",
}

# Generic USB-to-serial bridges. An inexpensive instrument is very often just
# a sensor behind one of these, which is good news: the transport is a plain
# serial port and the protocol is usually simple text or short binary frames.
SERIAL_BRIDGE_VENDORS = {
    "0403": "FTDI",
    "1a86": "QinHeng CH340 / CH341",
    "10c4": "Silicon Labs CP210x",
    "067b": "Prolific PL2303",
    "0557": "Aten / generic USB-serial",
}

REDACT = True
_SECTIONS: list[tuple[str, str]] = []


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def run(cmd: list[str], timeout: int = 40) -> str:
    """Run a command, return its output, never raise."""
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
    except FileNotFoundError:
        return f"[not available on this system: {cmd[0]}]"
    except subprocess.TimeoutExpired:
        return f"[timed out after {timeout}s: {' '.join(cmd)}]"
    except Exception as exc:                              # noqa: BLE001
        return f"[failed: {exc}]"
    out = proc.stdout or ""
    if proc.returncode != 0 and proc.stderr:
        out += f"\n[stderr] {proc.stderr}"
    return out.strip() or "[no output]"


# One rule per real-world serial-number format. A single clever regex missed
# three of them in testing: macOS system_profiler emits "serial_num", lsusb
# emits "iSerial <index> <value>", and Windows hides the serial in the tail of
# the device instance path.
_SERIAL_RULES = [
    (re.compile(r"(iSerial\s+\d+\s+)(\S{4,})"), "lsusb"),
    (re.compile(r"(USB\\VID_[0-9A-Fa-f]{4}&PID_[0-9A-Fa-f]{4}\\)([^\s\"',\\]{4,})"),
     "windows-instance-id"),
    # The {3,} tail keeps IOKit class names like "IOSerialBSDClient"=2 intact.
    (re.compile(r"([A-Za-z_]*[Ss]erial[A-Za-z_]*(?:\s*[Nn]umber|\s*[Nn]um)?"
                r"\"?\s*[:=]+\s*\"?)([A-Za-z0-9][\w\-]{3,})"), "generic-key"),
    (re.compile(r"()\b[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}"
                r"-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\b"), "uuid"),
]


def _hash_secret(match: re.Match) -> str:
    """Replace a secret with a stable short hash, keeping any key prefix.

    Stable, so the same device mentioned in two sections is still obviously
    one device without the real value appearing anywhere.
    """
    prefix = match.group(1) if match.lastindex and match.lastindex >= 1 else ""
    secret = (match.group(2) if match.lastindex and match.lastindex >= 2
              else match.group(0))
    digest = hashlib.sha256(secret.encode("utf-8", "replace")).hexdigest()[:8]
    return f"{prefix}<redacted:{digest}>"


def scrub(text: str) -> str:
    """Remove things that identify the person rather than the hardware."""
    if not REDACT or not text:
        return text
    try:
        user = getpass.getuser()
    except Exception:                                     # noqa: BLE001
        user = ""
    if user and len(user) >= 3:
        text = re.sub(rf"\b{re.escape(user)}\b", "USER", text)
    home = os.path.expanduser("~")
    if home and home not in ("/", ""):
        text = text.replace(home, "~")
    for pattern, _name in _SERIAL_RULES:
        text = pattern.sub(_hash_secret, text)
    return text


def section(title: str, body: str) -> None:
    _SECTIONS.append((title, scrub(body if body is not None else "")))


def ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return ""


def hr(char: str = "-") -> str:
    return char * 68


def _plural(count: int, singular: str, plural: str) -> str:
    """Explicit singular/plural — never '1 device(s)'."""
    return f"{count} {singular if count == 1 else plural}"


# --------------------------------------------------------------------------
# device discovery — one structured list, however the OS reports it
# --------------------------------------------------------------------------

class Device:
    """One USB device, normalised across the three platforms."""

    def __init__(self, vid: str, pid: str, name: str = "", extra: str = ""):
        self.vid = (vid or "").lower().replace("0x", "").zfill(4)
        self.pid = (pid or "").lower().replace("0x", "").zfill(4)
        self.name = (name or "").strip()
        self.extra = extra

    @property
    def ids(self) -> tuple[str, str]:
        return (self.vid, self.pid)

    def label(self) -> str:
        known = (ARGYLL_USB_SUPPORTED.get(self.ids)
                 or ARGYLL_KNOWN_UNSUPPORTED.get(self.ids))
        name = self.name or known or "unnamed device"
        return f"{self.vid}:{self.pid}  {name}"

    def verdict(self) -> str:
        """What this device means for ChromIQ support — the headline answer."""
        if self.ids in ARGYLL_USB_SUPPORTED:
            return ("ALREADY SUPPORTED by ArgyllCMS as "
                    f"'{ARGYLL_USB_SUPPORTED[self.ids]}' — ChromIQ can very "
                    "likely use this today.")
        if self.ids in ARGYLL_KNOWN_UNSUPPORTED:
            return (f"KNOWN BUT UNSUPPORTED: {ARGYLL_KNOWN_UNSUPPORTED[self.ids]}. "
                    "ArgyllCMS knows the USB id exists but has no driver for it.")
        if self.vid in INSTRUMENT_VENDORS:
            return (f"UNKNOWN MODEL from a known instrument maker "
                    f"({INSTRUMENT_VENDORS[self.vid]}). Not in ArgyllCMS's "
                    "device list — this is the interesting case.")
        if self.vid in SERIAL_BRIDGE_VENDORS:
            return (f"USB-to-SERIAL BRIDGE ({SERIAL_BRIDGE_VENDORS[self.vid]}). "
                    "Inexpensive instruments are often a sensor behind one of "
                    "these, which usually means a simple serial protocol.")
        return "Not a recognised instrument or serial bridge."

    def is_candidate(self) -> bool:
        return (self.ids in ARGYLL_USB_SUPPORTED
                or self.ids in ARGYLL_KNOWN_UNSUPPORTED
                or self.vid in INSTRUMENT_VENDORS
                or self.vid in SERIAL_BRIDGE_VENDORS)


def _devices_macos() -> list[Device] | None:
    """Devices found, or None if enumeration itself failed.

    The distinction matters: "nothing is plugged in" and "I could not look"
    need very different advice, and conflating them makes a working tool look
    broken to anyone who runs it with the instrument unplugged.
    """
    out = run(["system_profiler", "-json", "SPUSBDataType"], timeout=60)
    devices: list[Device] = []
    try:
        data = json.loads(out)
    except Exception:                                     # noqa: BLE001
        return None

    def walk(node):
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return
        vid = node.get("vendor_id")
        pid = node.get("product_id")
        if vid and pid:
            # system_profiler writes "0x0971  (X-Rite, Incorporated)"
            v = re.sub(r"\s*\(.*\)", "", str(vid)).strip()
            p = re.sub(r"\s*\(.*\)", "", str(pid)).strip()
            devices.append(Device(v, p, node.get("_name", "")))
        for value in node.values():
            if isinstance(value, (list, dict)):
                walk(value)

    walk(data)
    return devices


def _devices_linux() -> list[Device] | None:
    out = run(["lsusb"])
    if out.startswith("[") or out == "[no output]":
        return None                                   # lsusb missing or failed
    devices: list[Device] = []
    for line in out.splitlines():
        m = re.search(r"ID\s+([0-9a-fA-F]{4}):([0-9a-fA-F]{4})\s*(.*)", line)
        if m:
            devices.append(Device(m.group(1), m.group(2), m.group(3)))
    return devices


def _devices_windows() -> list[Device] | None:
    devices: list[Device] = []
    ps = shutil.which("powershell") or shutil.which("pwsh")
    if not ps:
        return None
    out = run([ps, "-NoProfile", "-Command",
               "Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -like 'USB*' } "
               "| ForEach-Object { $_.InstanceId + ' :: ' + $_.FriendlyName }"], timeout=90)
    for line in out.splitlines():
        m = re.search(r"VID_([0-9A-Fa-f]{4})&PID_([0-9A-Fa-f]{4})", line)
        if m:
            name = line.split("::", 1)[1].strip() if "::" in line else ""
            devices.append(Device(m.group(1), m.group(2), name))
    return devices


def discover_devices() -> list[Device] | None:
    """All USB devices, or None if this system could not be enumerated."""
    system = platform.system()
    try:
        if system == "Darwin":
            found = _devices_macos()
        elif system == "Linux":
            found = _devices_linux()
        elif system == "Windows":
            found = _devices_windows()
        else:
            found = None
    except Exception:                                     # noqa: BLE001
        found = None
    if found is None:
        return None
    # De-duplicate; hubs and composite devices are reported more than once.
    seen, unique = set(), []
    for dev in found:
        key = (dev.vid, dev.pid, dev.name)
        if key in seen:
            continue
        seen.add(key)
        unique.append(dev)
    return unique


# --------------------------------------------------------------------------
# what ArgyllCMS itself sees
# --------------------------------------------------------------------------

ARGYLL_SEARCH_DIRS = [
    "/Applications/Argyll/bin",
    "/usr/local/bin", "/opt/homebrew/bin", "/usr/bin",
    r"C:\Argyll\bin", r"C:\Program Files\Argyll\bin",
]


def find_argyll() -> str | None:
    """Locate ArgyllCMS's spotread, if it is installed."""
    exe = "spotread.exe" if platform.system() == "Windows" else "spotread"
    found = shutil.which(exe)
    if found:
        return found
    for directory in ARGYLL_SEARCH_DIRS:
        candidate = os.path.join(directory, exe)
        if os.path.exists(candidate):
            return candidate
    return None


def argyll_port_list(spotread: str) -> str:
    """Ask Argyll which instrument ports it can see.

    `-?` only prints usage and the detected port list. It does not open,
    calibrate or measure anything.
    """
    out = run([spotread, "-?"], timeout=30)
    lines, keep = [], False
    for line in out.splitlines():
        if re.search(r"-c\s+listno", line):
            keep = True
            continue
        if keep:
            # The list is the indented "N = 'name'" block; stop at the next flag.
            if re.match(r"\s*\d+\s*=", line):
                lines.append(line.strip())
                continue
            if line.strip().startswith("-"):
                break
    return "\n".join(lines) if lines else "[Argyll listed no instrument ports]"


# --------------------------------------------------------------------------
# transport — how a driver would have to talk to the device
# --------------------------------------------------------------------------

# USB interface class codes. Which one an instrument uses decides the whole
# shape of a driver, so it is worth stating in plain words rather than
# leaving a reader to look up numbers.
USB_CLASSES = {
    2: ("CDC / communications", "presents itself as a serial port — usually the "
                                "easiest kind to talk to"),
    3: ("HID", "talks in fixed-size HID reports; no special driver needed to "
               "open it, but the protocol is still the vendor's own"),
    7: ("printer", "printer class"),
    8: ("mass storage", "storage class — probably not the measuring part"),
    9: ("hub", "a USB hub, not the instrument itself"),
    10: ("CDC data", "the data half of a serial-style device"),
    255: ("vendor-specific", "raw bulk endpoints with a private protocol — this "
                             "is what the i1Pro and most serious instruments "
                             "use, and it means the protocol must be learned "
                             "from observed traffic"),
}


def interpret_transport(dump: str) -> str:
    """Summarise the USB interface classes present, in plain language."""
    classes = [int(v) for v in re.findall(r'"bInterfaceClass"\s*=\s*(\d+)', dump)]
    endpoints = re.findall(r'"bNumEndpoints"\s*=\s*(\d+)', dump)
    if not classes:
        return ("No USB interface descriptors were readable on this system, so "
                "the transport could not be determined from here. The full "
                "dumps above still contain everything that was available.")

    lines = ["Interface classes seen on the connected devices:", ""]
    for code in sorted(set(classes)):
        name, meaning = USB_CLASSES.get(code, (f"class {code}", "unrecognised class"))
        lines.append(f"  {code:3d}  {name} — {meaning}")
    if endpoints:
        lines.append("")
        lines.append(f"Endpoint counts reported: {', '.join(sorted(set(endpoints)))}")
    lines.append("")
    lines.append("Note this lists every USB device attached, not only the "
                 "instrument — read it alongside the detection summary.")
    return "\n".join(lines)


def interpret_argyll_ports(port_list: str, candidates: list["Device"]) -> str:
    """Explain what Argyll's port list means — including a silent absence.

    ArgyllCMS skips any USB device it does not recognise when building this
    list (`inst_usb_match(...) == instUnknown` -> `continue`, in every
    platform's usbio backend). So a missing device is not a fault: it is the
    answer. Said plainly here, because someone reading a short list would
    otherwise conclude the tool had failed.
    """
    # Classify what Argyll actually reported, rather than predicting it. A
    # plain serial path is not evidence of a recognised instrument; a named
    # USB entry is.
    usb_entries, serial_entries = [], []
    for line in port_list.splitlines():
        value = line.split("=", 1)[1].strip() if "=" in line else line.strip()
        value = value.strip("'\"")
        if not value:
            continue
        if value.startswith("/dev/") or re.match(r"^COM\d+", value):
            serial_entries.append(value)
        else:
            usb_entries.append(value)

    lines = ["What this list means:", ""]
    lines.append("ArgyllCMS only lists USB instruments it already has a driver")
    lines.append("for — anything it does not recognise is skipped silently.")
    lines.append("Serial ports are listed regardless of what is on the end of")
    lines.append("them, so an instrument behind a USB-to-serial adapter can")
    lines.append("appear as an unnamed port.")
    lines.append("")
    lines.append(f"Argyll named {_plural(len(usb_entries), 'USB instrument', 'USB instruments')}"
                 f" and {_plural(len(serial_entries), 'serial port', 'serial ports')}.")
    lines.append("")

    if not candidates:
        lines.append("No instrument-like USB device was detected here, so there")
        lines.append("is nothing to cross-check.")
        return "\n".join(lines)

    for dev in candidates:
        in_table = dev.ids in ARGYLL_USB_SUPPORTED
        if usb_entries and in_table:
            lines.append(f"  {dev.vid}:{dev.pid} — recognised. Argyll named a USB "
                         f"instrument ({usb_entries[0]}), which matches this "
                         "device being in its supported list.")
        elif usb_entries and not in_table:
            # Argyll on this machine is the authority — it may be newer than
            # the table compiled into this tool.
            lines.append(f"  {dev.vid}:{dev.pid} — not in THIS TOOL's list, but "
                         f"Argyll still named a USB instrument ({usb_entries[0]}).")
            lines.append("      Trust Argyll: your version is probably newer than")
            lines.append("      the table built into this tool, and the device is")
            lines.append("      supported after all.")
        elif in_table:
            lines.append(f"  {dev.vid}:{dev.pid} — expected to be supported, but "
                         "Argyll named no USB instrument. It may be a permissions")
            lines.append("      problem, or the device was busy in other software.")
        else:
            lines.append(f"  {dev.vid}:{dev.pid} — Argyll named no USB instrument, "
                         "and this device is not in its list.")
            lines.append("      That absence is the finding, not an error: it means")
            lines.append("      the device genuinely is not supported yet.")
            if serial_entries:
                lines.append("      Serial ports were listed though — if this device")
                lines.append("      is behind a USB-serial adapter, it may be one of")
                lines.append(f"      them ({', '.join(serial_entries[:3])}).")
    return "\n".join(lines)


def _facts_from_ioreg(dump: str, vid: str, pid: str) -> dict:
    """Per-device facts from an ioreg dump.

    ioreg prints idVendor/idProduct in DECIMAL, so the hex ids have to be
    converted before matching — a detail that silently returns nothing if
    you forget it.
    """
    try:
        want_v, want_p = int(vid, 16), int(pid, 16)
    except ValueError:
        return {}
    facts: dict[str, str] = {}
    for block in re.split(r"\n(?=\s*\+\-o )", dump):
        v = re.search(r'"idVendor"\s*=\s*(\d+)', block)
        p = re.search(r'"idProduct"\s*=\s*(\d+)', block)
        if not v or not p:
            continue
        if int(v.group(1)) != want_v or int(p.group(1)) != want_p:
            continue
        for key, pattern in (
            ("product", r'"USB Product Name"\s*=\s*"([^"]*)"'),
            ("manufacturer", r'"USB Vendor Name"\s*=\s*"([^"]*)"'),
            ("firmware", r'"bcdDevice"\s*=\s*(\d+)'),
            ("device class", r'"bDeviceClass"\s*=\s*(\d+)'),
            ("max packet size", r'"bMaxPacketSize0"\s*=\s*(\d+)'),
            ("USB version", r'"bcdUSB"\s*=\s*(\d+)'),
        ):
            m = re.search(pattern, block)
            if m:
                facts[key] = m.group(1)
        break
    return facts


def _facts_from_lsusb(dump: str, vid: str, pid: str) -> dict:
    """Per-device facts from `lsusb -v`, which prints ids in hex."""
    facts: dict[str, str] = {}
    for block in re.split(r"\n(?=Bus \d+ Device \d+:)", dump):
        if f"{vid}:{pid}" not in block.lower():
            continue
        for key, pattern in (
            ("product", r"iProduct\s+\d+\s+(.+)"),
            ("manufacturer", r"iManufacturer\s+\d+\s+(.+)"),
            ("firmware", r"bcdDevice\s+([\d.]+)"),
            ("device class", r"bDeviceClass\s+(\d+)"),
            ("USB version", r"bcdUSB\s+([\d.]+)"),
        ):
            m = re.search(pattern, block)
            if m:
                facts[key] = m.group(1).strip()
        eps = re.findall(r"bEndpointAddress\s+(0x[0-9a-fA-F]+)\s+EP\s+\d+\s+(\w+)", block)
        if eps:
            facts["endpoints"] = ", ".join(f"{a} {d}" for a, d in eps)
        types = re.findall(r"Transfer Type\s+(\w+)", block)
        if types:
            facts["transfer types"] = ", ".join(sorted(set(types)))
        break
    return facts


def driver_brief(candidates: list["Device"], dumps: str) -> str:
    """The essentials an implementer needs, gathered in one place.

    The full report runs to ~100 KB. Whoever eventually writes a driver
    should not have to mine it for the handful of facts that actually decide
    the work, so they are collected here at the top.
    """
    if not candidates:
        return ("No instrument-like device was detected, so there is nothing "
                "to summarise. If the instrument was plugged in and switched "
                "on, look through the full device list below — it may use an "
                "unexpected chipset.")

    system = platform.system()
    out: list[str] = []
    for dev in candidates:
        if system == "Darwin":
            facts = _facts_from_ioreg(dumps, dev.vid, dev.pid)
        elif system == "Linux":
            facts = _facts_from_lsusb(dumps, dev.vid, dev.pid)
        else:
            facts = {}

        out.append(f"USB {dev.vid}:{dev.pid}   {dev.name or '(unnamed)'}")
        out.append(f"  status        {dev.verdict()}")
        if facts.get("manufacturer"):
            out.append(f"  manufacturer  {facts['manufacturer']}")
        if facts.get("product"):
            out.append(f"  product       {facts['product']}")
        if facts.get("firmware"):
            fw = facts["firmware"]
            # ioreg reports bcdDevice as the decimal of a BCD word, so the low
            # byte must render as HEX: 272 -> 0x0110 -> "1.10", not "1.16".
            if fw.isdigit() and system == "Darwin":
                fw = f"{int(fw) >> 8}.{int(fw) & 0xFF:02x}  (raw {facts['firmware']})"
            out.append(f"  firmware rev  {fw}")
        # bcdUSB is also a decimal-of-BCD on macOS: 272 -> 0x0110 -> "1.10"
        # (low byte as hex, same trap as the firmware revision).
        if facts.get("USB version", "").isdigit() and system == "Darwin":
            u = int(facts["USB version"])
            facts["USB version"] = f"{u >> 8}.{u & 0xFF:02x}"
        for key in ("USB version", "device class", "max packet size",
                    "endpoints", "transfer types"):
            if facts.get(key):
                out.append(f"  {key:<13} {facts[key]}")
        if not facts:
            out.append("  (no per-device descriptor detail could be read on this")
            out.append("   platform — the full dumps below still hold whatever")
            out.append("   the system exposed)")
        out.append("")

    out.append("What is still missing, and why it needs a recording:")
    out.append("")
    out.append("  None of the above says what the BYTES mean. The descriptors")
    out.append("  tell us how to open a channel to the device; only watching")
    out.append("  the manufacturer's own software drive it reveals the commands")
    out.append("  and the replies. That is what the optional advanced step does.")
    return "\n".join(out)


# --------------------------------------------------------------------------
# collectors
# --------------------------------------------------------------------------

def collect_macos() -> str:
    """Collect macOS detail; returns the descriptor dumps for the brief."""
    section("macOS — USB device tree (JSON)",
            run(["system_profiler", "-json", "SPUSBDataType"], timeout=60))
    section("macOS — USB device tree (readable)",
            run(["system_profiler", "SPUSBDataType"], timeout=60))
    section("macOS — ioreg USB tree",
            run(["ioreg", "-p", "IOUSB", "-l", "-w", "0"], timeout=90))
    # The IOUSB plane alone barely reports interface descriptors. These two
    # classes carry what actually matters: device-level ids and bcdDevice,
    # and the per-interface class/subclass/protocol and endpoint counts that
    # say whether a driver would speak HID, serial or raw bulk.
    device_dump = run(["ioreg", "-r", "-c", "IOUSBHostDevice", "-l"], timeout=90)
    interface_dump = run(["ioreg", "-r", "-c", "IOUSBHostInterface", "-l"], timeout=90)
    section("macOS — USB device descriptors", device_dump)
    section("macOS — USB interface descriptors", interface_dump)
    section("How the device would have to be talked to",
            interpret_transport(device_dump + "\n" + interface_dump))
    section("macOS — serial ports present",
            run(["sh", "-c", "ls -l /dev/cu.* /dev/tty.* 2>/dev/null"]))
    for vendor_dir in ("/Library/Application Support/X-Rite",
                       "/Library/Application Support/Datacolor",
                       "/Library/Application Support/Konica Minolta"):
        if os.path.isdir(vendor_dir):
            section(f"macOS — vendor software: {os.path.basename(vendor_dir)}",
                    run(["find", vendor_dir, "-maxdepth", "3"], timeout=60))
    return device_dump + "\n" + interface_dump


def collect_linux() -> str:
    """Collect Linux detail; returns the descriptor dump for the brief."""
    section("Linux — lsusb (all devices)", run(["lsusb"]))
    # The verbose dump is the single most valuable thing on any platform: it
    # contains the interface class and endpoint descriptors, which decide how
    # a driver would have to talk to the device.
    verbose = run(["lsusb", "-v"], timeout=90)
    section("Linux — lsusb -v (full descriptors)", verbose)
    section("How the device would have to be talked to",
            interpret_transport(verbose))
    section("Linux — serial ports present",
            run(["sh", "-c", "ls -l /dev/ttyUSB* /dev/ttyACM* 2>/dev/null"]))
    section("Linux — kernel messages about USB",
            run(["sh", "-c", "dmesg 2>/dev/null | grep -i usb | tail -40"]))
    section("Linux — udev rules for colour instruments",
            run(["sh", "-c",
                 "cat /lib/udev/rules.d/*Argyll* /etc/udev/rules.d/*Argyll* "
                 "/lib/udev/rules.d/*color* 2>/dev/null | head -60"]))
    return verbose


def collect_windows() -> str:
    ps = shutil.which("powershell") or shutil.which("pwsh")
    if not ps:
        section("Windows", "[PowerShell not found]")
        return ""
    section("Windows — all USB devices",
            run([ps, "-NoProfile", "-Command",
                 "Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -like 'USB*' } "
                 "| Select-Object Status,Class,FriendlyName,InstanceId | Format-List"],
                timeout=120))
    section("Windows — device driver details",
            run([ps, "-NoProfile", "-Command",
                 "Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -like 'USB*' } "
                 "| ForEach-Object { $_.InstanceId } "
                 "| ForEach-Object { Get-PnpDeviceProperty -InstanceId $_ "
                 "-KeyName DEVPKEY_Device_DriverDesc,DEVPKEY_Device_Service "
                 "-ErrorAction SilentlyContinue } | Format-List"], timeout=120))
    section("Windows — serial ports present",
            run([ps, "-NoProfile", "-Command",
                 "[System.IO.Ports.SerialPort]::GetPortNames()"]))
    # Windows exposes little raw descriptor detail without extra tools; the
    # brief falls back to what the detection summary already knows.
    return ""


# --------------------------------------------------------------------------
# the question that decides how hard support would be
# --------------------------------------------------------------------------

REPEATABILITY_EXPLAINER = """\
  Why this matters, in one paragraph:

  Measuring instruments come in two very different kinds, and which kind
  yours is decides whether supporting it is a weekend of work or a research
  project.

    * Some do the colour maths inside the device and hand the computer
      finished numbers. ArgyllCMS's driver for such an instrument is around
      1,400 lines. Very achievable.

    * Others send raw sensor readings and expect the computer to do
      everything — wavelength calibration, stray light, lamp and temperature
      compensation. ArgyllCMS's i1Pro driver is over 13,000 lines and took
      years. Much harder.

  Measuring the SAME patch several times tells us which kind yours is. If the
  device returns identical numbers each time, it is doing the work itself. If
  the numbers wobble, we are seeing raw sensor data."""


DEVICE_CLASSES = {
    "1": ("handheld spot", [
        ("Connect", "Plug in the instrument and start its software. Nothing else yet."),
        ("Idle", "Leave everything untouched for about 10 seconds."),
        ("Calibrate", "Do the white-tile calibration the software asks for."),
        ("Measure white", "Measure the white calibration tile or plain white paper."),
        ("Measure black", "Measure the darkest thing you have to hand."),
        ("Same patch #1", "Measure one ordinary colour patch. Note the reading."),
        ("Same patch #2", "Measure the SAME patch again, without moving it."),
        ("Same patch #3", "Measure that SAME patch a third time."),
        ("Finish", "Close the measurement window or disconnect in the software."),
    ]),
    "2": ("handheld strip / chart reader", [
        ("Connect", "Plug in the instrument and start its software. Nothing else yet."),
        ("Idle", "Leave everything untouched for about 10 seconds."),
        ("Calibrate", "Do the white-tile calibration the software asks for."),
        ("Single spot", "If it can measure one spot, do that once."),
        ("Strip scan #1", "Scan ONE strip or row of a chart."),
        ("Strip scan #2", "Scan the SAME strip again, the same way."),
        ("Finish", "Close the measurement window or disconnect in the software."),
    ]),
    "3": ("automated table / sheet-fed reader", [
        ("Connect", "Power it on, start the software, let it find the device."),
        ("Idle", "Leave everything untouched for about 10 seconds."),
        ("Calibrate", "Let it calibrate, if it asks."),
        ("Position", "Do whatever positioning or alignment the software asks for."),
        ("Read a little", "Let it read one row or feed one sheet, then stop it."),
        ("Finish", "Let it finish or cancel, and wait until it has parked."),
    ]),
    "4": ("display colorimeter", [
        ("Connect", "Plug it in and start its software. Nothing else yet."),
        ("Idle", "Leave everything untouched for about 10 seconds."),
        ("Measure white", "Let it measure a white screen."),
        ("Measure black", "Let it measure a black screen."),
        ("Same colour #1", "Measure one fixed screen colour."),
        ("Same colour #2", "Measure that SAME screen colour again."),
        ("Finish", "Close the software's measurement window."),
    ]),
}


def choose_device_class() -> tuple[str, list[tuple[str, str]]]:
    print("\n  What kind of instrument is it?\n")
    print("    1. Handheld, measures one spot at a time")
    print("    2. Handheld, can be dragged along a strip of patches")
    print("    3. Automated table or sheet-fed chart reader")
    print("    4. Display/monitor colorimeter (the puck kind)")
    print()
    choice = ask("  Type 1, 2, 3 or 4 (Enter for 1): ") or "1"
    if choice not in DEVICE_CLASSES:
        choice = "1"
    name, steps = DEVICE_CLASSES[choice]
    print(f"\n  Right — treating it as: {name}.\n")
    return name, steps


# --------------------------------------------------------------------------
# macOS capture helper
# --------------------------------------------------------------------------
#
# Nothing is bundled and nothing is installed. Wireshark's ChmodBPF helper is
# a root LaunchDaemon, and its only purpose is letting Wireshark capture
# WITHOUT root; capturing WITH sudo needs no daemon, and macOS already ships
# tcpdump. The user only needs Wireshark to *read* a capture, and they don't
# have to — we do.
#
# Interface names must be discovered: every document says "XHC20", but a
# current Apple-Silicon Mac has XHC0/XHC1/XHC2.

CAPTURE_SCRIPT_NAME = "start-usb-capture.command"
_USB_IFACE_RE = re.compile(r"^(?:XHC|VHC|usb)\w*$", re.IGNORECASE)


def macos_usb_capture_interfaces() -> list[str]:
    """Discover macOS's USB capture pseudo-interfaces. Read-only."""
    out = run(["ifconfig", "-l"], timeout=10)
    if not out or out.startswith("["):
        return []
    return [n for n in out.split() if _USB_IFACE_RE.match(n)]


def macos_capture_script(interfaces: list[str], outdir: str) -> str:
    """A readable capture script the user runs themselves.

    Deliberately a separate file rather than something this tool executes:
    the privileged part stays visible and opt-in, and this program keeps its
    "changes nothing" guarantee.
    """
    iface_list = " ".join(shlex.quote(i) for i in interfaces)
    return f"""#!/bin/bash
# ChromIQ — macOS USB capture helper
# Generated by the ChromIQ instrument probe.
#
# WHAT THIS DOES
#   Records the USB traffic between this Mac and your measuring instrument
#   while you use the manufacturer's own software, so ChromIQ can learn how
#   the device is driven.
#
# WHAT IT DOES NOT DO
#   It never sends anything to the instrument -- it only listens. It installs
#   NOTHING: `ifconfig` and `tcpdump` are both part of macOS already. No
#   Wireshark, no ChmodBPF, no drivers.
#
# WHY IT ASKS FOR YOUR PASSWORD
#   Listening to raw USB traffic is privileged on macOS. The password goes to
#   macOS's own `sudo`, never to this script.
#
# TO UNDO EVERYTHING: nothing to undo. Any capture interface this script
# switches on is switched off again when it finishes.

set -u

OUTDIR={shlex.quote(outdir)}
INTERFACES=({iface_list})

BROUGHT_UP=()
STARTED=()
KEEPALIVE=""
STAMP=""

# macOS ships bash 3.2, where "${{ARR[@]}}" on an EMPTY array aborts the script
# under `set -u`. Every loop over a possibly-empty array is therefore guarded
# by a count check -- this is not redundant, it is load-bearing.
restore_interfaces() {{
    if [ "${{#BROUGHT_UP[@]}}" -gt 0 ]; then
        for IF in "${{BROUGHT_UP[@]}}"; do
            sudo ifconfig "$IF" down 2>/dev/null
        done
    fi
}}

# NOTE: SIGTERM, not SIGINT. A command started with `&` from a non-interactive
# shell inherits SIGINT as *ignored*, so `pkill -INT` reports success and does
# nothing at all -- verified on macOS. That would leave root tcpdumps running
# and produce an unusable capture.
stop_capture() {{
    if [ "${{#STARTED[@]}}" -gt 0 ]; then
        for IF in "${{STARTED[@]}}"; do
            sudo pkill -TERM -f "tcpdump -U -i $IF -w io-capture-$STAMP-$IF.pcap" 2>/dev/null
        done
    fi
}}

# Closing the window must not leave root tcpdumps running or interfaces up.
cleanup() {{
    stop_capture
    [ -n "$KEEPALIVE" ] && kill "$KEEPALIVE" 2>/dev/null
    restore_interfaces
}}
trap cleanup EXIT

cd "$OUTDIR" || {{ echo "Cannot enter $OUTDIR"; exit 1; }}

echo "======================================================================"
echo "  ChromIQ — USB capture for a measuring instrument"
echo "======================================================================"
echo
echo "  Recording to: $OUTDIR"
echo "  Interfaces:   ${{INTERFACES[*]}}"
echo
echo "  This only listens. It cannot operate the instrument."
echo
echo "  macOS needs your administrator password to listen to USB traffic."
echo

if ! sudo -v; then
    echo
    echo "  Could not get administrator rights, so capturing is not possible."
    echo "  That is fine -- the main report on its own is still useful."
    exit 1
fi

# The walkthrough takes several minutes; sudo's grace period is 5.
( while true; do sudo -n true 2>/dev/null; sleep 50; done ) &
KEEPALIVE=$!
disown "$KEEPALIVE" 2>/dev/null || true

ACTIVE=()
for IF in "${{INTERFACES[@]}}"; do
    if ! ifconfig "$IF" >/dev/null 2>&1; then
        echo "  - $IF: not present, skipping"
        continue
    fi
    if ifconfig "$IF" 2>/dev/null | head -1 | grep -qE '[<,]UP[,>]'; then
        ACTIVE+=("$IF")
    elif sudo ifconfig "$IF" up 2>/dev/null; then
        BROUGHT_UP+=("$IF")
        ACTIVE+=("$IF")
    else
        echo "  - $IF: could not be switched on, skipping"
    fi
done

if [ "${{#ACTIVE[@]}}" -eq 0 ]; then
    echo
    echo "  No USB capture interfaces could be started on this Mac. This"
    echo "  happens on some models. Please skip the capture -- or, if you have"
    echo "  a Linux or Windows machine, it is easier there and the data is"
    echo "  identical."
    exit 1
fi

# One tcpdump per interface: we cannot know which USB bus the instrument is
# on, and capturing them all is cheaper than making the user guess.
STAMP=$(date +%Y%m%d-%H%M%S)
for IF in "${{ACTIVE[@]}}"; do
    OUT="io-capture-$STAMP-$IF.pcap"
    # -U writes each packet straight out, so an abrupt end still leaves a
    # readable file rather than an empty one.
    sudo tcpdump -U -i "$IF" -w "$OUT" >/dev/null 2>"tcpdump-$IF.log" &
    disown $! 2>/dev/null || true
    STARTED+=("$IF")
done

sleep 2

LIVE=0
for IF in "${{STARTED[@]}}"; do
    if pgrep -f "tcpdump -U -i $IF -w io-capture-$STAMP-$IF.pcap" >/dev/null 2>&1; then
        echo "  - $IF: recording"
        LIVE=$((LIVE + 1))
    else
        echo "  - $IF: FAILED to start —"
        sed 's/^/        /' "tcpdump-$IF.log" 2>/dev/null | head -5
    fi
done

if [ "$LIVE" -eq 0 ]; then
    echo
    echo "  Nothing could be recorded on this Mac. Please skip the capture"
    echo "  step -- the main report is still genuinely useful on its own."
    exit 1
fi

echo
echo "======================================================================"
echo "  RECORDING. Leave this window open."
echo "======================================================================"
echo
echo "  Now switch to the ChromIQ probe window and work through the steps."
echo
read -r -p "  When you have finished all the steps, press Enter here... " _

echo
echo "  Stopping..."
stop_capture
sleep 2

# tcpdump wrote these as root; hand them back so they can be attached.
sudo chown "$(id -u):$(id -g)" io-capture-"$STAMP"-*.pcap 2>/dev/null

restore_interfaces

echo
echo "======================================================================"
echo "  DONE — here is what was recorded"
echo "======================================================================"
echo
ls -lh io-capture-"$STAMP"-*.pcap 2>/dev/null | sed 's/^/  /'
echo
echo "  A file of only a few hundred bytes means nothing was captured on that"
echo "  bus -- normal for the buses your instrument is not plugged into. If"
echo "  ALL of them are tiny, capture did not work on this Mac; just send the"
echo "  main report instead."
echo
echo "  Please attach the largest .pcap file AND the probe report to the"
echo "  ChromIQ issue you are helping with."
echo
read -r -p "  Press Enter to close. " _
"""


CAPTURE_HELP = {
    "Linux": """\
  1. sudo modprobe usbmon
  2. Find the bus number of your instrument in the 'lsusb' output above.
  3. In a second terminal:  sudo tcpdump -i usbmon<BUS> -w capture.pcap
  4. Come back here and follow the prompts.
  5. Stop tcpdump with Ctrl-C when this tool says you are done.""",
    "Windows": """\
  1. Install USBPcap (desowin.org/usbpcap) and Wireshark.
  2. Start Wireshark, choose the USBPcap interface your instrument is on,
     and start the capture.
  3. Come back here and follow the prompts.
  4. Stop and save the capture as capture.pcapng when this tool says so.""",
    "Darwin": """\
  macOS already ships everything needed — no Wireshark, no ChmodBPF.
  Find your USB interfaces with 'ifconfig -l' (the XHC* ones), then:
      sudo ifconfig XHC0 up
      sudo tcpdump -U -i XHC0 -w capture.pcap""",
}


def prepare_macos_capture() -> str:
    """Write the capture script next to the report, return instructions.

    The script must know the folder it lives in, so the directory is chosen
    first and the content built around it.
    """
    interfaces = macos_usb_capture_interfaces()
    if not interfaces:
        return ("""\
  This Mac exposes no USB capture interfaces, so a capture is not possible
  here. Please skip this step — the main report is still useful. (If you have
  a Linux or Windows machine, capturing there is easier and identical.)""")

    script_path = None
    for directory in candidate_dirs():
        if not os.path.isdir(directory):
            continue
        path = os.path.join(directory, CAPTURE_SCRIPT_NAME)
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(macos_capture_script(interfaces, directory))
            os.chmod(path, 0o755)
            script_path = path
            break
        except OSError:
            continue

    if not script_path:
        return CAPTURE_HELP["Darwin"]

    names = ", ".join(interfaces)
    return f"""\
  Good news: nothing needs to be installed. macOS already has everything
  required, and I have written a ready-made script for you:

      {script_path}

  1. Open a NEW Terminal window.
  2. Drag that file into it and press Enter (or double-click it in Finder).
  3. It will ask for your admin password — that is macOS asking, because
     listening to USB traffic is privileged. It only listens and installs
     nothing.
  4. When it says RECORDING, come back here and follow the prompts.

  (For the curious: under sudo it runs `ifconfig <if> up` and `tcpdump -w`
  on this Mac's USB interfaces — {names} — and puts everything back as it
  was when it finishes. You can read the whole script first.)"""


# --------------------------------------------------------------------------
# stage 2 — annotated walkthrough
# --------------------------------------------------------------------------

def annotate_session() -> None:
    system = platform.system()
    print("\n" + hr("="))
    print("STAGE 2 — guided walkthrough with a traffic recording")
    print(hr("="))
    print("\nThis does NOT record anything itself. You start the recording;")
    print("this tool times each step, so the recording can be cut into pieces")
    print("afterwards. That alignment is what makes a capture readable instead")
    print("of an undifferentiated blob.\n")
    print("Set up the recording first:\n")
    if system == "Darwin":
        print(prepare_macos_capture())
    else:
        print(CAPTURE_HELP.get(system, CAPTURE_HELP["Linux"]))

    class_name, steps = choose_device_class()

    print(hr())
    print(f"Next: {len(steps)} short operations in your instrument's own software,")
    print("timed as you go. It takes about 10 minutes and needs the recording")
    print("to be running.")
    print(hr())
    print()
    print(REPEATABILITY_EXPLAINER)

    if ask("\n\nIs the recording running — shall I start the walkthrough? (yes / no): ")\
            .lower() not in ("y", "yes"):
        print("\n  Skipping the walkthrough — that is absolutely fine.")
        print("  Your main report is unaffected and still worth sending.")
        print("  To do it another time, run this tool again with  --annotate .\n")
        section("Stage 2 — guided walkthrough",
                "[skipped by operator — no recording running]")
        return

    t0 = time.time()
    log = [f"device class: {class_name}",
           f"session start: {datetime.datetime.now().isoformat()}"]
    print("\nDo each step in the instrument's software, then press Enter here")
    print("immediately afterwards. If a step is impossible, type 'skip'.\n")

    readings: list[str] = []
    for name, instruction in steps:
        print(f"--- {name} ---")
        print(f"    {instruction}")
        start = time.time() - t0
        answer = ask("    press Enter when finished (or 'skip'): ")
        end = time.time() - t0
        if answer.lower().startswith("s"):
            log.append(f"{name}: SKIPPED")
            print("    skipped\n")
            continue
        # Instructions may wrap on screen; the timeline stays one line per step.
        flat = " ".join(instruction.split())
        log.append(f"{name}: t={start:8.3f}s .. {end:8.3f}s   ({flat})")
        print(f"    recorded {start:.3f}s .. {end:.3f}s")
        if "same" in name.lower():
            value = ask("    what did the software show? (Lab/XYZ/density, Enter to skip): ")
            if value:
                readings.append(f"{name}: {value}")
        print()

    if readings:
        log.append("")
        log.append("repeated measurements of the same patch, as reported on screen:")
        log.extend("  " + r for r in readings)
        section("Repeatability — the key question", "\n".join(readings) + "\n\n"
                "Identical values suggest the instrument does its own colour\n"
                "maths (a driver is realistic). Values that wobble suggest raw\n"
                "sensor data (much harder).")

    notes = ask("Anything odd happen? (free text, Enter to skip): ")
    if notes:
        log.append(f"operator notes: {notes}")
    section("Stage 2 — walkthrough timeline", "\n".join(log))
    print("\nStop the recording now and save the file.")
    print("Send BOTH the recording and this report.\n")


# --------------------------------------------------------------------------
# output
# --------------------------------------------------------------------------

def candidate_dirs() -> list[str]:
    """Folders to save output in, most preferred first."""
    dirs: list[str] = []
    # When frozen by PyInstaller, __file__ points into a temp bundle that is
    # DELETED on exit, so the real executable's folder must be used or the
    # report vanishes the moment the program closes.
    base_dir = None
    if getattr(sys, "frozen", False):
        base_dir = os.path.dirname(os.path.abspath(sys.executable))
    else:
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        except Exception:                                 # noqa: BLE001
            base_dir = None
    if base_dir:
        dirs.append(base_dir)
    home = os.path.expanduser("~")
    dirs.append(os.path.join(home, "Desktop"))
    dirs.append(home)
    dirs.append(tempfile.gettempdir())
    return dirs


def write_report(report: str, explicit: str | None) -> str | None:
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    name = f"chromiq-instrument-probe-{stamp}.txt"
    candidates = ([explicit] if explicit
                  else [os.path.join(d, name) for d in candidate_dirs()])
    for path in candidates:
        try:
            parent = os.path.dirname(path) or "."
            if not os.path.isdir(parent):
                continue
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(report)
            return path
        except OSError:
            continue
    return None


# --------------------------------------------------------------------------
# capture analysis — turn a raw .pcap into a plain verdict + command timeline
#
# The "analysis half" of the workflow. It NEVER touches a device; it only reads
# a capture file the user already made. It is deliberately DEVICE-AGNOSTIC — it
# assumes no vendor opcodes, because the whole purpose is unknown instruments.
# It reports the raw USB command structure (control setups + bulk volume) so an
# implementer can see what the device's own software said to it, and so the
# person who made the capture can confirm it actually holds traffic before they
# send a multi-megabyte file for nothing.
#
# Only the macOS (Darwin) format is decoded in detail — it is the only one
# validated against real hardware (a ColorMunki via ChromIQ, matched byte-for-
# byte to Argyll's munki driver). Linux (usbmon) and Windows (USBPcap) captures
# are still reported as valid with counts, plus an honest "timeline not decoded
# on this platform yet"; the file itself is complete and worth sending.
# --------------------------------------------------------------------------

LINKTYPE_USB_LINUX = 189
LINKTYPE_USB_LINUX_MMAPPED = 220
LINKTYPE_USBPCAP = 249
LINKTYPE_USB_DARWIN = 266

_LINKTYPE_NAMES = {
    LINKTYPE_USB_LINUX: "Linux usbmon",
    LINKTYPE_USB_LINUX_MMAPPED: "Linux usbmon",
    LINKTYPE_USBPCAP: "Windows USBPcap",
    LINKTYPE_USB_DARWIN: "macOS (Darwin USB)",
}

# Darwin USB header layout (40 bytes), reverse-engineered from real captures and
# confirmed against Argyll's munki driver:
#   [2]       header length (0x28 = 40)
#   [3]       0 = submit (host->device), 1 = complete (device->host)
#   [4:8]     data length, little-endian
#   [0x10:14] URB sequence id (a submit and its completion share it)
#   [0x24:26] idVendor LE   [0x26:28] idProduct LE
#   [40:]     payload; for a control submit this begins with the 8-byte setup
_DARWIN_HDR = 40


def _read_pcap(path):
    """Return (linktype, [(ts, data), ...]). Raise ValueError if not a pcap."""
    with open(path, "rb") as fh:
        blob = fh.read()
    if len(blob) < 24:
        raise ValueError("file too short to be a capture")
    magic = blob[:4]
    if magic in (b"\xd4\xc3\xb2\xa1", b"\x4d\x3c\xb2\xa1"):
        endian = "<"
    elif magic in (b"\xa1\xb2\xc3\xd4", b"\xa1\xb2\x3c\x4d"):
        endian = ">"
    else:
        raise ValueError("not a pcap file")
    nano = magic in (b"\x4d\x3c\xb2\xa1", b"\xa1\xb2\x3c\x4d")
    linktype = struct.unpack(endian + "I", blob[20:24])[0]
    off, recs = 24, []
    while off + 16 <= len(blob):
        ts_s, ts_u, incl, _orig = struct.unpack(endian + "IIII", blob[off:off + 16])
        off += 16
        if incl > len(blob) - off:                 # truncated final record
            break
        recs.append((ts_s + ts_u / (1e9 if nano else 1e6), blob[off:off + incl]))
        off += incl
    return linktype, recs


def _fmt_ascii(data):
    return "".join(chr(b) if 32 <= b < 127 else "." for b in data)


def _analyze_darwin(recs):
    """Device-agnostic summary: (devices, cmd_counts, timeline, bulk_bytes)."""
    submits = {}                            # seq -> (bRequest, dir_in, wLen, ts)
    cmd_counts = {}                         # bRequest -> count
    devices = {}                            # (vid, pid) -> packet count
    timeline = []
    bulk_bytes = 0
    t0 = recs[0][0] if recs else 0.0
    for ts, data in recs:
        if len(data) < _DARWIN_HDR:
            continue
        direction = data[3]                 # 0 submit, 1 complete
        dlen = struct.unpack("<I", data[4:8])[0]
        seq = struct.unpack("<I", data[0x10:0x14])[0]
        vid = struct.unpack("<H", data[0x24:0x26])[0]
        pid = struct.unpack("<H", data[0x26:0x28])[0]
        if vid or pid:
            devices[(vid, pid)] = devices.get((vid, pid), 0) + 1
        payload = data[_DARWIN_HDR:]
        # A control submit begins with an 8-byte setup packet. Validate both the
        # bmRequestType field (type 0..2 = std/class/vendor, recipient 0..3) AND
        # the USB length invariant — the payload is exactly the 8-byte setup (IN,
        # data returns in the completion) or setup + wLength outbound bytes (OUT).
        # This rejects bulk transfers whose first byte merely looks like a setup.
        # Neither check assumes any specific vendor opcode.
        if (direction == 0 and len(payload) >= 8
                and ((payload[0] >> 5) & 3) <= 2 and (payload[0] & 0x1f) <= 3):
            wlen = struct.unpack("<H", payload[6:8])[0]
            if len(payload) in (8, 8 + wlen):
                breq = payload[1]
                dir_in = bool(payload[0] & 0x80)
                submits[seq] = (breq, dir_in, wlen, ts)
                cmd_counts[breq] = cmd_counts.get(breq, 0) + 1
        elif direction == 1:
            info = submits.get(seq)
            if info:
                if len(timeline) < 30:
                    breq, dir_in, wlen, tsub = info
                    resp = payload[:dlen] if dlen else payload
                    timeline.append((tsub - t0, breq, dir_in, wlen, resp[:16]))
            elif dlen >= 64:                # completion with no control setup
                bulk_bytes += dlen          # = streamed bulk (e.g. sensor data)
    return devices, cmd_counts, timeline, bulk_bytes


def find_captures():
    """Newest io-capture-*.pcap set sitting next to the tool (or Desktop)."""
    for directory in candidate_dirs():
        hits = glob.glob(os.path.join(directory, "io-capture-*.pcap"))
        if hits:
            newest = max(os.path.getmtime(h) for h in hits)
            recent = [h for h in hits if newest - os.path.getmtime(h) < 60]
            return sorted(recent) or sorted(hits)
    return []


def summarize_captures(paths):
    """Plain-language verdict + command timeline for one or more captures."""
    out = ["=" * 68, "  USB capture check", "=" * 68, "",
           "  Reads capture files you already made — it sends NOTHING to any",
           "  device. It confirms a capture really holds instrument traffic",
           "  before you send it, and prints the command timeline.", ""]
    any_real = False
    for path in paths:
        out.append("  " + os.path.basename(path))
        try:
            linktype, recs = _read_pcap(path)
        except (OSError, ValueError) as exc:
            out += [f"     not a readable capture: {exc}", ""]
            continue
        name = _LINKTYPE_NAMES.get(linktype, f"linktype {linktype}")
        total = sum(len(d) for _, d in recs)
        out.append(f"     format: {name}   packets: {len(recs)}   bytes: {total:,}")
        if linktype != LINKTYPE_USB_DARWIN:
            if recs:
                out += ["     Valid capture. A detailed timeline is decoded for macOS",
                        "     captures for now; this file is complete — send it in."]
                any_real = any_real or total > 4096
            else:
                out.append("     Empty — nothing was recorded on this bus.")
            out.append("")
            continue
        devices, cmds, timeline, bulk = _analyze_darwin(recs)
        if devices:
            devstr = ", ".join(f"{v:04x}:{p:04x}" for v, p in
                               sorted(devices, key=lambda k: -devices[k]))
            out.append(f"     device(s) on this bus: {devstr}")
        n_cmd = sum(cmds.values())
        out.append(f"     control commands: {n_cmd}   distinct opcodes: "
                   f"{len(cmds)}   bulk data: {bulk:,} bytes")
        real = bool(devices) and (n_cmd > 0 or bulk > 2048)
        any_real = any_real or real
        if timeline:
            out.append("     timeline (device-agnostic — no opcode is assumed):")
            for tsec, breq, dir_in, wlen, resp in timeline:
                out.append(f"        {tsec:7.3f}s  req=0x{breq:02X} "
                           f"{'IN ' if dir_in else 'OUT'} wLen={wlen:<4} -> "
                           f"{resp.hex(' ')}  |{_fmt_ascii(resp)}|")
        out.append("     VERDICT: " + (
            "OK — real device traffic captured. Good to send."
            if real else
            "little/no device traffic — wrong bus, or no measurement was taken."))
        out.append("")
    out.append("-" * 68)
    out.append("  Overall: " + (
        "at least one file holds real instrument traffic."
        if any_real else
        "no clear instrument traffic found in any file."))
    if not any_real:
        out.append("  Re-run the capture and TAKE A MEASUREMENT while it records.")
    out.append("=" * 68)
    return "\n".join(out)


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main() -> int:
    global REDACT

    parser = argparse.ArgumentParser(
        description="Collect information about a colour measuring instrument "
                    "for ChromIQ. Never sends anything to the device.")
    parser.add_argument("--annotate", action="store_true",
                        help="go straight to the guided walkthrough (stage 2)")
    parser.add_argument("--skip-annotate", action="store_true",
                        help="never offer the guided walkthrough")
    parser.add_argument("--no-redact", action="store_true",
                        help="keep serial numbers and paths as-is")
    parser.add_argument("--capture-setup", action="store_true",
                        help="(macOS) just write the USB capture script and exit")
    parser.add_argument("--analyze", nargs="*", default=None, metavar="PCAP",
                        help="read a USB capture (.pcap) and print a plain "
                             "verdict + command timeline; with no path, finds "
                             "the newest capture next to the tool")
    parser.add_argument("-o", "--output", default=None, help="output file path")
    args = parser.parse_args()
    REDACT = not args.no_redact

    if args.capture_setup:
        if platform.system() != "Darwin":
            print("--capture-setup is macOS-only; see the README for Linux "
                  "(usbmon) and Windows (USBPcap).")
            return 1
        print(prepare_macos_capture())
        return 0

    if args.analyze is not None:
        paths = args.analyze or find_captures()
        if not paths:
            print("No capture file given or found next to the tool.\n"
                  "Make one first with --capture-setup, or pass a path:\n"
                  "    --analyze path/to/capture.pcap")
            return 1
        print(summarize_captures(paths))
        return 0

    print(hr("="))
    print("  ChromIQ — colour instrument probe")
    print(hr("="))
    print()
    print("  This only READS information your computer already has about")
    print("  connected hardware. It never sends anything to your instrument")
    print("  and cannot operate it. It is safe to run at any time.")
    print()
    print(hr())
    print("STEP 1 of 3 — looking for measuring instruments")
    print(hr())
    print()

    devices = discover_devices()
    enumeration_failed = devices is None
    devices = devices or []
    candidates = [d for d in devices if d.is_candidate()]

    lines = []
    if enumeration_failed:
        lines.append("Could not enumerate USB devices on this system — the")
        lines.append("tool that lists them is missing or refused to run.")
        lines.append("The rest of the report is still worth sending.")
    elif not devices:
        lines.append("NO USB DEVICES ARE CONNECTED.")
        lines.append("")
        lines.append("Please plug your instrument in, switch it on, and run")
        lines.append("this again — right now there is nothing to look at.")
    elif not candidates:
        lines.append(f"{_plural(len(devices), 'USB device', 'USB devices')} found, "
                     "but none of them look like a colour instrument or a "
                     "serial adapter.")
        lines.append("If your instrument is plugged in and switched on, it may")
        lines.append("use an unusual chipset — the full device list in the")
        lines.append("report will still show it.")
    else:
        lines.append(f"{_plural(len(devices), 'USB device', 'USB devices')} found, "
                     f"{len(candidates)} of interest:")
        lines.append("")
        for dev in candidates:
            lines.append(f"  {dev.label()}")
            lines.append(f"      -> {dev.verdict()}")
    summary = "\n".join(lines)
    print("  " + summary.replace("\n", "\n  ") + "\n")

    section("Detection summary", summary)
    section("All USB devices seen",
            "\n".join(f"{d.vid}:{d.pid}  {d.name}" for d in devices)
            or "[none enumerated]")

    section("Environment", json.dumps({
        "probe_version": PROBE_VERSION,
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "platform": platform.platform(),
        "system": platform.system(),
        "machine": platform.machine(),
        "python": sys.version.split()[0],
        "redacted": REDACT,
    }, indent=2))

    print(hr())
    print("STEP 2 of 3 — collecting the details")
    print(hr())
    print("\n  Please wait, this takes a few seconds...\n")

    system = platform.system()
    if system == "Darwin":
        dumps = collect_macos()
    elif system == "Linux":
        dumps = collect_linux()
    elif system == "Windows":
        dumps = collect_windows()
    else:
        section("Unsupported OS", f"[{system}]")
        dumps = ""

    # The one section a driver author reads first. Inserted near the top of
    # the report (position 2), not appended after 100 KB of raw dumps.
    _SECTIONS.insert(2, ("DRIVER BRIEF — the essentials for adding support",
                         scrub(driver_brief(candidates, dumps))))

    # Asking ArgyllCMS what it recognises is the most direct answer available
    # to "is this already supported?".
    spotread = find_argyll()
    if spotread:
        ports = argyll_port_list(spotread)
        section("ArgyllCMS — installed at", spotread)
        section("ArgyllCMS — instrument ports it detects", ports)
        section("ArgyllCMS — how to read that list",
                interpret_argyll_ports(ports, candidates))
        print("  ArgyllCMS found — asked it which instruments it can see.\n")
    else:
        section("ArgyllCMS",
                "[not installed, or not in the usual places]\n\n"
                "Installing ArgyllCMS and re-running would add a useful\n"
                "cross-check, but it is not required.")

    print(hr())
    print("STEP 3 of 3 — three quick questions")
    print(hr())
    print("\n  Just press Enter to skip any of them.\n")
    answers = {
        "make and model of the instrument":
            ask("  1. What make and model is it?\n     > "),
        "software normally used with it":
            ask("  2. Which software do you normally use it with?\n     > "),
        "what it is used for":
            ask("  3. What do you measure with it (prints, screens, fabric…)?\n     > "),
    }
    section("Operator answers",
            "\n".join(f"{q}\n    {a or '[no answer]'}" for q, a in answers.items()))

    if args.annotate:
        annotate_session()
    elif not args.skip_annotate:
        print("\n" + hr())
        print("OPTIONAL EXTRA — only if you have time")
        print(hr())
        print()
        print("  There is a second, more advanced step that records what your")
        print("  instrument's own software says to it. That recording is the")
        print("  one thing that could make support possible, but it takes")
        print("  about 10 more minutes.")
        print()
        print("  You do NOT need to do this. The report you already have is a")
        print("  genuinely useful contribution on its own.")
        print()
        if ask("  Try the advanced step too? (yes / no): ").lower().startswith("y"):
            annotate_session()
        else:
            print("\n  No problem at all — skipping it.\n")

    body = [
        "ChromIQ instrument probe report",
        f"probe version {PROBE_VERSION}",
        f"Redaction: {'ON (serials hashed, paths stripped)' if REDACT else 'OFF'}",
        "",
    ]
    for title, content in _SECTIONS:
        body.append("=" * 72)
        body.append(title)
        body.append("=" * 72)
        body.append(content)
        body.append("")
    report = "\n".join(body)

    out_path = write_report(report, args.output)
    if not out_path:
        print("\n  Could not write the report anywhere. Printing it instead:\n")
        print(report)
        return 1

    size_kb = os.path.getsize(out_path) / 1024.0
    print("\n" + hr("="))
    print("  ALL DONE — thank you!")
    print(hr("="))
    print()
    print("  Your report was saved here:")
    print()
    print(f"      {out_path}")
    print()
    print(f"  It is a plain text file ({size_kb:.0f} KB). Please open it and")
    print("  have a look first — you can see exactly what is being shared,")
    print("  and delete anything you are not comfortable with.")
    print()
    print("  Then attach it to the ChromIQ issue you are helping with:")
    print("      https://github.com/itsab1989/ChromIQ/issues")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())

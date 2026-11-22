"""--check ZIP: show the owner what he is about to send, and look for mistakes.

It does not trust the filter that made the zip (review M1). It:
  * searches every file of the zip for the identifiers it knows: this
    computer's names, and, when the session folder is next to the zip, the
    REAL serial numbers, addresses and --hide texts kept there (in any case,
    as ASCII, UTF-8, UTF-16LE and UTF-16BE, IP addresses also as 4 bytes);
  * lists every distinct device (USB) or host (network) that appears in the
    recordings, and calls it a problem when one is not the chosen instrument
    or this computer;
  * filters every recording again with the instrument from the manifest;
  * lists ALL readable text inside the recordings (4 characters or more with a
    letter, ASCII and UTF-16): the first 200 on screen, every one of them in a
    file next to the zip, so the owner can read it all.
What it cannot see is said in the README: an identifier it has never been told
and that does not appear in a standard field, or a name split across two
network messages.
Exit code 0 when nothing was found, 3 when something was.
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import zipfile

from . import capture, net, privacy, usb
from .package import filter_capture, transport_of

_PLACEHOLDER_NETS = privacy.PLACEHOLDER_NETS
SHOW = 200


def _strings(blob: bytes) -> set:
    found = set()
    for m in re.finditer(rb"[ -~]{4,}", blob):
        t = m.group(0).decode("ascii")
        if re.search(r"[A-Za-z]", t):
            found.add(t)
    for m in re.finditer(rb"(?:[ -~]\x00){4,}", blob):
        t = m.group(0).decode("utf-16-le")
        if re.search(r"[A-Za-z]", t):
            found.add(t)
    return found


def _forms(value: str):
    out = set()
    for v in {value, value.lower(), value.upper()}:
        for enc in ("utf-8", "utf-16-le", "utf-16-be"):
            try:
                out.add(v.encode(enc))
            except UnicodeEncodeError:
                pass
    return out


def local_secrets(zip_path: str, manifest: dict) -> dict:
    """The real identifiers kept in the session folder next to the zip
    (never in the zip itself): {kind: [values]}."""
    stamp = manifest.get("stamp")
    if not stamp:
        return {}
    folder = os.path.join(os.path.dirname(os.path.abspath(zip_path)), f"probe-session-{stamp}")
    try:
        with open(os.path.join(folder, "session.json"), encoding="utf-8") as fh:
            st = json.load(fh)
    except (OSError, ValueError):
        return {}
    sel = st.get("selection", {})
    serials = {d.get("serial") for d in usb.chosen_devices(sel)} if sel.get("transport") == "usb" \
        else set()
    for b in st.get("blocks", []):
        serials |= set(b.get("check", {}).get("serials", []))
    keep_serial = bool(st.get("keep_serial"))
    return {"serial number": sorted(x for x in serials if x and len(x) >= 3 and not keep_serial),
            "hidden text": [h for h in st.get("hide", []) if h],
            "address": sorted(set(sel.get("ips", []) + sel.get("gateways", [])
                                  + st.get("confirmed_ips", []))),
            "network card": sorted(sel.get("macs", []))}


def _census(name: str, cap, sel: dict, problems: list, notes: list,
            warnings: list = None) -> list:
    """Every distinct device or host in one recording."""
    rows = []
    warnings = [] if warnings is None else warnings
    if transport_of(cap.linktype) == "usb":
        chosen = {(d["vid"], d["pid"]) for d in usb.chosen_devices(sel)}
        seen = {}
        for ev in usb.usb_events(cap.linktype, cap.records):
            if ev["kind"] == "control" and ev["rt"] == 0x80 and ev["req"] == 6 and \
                    (ev["wValue"] >> 8) == 1:
                d = usb.parse_device_descriptor(ev["in"])
                if d:
                    seen.setdefault(ev["key"], set()).add((d["vid"], d["pid"]))
        keys = set()
        for _ts, d in cap.records:
            info = usb.record_info(cap.linktype, d)
            if info:
                keys.add(info[0])
        keyish = {}
        for _ts, d in cap.records:
            info = usb.record_info(cap.linktype, d)
            if info and info[2] == 1 and info[1] & 0x80 and usb._looks_like_key_report(info[3]):
                keyish[info[0]] = keyish.get(info[0], 0) + 1
        for k in sorted(keys, key=str):
            ids = seen.get(k) or ({(k[1], k[2])} if k and k[0] == "mac" else set())
            label = ", ".join(f"{v:04x}:{p:04x}" for v, p in sorted(ids)) or "no description"
            if not ids:
                warnings.append(f"{name}: records at USB address {k} were kept WITHOUT a USB "
                                "description of the device there.")
            if keyish.get(k):
                problems.append(f"{name}: {keyish[k]} records at USB address {k} look like a "
                                "keyboard's typed keys.")
            rows.append(f"USB device at {k}: {label}")
            if ids and not ids <= chosen:
                problems.append(f"{name}: holds a USB device that is not your instrument "
                                f"({label}).")
        if len(keys) > max(1, len(chosen)):
            notes.append(f"{name}: your instrument appears at {len(keys)} USB addresses (normal "
                         "after unplugging it; check that each is really yours).")
        return rows
    hosts = {}
    for _ts, d in cap.records:
        f = net.parse_frame(cap.linktype, d)
        ip = net.parse_ip(d, f.l3) if f and f.ethertype in (0x0800, 0x86DD) else None
        for a in (ip[1], ip[2]) if ip else ():
            hosts[a] = hosts.get(a, 0) + 1
    unicast = []
    for a, n in sorted(hosts.items(), key=lambda x: str(x[0])):
        special = a.is_multicast or a.is_unspecified or a.is_loopback or \
            str(a) == "255.255.255.255" or (a.version == 4 and a.packed[3] == 255)
        role = "the instrument" if a in privacy.DEVICE_NET else \
            "a multicast or broadcast address" if special else "this computer, or another host"
        rows.append(f"host {a}: {n} packets ({role})")
        if not special and not any(a in nw for nw in _PLACEHOLDER_NETS):
            problems.append(f"{name}: a real network address is still in it.")
        if not special and a not in privacy.DEVICE_NET:
            unicast.append(a)
    if len(unicast) > 1:
        problems.append(f"{name}: {len(unicast)} hosts besides the instrument talk in it; "
                        "only this computer should.")
    return rows


def check_zip(path: str, ids: dict | None = None, secrets: dict | None = None) -> dict:
    ids = privacy.computer_identifiers() if ids is None else ids
    problems, notes, strings, census, warnings = [], [], set(), [], []
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if "manifest.json" not in names:
            return {"problems": ["This zip has no manifest.json, so it was not made by this "
                                 "tool (or it was changed). Please do not send it."],
                    "notes": [], "strings": [], "names": names, "census": [], "warnings": []}
        manifest = json.loads(z.read("manifest.json"))
        sel = manifest.get("instrument", {})
        secrets = local_secrets(path, manifest) if secrets is None else secrets
        if not secrets:
            notes.append("The session folder was not found next to the zip, so the real "
                         "serial numbers and addresses could not be searched for.")
        needles = []
        for key in ("user", "host", "host_short", "home", "computer_name", "local_host"):
            v = ids.get(key)
            if v and len(v) >= 3:
                needles.append((f"this computer's {key.replace('_short', '').replace('_', ' ')}",
                                v))
        for kind, values in secrets.items():
            for v in values:
                needles.append((kind, v))
        for n in names:
            blob = z.read(n)
            low = blob.lower()
            for kind, v in needles:
                hit = any(f.lower() in low or f in blob for f in _forms(v))
                if kind == "address":
                    try:
                        hit = hit or ipaddress.ip_address(v).packed in blob
                    except ValueError:
                        pass
                if kind == "network card":
                    try:
                        mac = net.parse_mac(v)
                        hit = hit or mac in blob or mac.hex().encode() in low
                    except ValueError:
                        pass
                if hit:
                    problems.append(f"{n}: holds a {kind} that should have been replaced.")
            if n.endswith(".pcap"):
                try:
                    cap = capture.read_capture_bytes(blob)
                except ValueError as exc:
                    problems.append(f"{n}: not readable ({exc}).")
                    continue
                if blob[:4] != b"\xd4\xc3\xb2\xa1":
                    problems.append(f"{n}: not written by this tool (it writes plain pcap).")
                census += [f"{n}: {r}" for r in _census(n, cap, sel, problems, notes, warnings)]
                res = filter_capture(cap, sel)
                foreign = len(cap.records) - len(res["keep"])
                if res.get("ambiguous"):
                    problems.append(f"{n}: two devices with the same USB numbers (and the same "
                                    "serial number, as cheap copies often have) are in it; the "
                                    "tool cannot tell which is yours.")
                elif foreign:
                    problems.append(f"{n}: {foreign} of {len(cap.records)} records do not "
                                    "belong to the instrument named in the manifest (another "
                                    "device, or this zip was changed).")
                strings |= _strings(blob)
            else:
                for m in privacy._MAC_TEXT.finditer(blob.decode("utf-8", "replace")):
                    if not m.group(0).lower().replace("-", ":").startswith("02:00:00:00"):
                        problems.append(f"{n}: a MAC address is still in it.")
                        break
    for d in manifest.get("kept_without_description", []):
        warnings.append(f"You agreed to keep the traffic of {d} although the recording holds "
                        "no USB description of it.")
    if manifest.get("instrument_serial") == "kept, as you agreed":
        notes.append("You agreed to keep your instrument's serial number in this zip.")
    if manifest.get("encrypted_connections"):
        notes.append("Some connections were treated as encrypted: their contents are zeros.")
    if manifest.get("essential_missing"):
        notes.append("Essential blocks not recorded: " + ", ".join(manifest["essential_missing"]))
    all_strings = sorted(strings)
    listing = os.path.join(os.path.dirname(os.path.abspath(path)),
                           f"check-{manifest.get('stamp') or 'zip'}-strings.txt")
    try:
        fd = os.open(listing, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write("\n".join(all_strings) + "\n")
    except OSError:
        listing = ""
    return {"problems": sorted(set(problems)), "notes": notes, "strings": all_strings,
            "names": names, "manifest": manifest, "census": census, "listing": listing,
            "warnings": sorted(set(warnings))}


def render(result: dict, path: str) -> str:
    L = [f"Checking {path}", ""]
    if result.get("warnings"):
        L += ["!" * 70, "LOOK AT THIS FIRST:"] + [f"  - {w}" for w in result["warnings"]] + \
            ["Please make sure these are really your instrument's before you send the zip.",
             "!" * 70, ""]
    m = result.get("manifest") or {}
    if m:
        L += [f"Made by {m.get('tool')} on {m.get('made')}.",
              f"Instrument: {m.get('instrument', {}).get('name', '')}",
              "Blocks recorded: " + (", ".join(m.get("blocks_recorded", [])) or "none"), ""]
    L.append("Files in it:")
    L += [f"  {n}" for n in result["names"]]
    if result.get("census"):
        L += ["", "Devices and hosts that appear in the recordings:"]
        L += [f"  {c}" for c in result["census"]]
    s = result["strings"]
    if s:
        L += ["", f"Readable text inside the recordings: {len(s)} different pieces. Please look "
                  "through them; if anything is private, make the zip again with  --remake "
                  "<session folder> --hide \"that text\"."]
        L += [f"  {x[:76]}" for x in s[:SHOW]]
        if len(s) > SHOW:
            L.append(f"  ... and {len(s) - SHOW} more.")
        if result.get("listing"):
            L.append(f"Every one of them is listed in {result['listing']}")
    L += [""] + [f"Note: {x}" for x in result["notes"]]
    if result["problems"]:
        L += ["", "PROBLEMS FOUND. Please do not send this zip yet:"]
        L += [f"  - {p}" for p in result["problems"]]
    else:
        L += ["", "Nothing of other devices, other hosts or this computer's names was found, "
                  "and none of the identifiers the tool knows. If the text above looks fine to "
                  "you, the zip is ready to send."]
    return "\n".join(L) + "\n"

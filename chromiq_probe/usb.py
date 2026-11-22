"""USB recordings: records, transfers, descriptors, the instrument-only filter.

Ported from the ChromIQ X-Rite probe 1.6.6 (same author, MIT):
`_setup_fields`, `_plausible_setup`, `_events_usbpcap`, `_events_usbmon`,
`_events_darwin` (with its measured rule that macOS carries OUT data in the
completion record), `record_device_keys`, and the 1.6.2 ownership rules:

  1. each device description at an address starts a new owner of that
     address; address 0 (every device while it is being set up) is never kept;
  2. a transfer on an endpoint the instrument does not have is left out;
  3. a disk's commands (CBW "USBC" / CSW "USBS") and requests to a hub's ports
     are left out even at the instrument's address.

What is new here: the instrument is any device the owner chose, by its USB
vendor and product number (and, on a Mac, its location), not a list of
X-Rite numbers. What is NOT ported: 1.6.6's "follow the instrument under a
hub's stale address", which needs the instrument family's own commands to be
safe; the universal tool keeps nothing there and says so in the check.
"""

from __future__ import annotations

import struct

from .capture import (LINKTYPE_USB_DARWIN, LINKTYPE_USB_LINUX, LINKTYPE_USB_LINUX_MMAPPED,
                      LINKTYPE_USBPCAP)

XFER_NAMES = {0: "isochronous", 1: "interrupt", 2: "control", 3: "bulk"}
_DARWIN_EP_TYPES = {0: "control", 1: "isochronous", 2: "bulk", 3: "interrupt"}
DARWIN_HDR = 40
CLASS_NAMES = {0x01: "audio", 0x02: "communications (serial)", 0x03: "HID (keyboard, mouse, "
               "or an instrument)", 0x07: "printer", 0x08: "disk / memory stick",
               0x09: "USB hub", 0x0A: "serial data", 0x0E: "camera", 0xE0: "wireless",
               0xFF: "vendor-specific"}


# ---- request helpers (ported) ---------------------------------------------

def setup_fields(setup: bytes) -> dict:
    rt, req, wvalue, windex, wlen = struct.unpack("<BBHHH", setup[:8])
    return {"rt": rt, "req": req, "wValue": wvalue, "wIndex": windex, "wLength": wlen}


def plausible_setup(setup: bytes) -> bool:
    return len(setup) >= 8 and ((setup[0] >> 5) & 3) <= 2 and (setup[0] & 0x1f) <= 3


def darwin_hdr_len(data: bytes) -> int:
    n = data[2] if len(data) > 2 else DARWIN_HDR
    return n if DARWIN_HDR <= n <= len(data) else DARWIN_HDR


# ---- record level ----------------------------------------------------------

def record_info(linktype: int, d: bytes):
    """(key, endpoint, transfer type, payload) of one record, or None.
    key: (bus, address) on Windows / Linux, ("mac", vid, pid, location) on macOS."""
    if linktype == LINKTYPE_USBPCAP:
        if len(d) < 27:
            return None
        hlen = struct.unpack_from("<H", d, 0)[0]
        bus, dev = struct.unpack_from("<HH", d, 17)
        ep, xfer = d[21], d[22]
        return (bus, dev), ep, xfer, d[hlen:] if 27 <= hlen <= len(d) else b""
    if linktype in (LINKTYPE_USB_LINUX, LINKTYPE_USB_LINUX_MMAPPED):
        hl = 48 if linktype == LINKTYPE_USB_LINUX else 64
        if len(d) < hl:
            return None
        xfer, ep, dev = d[9], d[10], d[11]
        bus = struct.unpack_from("<H", d, 12)[0]
        return (bus, dev), ep, xfer, d[hl:]
    if linktype == LINKTYPE_USB_DARWIN:
        if len(d) < DARWIN_HDR:
            return None
        loc = struct.unpack_from("<I", d, 24)[0]
        vid, pid = struct.unpack_from("<HH", d, 0x24)
        etype = {0: 2, 1: 0, 2: 3, 3: 1}.get(d[31] & 3, 3)
        return ("mac", vid, pid, loc), d[30], etype, d[darwin_hdr_len(d):]
    return None


def id_field(linktype: int):
    """(offset, length) of the per-transfer id the recorder writes (a kernel
    pointer on Windows and Linux): replaced by a counter in a kept copy."""
    if linktype == LINKTYPE_USBPCAP:
        return 2, 8
    if linktype in (LINKTYPE_USB_LINUX, LINKTYPE_USB_LINUX_MMAPPED):
        return 0, 8
    if linktype == LINKTYPE_USB_DARWIN:
        return 16, 8
    return None


# ---- transfers (ported from the X-Rite probe 1.6.6, as generators) ---------
# Each yields events one by one, so a recording of many hours never has to be
# in memory. A control transfer is yielded when it completes (or at the end,
# if its completion was not recorded); "t" is always the time of its setup.

def _events_usbpcap(recs):
    pending = {}
    for ri, (ts, d) in enumerate(recs):
        if len(d) < 27:
            continue
        (hlen, irp, _status, _func, info, bus, dev, ep, xfer,
         dlen) = struct.unpack_from("<HQIHBHHBBI", d, 0)
        if hlen < 27 or hlen > len(d):
            continue
        data = d[hlen:hlen + dlen]
        completion = bool(info & 1)
        if xfer == 2:
            stage = d[27] if hlen >= 28 else None
            key = (bus, irp)
            if stage == 0 and not completion and plausible_setup(data):
                old = pending.pop(key, None)
                if old is not None:
                    yield old
                ev = {"kind": "control", "t": ts, "key": (bus, dev), "out": bytes(data[8:]),
                      "in": b"", "_ri": [ri]}
                ev.update(setup_fields(data))
                pending[key] = ev
                continue
            ev = pending.get(key)
            if ev is None:
                continue
            ev["_ri"].append(ri)
            if not completion and stage == 1 and not (ev["rt"] & 0x80):
                ev["out"] += bytes(data)
            elif completion:
                if (ev["rt"] & 0x80) and data and not ev["in"]:
                    ev["in"] = bytes(data)
                if stage in (2, 3) or stage is None:
                    yield pending.pop(key)
            continue
        dir_in = bool(ep & 0x80)
        if not data or dir_in != completion:
            continue
        yield {"kind": "data", "t": ts, "key": (bus, dev), "ep": ep,
               "type": XFER_NAMES.get(xfer, f"type {xfer}"), "dir_in": dir_in,
               "data": bytes(data), "_ri": [ri]}
    yield from pending.values()


def _events_usbmon(recs, hdr_len: int):
    pending = {}
    for ri, (ts, d) in enumerate(recs):
        if len(d) < hdr_len:
            continue
        (uid, typ, xfer, epnum, devnum, busnum, flag_setup, _flag_data, _sec, _usec,
         _status, _length, len_cap, setup) = struct.unpack_from("<QcBBBHccqiiII8s", d, 0)
        data = d[hdr_len:hdr_len + len_cap]
        key = (busnum, uid)
        if xfer == 2:
            if typ == b"S" and flag_setup == b"\x00" and plausible_setup(setup):
                old = pending.pop(key, None)
                if old is not None:
                    yield old
                ev = {"kind": "control", "t": ts, "key": (busnum, devnum), "out": bytes(data),
                      "in": b"", "_ri": [ri]}
                ev.update(setup_fields(setup))
                pending[key] = ev
            elif typ == b"C":
                ev = pending.pop(key, None)
                if ev is not None:
                    ev["_ri"].append(ri)
                    if ev["rt"] & 0x80:
                        ev["in"] = bytes(data)
                    yield ev
            continue
        dir_in = bool(epnum & 0x80)
        if not data or (typ == b"C") != dir_in:
            continue
        yield {"kind": "data", "t": ts, "key": (busnum, devnum), "ep": epnum,
               "type": XFER_NAMES.get(xfer, f"type {xfer}"), "dir_in": dir_in,
               "data": bytes(data), "_ri": [ri]}
    yield from pending.values()


def _events_darwin(recs):
    """macOS: data going TO the device travels in the COMPLETION record
    (measured by the X-Rite probe 1.5.4 on real recordings)."""
    pending = {}
    out_submits = {}
    for ri, (ts, d) in enumerate(recs):
        if len(d) < DARWIN_HDR:
            continue
        direction = d[3]
        dlen = struct.unpack("<I", d[4:8])[0]
        seq = struct.unpack("<I", d[0x10:0x14])[0]
        ep = d[30]
        etype = _DARWIN_EP_TYPES.get(d[31] & 3, "unknown")
        key = record_info(LINKTYPE_USB_DARWIN, d)[0]
        payload = d[darwin_hdr_len(d):]
        if direction == 0 and plausible_setup(payload[:8]) and (ep & 0x7f) == 0:
            wlen = struct.unpack("<H", payload[6:8])[0]
            if len(payload) in (8, 8 + wlen):
                ev = {"kind": "control", "t": ts, "key": key, "out": bytes(payload[8:]),
                      "in": b"", "_ri": [ri]}
                ev.update(setup_fields(payload))
                old = pending.pop(seq, None)
                if old is not None:
                    yield old
                pending[seq] = ev
                continue
        if direction == 1 and seq in pending:
            ev = pending.pop(seq)
            ev["_ri"].append(ri)
            body = bytes(payload[:dlen] if dlen else payload)
            if ev["rt"] & 0x80:
                ev["in"] = body
            elif body and not ev["out"]:
                ev["out"] = body
            yield ev
            continue
        dir_in = bool(ep & 0x80)
        data = payload[:dlen] if dlen else payload
        ris = [ri]
        if not dir_in and (ep & 0x7f):
            if direction == 0:
                out_submits[seq] = {"kind": "data", "t": ts, "key": key, "ep": ep,
                                    "type": etype, "dir_in": False, "data": bytes(data),
                                    "_ri": [ri]}
                continue
            sub = out_submits.pop(seq, None)
            data = data or (sub["data"] if sub else b"")
            ris = (sub["_ri"] if sub else []) + [ri]
        elif direction != 1:
            continue
        if not data:
            continue
        yield {"kind": "data", "t": ts, "key": key, "ep": ep, "type": etype,
               "dir_in": dir_in, "data": bytes(data), "_ri": ris}
    yield from (ev for ev in out_submits.values() if ev["data"])
    yield from pending.values()


def iter_usb_events(linktype: int, recs):
    if linktype == LINKTYPE_USBPCAP:
        return _events_usbpcap(recs)
    if linktype == LINKTYPE_USB_LINUX:
        return _events_usbmon(recs, 48)
    if linktype == LINKTYPE_USB_LINUX_MMAPPED:
        return _events_usbmon(recs, 64)
    if linktype == LINKTYPE_USB_DARWIN:
        return _events_darwin(recs)
    return iter(())


def usb_events(linktype: int, recs) -> list:
    """All events of a (small) recording, in time order."""
    return sorted(iter_usb_events(linktype, recs), key=lambda e: e["t"])


# ---- descriptors -----------------------------------------------------------

def parse_device_descriptor(b: bytes):
    if len(b) < 18 or b[1] != 1:
        return None
    vid, pid = struct.unpack_from("<HH", b, 8)
    return {"vid": vid, "pid": pid, "class": b[4], "iManufacturer": b[14],
            "iProduct": b[15], "iSerial": b[16], "max_packet0": b[7]}


def parse_config_descriptor(b: bytes) -> dict:
    """Interfaces (class, subclass, protocol) and endpoints {address: (type, max packet)}."""
    out = {"interfaces": [], "endpoints": {}}
    i = 0
    while i + 2 <= len(b):
        ln, kind = b[i], b[i + 1]
        if ln < 2:
            break
        if kind == 4 and ln >= 9 and i + 9 <= len(b):
            out["interfaces"].append((b[i + 5], b[i + 6], b[i + 7]))
        elif kind == 5 and ln >= 7 and i + 7 <= len(b):
            out["endpoints"][b[i + 2]] = (b[i + 3] & 3, struct.unpack_from("<H", b, i + 4)[0]
                                          & 0x7FF)
        i += ln
    return out


def string_descriptor_text(b: bytes) -> str:
    if len(b) < 2 or b[1] != 3:
        return ""
    return b[2:b[0] if b[0] <= len(b) else len(b)].decode("utf-16-le", "replace")


def device_kind(desc: dict | None, cfg: dict | None) -> str:
    """A plain kind of device for the check and the manifest."""
    classes = []
    if cfg:
        classes = [c for c, _s, _p in cfg["interfaces"]]
    if desc and desc.get("class"):
        classes.insert(0, desc["class"])
    for c in (9, 8, 3, 7, 0x0E, 0xE0, 1, 2, 0x0A, 0xFF):
        if c in classes:
            if c == 3 and cfg and any(i == (3, 1, 1) for i in cfg["interfaces"]):
                return "keyboard"
            if c == 3 and cfg and any(i == (3, 1, 2) for i in cfg["interfaces"]):
                return "mouse"
            return CLASS_NAMES.get(c, "other")
    return "a device whose description the recording does not hold"


class DeviceTable:
    """What the recording itself says about each address over time."""

    def __init__(self):
        self.desc = {}       # key -> device descriptor dict (latest)
        self.cfg = {}        # key -> config dict
        self.strings = {}    # (key, index) -> text


def descriptor_events(events):
    """Yield (event, kind, parsed) for GET_DESCRIPTOR answers."""
    for ev in events:
        if ev["kind"] != "control" or ev["rt"] != 0x80 or ev["req"] != 6 or not ev["in"]:
            continue
        dtype = ev["wValue"] >> 8
        if dtype == 1:
            d = parse_device_descriptor(ev["in"])
            if d:
                yield ev, "device", d
        elif dtype == 2:
            yield ev, "config", parse_config_descriptor(ev["in"])
        elif dtype == 3:
            yield ev, "string", (ev["wValue"] & 0xFF, string_descriptor_text(ev["in"]))




# ---- the instrument-only filter ---------------------------------------------
#
# Two passes over a recording, each reading it record by record:
#   pass 1 (UsbPlan): who owned which address when (each device description
#     starts a new "epoch" at its address), which serial number each epoch
#     showed, its endpoints; then which epochs are the chosen devices';
#   pass 2 (UsbPlan.decide): every record, in order, kept or dropped.
#
# A chosen device is bound to ONE physical unit:
#   * its serial number (from the system's device list), when the recording
#     shows the epoch's serial: equal -> this unit, different -> another unit;
#   * on a Mac its location (the port it is plugged into), in every record;
#   * the address the system gave it at the start of the block (Linux), used
#     until the recording names another owner of that address;
#   * otherwise: the only device with these numbers in the recording.
# Two units with the same numbers that the recording cannot tell apart are
# BOTH left out, and the check says so. A unit that comes back at a new
# address without showing its serial is followed only in a block where the
# owner unplugs or switches it off on purpose ("disconnects"), and only when
# no other unit with those numbers is present at the same time.

def _is_disk_command(payload: bytes) -> bool:
    return len(payload) == 31 and payload[:4] == b"USBC"


def _is_disk_status(payload: bytes) -> bool:
    return len(payload) == 13 and payload[:4] == b"USBS"


def _looks_like_key_report(payload: bytes) -> bool:
    """A boot keyboard report: 8 bytes, byte 1 zero, key codes in 2..7, a key
    pressed (a typed key, not an empty report)."""
    return (len(payload) == 8 and payload[1] == 0 and any(payload[2:])
            and all(k <= 0xE7 for k in payload[2:]))


UNIDENTIFIED_SMALL = ("small reports that could be a keyboard's (the device could not be "
                      "identified)")


def _could_be_keys(p: bytes) -> bool:
    if _looks_like_key_report(p):
        return True
    if len(p) == 9 and _looks_like_key_report(p[1:]):
        return True
    if 16 <= len(p) <= 33:
        nz = sum(1 for b in p if b)
        return 0 < nz <= len(p) // 4
    return False


def chosen_devices(selection: dict) -> list:
    """The selection as a list of device dicts (old single-device form too)."""
    if selection.get("devices"):
        return list(selection["devices"])
    if "vid" in selection:
        return [{k: selection[k] for k in ("vid", "pid", "serial", "location", "addresses",
                                           "endpoints", "name", "allow_undescribed",
                                           "interfaces") if k in selection}]
    return []


class _Epoch:
    __slots__ = ("key", "vidpid", "start", "end", "iserial", "serial", "cfg", "desc", "n",
                 "last")

    def __init__(self, key, vidpid, start, desc=None):
        self.key, self.vidpid, self.start, self.end = key, vidpid, start, None
        self.desc = desc
        self.iserial = desc["iSerial"] if desc else 0
        self.serial = None
        self.cfg = None
        self.n = 0
        self.last = start


class UsbPlan:
    def __init__(self, linktype: int, records, selection: dict, follow: bool = False):
        """records: an iterable of (ts, data), read once."""
        self.linktype = linktype
        self.devices = chosen_devices(selection)
        self.follow = follow
        self.notes: list = []
        self.epochs: list = []
        self.changes: dict = {}          # record index -> [(key, epoch)]
        self.drop_ri: set = set()        # hub-port class requests at a chosen address
        self.mac_keys: dict = {}         # macOS: key -> device index
        self.mine: dict = {}             # epoch -> device index
        self.ambiguous: list = []
        self.serials: dict = {}          # device index -> serial texts seen
        self.undescribed: dict = {}      # device index -> epoch kept back (no description)
        self._scan(records)
        self._bind()

    # pass 1 -----------------------------------------------------------
    def _scan(self, records):
        current = {}
        darwin = self.linktype == LINKTYPE_USB_DARWIN
        dkeys = {}
        for i, d in enumerate(self.devices):
            for b, a in d.get("addresses") or []:
                ep = _Epoch((b, a), (d["vid"], d["pid"]), 0)
                ep.serial = None
                current[(b, a)] = ep
                self.epochs.append(ep)
        string_of = {}
        for ev in iter_usb_events(self.linktype, _Indexed(records, dkeys if darwin else None)):
            key = ev["key"]
            cur = current.get(key)
            is_devdesc = (ev["kind"] == "control" and ev["rt"] == 0x80 and ev["req"] == 6
                          and (ev["wValue"] >> 8) == 1)
            if cur is not None and not is_devdesc:
                cur.last = max(cur.last, ev["_ri"][-1])
            if ev["kind"] == "control" and (ev["rt"] & 0x1F) == 3 and \
                    ((ev["rt"] >> 5) & 3) == 1:
                self.drop_ri.update(ev["_ri"])
            if ev["kind"] != "control" or ev["rt"] != 0x80 or ev["req"] != 6 or not ev["in"]:
                continue
            dtype = ev["wValue"] >> 8
            at = ev["_ri"][0]                  # the setup record: the new owner's from there
            if dtype == 1:
                desc = parse_device_descriptor(ev["in"])
                if not desc or (not darwin and key[1] == 0):
                    continue
                old = current.get(key)
                if old is not None and old.vidpid == (desc["vid"], desc["pid"]) and \
                        old.desc is not None and at - old.start < 50 and old.serial is None:
                    old.desc = desc                       # the same description again
                    old.iserial = desc["iSerial"]
                    continue
                if old is not None and old.end is None:
                    old.end = at
                ep = _Epoch(key, (desc["vid"], desc["pid"]), at, desc)
                current[key] = ep
                self.epochs.append(ep)
                self.changes.setdefault(at, []).append((key, ep))
            elif dtype == 2:
                ep = current.get(key)
                if ep is not None:
                    ep.cfg = parse_config_descriptor(ev["in"])
            elif dtype == 3:
                ep = current.get(key)
                if ep is not None:
                    string_of[(id(ep), ev["wValue"] & 0xFF)] = string_descriptor_text(ev["in"])
                    if ep.iserial and (ev["wValue"] & 0xFF) == ep.iserial:
                        ep.serial = string_descriptor_text(ev["in"])
        self._dkeys = dkeys

    # binding --------------------------------------------------------------
    def _bind(self):
        darwin = self.linktype == LINKTYPE_USB_DARWIN
        if darwin:
            for i, d in enumerate(self.devices):
                keys = [k for k in self._dkeys if (k[1], k[2]) == (d["vid"], d["pid"])]
                if d.get("location") is not None:
                    keys = [k for k in keys if k[3] == d["location"]]
                if len(keys) > 1:
                    self.ambiguous.append(d.get("name") or f"{d['vid']:04x}:{d['pid']:04x}")
                    continue
                for k in keys:
                    self.mac_keys[k] = i
            self._serials_from_epochs()
            return
        for i, d in enumerate(self.devices):
            want = (d["vid"], d["pid"])
            cands = [e for e in self.epochs if e.vidpid == want]
            serial = d.get("serial") or ""
            seeded = {tuple(a) for a in d.get("addresses") or []}
            mine, other = [], []
            for e in cands:
                if serial and e.serial:
                    (mine if e.serial == serial else other).append(e)
            undecided = [e for e in cands if e not in mine and e not in other]

            def overlaps(a, b):
                # both ACTIVE at the same time (an unplugged device's address is
                # never re-described, so its epoch has no end; its traffic has)
                a_end = min(a.end if a.end is not None else a.last, a.last)
                b_end = min(b.end if b.end is not None else b.last, b.last)
                return a.key != b.key and a.start <= b_end and b.start <= a_end
            # review 2, S-M1: cheap clones share one serial. Two units showing the
            # chosen serial at the same time are told apart only by the address the
            # system gave this unit (Linux, refreshed by port before each block);
            # otherwise neither is kept.
            clones = [e for e in mine if any(overlaps(e, x) for x in mine if x is not e)]
            if clones:
                by_seed = [e for e in clones if e.key in seeded]
                for e in clones:
                    if e not in by_seed:
                        mine.remove(e)
                        other.append(e) if by_seed else self.ambiguous.append(e)
            for e in sorted(undecided, key=lambda x: x.start):
                rivals = [x for x in cands if x is not e and x not in other and overlaps(e, x)]
                if e.key in seeded and e.start == 0:
                    # the system's own address at the start, with NO description in the
                    # recording (review 2, S-B1): kept only when the owner said yes after
                    # seeing what it looks like; counted either way
                    if d.get("allow_undescribed"):
                        mine.append(e)
                    else:
                        self.undescribed.setdefault(i, e)
                        other.append(e)
                    continue
                if any(x in mine for x in rivals):
                    other.append(e)
                    continue
                if rivals:
                    if e not in self.ambiguous:
                        self.ambiguous.append(e)
                    continue
                earlier = [x for x in mine if x.start < e.start]
                if earlier and e.serial and any(x.serial == e.serial for x in earlier):
                    mine.append(e)                 # the same unit: it shows the same serial
                    continue
                if earlier and not self.follow:
                    self.notes.append("a device with your instrument's numbers appeared at a "
                                      "new USB address; without its serial number it is "
                                      "followed only in blocks where you unplug it on purpose")
                    other.append(e)
                    continue
                mine.append(e)
            for e in mine:
                self.mine[e] = i
            amb = [e for e in self.ambiguous if isinstance(e, _Epoch) and e.vidpid == want]
            if amb:
                self.ambiguous = [e for e in self.ambiguous if e not in amb]
                self.ambiguous.append(d.get("name") or f"{want[0]:04x}:{want[1]:04x}")
                for e in amb:
                    self.mine.pop(e, None)
                for e in [e for e in mine if any(overlaps(e, a) for a in amb)]:
                    self.mine.pop(e, None)
        for i in list(self.undescribed):
            if any(v == i and e.desc is not None for e, v in self.mine.items()):
                # the instrument was replugged and described later in this recording:
                # what came before, at the old address, is simply left out
                del self.undescribed[i]
                self.notes.append("the records before you plugged the instrument in again "
                                  "were left out (it could not be identified yet)")
        self._serials_from_epochs()

    def _serials_from_epochs(self):
        for e, i in self.mine.items():
            if e.serial:
                self.serials.setdefault(i, set()).add(e.serial)
        for e in self.epochs:
            if e.key in self.mac_keys and e.serial:
                self.serials.setdefault(self.mac_keys[e.key], set()).add(e.serial)
        for i, d in enumerate(self.devices):
            if d.get("serial"):
                self.serials.setdefault(i, set()).add(d["serial"])

    # pass 2 -----------------------------------------------------------------
    def decider(self):
        """A function (index, data) -> (keep, reason, device index)."""
        current = {}
        for e in self.epochs:
            if e.start == 0 and e.desc is None:
                current[e.key] = e
        disk_open = set()
        changes = self.changes
        darwin = self.linktype == LINKTYPE_USB_DARWIN

        def decide(ri, d):
            for key, e in changes.get(ri, ()):
                current[key] = e
            info = record_info(self.linktype, d)
            if info is None:
                return False, "not a USB record", None
            key, ep, _xfer, payload = info
            if darwin:
                dev = self.mac_keys.get(key)
                epoch = None
                if dev is None:
                    return False, "other", None
            else:
                if key[1] == 0:
                    return False, "a device being set up (address 0)", None
                epoch = current.get(key)
                dev = self.mine.get(epoch) if epoch is not None else None
                if dev is None:
                    return False, "other", None
            if ri in self.drop_ri:
                return False, "requests to a USB hub's ports", None
            cfg = epoch.cfg if epoch is not None else None
            eps = set(cfg["endpoints"]) if cfg and cfg["endpoints"] else \
                set(self.devices[dev].get("endpoints") or [])
            if (ep & 0x7F) != 0:
                if eps and ep not in eps:
                    return False, "an endpoint your instrument does not have", None
                if _is_disk_command(payload):
                    disk_open.add(key)
                    return False, "a disk's commands and data", None
                if key in disk_open:
                    if _is_disk_status(payload):
                        disk_open.discard(key)
                    if payload:
                        return False, "a disk's commands and data", None
                # review 2, S-B1: always, also without a description. Only a device
                # that is known to be HID (its description, or the system's list) may
                # send boot-keyboard-shaped reports.
                itfs = (cfg["interfaces"] if cfg else []) + \
                    [tuple(x) for x in self.devices[dev].get("interfaces") or []]
                hid = any(c == 3 for c, _s, _p in itfs)
                if not hid and (ep & 0x80) and _xfer == 1 and _looks_like_key_report(payload):
                    return False, "a keyboard's typed keys", None
                if not hid and (ep & 0x80) and _xfer == 1 and cfg is None and \
                        len(payload) in (3, 4) and payload[0] <= 7:
                    return False, "a mouse's reports", None
                # review 2 re-check, R-2: a device kept WITHOUT a description (the owner
                # said yes) could still be a keyboard in report protocol. Also dropped then,
                # even when the system lists the instrument as HID: a report id followed by
                # a boot report (9 bytes), a boot report itself, and a sparse 16 to 33 byte
                # key bitmap (multi-key "NKRO" keyboards: at most a quarter of the bytes
                # non-zero). What could be lost: an HID instrument's own small reports of
                # that shape; the block check says how many, and how to avoid it (plug the
                # instrument in after the recording has started, so its description is in it).
                if epoch is not None and epoch.desc is None and (ep & 0x80) and _xfer == 1 \
                        and _could_be_keys(payload):
                    return False, UNIDENTIFIED_SMALL, None
            if epoch is not None:
                epoch.n += 1
            return True, None, dev
        return decide

    def other_kind(self, ri, d) -> str:
        return "another device"


class _Indexed:
    """Iterates records and, on a Mac, notes every device key seen."""

    def __init__(self, records, dkeys):
        self.records, self.dkeys = records, dkeys

    def __iter__(self):
        for ts, d in self.records:
            if self.dkeys is not None and len(d) >= DARWIN_HDR:
                k = record_info(LINKTYPE_USB_DARWIN, d)[0]
                self.dkeys[k] = self.dkeys.get(k, 0) + 1
            yield ts, d


def _kind_of_epoch(e) -> str:
    return device_kind(e.desc, e.cfg) if e is not None else \
        "a device whose description the recording does not hold"


def filter_usb_stream(linktype: int, open_records, selection: dict, sink=None,
                      follow: bool = False) -> dict:
    """open_records(): a fresh iterator over the recording's records (called
    twice). sink(ts, data, device_index) receives each kept record in order."""
    plan = UsbPlan(linktype, open_records(), selection, follow)
    decide = plan.decider()
    dropped, others = {}, {}
    per_device = [0] * len(plan.devices)
    keep_idx = []
    epoch_at = {}
    for e in plan.epochs:
        if e.desc is not None:
            epoch_at.setdefault(e.key, []).append(e)
    current_other = {}
    for ri, (ts, d) in enumerate(open_records()):
        for key, e in plan.changes.get(ri, ()):
            current_other[key] = e
        keep, reason, dev = decide(ri, d)
        if keep:
            per_device[dev] += 1
            keep_idx.append(ri)
            if sink is not None:
                sink(ts, d, dev)
        elif reason == "other":
            info = record_info(linktype, d)
            kind = _kind_of_epoch(current_other.get(info[0])) if info else "unknown"
            others[kind] = others.get(kind, 0) + 1
        else:
            dropped[reason] = dropped.get(reason, 0) + 1
    names = [d.get("name") or f"{d['vid']:04x}:{d['pid']:04x}" for d in plan.devices]
    return {"keep": keep_idx, "dropped": dropped, "others": others,
            "per_device": dict(zip(names, per_device)),
            "serials": sorted(set().union(*plan.serials.values())) if plan.serials else [],
            "serial": sorted(set().union(*plan.serials.values()))[0] if plan.serials else "",
            "ambiguous": [a if isinstance(a, str) else f"{a.vidpid[0]:04x}:{a.vidpid[1]:04x}"
                          for a in plan.ambiguous],
            "undescribed": _undescribed_summary(plan, open_records, linktype),
            "described": any(e.desc is not None for e in plan.mine)
            or any(e.desc is not None and e.key in plan.mac_keys for e in plan.epochs),
            "notes": sorted(set(plan.notes))}


def _undescribed_summary(plan, open_records, linktype) -> list:
    """What a kept-back device without a description looks like, so the owner
    can decide: per device, counts by endpoint and direction, sizes, and the
    first bytes of a few transfers (hex)."""
    out = []
    for i, e in plan.undescribed.items():
        by_ep, examples, n = {}, [], 0
        for ts, d in open_records():
            info = record_info(linktype, d)
            if not info or info[0] != e.key or not info[3]:
                continue
            n += 1
            k = f"endpoint {info[1]:02x} " + XFER_NAMES.get(info[2], "?") + \
                (" from it" if info[1] & 0x80 else " to it")
            sz = by_ep.setdefault(k, [0, 0])
            sz[0] += 1
            sz[1] = max(sz[1], len(info[3]))
            if len(examples) < 4:
                examples.append(info[3][:12].hex())
        d = plan.devices[i]
        out.append({"device": d.get("name") or f"{d['vid']:04x}:{d['pid']:04x}",
                    "address": list(e.key), "records": n,
                    "by_endpoint": {k: f"{v[0]} transfers, up to {v[1]} bytes"
                                    for k, v in by_ep.items()},
                    "examples": examples})
    return out


def filter_usb(linktype: int, recs, selection: dict, follow: bool = False) -> dict:
    """filter_usb_stream for a list of records (tests, small files)."""
    return filter_usb_stream(linktype, lambda: iter(recs), selection, follow=follow)


# ---- the privacy pass on one kept record --------------------------------------

class UsbRewriter:
    def __init__(self, linktype: int, mapper, rules):
        self.linktype, self.mapper, self.rules = linktype, mapper, rules
        self.idf = id_field(linktype)
        self.ids = {}

    def __call__(self, d: bytes) -> bytes:
        d = bytearray(d)
        if self.idf:
            off, ln = self.idf
            raw = bytes(d[off:off + ln])
            if raw not in self.ids:
                self.ids[raw] = len(self.ids) + 1
            d[off:off + ln] = struct.pack("<Q", self.ids[raw])
        hdr = _header_len(self.linktype, d)
        return bytes(d[:hdr]) + self.mapper.scrub_bytes(bytes(d[hdr:]), self.rules)


def rewrite_usb(linktype: int, recs, keep: list, mapper, serial: str = "",
                keep_serial: bool = False, rules=None) -> list:
    """The kept records with ids replaced by counters and identifiers replaced
    (tests and small files; the zip uses UsbRewriter record by record)."""
    if serial and not keep_serial and len(serial) >= 3:
        mapper.text("serial", serial)
    rw = UsbRewriter(linktype, mapper, mapper.byte_rules() if rules is None else rules)
    return [(recs[ri][0], rw(recs[ri][1])) for ri in keep]


def collect_serials(linktype: int, records) -> list:
    """Serial strings in the description of every device in a (kept) recording."""
    plan_devices = {}
    out = set()
    current = {}
    for ev in iter_usb_events(linktype, records):
        if ev["kind"] != "control" or ev["rt"] != 0x80 or ev["req"] != 6 or not ev["in"]:
            continue
        dt = ev["wValue"] >> 8
        if dt == 1:
            desc = parse_device_descriptor(ev["in"])
            if desc:
                current[ev["key"]] = desc["iSerial"]
        elif dt == 3:
            idx = ev["wValue"] & 0xFF
            if idx and current.get(ev["key"]) == idx:
                out.add(string_descriptor_text(ev["in"]))
    del plan_devices
    return sorted(x for x in out if x)


def _header_len(linktype: int, d) -> int:
    if linktype == LINKTYPE_USBPCAP and len(d) >= 2:
        return min(struct.unpack_from("<H", d, 0)[0], len(d))
    if linktype == LINKTYPE_USB_LINUX:
        return min(48, len(d))
    if linktype == LINKTYPE_USB_LINUX_MMAPPED:
        return min(64, len(d))
    if linktype == LINKTYPE_USB_DARWIN:
        return min(darwin_hdr_len(bytes(d)), len(d))
    return 0

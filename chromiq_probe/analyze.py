"""--analyze: from a recording to a timeline, for us (and for the curious).

It assumes nothing about any maker's commands. Per recording:
  * a timeline of messages: USB control requests (setup and reply) and bulk /
    interrupt transfers by endpoint; network messages by connection;
  * request -> answer pairs (the next message back within 2 s) with the
    time the instrument took;
  * time gaps over 1 s;
  * "forms": messages grouped by direction, length and first bytes, with the
    byte positions that vary;
  * framing guesses: text lines (CR, LF, CRLF), a length byte, a last byte
    that is the sum or XOR of the rest, a CRC-16 (Modbus or CCITT) at the end;
  * for a USB serial adapter: the serial bytes and line settings.
--diff A B compares two labelled recordings: forms only in A, only in B, and
counts that changed ("what changed when Cancel was pressed").
--json OUT writes the same as data.
"""

from __future__ import annotations

import io
import json
import os
import zipfile

from . import capture, net, serial_decode, usb
from .capture import USB_LINKTYPES

PAIR_WINDOW = 2.0
GAP = 1.0


def _messages(cap) -> list:
    """[{t, dir ('out' to the instrument / 'in'), chan, data, setup}]"""
    msgs = []
    if cap.linktype in USB_LINKTYPES:
        for ev in usb.usb_events(cap.linktype, cap.records):
            if ev["kind"] == "control":
                setup = f"rt={ev['rt']:02x} req={ev['req']:02x} val={ev['wValue']:04x} " \
                        f"idx={ev['wIndex']:04x} len={ev['wLength']}"
                msgs.append({"t": ev["t"], "dir": "out", "chan": "control", "setup": setup,
                             "data": ev["out"], "reply": ev["in"],
                             "req": (ev["rt"], ev["req"], ev["wValue"])})
            else:
                msgs.append({"t": ev["t"], "dir": "in" if ev["dir_in"] else "out",
                             "chan": f"ep {ev['ep']:02x} {ev['type']}", "data": ev["data"]})
        return msgs
    flows = net.flows(cap.linktype, cap.records)
    # in a cleaned recording the instrument's addresses are 198.51.100.x /
    # 2001:db8:1::x; otherwise guess: the lower port is the instrument's
    for f in flows:
        if not f["data"]:
            continue
        if _is_device_ip(f["src"]):
            d = "in"
        elif _is_device_ip(f["dst"]):
            d = "out"
        else:
            d = "in" if f["sp"] == min(f["sp"], f["dp"]) else "out"
        msgs.append({"t": f["t"], "dir": d, "chan": f["conn"], "data": f["data"]})
    return msgs


def _is_device_ip(ip: str) -> bool:
    return ip.startswith("198.51.100.") or ip.startswith("2001:db8:1::")


def _crc16(data: bytes, poly: int, init: int, reflect: bool) -> int:
    crc = init
    for b in data:
        if reflect:
            crc ^= b
            for _ in range(8):
                crc = (crc >> 1) ^ poly if crc & 1 else crc >> 1
        else:
            crc ^= b << 8
            for _ in range(8):
                crc = ((crc << 1) ^ poly) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc & 0xFFFF


def framing_guesses(datas: list) -> list:
    """Guesses that hold for EVERY message of a group (at least 3 messages)."""
    datas = [d for d in datas if d]
    if len(datas) < 3:
        return []
    out = []
    if all(d.endswith(b"\r\n") for d in datas):
        out.append("text lines ending in CR LF")
    elif all(d.endswith(b"\r") for d in datas):
        out.append("text lines ending in CR")
    elif all(d.endswith(b"\n") for d in datas):
        out.append("text lines ending in LF")
    for pos in (0, 1):
        if all(len(d) > pos and d[pos] in (len(d), len(d) - pos - 1, len(d) - 2) for d in datas):
            out.append(f"byte {pos} holds the length")
    if all(len(d) >= 2 and sum(d[:-1]) & 0xFF == d[-1] for d in datas):
        out.append("last byte is the sum of the others (mod 256)")
    if all(len(d) >= 2 and _xor(d[:-1]) == d[-1] for d in datas):
        out.append("last byte is the XOR of the others")
    if all(len(d) >= 3 and _crc16(d[:-2], 0xA001, 0xFFFF, True) ==
           int.from_bytes(d[-2:], "little") for d in datas):
        out.append("last two bytes are a CRC-16 (Modbus)")
    if all(len(d) >= 3 and _crc16(d[:-2], 0x1021, 0xFFFF, False) ==
           int.from_bytes(d[-2:], "big") for d in datas):
        out.append("last two bytes are a CRC-16 (CCITT)")
    return out


def _xor(b: bytes) -> int:
    x = 0
    for v in b:
        x ^= v
    return x


def forms(msgs: list) -> list:
    """Group messages by (direction, channel, length, first 2 bytes)."""
    groups = {}
    for m in msgs:
        d = m["data"]
        key = (m["dir"], m["chan"], m.get("setup", "")[:23], len(d), d[:2].hex())
        groups.setdefault(key, []).append(d)
    out = []
    for (direction, chan, setup, ln, head), datas in groups.items():
        varying = [i for i in range(ln) if len({d[i] for d in datas}) > 1]
        out.append({"dir": direction, "chan": chan, "setup": setup, "length": ln, "head": head,
                    "count": len(datas), "varying_bytes": varying,
                    "example": datas[0][:48].hex(), "framing": framing_guesses(datas)})
    return sorted(out, key=lambda f: (-f["count"], f["dir"], f["chan"]))


def pairs(msgs: list) -> list:
    out = []
    for i, m in enumerate(msgs):
        if m["dir"] != "out":
            continue
        if m.get("reply"):
            continue
        for n in msgs[i + 1:]:
            if n["t"] - m["t"] > PAIR_WINDOW:
                break
            if n["dir"] == "in":
                out.append({"t": m["t"], "request": m["data"][:16].hex(),
                            "answer": n["data"][:16].hex(), "ms": round((n["t"] - m["t"]) * 1000, 1)})
                break
    return out


def gaps(msgs: list) -> list:
    return [{"after": round(a["t"] - msgs[0]["t"], 3), "seconds": round(b["t"] - a["t"], 3)}
            for a, b in zip(msgs, msgs[1:]) if b["t"] - a["t"] > GAP]


def _text(b: bytes) -> str:
    return "".join(chr(c) if 32 <= c < 127 else "." for c in b)


def serial_view(cap) -> dict | None:
    if cap.linktype not in USB_LINKTYPES:
        return None
    events = usb.usb_events(cap.linktype, cap.records)
    vid, interfaces, mp = None, [], 64
    for _ev, kind, parsed in usb.descriptor_events(events):
        if kind == "device":
            vid = parsed["vid"]
        elif kind == "config":
            interfaces = parsed["interfaces"]
            ins = [m for a, (_t, m) in parsed["endpoints"].items() if a & 0x80 and _t == 2]
            mp = ins[0] if ins else 64
    if vid is None and cap.linktype == capture.LINKTYPE_USB_DARWIN and cap.records:
        vid = usb.record_info(cap.linktype, cap.records[0][1])[0][1]
    kind = serial_decode.bridge_kind(vid or 0, interfaces)
    if not kind:
        return None
    return dict(serial_decode.decode(events, kind, mp), kind=kind)


def analyze_capture(cap) -> dict:
    msgs = _messages(cap)
    t0 = msgs[0]["t"] if msgs else 0
    timeline = []
    for m in msgs[:400]:
        row = {"t": round(m["t"] - t0, 4), "dir": m["dir"], "chan": m["chan"],
               "len": len(m["data"]), "hex": m["data"][:32].hex()}
        if m.get("setup"):
            row["setup"] = m["setup"]
            row["reply"] = m.get("reply", b"")[:32].hex()
        timeline.append(row)
    return {"format": capture.LINKTYPE_NAMES.get(cap.linktype, str(cap.linktype)),
            "records": len(cap.records), "messages": len(msgs),
            "duration_s": round(msgs[-1]["t"] - t0, 3) if msgs else 0,
            "timeline": timeline, "timeline_cut": len(msgs) > 400,
            "pairs": pairs(msgs)[:200], "gaps": gaps(msgs), "forms": forms(msgs),
            "serial": _jsonable_serial(serial_view(cap))}


def _jsonable_serial(s):
    if not s:
        return None
    return {"kind": s["kind"], "settings": s["settings"],
            "chunks": [{"t": c["t"], "dir": c["dir"], "hex": c["data"].hex(),
                        "text": _text(c["data"])} for c in s["chunks"][:400]]}


def render(name: str, a: dict) -> str:
    L = [f"=== {name}", f"{a['format']}: {a['records']} records, {a['messages']} messages, "
                        f"{a['duration_s']} s"]
    L.append("Forms (most frequent first):")
    for f in a["forms"][:30]:
        extra = f" setup {f['setup']}" if f["setup"] else ""
        var = f", bytes that vary: {f['varying_bytes'][:12]}" if f["varying_bytes"] else ""
        fr = f", {'; '.join(f['framing'])}" if f["framing"] else ""
        L.append(f"  {f['count']:5d} x {f['dir']:3s} {f['chan']}{extra} length {f['length']}"
                 f"{var}{fr}  e.g. {f['example'][:40]}")
    if a["pairs"]:
        times = sorted(p["ms"] for p in a["pairs"])
        L.append(f"Request -> answer pairs: {len(a['pairs'])}, answer time "
                 f"{times[0]} to {times[-1]} ms (median {times[len(times) // 2]})")
    if a["gaps"]:
        L.append("Quiet gaps over 1 s: " + ", ".join(f"{g['seconds']} s after {g['after']} s"
                                                    for g in a["gaps"][:15]))
    if a["serial"]:
        s = a["serial"]
        L.append(f"Serial adapter ({s['kind']}):")
        L += [f"  line settings: {x['text']}" for x in s["settings"][:10]]
        for c in s["chunks"][:40]:
            L.append(f"  {c['dir']:16s} {c['text'][:60]}")
    L.append("Timeline (first messages):")
    for r in a["timeline"][:60]:
        extra = f" [{r['setup']}] reply {r['reply'][:24]}" if r.get("setup") else ""
        L.append(f"  {r['t']:9.4f} {r['dir']:3s} {r['chan']:24s} {r['len']:5d}{extra} "
                 f"{r['hex'][:40]}")
    return "\n".join(L)


def analyze_blobs(files: dict) -> str:
    out = []
    for name, blob in sorted(files.items()):
        try:
            cap = capture.read_capture_bytes(blob)
        except ValueError as exc:
            out.append(f"=== {name}\nnot readable: {exc}")
            continue
        out.append(render(name, analyze_capture(cap)))
    return "\n\n".join(out) + "\n" if out else "No recordings.\n"


def load_inputs(paths: list) -> dict:
    """{name: bytes} from files, folders (their *.pcap / *.pcapng) and zips."""
    files = {}
    for p in paths:
        if os.path.isdir(p):
            for root, _dirs, names in os.walk(p):
                for n in sorted(names):
                    if n.endswith((".pcap", ".pcapng")):
                        with open(os.path.join(root, n), "rb") as fh:
                            files[os.path.relpath(os.path.join(root, n), p)] = fh.read()
        elif zipfile.is_zipfile(p):
            with zipfile.ZipFile(p) as z:
                for n in z.namelist():
                    if n.endswith((".pcap", ".pcapng")):
                        files[n] = z.read(n)
        else:
            with open(p, "rb") as fh:
                files[os.path.basename(p)] = fh.read()
    return files


def _label_match(name: str, label: str) -> bool:
    base = os.path.basename(name).rsplit(".", 1)[0].lower()
    label = label.lower()
    return base == label or base.endswith("-" + label) or base.startswith(label + "-") \
        or f"-{label}-" in base


def diff(files: dict, a_label: str, b_label: str) -> dict:
    def pick(label):
        names = [n for n in files if _label_match(n, label)]
        fs = []
        for n in names:
            fs += analyze_capture(capture.read_capture_bytes(files[n]))["forms"]
        return names, {(f["dir"], f["chan"], f["setup"], f["length"], f["head"]): f for f in fs}
    an, af = pick(a_label)
    bn, bf = pick(b_label)
    only_a = [af[k] for k in af if k not in bf]
    only_b = [bf[k] for k in bf if k not in af]
    changed = [{"form": bf[k], "a": af[k]["count"], "b": bf[k]["count"]}
               for k in af if k in bf and af[k]["count"] != bf[k]["count"]]
    return {"a": an, "b": bn, "only_a": only_a, "only_b": only_b, "changed": changed}


def render_diff(d: dict, a: str, b: str) -> str:
    if not d["a"] or not d["b"]:
        return (f"No recording labelled \"{a if not d['a'] else b}\" was found. Labels are the "
                "words after the block number in the file names, for example \"cancel-reading\".")
    L = [f"Difference between \"{a}\" ({', '.join(d['a'])}) and \"{b}\" ({', '.join(d['b'])})"]

    def row(f):
        return f"{f['dir']:3s} {f['chan']} {f['setup']} length {f['length']} e.g. {f['example'][:40]}"
    L.append(f"Only in {a}: {len(d['only_a'])}")
    L += ["  " + row(f) for f in d["only_a"][:40]]
    L.append(f"Only in {b}: {len(d['only_b'])}")
    L += ["  " + row(f) for f in d["only_b"][:40]]
    L.append(f"In both, a different number of times: {len(d['changed'])}")
    L += [f"  {c['a']} -> {c['b']}  {row(c['form'])}" for c in d["changed"][:40]]
    return "\n".join(L)


def to_json(files: dict) -> str:
    data = {}
    for name, blob in sorted(files.items()):
        try:
            data[name] = analyze_capture(capture.read_capture_bytes(blob))
        except ValueError as exc:
            data[name] = {"error": str(exc)}
    buf = io.StringIO()
    json.dump({"format": "chromiq-probe-analysis/1", "recordings": data}, buf, indent=1)
    return buf.getvalue()

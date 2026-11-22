"""From full recordings to the one zip the owner sends.

The order is the safety contract:
  1. right after each take, every full recording is read record by record
     and filtered (usb.filter_usb_stream, net.filter_net_stream); only the
     chosen instrument's records are written, into kept/<take>.pcap (0600);
     the runner then deletes the full recording;
  2. for the zip, every identifier is collected FIRST, from every kept file
     and from what the system's device list said (serial numbers), so that
     no take is written before a later take has revealed a serial;
  3. then every kept file is rewritten record by record with the identifiers
     replaced (one Mapper for the whole session: the same value has the same
     placeholder in every file), into NEW capture files (capture.PcapWriter);
  4. the manifest, the report, the cleaned session.json and the analysis are
     written, and everything goes into the zip.
"""

from __future__ import annotations

import datetime
import ipaddress
import json
import os
import re
import zipfile

from . import VERSION, analyze, capture, net, privacy, usb
from .capture import NET_LINKTYPES, USB_LINKTYPES

HONEST = ("The tool replaces what it knows: identifiers it was told (your --hide texts), "
          "this computer's names, the addresses in the traffic, and serial numbers from "
          "the system's device list or the instruments' USB descriptions. It cannot know an "
          "identifier it has not been told and that does not appear in a standard field, "
          "for example a serial number the instrument sends in its own binary format.")


def transport_of(linktype: int) -> str | None:
    if linktype in USB_LINKTYPES:
        return "usb"
    if linktype in NET_LINKTYPES:
        return "net"
    return None


class _Counter:
    def __init__(self, it):
        self.it, self.n = it, 0

    def __iter__(self):
        for r in self.it:
            self.n += 1
            yield r


def filter_file(path_or_cf, selection: dict, sink=None, follow: bool = False) -> dict:
    """Filter one recording record by record. Returns the filter's result plus
    "records" (how many records the recording held)."""
    cf = path_or_cf if isinstance(path_or_cf, capture.CaptureFile) else \
        capture.CaptureFile(path_or_cf)
    t = transport_of(cf.linktype)
    counter = {}

    def opener():
        c = _Counter(cf.records())
        counter["c"] = c
        return c
    if t == "usb" and selection.get("transport") == "usb":
        res = usb.filter_usb_stream(cf.linktype, opener, selection, sink, follow)
    elif t == "net" and selection.get("transport") == "net":
        res = net.filter_net_stream(cf.linktype, opener, selection, sink)
    else:
        n = sum(1 for _ in cf.records())
        return {"keep": [], "dropped": {"a recording of another kind than your instrument's "
                                        "connection": n}, "others": {}, "records": n,
                "linktype": cf.linktype}
    res["records"] = counter["c"].n
    res["linktype"] = cf.linktype
    return res


def filter_capture(cap, selection: dict) -> dict:
    """filter_file for a capture held in memory (the zip's own files, tests)."""
    if transport_of(cap.linktype) == "usb" and selection.get("transport") == "usb":
        return usb.filter_usb(cap.linktype, cap.records, selection)
    if transport_of(cap.linktype) == "net" and selection.get("transport") == "net":
        return net.filter_net(cap.linktype, cap.records, selection)
    return {"keep": [], "dropped": {"a recording of another kind than your instrument's "
                                    "connection": len(cap.records)}, "others": {}}


def process_take(raw_paths: list, selection: dict, kept_dir: str, stem: str,
                 follow: bool = False) -> dict:
    """Filter the take's full recordings into kept files; return the check
    (counts only, never contents). The full recordings are not touched."""
    os.makedirs(kept_dir, mode=0o700, exist_ok=True)
    out = {"files": 0, "records": 0, "kept": 0, "dropped": {}, "others": {}, "unreadable": [],
           "only_descriptions": False, "all_zero": False, "refused": "", "ambiguous": [],
           "new_addresses": [], "per_device": {}, "serials": [], "notes": [], "undescribed": [],
           "unproven_addresses": [],
           "commands": 0, "answers": 0, "kept_files": []}
    for n, p in enumerate(raw_paths):
        kept_path = os.path.join(kept_dir, f"{stem}" + (f"-{n + 1}" if n else "") + ".pcap")
        writer = {}
        try:
            cf = capture.CaptureFile(p)

            def sink(ts, d, _dev, cf=cf, kept_path=kept_path):
                if "w" not in writer:
                    writer["w"] = capture.PcapWriter(kept_path, cf.linktype)
                writer["w"].write(ts, d)
            res = filter_file(cf, selection, sink, follow)
        except (OSError, ValueError) as exc:
            out["unreadable"].append(f"{os.path.basename(p)}: {exc}")
            continue
        finally:
            if "w" in writer:
                writer["w"].close()
        out["files"] += 1
        out["records"] += res.get("records", 0)
        out["kept"] += len(res["keep"])
        for key in ("dropped", "others", "per_device"):
            for k, v in res.get(key, {}).items():
                out[key][k] = out[key].get(k, 0) + v
        for key in ("ambiguous", "new_addresses", "serials", "notes", "undescribed",
                    "unproven_addresses"):
            for v in res.get(key, []):
                if v not in out[key]:
                    out[key].append(v)
        out["refused"] = out["refused"] or res.get("refused", "")
        if "w" in writer:
            out["kept_files"].append(os.path.basename(kept_path))
    _content_counts(out, kept_dir, selection)
    return out


def _content_counts(out: dict, kept_dir: str, selection: dict) -> None:
    zero_data, any_data, nondesc = True, False, False
    for name in out["kept_files"]:
        cf = capture.CaptureFile(os.path.join(kept_dir, name))
        if transport_of(cf.linktype) == "usb":
            for ev in usb.iter_usb_events(cf.linktype, cf.records()):
                if ev["kind"] == "control":
                    if not (ev["rt"] == 0x80 and ev["req"] == 6):
                        nondesc = True
                        out["commands"] += 1
                    continue
                nondesc = any_data = True
                out["answers" if ev["dir_in"] else "commands"] += 1
                if any(ev["data"]):
                    zero_data = False
        else:
            ips = set(selection.get("ips", []))
            for fl in net.flows(cf.linktype, cf.records()):
                if fl["data"]:
                    any_data = nondesc = True
                    if any(fl["data"]):
                        zero_data = False
                    out["commands" if fl["dst"] in ips else "answers"] += 1
    out["only_descriptions"] = out["kept"] > 0 and not nondesc
    out["all_zero"] = any_data and zero_data


def check_lines(c: dict, transport: str) -> list:
    """Plain sentences for the owner after a take."""
    if c.get("refused"):
        return [f"KEPT NOTHING: {c['refused']}. A router carries this computer's internet "
                "traffic, so the tool never keeps it. Please start again and choose the "
                "instrument's own address."]
    if c["unreadable"] and not c["files"]:
        return ["NOTHING RECORDED: the recording could not be read ("
                + "; ".join(c["unreadable"]) + "). Please record this block again."]
    if not c["records"]:
        return ["EMPTY: the recorder wrote nothing in this block. Please record it again."]
    what = "USB" if transport == "usb" else "network"
    lines = []
    if c.get("ambiguous"):
        lines.append("TWO DEVICES WITH THE SAME NUMBERS: the recording holds another device "
                     "with the numbers of " + ", ".join(c["ambiguous"]) + ", and it cannot "
                     "tell which one is yours, so it kept neither. Please unplug the other "
                     "device and record this block again.")
    for u in c.get("undescribed", []):
        lines.append(f"HELD BACK: {u['records']} records at the address where the system saw "
                     f"{u['device']}, but the recording itself holds no description of the "
                     "device there, so the tool cannot be sure it is your instrument (it could "
                     "be, for example, a keyboard). They are not kept unless you say so.")
    if not c["kept"]:
        lines.append(f"KEPT NOTHING: the recording holds {c['records']} {what} records, but "
                     "none of them could be attributed to your instrument, so nothing of this "
                     "block will be sent.")
        if c["others"]:
            lines.append("Seen instead (counts only): " + ", ".join(
                f"{n} from {k}" for k, n in sorted(c["others"].items())) + ".")
        lines.append("Please check that the program really talked to the instrument in this "
                     "block, and that you chose the right device at the start.")
        return lines
    if c["only_descriptions"]:
        lines.append(f"ONLY THE DESCRIPTION: kept {c['kept']} records, but they are only the "
                     "instrument's USB description, no conversation with the program. Did the "
                     "program show the instrument as connected?")
    else:
        lines.append(f"GOOD: kept {c['kept']} records of your instrument in this block "
                     f"({c['commands']} to it, {c['answers']} from it).")
    if len(c.get("per_device", {})) > 1:
        lines.append("Per device in this block: " + ", ".join(
            f"{k}: {v}" for k, v in c["per_device"].items()) + ".")
        for k, v in c["per_device"].items():
            if not v:
                lines.append(f"NOTHING FROM {k} in this block. If it should have been "
                             "busy, please record the block again.")
    if c["all_zero"]:
        lines.append("WARNING: every data byte in this block is zero. That has been seen on "
                     "Apple Silicon Macs; such a recording cannot show the commands.")
    for n in c.get("notes", []):
        lines.append("Note: " + n + ".")
    small = c["dropped"].get("small reports that could be a keyboard's (the device could not "
                             "be identified)")
    if small:
        lines.append(f"Note: {small} small reports were left out because the device could not "
                     "be identified and they could be a keyboard's typed keys. If they were "
                     "your instrument's, record the block again and plug the instrument in "
                     "AFTER the recording has started, so that its description is in it.")
    v6 = c["dropped"].get("the instrument's IPv6 traffic (this version keeps IPv4 only)")
    if v6:
        lines.append(f"Note: {v6} records of your instrument used IPv6; this version keeps "
                     "only its IPv4 traffic, so they are left out (counted in the manifest).")
    for a in c.get("unproven_addresses", []):
        lines.append(f"Note: your instrument's network card also announced the address {a}, "
                     "but this computer never talked to it there, so it was not followed.")
    left = sum(c["dropped"].values()) + sum(c["others"].values())
    if left:
        lines.append(f"Left out: {left} records of other devices or other traffic (counts "
                     "only; nothing of them is kept).")
    return lines


# ---- the zip ------------------------------------------------------------------

def _sanitised_selection(sel: dict, mapper) -> dict:
    out = {k: v for k, v in sel.items() if not k.startswith("_")
           and k not in ("serial", "gateways", "dedupe")}
    if "ips" in out:
        out["ips"] = [str(mapper.ip(i)) for i in out["ips"]]
    if "macs" in out:
        out["macs"] = [net.mac_text(mapper.mac(net.parse_mac(m))) for m in out["macs"]]
    if "devices" in out:
        out["devices"] = [{k: v for k, v in d.items() if k not in ("serial", "port_path",
                                                                   "instance")}
                          for d in out["devices"]]
    return out


def zip_selection(state: dict) -> dict:
    sel = dict(state["selection"])
    if sel.get("transport") == "net":
        sel["ips"] = sorted(set(sel.get("ips", []) + state.get("confirmed_ips", [])))
    return sel


def kept_entries(state: dict):
    for b in state["blocks"]:
        for name in b.get("kept", []):
            yield b, name


def build_zip(state: dict, session_dir: str, full_dir: str | None, zip_path: str,
              ids: dict | None = None) -> dict:
    """Write the zip from the session's kept files; returns the manifest."""
    privacy.new_salt()
    mapper = privacy.Mapper()
    ids = privacy.computer_identifiers() if ids is None else ids
    hide = state.get("hide", [])
    sources = []
    for value in hide:
        mapper.text("hidden", value)
    if hide:
        sources.append({"what": f"{len(hide)} text(s) you named with --hide",
                        "learned_from": "you"})
    for key in ("computer_name", "local_host", "host", "host_short"):
        if ids.get(key):
            mapper.text("computer", ids[key])
    if ids.get("user"):
        mapper.text("user", ids["user"])
    if ids.get("home"):
        mapper.text("folder", ids["home"])
    if any(ids.get(k) for k in ("host", "user", "home")):
        sources.append({"what": "this computer's name, your user name and home folder",
                        "learned_from": "this computer"})
    sel = zip_selection(state)
    kept_dir = os.path.join(session_dir, "kept")
    # pass 1: every identifier first
    serials = set()
    from_system = set()
    for d in usb.chosen_devices(sel) if sel.get("transport") == "usb" else []:
        if d.get("serial"):
            from_system.add(d["serial"])
    for b in state["blocks"]:
        serials |= set(b.get("check", {}).get("serials", []))
    net_rw = {}
    from_recording = set()
    for b, name in kept_entries(state):
        path = os.path.join(kept_dir, name)
        try:
            cf = capture.CaptureFile(path)
        except (OSError, ValueError):
            continue
        if transport_of(cf.linktype) == "usb":
            from_recording |= set(usb.collect_serials(cf.linktype, cf.records()))
        else:
            rw = net_rw.setdefault(cf.linktype, net.NetRewriter(cf.linktype, mapper, sel))
            for _ts, d in cf.records():
                rw.register(d)
    serials |= from_system | from_recording
    serials = {x for x in serials if x and len(x) >= 3}
    if serials and not state.get("keep_serial"):
        for x in sorted(serials):
            mapper.text("serial", x)
        src = []
        if from_system:
            src.append("the system's device list")
        if from_recording or (serials - from_system):
            src.append("the instrument's USB description in the recording")
        sources.append({"what": f"{len(serials)} serial number(s)",
                        "learned_from": " and ".join(src)})
    if sel.get("transport") == "net":
        sources.append({"what": "network addresses (MAC and IP) in the kept traffic, as "
                                "text and, for known addresses, as 4 bytes",
                        "learned_from": "the recordings themselves"})
    # pass 2: rewrite, record by record, into temporary files
    files_out, manifest_recs = [], []
    encrypted_all = {}
    usb_rules = None
    used = set()
    for b, name in kept_entries(state):
        path = os.path.join(kept_dir, name)
        try:
            cf = capture.CaptureFile(path)
        except (OSError, ValueError) as exc:
            manifest_recs.append({"block": b["id"], "file": None, "problem": str(exc)})
            continue
        safe = re.sub(r"[^A-Za-z0-9-]", "-", f"{b['id']}-{b['label']}")[:60]
        base = f"recordings/{safe}.pcap"
        k = 2
        while base in used:
            base = f"recordings/{safe}-{k}.pcap"
            k += 1
        used.add(base)
        tmp = os.path.join(session_dir, f".zip-part-{len(used)}.pcap")
        w = capture.PcapWriter(tmp, cf.linktype)
        try:
            if transport_of(cf.linktype) == "usb":
                usb_rules = usb_rules or mapper.byte_rules()
                rw = usb.UsbRewriter(cf.linktype, mapper, usb_rules)
                for ts, d in cf.records():
                    w.write(ts, rw(d))
            else:
                rw = net_rw[cf.linktype]
                for ts, d in cf.records():
                    w.write(ts, rw.rewrite(d))
        finally:
            w.close()
        files_out.append((base, tmp))
        manifest_recs.append({"block": b["id"], "label": b["label"], "file": base,
                              "kept": w.count,
                              "format": capture.LINKTYPE_NAMES.get(cf.linktype, str(cf.linktype)),
                              "left_out": _left_out(b.get("check", {}))})
    for rw in net_rw.values():
        encrypted_all.update(rw.encrypted)
    clean_state = {k: v for k, v in state.items() if k not in ("hide", "confirmed_ips")}
    clean_state["blocks"] = [{k: v for k, v in b.items() if k not in ("files",)}
                             for b in state["blocks"]]
    for b in clean_state["blocks"]:
        if "check" in b:
            b["check"] = {k: v for k, v in b["check"].items() if k != "serials"}
    clean_state["selection"] = _scrub_obj(_sanitised_selection(sel, mapper), mapper, ids, hide)
    scrubbed = _scrub_obj(clean_state, mapper, ids, hide)
    blocks_done = [b for b in state["blocks"] if b.get("status") in ("recorded", "answered")
                   and (b.get("status") == "answered" or b.get("kept"))]
    plan = state.get("plan", [])
    done_ids = {b["id"] for b in blocks_done}
    skipped = sorted({b["id"] for b in state["blocks"] if b.get("status") == "skipped"})
    empty = sorted({b["id"] for b in state["blocks"] if b.get("status") == "recorded"
                    and not b.get("kept")} - done_ids)
    not_reached = [p["id"] for p in plan if p["id"] not in done_ids and p["id"] not in skipped
                   and p["id"] not in empty]
    manifest = {
        "tool": f"chromiq-instrument-probe {VERSION}",
        "made": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "stamp": state.get("stamp"),
        "session": state.get("session_id"), "session_title": state.get("session_title"),
        "instrument": clean_state["selection"],
        "blocks_recorded": sorted(done_ids), "blocks_skipped": skipped,
        "blocks_that_kept_nothing": empty, "blocks_not_reached": not_reached,
        "essential_missing": [p["id"] for p in plan if p.get("priority") == "essential"
                              and p["id"] not in done_ids],
        "recordings": manifest_recs,
        "replaced": dict(mapper.counts),
        "identifiers_replaced": sources,
        "kept_without_description": list(state.get("kept_without_description", [])),
        "what_the_tool_cannot_know": HONEST,
        "instrument_serial": ("kept, as you agreed" if state.get("keep_serial") and serials
                              else "replaced by a placeholder" if serials
                              else "no serial number was known to the tool"),
        "encrypted_connections": encrypted_all,
        "not_in_this_zip": ["the full recordings (deleted after each block, or kept only "
                            "where you said so)",
                            "anything of other devices, other computers or the internet"],
    }
    blobs = {}
    for name, tmp in files_out:
        with open(tmp, "rb") as fh:
            head = fh.read(2_000_000)
        blobs[name] = head
    analysis_text = analyze.analyze_blobs(blobs)
    report = privacy.scrub_text(report_text(state), mapper, ids, hide)
    manifest_text = manifest_txt(manifest)
    try:
        fd = os.open(zip_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as fh, zipfile.ZipFile(fh, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("MANIFEST.txt", manifest_text)
            z.writestr("manifest.json", json.dumps(manifest, indent=2))
            z.writestr("session.json", json.dumps(scrubbed, indent=2))
            z.writestr("notes.txt", notes_text(scrubbed))
            z.writestr("report.txt", report)
            z.writestr("analysis.txt", analysis_text)
            for name, tmp in files_out:
                z.write(tmp, name)
    finally:
        for _name, tmp in files_out:
            try:
                os.remove(tmp)
            except OSError:
                pass
    return manifest


def _left_out(check: dict) -> dict:
    out = dict(check.get("dropped", {}))
    for k, v in check.get("others", {}).items():
        out[f"other device: {k}"] = v
    return out


def notes_text(state: dict) -> str:
    """One line per block with its label, status, clock time and note, and
    the marks typed during it."""
    lines = []
    for x in state["blocks"]:
        when = datetime.datetime.fromtimestamp(x["started"]).strftime("%Y-%m-%d %H:%M:%S") \
            if x.get("started") else ""
        line = f"{x['id']} {x['label']} {x['status']} {when}".rstrip()
        if x.get("notes"):
            line += f": {x['notes']}"
        if x.get("saved_file"):
            line += f" (saved file: {x['saved_file']})"
        lines.append(line)
        for m in x.get("marks", []):
            lines.append(f"    at {m['t']} s: {m['text']}")
        for a in x.get("answers", []):
            lines.append(f"    {a['question']} {a['answer']}")
    return "\n".join(lines) + "\n"


def _scrub_obj(obj, mapper, ids, hide):
    """Scrub every text value (never the keys, so the JSON stays valid)."""
    if isinstance(obj, str):
        return privacy.scrub_text(obj, mapper, ids, hide)
    if isinstance(obj, list):
        return [_scrub_obj(x, mapper, ids, hide) for x in obj]
    if isinstance(obj, dict):
        return {k: _scrub_obj(v, mapper, ids, hide) for k, v in obj.items()}
    return obj


def report_text(state: dict) -> str:
    env = state.get("environment", {})
    lines = [f"ChromIQ instrument probe {VERSION}", "",
             f"System: {env.get('system', '?')} {env.get('release', '')} "
             f"({env.get('machine', '?')}), Python {env.get('python', '?')}",
             f"Session: {state.get('session_title')} ({state.get('session_id')})",
             f"Instrument: {state['selection'].get('name', '?')}",
             f"Verdict: {state.get('verdict', '')}", "",
             "Recorder: " + state.get("recorder", "?")]
    for line in state.get("readiness", []):
        lines.append("  " + line)
    if state.get("recorder_diag"):
        lines += ["", "What the recorder did:", state["recorder_diag"]]
    if state.get("other_devices_count") is not None:
        lines += ["", f"Other devices on this computer: {state['other_devices_count']} "
                      "(not named, not recorded)."]
    return "\n".join(lines) + "\n"


def manifest_txt(m: dict) -> str:
    L = [f"WHAT IS IN THIS ZIP  ({m['tool']}, made {m['made']})", "",
         f"Session: {m['session_title']}", f"Instrument: {m['instrument'].get('name', '')}",
         "", "Files:",
         "  MANIFEST.txt    this page",
         "  manifest.json   the same, for programs",
         "  session.json    the blocks, their times, your notes and marks",
         "  notes.txt       the same notes, one line per block",
         "  report.txt      your system and the recorder (no other devices named)",
         "  analysis.txt    the tool's own reading of the recordings"]
    for r in m["recordings"]:
        if r.get("file"):
            L.append(f"  {r['file']}  {r['kept']} records of your instrument ({r['format']})")
    L += ["", "Blocks recorded: " + (", ".join(m["blocks_recorded"]) or "none"),
          "Blocks skipped: " + (", ".join(m["blocks_skipped"]) or "none"),
          "Blocks not reached: " + (", ".join(m["blocks_not_reached"]) or "none")]
    if m["essential_missing"]:
        L.append("Essential blocks still missing: " + ", ".join(m["essential_missing"]))
    L += ["", "What was left out before anything was written (counts only):"]
    total = {}
    for r in m["recordings"]:
        for k, v in (r.get("left_out") or {}).items() if isinstance(r.get("left_out"), dict) \
                else []:
            total[k] = total.get(k, 0) + v
    L += [f"  {v} records: {k}" for k, v in sorted(total.items())] or ["  nothing"]
    L += ["", "What was replaced in what is kept:"]
    L += [f"  {v} x {k}" for k, v in sorted(m["replaced"].items())] or ["  nothing"]
    L += [f"  The instrument's serial number: {m['instrument_serial']}."]
    L += ["", "Where the replaced identifiers were learned from:"]
    L += [f"  {x['what']}: from {x['learned_from']}" for x in m["identifiers_replaced"]] \
        or ["  nothing"]
    L += ["", "Honestly: " + m["what_the_tool_cannot_know"]]
    if m.get("kept_without_description"):
        L.append("KEPT WITHOUT A DESCRIPTION (you agreed after seeing it): "
                 + ", ".join(m["kept_without_description"]) + ". The recording holds no USB "
                 "description of this device, so the tool could not prove it is your "
                 "instrument.")
    if m.get("blocks_that_kept_nothing"):
        L.append("Blocks that kept nothing: " + ", ".join(m["blocks_that_kept_nothing"]))
    if m["encrypted_connections"]:
        L += ["", "Connections treated as encrypted (their contents are zeros here; record "
                  "headers, sizes and times are kept):"]
        L += [f"  {k}: {v['kind']}, {v['zeroed']} bytes replaced by zeros"
              for k, v in m["encrypted_connections"].items()]
    L += ["", "Not in this zip:"] + [f"  {x}" for x in m["not_in_this_zip"]]
    L += ["", "Check it yourself before sending:  instrument_probe --check <this zip>"]
    return "\n".join(L) + "\n"

"""The guided session: choose the instrument, record block by block, make the zip.

Rules carried over from the X-Rite probe's testers, and from the review of
2.0 (2026-11-22):
  * keys typed while the tool was busy are thrown away before every question;
    a recording ends only with "e" and Enter; any other line typed during a
    recording is a mark with its time;
  * a device list has NO default: Enter alone never chooses a device, and a
    router is refused with a plain sentence;
  * the full recordings live in a private folder of this user (0700, files
    0600; on Windows the user's own AppData folder), are filtered as soon as a
    block ends, and are then deleted (kept only when the owner says so, for a
    block that kept nothing); leftovers of an earlier run are dealt with at
    the next start;
  * a block's entry is written to session.json BEFORE it is checked, and an
    error anywhere ends with the session saved and a zip of what exists;
  * a watchdog notices at once when the recorder stops, when a block reaches
    its size or time limit, and when a timed block's time is up.
"""

from __future__ import annotations

import datetime
import json
import os
import shutil
import threading
import time

from . import VERSION, discovery, known, package, recorders, sessions
from .console import StopSession

SAFETY = ("This tool only LISTENS. It never sends anything to your instrument or to any "
          "other device, and it uploads nothing. It keeps only your instrument's traffic, "
          "hides private details, and makes one zip that you can check before you send it.")
MARK_WORDS = {"cancel", "killed", "quit", "power off", "power on", "pulled", "plugged", "home",
              "calibrating", "a", "l", "d", "u", "lights", "error"}


class Env:
    """What the session needs from the outside world (replaced in tests)."""

    def __init__(self):
        self.usb_devices = discovery.usb_devices
        self.neighbours = discovery.neighbours
        self.connections = discovery.connections
        self.gateways = discovery.gateways
        self.refresh_usb = discovery.refresh_usb_selection
        self.readiness = recorders.readiness
        self.make_recorder = recorders.make_recorder
        self.now = time.time
        self.environment = discovery.environment
        self.private_root = recorders.private_root
        self.watch_interval = 1.0


def stamp(now: float) -> str:
    return datetime.datetime.fromtimestamp(now).strftime("%Y%m%d-%H%M%S")


class NotPrivate(Exception):
    pass


def make_private_dir(path: str) -> str:
    os.makedirs(path, mode=0o700, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    if not recorders.restrict_to_user(path):
        raise NotPrivate(path)
    return path


class Session:
    def __init__(self, base: str, state: dict, private_root: str):
        self.base = base
        self.state = state
        self.dir = os.path.join(base, f"probe-session-{state['stamp']}")
        self.state.setdefault("raw_dir", os.path.join(private_root, "raw", state["stamp"]))
        self.full = self.state["raw_dir"]
        self.kept = os.path.join(self.dir, "kept")

    @classmethod
    def resume(cls, folder: str, private_root: str):
        folder = folder.rstrip("/\\")
        with open(os.path.join(folder, "session.json"), encoding="utf-8") as fh:
            state = json.load(fh)
        return cls(os.path.dirname(folder) or ".", state, private_root)

    def prepare(self) -> None:
        make_private_dir(self.dir)
        make_private_dir(self.kept)
        make_private_dir(self.full)
        for name, text in (("session-folder.txt", os.path.abspath(self.dir)),
                           ("owner.pid", str(os.getpid()))):
            fd = os.open(os.path.join(self.full, name), os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                         0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(text + "\n")

    def save(self) -> None:
        make_private_dir(self.dir)
        path = os.path.join(self.dir, "session.json")
        tmp = path + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(self.state, fh, indent=2)
        os.replace(tmp, path)


# ---- small helpers ------------------------------------------------------------

def _menu(ui, title: str, options: list, default: int | None = None) -> int:
    ui.say("")
    ui.say(title)
    for i, (text, hint) in enumerate(options, 1):
        ui.say(f"  {i}. {text}" + (f"   <- {hint}" if hint else ""))
    while True:
        prompt = "  Type a number" + (f", or press Enter for {default}" if default else "") + ": "
        a = ui.ask(prompt).strip()
        if not a and default:
            return default - 1
        if a.isdigit() and 1 <= int(a) <= len(options):
            return int(a) - 1
        if a.lower() in ("q", "quit"):
            raise StopSession("q")
        ui.say("  Please type one of the numbers shown.")


def _pick_many(ui, title: str, options: list) -> list:
    """A device list: no default; one or several numbers, separated by commas."""
    ui.say("")
    ui.say(title)
    for i, text in enumerate(options, 1):
        ui.say(f"  {i}. {text}")
    while True:
        a = ui.ask("  Type the number (several: separated by commas, for example 1,2): ").strip()
        if a.lower() in ("q", "quit"):
            raise StopSession("q")
        parts = [x.strip() for x in a.replace(" ", ",").split(",") if x.strip()]
        if parts and all(x.isdigit() and 1 <= int(x) <= len(options) for x in parts):
            return sorted({int(x) - 1 for x in parts})
        ui.say("  Please type the number of your instrument. Pressing Enter alone chooses "
               "nothing.")


def _yes(ui, prompt: str, default: bool = False) -> bool:
    a = ui.ask(prompt + (" [Y/n] " if default else " [y/N] ")).strip().lower()
    if not a:
        return default
    return a in ("y", "yes", "j", "ja")


TYPES = [("handheld", "a handheld instrument (spot or strip)"),
         ("table", "a motorised table (an arm moves the instrument over the sheet)"),
         ("sheetfed", "a sheet-fed chart reader (it pulls the page in by itself)"),
         ("network", "an instrument connected by network cable or Wi-Fi"),
         ("serial", "a serial (RS-232) instrument on a USB serial adapter"),
         ("other", "something else")]


def choose_type(ui) -> str:
    i = _menu(ui, "What kind of instrument is it?", [(t, "") for _k, t in TYPES])
    return TYPES[i][0]


def choose_transport(ui, session_data: dict) -> str:
    default = 2 if session_data.get("transport") == "net" else 1
    i = _menu(ui, "How is it connected to this computer?",
              [("a USB cable (also a USB serial adapter)", ""),
               ("a network cable or Wi-Fi", ""),
               ("a serial port of the computer itself, without a USB adapter", ""),
               ("Bluetooth", "")], default)
    if i == 2:
        ui.say("")
        ui.say("A serial port built into the computer cannot be listened to: Windows, macOS "
               "and Linux offer no way to do it without installing a special driver. Please "
               "connect the instrument through a USB serial adapter for the recording; then "
               "choose \"a USB cable\".")
        raise StopSession("serial port without adapter")
    if i == 3:
        ui.say("")
        ui.say("Bluetooth recordings are not part of this version yet. If your instrument "
               "can also use a USB cable, please choose that. Otherwise tell us in a GitHub "
               "issue which instrument it is: a later version may help.")
        raise StopSession("bluetooth")
    return "net" if i == 1 else "usb"


def _twins(dev, devices) -> list:
    """Other plugged-in devices the recording could not tell from dev."""
    out = []
    for o in devices:
        if o is dev or (o.vid, o.pid) != (dev.vid, dev.pid):
            continue
        if dev.location is not None and o.location is not None and dev.location != o.location:
            continue                                     # macOS: the location tells them apart
        out.append(o)
    return out


def choose_usb(ui, env, kind: str) -> dict:
    ui.say("")
    ui.say("Finding your instrument. The easiest way: unplug it now, press Enter, plug it "
           "in again, and press Enter once more. The tool then shows only what is new.")
    if kind in ("table", "sheetfed"):
        ui.say("A table or reader is often TWO USB devices (the table itself and the "
               "instrument in its arm). Plug in everything the program uses, and choose "
               "all of them.")
    ui.say("(If you would rather not unplug it, type  l  and press Enter to see the whole "
           "list.)")
    a = ui.ask("  Unplug the instrument, then press Enter (or type l): ").strip().lower()
    before = env.usb_devices()
    if a != "l":
        ui.ask("  Now plug it in, wait five seconds, then press Enter: ")
        after = env.usb_devices()
        new = discovery.new_devices(before, after)
    else:
        after, new = before, []
    candidates = new or after
    if not candidates:
        ui.say("No USB device was found at all. Please check the cable and that the "
               "instrument is switched on, then start the tool again.")
        raise StopSession("no USB device")
    if new:
        ui.say("")
        ui.say("New since you plugged it in:")
    while True:
        opts = []
        for d in candidates:
            verdict = d.verdict()
            opts.append(d.label() + (f"\n       {verdict}" if verdict else ""))
        picks = _pick_many(ui, "Which one is your instrument?", opts)
        chosen = [candidates[i] for i in picks]
        bad = [(d, known.is_unsuitable(d.interfaces)) for d in chosen]
        bad = [(d, why) for d, why in bad if why]
        if bad:
            ui.say(f"That cannot be the instrument: {bad[0][1]}. Please choose again.")
            continue
        twins = [(d, _twins(d, after)) for d in chosen]
        twins = [(d, t) for d, t in twins if t]
        if twins:
            d, t = twins[0]
            ui.say("")
            ui.say(f"Another device with the same USB numbers ({d.ids}) is plugged in. Cheap "
                   "adapters and sticks often share the numbers of serial instruments, and "
                   "a recording cannot always tell them apart, so the tool would keep "
                   "neither. Please unplug the other device now (or the other units), then "
                   "press Enter.")
            ui.ask("  Press Enter when it is unplugged: ")
            after = env.usb_devices()
            if any(_twins(x, after) for x in chosen if x in after or True):
                still = [x for x in after if (x.vid, x.pid) == (d.vid, d.pid)]
                if len(still) > 1 and not (d.location is not None):
                    ui.say("There are still two devices with these numbers. The tool cannot "
                           "record safely like this. Please unplug the other one and start "
                           "the tool again.")
                    raise StopSession("two identical devices")
        break
    devs = [d.selection() for d in chosen]
    sel = {"transport": "usb", "devices": devs,
           "name": " + ".join(d.label() for d in chosen)}
    sel["verdict"] = "; ".join(v for v in (d.verdict() for d in chosen) if v)
    sel["other_devices"] = max(0, len(after) - len(chosen))
    return sel


def choose_network(ui, env) -> dict:
    ui.say("")
    ui.say("Finding your instrument on the network. The tool only reads lists your computer "
           "already keeps; it sends nothing to find it.")
    gateways = set(env.gateways())
    neigh = dict(env.neighbours())
    gw_macs = {neigh.get(g) for g in gateways if neigh.get(g)}
    no_router = not gateways
    if no_router:
        ui.say("")
        ui.say("This computer has no router at all (no default route), for example because its "
               "only network is a cable straight to the instrument. Then there is no internet "
               "traffic to protect; the tool keeps only the traffic of the address you choose.")
    elif not gw_macs:
        ui.say("")
        ui.say("The tool could not identify this computer's router (and its network card). That "
               "happens, for example, while a VPN is connected. Without it the tool cannot make "
               "sure it is not recording your router and your internet traffic, so it does not "
               "record. Please disconnect the VPN (or connect this computer to the network the "
               "instrument is on), then start the tool again.")
        raise StopSession("router unknown")

    def refuse(ip, mac) -> str:
        if ip in gateways or (mac and mac in gw_macs):
            return ("That is your router (this computer's way to the internet), not an "
                    "instrument. Recording it would record your internet traffic, so the tool "
                    "never does that. Please choose your instrument's own address.")
        return ""
    import ipaddress                                      # noqa: PLC0415
    while True:
        i = _menu(ui, "How would you like to find it?",
                  [("start the maker's program and connect it; the tool sees what is new",
                    "easiest"),
                   ("type its address (the program or the instrument's display may show it)",
                    ""),
                   ("choose from the list of devices this computer has seen recently", "")], 1)
        rows = []
        if i == 0:
            ui.ask("  Close the maker's program if it is open, then press Enter: ")
            before = {"neighbours": env.neighbours(), "connections": env.connections()}
            ui.ask("  Now start the program, connect it to the instrument, wait until it shows "
                   "the instrument, then press Enter: ")
            after = {"neighbours": env.neighbours(), "connections": env.connections()}
            rows = discovery.network_candidates(before, after)
            if not rows:
                ui.say("Nothing new was seen. Please type the address instead.")
                i = 1
        if i == 2:
            rows = [(ip, mac, "seen recently") for ip, mac in env.neighbours()]
            if not rows:
                ui.say("The list is empty. Please type the address instead.")
                i = 1
        if i == 1:
            a = ui.ask("  The instrument's address (for example 192.168.1.50): ").strip()
            try:
                ip = ipaddress.ip_address(a)
            except ValueError:
                ui.say("  That is not an address of the form 192.168.1.50.")
                continue
            if ip.version == 6:
                ui.say("  This version records instruments by their IPv4 address only (of the "
                       "form 192.168.1.50). The program or the instrument usually shows one.")
                continue
            rows = [(a, neigh.get(a, ""), "typed by you")]
            choice = 0
        else:
            opts = [f"{ip}" + (f"  ({mac})" if mac else "") + f"  {why}" +
                    ("   (your router)" if refuse(ip, mac) else "")
                    for ip, mac, why in rows]
            choice = _pick_many(ui, "Which one is your instrument?", opts)[0]
        ip, mac, _why = rows[choice]
        why = refuse(ip, mac)
        if why:
            ui.say(why)
            continue
        break
    if not ipaddress.ip_address(ip).is_private:
        ui.say("Note: that is an internet address, not one on your own network. That is "
               "unusual for an instrument; please make sure it is the right one.")
    return {"transport": "net", "ips": [ip], "macs": [mac] if mac else [],
            "gateways": sorted(gateways), "gateway_macs": sorted(gw_macs),
            "no_router": no_router,
            "name": f"network instrument at {ip}",
            "verdict": "", "other_devices": None}


def what_is_kept(sel: dict) -> str:
    if sel["transport"] == "usb":
        return (f"Only the traffic of {sel.get('name')} will be kept: the tool recognises it "
                "by its USB numbers, its serial number or port, and its own description in "
                "the recording. Everything else on the USB connections (keyboards, mice, "
                "disks, hubs, other devices) is left out before anything is written.")
    return (f"Only the traffic to and from {', '.join(sel['ips'])}"
            + (f" (network card {sel['macs'][0]})" if sel.get("macs") else "")
            + " will be kept. Everything else (other computers, your router, web pages, "
            "mail, name look-ups) is left out before anything is written.")


# ---- the watchdog --------------------------------------------------------------

class Watchdog:
    """Runs while a block records: says at once when the recorder stopped,
    stops a block at its size or time limit, and says when a timed block's
    time is up. Never touches the input."""

    def __init__(self, ui, env, recorder, block: dict):
        self.ui, self.env, self.recorder, self.block = ui, env, recorder, block
        self.stop_event = threading.Event()
        self.events: list = []
        self.started = env.now()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.stop_event.set()
        self.thread.join(timeout=5)

    def _say(self, text, what):
        if what not in self.events:
            self.events.append(what)
            self.ui.say("")
            self.ui.say(text)

    def _run(self):
        timer = self.block.get("timer_minutes")
        while not self.stop_event.wait(self.env.watch_interval):
            mins = (self.env.now() - self.started) / 60
            alive = getattr(self.recorder, "alive", lambda: True)()
            if not alive:
                code = getattr(self.recorder, "exit_codes", lambda: [])()
                self._say(f"THE RECORDER STOPPED after {mins:.1f} minutes"
                          + (f" (exit code {', '.join(map(str, code))})" if code else "")
                          + ". Nothing more is being recorded. Type  e  and press Enter; this "
                          "block will be marked as failed, and you can record it again.",
                          "died")
            over = getattr(self.recorder, "over_limit", lambda: "")()
            if over:
                try:
                    self.recorder.stop_early()
                except Exception:                         # noqa: BLE001
                    pass
                stopped = getattr(self.recorder, "alive", lambda: True)() is False or \
                    not getattr(self.recorder, "running", False)
                self._say(f"THIS BLOCK REACHED ITS LIMIT ({over})"
                          + (", so the recording was stopped." if stopped else
                             "; the tool asked the recorder to stop.")
                          + " Type  e  and press Enter.", "limit")
            if timer and mins >= timer:
                self._say(f"TIME IS UP: {timer} minutes have passed. Type  e  and press "
                          "Enter.", "timer")


# ---- the blocks ----------------------------------------------------------------

def _show_block(ui, data, b, index, done):
    ui.say("")
    ui.say("-" * 70)
    ui.say(sessions.progress_line(data, done, index))
    ui.say(f"{b['id']}  {b['title']}   (about {b['minutes']} min, label: {b['label']})")
    if b.get("only_if"):
        ui.say(b["only_if"])
    for i, s in enumerate(b["steps"], 1):
        ui.say(f"  {i}. {s}")
    if b.get("timer_minutes"):
        ui.say(f"The tool will tell you when {b['timer_minutes']} minutes have passed.")
    ui.say(f"Why: {b['why']}")


def _as_path(text: str) -> str:
    """A path as Windows' "Copy as path" or a Mac's drag and drop gives it."""
    t = text.strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'":
        t = t[1:-1]
    if os.name != "nt":
        t = t.replace("\\ ", " ")
    return os.path.expanduser(t)


def _looks_like_path(text: str) -> bool:
    t = text.strip().strip("\"'")
    return ("/" in t or "\\" in t) and t.lower().endswith((".pcap", ".pcapng", ".etl", ".cap"))


def record_block(ui, env, session: Session, recorder, b: dict, label: str) -> dict:
    """One recording. Returns the block's state entry (raw files not yet checked)."""
    st = session.state
    n = sum(1 for x in st["blocks"] if x["id"] == b["id"])
    stem = f"{b['id']}-{label}" + (f"-{n + 1}" if n else "")
    entry = {"id": b["id"], "label": label, "status": "recorded", "raw": [], "kept": [],
             "marks": [], "notes": "", "started": env.now(), "stem": stem}
    if isinstance(recorder, recorders.FileRecorder):
        ui.say("Record this block with your own recorder now. When you have saved its file, "
               "type (or paste) the file's full path here.")
    live = recorder.start(stem)
    if not live:
        ui.say("The recorder could not start. What it said:")
        ui.say(getattr(recorder, "diag_text", lambda: "")() or "(nothing)")
        for note in getattr(recorder, "notes", []):
            ui.say("  " + note)
        entry["status"] = "failed"
        return entry
    ui.say("")
    ui.say("RECORDING. Do the steps above now.")
    devs = st["selection"].get("devices", []) if st["selection"]["transport"] == "usb" else []
    if any(d.get("addresses") for d in devs) and not st.get("described_seen") and \
            not isinstance(recorder, recorders.FileRecorder):
        # Linux writes no description of a device that was plugged in before the
        # recording started; one replug puts it into the recording, so the tool can
        # identify the instrument (review 2 re-check, R-2)
        ui.say("FIRST, so that the recording can identify your instrument: unplug its USB "
               "cable now, wait 3 seconds, plug it in again (into the same port), and wait "
               "until the program sees it again. Type  plugged  and press Enter when done. "
               "Then do the steps above.")
    ui.say("Type a short line and press Enter at any moment to mark it with the time. When "
           "you are done, type  e  and press Enter.")
    interrupted = None
    with Watchdog(ui, env, recorder, b) as dog:
        while True:
            try:
                line = ui.ask("  > ", flush=False)
            except StopSession as why:
                interrupted = why
                break
            text = line.strip()
            if text.lower() == "e":
                break
            if isinstance(recorder, recorders.FileRecorder) and (
                    os.path.isfile(_as_path(text)) or _looks_like_path(text)):
                path = _as_path(text)
                if os.path.isfile(path):
                    recorder.pending.append(path)
                    ui.say("  Got it. Type  e  and press Enter to finish this block.")
                else:
                    ui.say(f"  File not found: {path}. Please check the path and paste it "
                           "again.")
                continue
            if text:
                t = round(env.now() - entry["started"], 1)
                entry["marks"].append({"t": t, "text": text})
                rec = " (recognised)" if text.lower() in MARK_WORDS else ""
                ui.say(f"  marked at {t} s{rec}: {text}")
    if "died" in dog.events:
        entry["status"] = "failed"
        entry["failure"] = "the recorder stopped during the block"
    if "limit" in dog.events:
        entry["limit"] = True
    files = _stop(recorder)
    entry["ended"] = env.now()
    entry["raw"] = [_into_full(session, f) for f in files]
    if interrupted is not None:
        entry["stopped_early"] = True
        raise _Interrupted(entry)
    return entry


class _Interrupted(Exception):
    def __init__(self, entry):
        super().__init__("interrupted")
        self.entry = entry


def _stop(recorder) -> list:
    try:
        return recorder.stop()
    except BaseException as exc:                          # noqa: BLE001
        getattr(recorder, "notes", []).append(f"stopping failed: {exc!r}")
        try:
            return [f for f in getattr(recorder, "files", {}).values() if os.path.exists(f)]
        except Exception:                                 # noqa: BLE001
            return []


def _into_full(session: Session, path: str) -> str:
    """Files of the import route are copied into the private full folder."""
    if os.path.dirname(os.path.abspath(path)) == os.path.abspath(session.full):
        return os.path.basename(path)
    dst = os.path.join(session.full, os.path.basename(path))
    with open(path, "rb") as src, open(dst, "wb") as out:
        shutil.copyfileobj(src, out)
    try:
        os.chmod(dst, 0o600)
    except OSError:
        pass
    return os.path.basename(dst)


def _remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def check_and_tidy(ui, session: Session, b: dict, entry: dict, ask=True) -> None:
    """Filter the block's full recordings into kept files, ask what only the
    owner can answer, then delete the full recordings."""
    st = session.state
    sel = package.zip_selection(st)
    raw_paths = [os.path.join(session.full, f) for f in entry.get("raw", [])]
    for k in entry.get("kept", []):
        _remove(os.path.join(session.kept, k))
    check = package.process_take(raw_paths, sel, session.kept, entry["stem"],
                                 follow=bool(b.get("disconnects")))
    if ask and check.get("new_addresses"):
        na = check["new_addresses"][0]
        ui.say("")
        ui.say(f"The instrument's network card announced a new address: {na['ip']} (seen in "
               f"{na['evidence']}); {na.get('talk', '')}. That happens after a restart. But "
               "behind a Wi-Fi extender another device (a phone, a laptop) can look the same. "
               "If you are not sure, answer no.")
        if _yes(ui, f"  Is {na['ip']} your instrument? Only then is its traffic kept."):
            st.setdefault("confirmed_ips", [])
            if na["ip"] not in st["confirmed_ips"]:
                st["confirmed_ips"].append(na["ip"])
            for k in check["kept_files"]:
                _remove(os.path.join(session.kept, k))
            check = package.process_take(raw_paths, package.zip_selection(st), session.kept,
                                         entry["stem"], follow=bool(b.get("disconnects")))
    if ask and check.get("undescribed"):
        for u in check["undescribed"]:
            dev = next((d for d in st["selection"].get("devices", [])
                        if (d.get("name") or "") == u["device"]), {})
            kinds = sorted({known.CLASS_NAME.get(c, f"class {c}")
                            for c, _s, _p in (tuple(x) for x in dev.get("interfaces") or [])})
            ui.say("")
            ui.say(f"The recording holds {u['records']} records at the address where the "
                   f"system saw {u['device']}"
                   + (f" (the system lists it as: {', '.join(kinds)})" if kinds else "")
                   + ", but no USB description of the device there, so the tool cannot prove "
                   "they are your instrument's. This is what they look like:")
            for k, v in u["by_endpoint"].items():
                ui.say(f"    {k}: {v}")
            for ex in u["examples"]:
                ui.say(f"    first bytes: {ex}")
            ui.say("Standard keyboard and mouse reports, and other small reports shaped like "
                   "them, are left out in any case, but not every keyboard's reports can be "
                   "recognised. Answer yes only if this is your instrument and no USB keyboard "
                   "or mouse is plugged into the same computer port group. If you are unsure, "
                   "answer no, and plug the instrument in again after the recording has "
                   "started: then the recording holds its description and this question does "
                   "not come up.")
            if _yes(ui, "  Are these your instrument's? Keep them?"):
                for d in st["selection"].get("devices", []):
                    if (d.get("name") or "") == u["device"]:
                        d["allow_undescribed"] = True
                st.setdefault("kept_without_description", [])
                if u["device"] not in st["kept_without_description"]:
                    st["kept_without_description"].append(u["device"])
        if st.get("kept_without_description"):
            for k in check["kept_files"]:
                _remove(os.path.join(session.kept, k))
            check = package.process_take(raw_paths, package.zip_selection(st), session.kept,
                                         entry["stem"], follow=bool(b.get("disconnects")))
    entry["kept"] = check.pop("kept_files")
    entry["check"] = {k: v for k, v in check.items() if k != "unreadable"}
    if entry["status"] == "recorded" and not entry["kept"]:
        entry["status"] = "kept nothing"
    for line in package.check_lines(check, st["selection"]["transport"]):
        ui.say(line)
    keep_raw = False
    if ask and not entry["kept"] and raw_paths and check["records"]:
        ui.say("")
        ui.say("This block kept nothing. Its full recording could help a later version find "
               "out why, but it holds EVERYTHING on the USB bus or the network during the "
               "block, for example what you typed on a USB keyboard. It stays only on your "
               "computer, in a folder only you can read.")
        keep_raw = _yes(ui, "  Keep that full recording for now?")
    if keep_raw:
        entry["raw_kept_by_owner"] = True
    else:
        for p in raw_paths:
            _remove(p)
        entry["raw"] = []


def run_blocks(ui, env, session: Session, recorder, data: dict, short: bool) -> None:
    st = session.state
    plan = [b for b in data["blocks"] if not short or b.get("short")]
    for b in plan:
        done = {x["id"] for x in st["blocks"] if x["status"] in ("recorded", "answered",
                                                                 "skipped")}
        if b["id"] in done and not b.get("repeatable"):
            continue
        index = data["blocks"].index(b)
        while True:
            _show_block(ui, data, b, index, {x["id"] for x in st["blocks"]
                                             if x["status"] in ("recorded", "answered")})
            if b["kind"] == "question":
                st["blocks"].append(ask_questions(ui, b))
                session.save()
                break
            a = ui.ask("  Press Enter to start recording, s to skip this block, q to finish: "
                       ).strip().lower()
            if a == "q":
                raise StopSession("q")
            if a == "s":
                st["blocks"].append({"id": b["id"], "label": b["label"], "status": "skipped"})
                session.save()
                break
            label = b["label"]
            if b.get("ask_label"):
                raw = ui.ask("  A short label for this recording (letters, digits, hyphens): ")
                label = "".join(c if c.isalnum() else "-" for c in raw.strip().lower())[:30] \
                    or b["label"]
            if st["selection"]["transport"] == "usb":
                try:
                    env.refresh_usb(st["selection"])
                except Exception:                         # noqa: BLE001
                    pass
            need = 2 * recorders.MAX_BLOCK_MB + 512
            if not recorders.free_space_ok(session.full, need):
                ui.say(f"There is not enough free disk space for a block: the tool needs about "
                       f"{need // 1024} GB free (a block's recording may grow to "
                       f"{recorders.MAX_BLOCK_MB // 1024} GB, and is converted once). Please "
                       "free some space, then press Enter.")
                ui.ask("  Press Enter to try again: ")
                continue
            try:
                entry = record_block(ui, env, session, recorder, b, label)
            except _Interrupted as stop:
                st["blocks"].append(stop.entry)
                session.save()
                _safe_check(ui, session, b, stop.entry, ask=False)
                session.save()
                raise StopSession("stopped during a recording") from None
            st["blocks"].append(entry)
            session.save()                                # before the check (review M7)
            ui.say("")
            _safe_check(ui, session, b, entry)
            c = entry.get("check", {})
            if c.get("kept") and not c.get("undescribed"):
                st["described_seen"] = True
            if entry["status"] == "failed":
                ui.say("This block is marked as failed. Please record it again (r).")
            if b.get("note"):
                entry["notes"] = ui.ask("  " + b["note"] + "\n  Your note (it goes into the "
                                        "zip; Enter to skip): ").strip()
            if b.get("ask_saved_file"):
                entry["saved_file"] = ui.ask("  Did the program save a measurement file in this "
                                             "block? Its name (Enter if none): ").strip()
            session.save()
            write_notes(session)
            again = ui.ask("  Press Enter to go on, r to record this block again, q to finish: "
                           ).strip().lower()
            if again == "q":
                raise StopSession("q")
            if again == "r":
                entry["status"] = "repeated"
                session.save()
                continue
            if b.get("repeatable") and _yes(ui, "  Record another one of this kind?"):
                continue
            break


def _safe_check(ui, session, b, entry, ask=True):
    try:
        check_and_tidy(ui, session, b, entry, ask=ask)
    except StopSession:
        raise
    except BaseException as exc:                          # noqa: BLE001
        entry["status"] = "check failed"
        entry["check_error"] = repr(exc)[:300]
        ui.say(f"The check of this block failed ({type(exc).__name__}). Its recording is kept "
               "in your private folder, and the next start of the tool will try again.")
    finally:
        session.save()


def write_notes(session: Session) -> None:
    path = os.path.join(session.dir, "notes.txt")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(package.notes_text(session.state))


def ask_questions(ui, b: dict) -> dict:
    answers = []
    ui.say("Your answers go into the zip. Please do not type anything private.")
    for q in b.get("questions", []):
        answers.append({"question": q, "answer": ui.ask(f"  {q}\n  > ").strip()})
    return {"id": b["id"], "label": b["label"], "status": "answered", "answers": answers}


# ---- leftovers of an earlier run ----------------------------------------------

def tidy_leftovers(ui, private_root: str) -> None:
    """Full recordings left behind by a run that ended abruptly: filter them
    into their session if it still exists, then delete them."""
    xhc = recorders.read_marker("xhc")
    if xhc and xhc.get("interfaces"):
        names = ", ".join(xhc["interfaces"])
        ui.say(f"An earlier run left the Mac's USB recording interfaces ({names}) switched on. "
               "They switch off by themselves when the Mac restarts; to do it now, type in "
               "Terminal:  sudo ifconfig <name> down  for each of them.")
        recorders.clear_marker("xhc")
    root = os.path.join(private_root, "raw")
    if not os.path.isdir(root):
        return
    removed = rescued = 0
    for name in sorted(os.listdir(root)):
        folder = os.path.join(root, name)
        if not os.path.isdir(folder):
            continue
        try:
            with open(os.path.join(folder, "owner.pid"), encoding="utf-8") as fh:
                if recorders.pid_alive(int(fh.read().strip() or 0)):
                    continue                     # a session running in another window
        except (OSError, ValueError):
            pass
        sess_dir = ""
        try:
            with open(os.path.join(folder, "session-folder.txt"), encoding="utf-8") as fh:
                sess_dir = fh.read().strip()
        except OSError:
            pass
        state = None
        try:
            with open(os.path.join(sess_dir, "session.json"), encoding="utf-8") as fh:
                state = json.load(fh)
        except (OSError, ValueError):
            state = None
        keep = set()
        if state:
            s = Session(os.path.dirname(sess_dir), state, private_root)
            for e in state["blocks"]:
                if e.get("raw_kept_by_owner"):
                    keep |= set(e.get("raw", []))
                    continue
                if e.get("raw"):
                    try:
                        check_and_tidy(_Quiet(), s, {"disconnects": False}, e, ask=False)
                        rescued += 1
                    except BaseException:                 # noqa: BLE001
                        pass
            s.save()
        for f in os.listdir(folder):
            if f in keep or f in ("session-folder.txt", "owner.pid") and keep:
                continue
            _remove(os.path.join(folder, f))
            removed += 1
        try:
            os.rmdir(folder)
        except OSError:
            pass
    if removed or rescued:
        ui.say(f"Tidied up after an earlier run: {rescued} block(s) checked, {removed} "
               "leftover file(s) of full recordings deleted.")


class _Quiet:
    def say(self, text=""):
        pass

    def ask(self, prompt, flush=True):
        return ""


# ---- the whole thing -------------------------------------------------------------

def guided(ui, env=None, base: str = ".", args=None) -> int:
    """The interactive session. Returns an exit code."""
    env = env or Env()
    args = args or {}
    session = None
    recorder = None
    try:
        ui.say("")
        ui.say(f"ChromIQ instrument probe {VERSION}")
        ui.say("")
        ui.say(SAFETY)
        tidy_leftovers(ui, env.private_root())
        if args.get("resume"):
            session = Session.resume(args["resume"], env.private_root())
            st = session.state
            data = sessions.load(st["session_file"]) if st.get("session_file") \
                else sessions.builtin(st["type"])
            for h in args.get("hide") or []:
                if h not in st.setdefault("hide", []):
                    st["hide"].append(h)
            if args.get("keep_serial"):
                st["keep_serial"] = True
            session.save()
            ui.say("")
            ui.say(f"Continuing the session from {st['stamp']} ({data['title']}).")
            if args.get("remake"):
                return finish(ui, session, None)
            sel = st["selection"]
        else:
            data = sessions.load(args["session_file"]) if args.get("session_file") else None
            kind = data["id"] if data else (args.get("type") or choose_type(ui))
            data = data or sessions.builtin(kind)
            transport = choose_transport(ui, data)
            ready = env.readiness(transport)              # before any question (review m12)
            if not ready["can"] and not args.get("import_mode"):
                ui.say("")
                for line in ready["lines"]:
                    ui.say(line)
                for o in ready["options"]:
                    ui.say("  - " + o)
                ui.say("")
                ui.say("You can still record with your own recorder and give the files to "
                       "this tool: start it again with  --import  (see the README).")
                return 2
            if ready.get("admin") and not args.get("import_mode") and \
                    ready["kind"] in ("usbpcap", "pktmon"):
                ui.say("")
                ui.say(ready["admin"])
                return 2
            sel = choose_usb(ui, env, kind) if transport == "usb" else choose_network(ui, env)
            ui.say("")
            ui.say(what_is_kept(sel))
            now = env.now()
            state = {"tool": VERSION, "stamp": stamp(now), "type": kind,
                     "session_id": data["id"], "session_title": data["title"],
                     "session_file": os.path.abspath(args["session_file"])
                     if args.get("session_file") else None,
                     "selection": sel, "verdict": sel.pop("verdict", ""),
                     "other_devices_count": sel.pop("other_devices", None),
                     "keep_serial": bool(args.get("keep_serial")),
                     "hide": list(args.get("hide") or []),
                     "environment": env.environment(), "blocks": [],
                     "plan": [{"id": b["id"], "priority": b["priority"]} for b in data["blocks"]]}
            if sel["transport"] == "usb" and not args.get("keep_serial"):
                ui.say("")
                ui.say("Your instrument's serial number is part of the conversation (the "
                       "program reads it every time). It identifies the instrument, not you. "
                       "By default it is replaced by a placeholder in the zip.")
                state["keep_serial"] = _yes(ui, "  Keep the real serial number in the zip?")
            session = Session(base, state, env.private_root())
        ready = env.readiness(sel["transport"])
        imported = args.get("import_mode")
        if not ready["can"] and not imported:
            for line in ready["lines"]:
                ui.say(line)
            return 2
        if imported and sel["transport"] == "usb":
            # review 2, S-B1: an imported file was not made with this computer's
            # USB addresses; only the recording's own descriptions count
            for d in sel.get("devices", []):
                d.pop("addresses", None)
                d.pop("port_path", None)
        session.prepare()
        session.state["readiness"] = ready["lines"]
        session.state["recorder_kind"] = "import" if imported else ready["kind"]
        if sel["transport"] == "net":
            sel["dedupe"] = ready["kind"] == "pktmon" and not imported
        session.save()
        ui.say("")
        for line in ready["lines"]:
            ui.say(line)
        if ready.get("admin") and not imported:
            ui.say(ready["admin"])
        recorder = recorders.FileRecorder(sel["transport"]) if imported else \
            env.make_recorder(ready["kind"], session.full, sel)
        session.state["recorder"] = recorder.label
        left = recorder.leftover() if hasattr(recorder, "leftover") else None
        if left:
            ui.say("")
            ui.say(("A network recording this tool started earlier is still running"
                    if left.get("certain") else
                    "A pktmon network recording is running. It MAY be one this tool started "
                    "earlier (after a power cut the tool cannot be sure; it could also be one "
                    "you or another program started)")
                   + ". It records ALL of this computer's network traffic. The tool can stop it "
                   f"now with the command:  {recorder.STOP_BY_HAND}")
            if _yes(ui, "  Stop it now?"):
                recorder.stop_leftover()
                ui.say("Stopped.")
            else:
                ui.say("Left running. To stop it later: open Command Prompt as administrator "
                       f"and type  {recorder.STOP_BY_HAND}")
                return 2
        if not recorder.session_start():
            ui.say("The recorder could not be prepared:")
            for n in recorder.notes:
                ui.say("  " + n)
            return 2
        ui.say("")
        ui.say(f"Session: {data['title']}. {len(data['blocks'])} blocks, about "
               f"{sessions.minutes(data['blocks'])} minutes; the short set takes about "
               f"{sessions.minutes(sessions.short_set(data))} minutes.")
        ui.say("Before you start:")
        for x in data.get("before_you_start", []):
            ui.say("  - " + x)
        short = args.get("short")
        if short is None:
            short = _menu(ui, "Which set would you like to record?",
                          [("all blocks (you can stop after any block)", "best"),
                           ("only the short set (about 20 minutes)", "")], 1) == 1
        run_blocks(ui, env, session, recorder, data, short)
    except NotPrivate as where:
        ui.say("")
        ui.say(f"The tool could not make the folder {where} private to your user (Windows' "
               "icacls did not succeed), so it does not record into it. Please move the tool "
               "into a folder of your own (for example in Documents) and start it again.")
        return 2
    except StopSession as why:
        if session is None:
            ui.say("")
            ui.say(f"Stopped ({why}). Nothing was recorded.")
            return 4
        ui.say("")
        ui.say("Stopping. What you finished is kept.")
    except BaseException as exc:                          # noqa: BLE001
        if session is None:
            ui.say(f"The tool stopped because of an error ({type(exc).__name__}: {exc}). "
                   "Nothing was recorded.")
            return 1
        ui.say("")
        ui.say(f"The tool ran into an error ({type(exc).__name__}). What you finished is kept, "
               "and the zip is made from it now.")
    finally:
        if recorder is not None:
            try:
                recorder.session_end()
            except BaseException:                         # noqa: BLE001
                pass
    try:
        return finish(ui, session, recorder)
    except BaseException as exc:                          # noqa: BLE001
        ui.say(f"The zip could not be made ({type(exc).__name__}: {exc}). Your session is "
               f"saved in {session.dir}: start the tool again with  --remake {session.dir}  "
               "once the problem (for example a full disk) is solved.")
        return 2


def finish(ui, session: Session, recorder=None) -> int:
    st = session.state
    if recorder is not None and hasattr(recorder, "diag_text"):
        st["recorder_diag"] = recorder.diag_text()
    session.save()
    recorded = [b for b in st["blocks"] if b.get("kept")]
    if not recorded and not any(b["status"] == "answered" for b in st["blocks"]):
        if not any(b["status"] in ("kept nothing", "failed", "check failed")
                   for b in st["blocks"]):
            ui.say("No block was recorded, so there is nothing to send.")
            return 4
    zip_path = os.path.join(session.base, f"SEND-THIS-{st['stamp']}.zip")
    manifest = package.build_zip(st, session.dir, None, zip_path)
    ui.say("")
    ui.say("=" * 70)
    ui.say(f"Done. The file to send is:\n  {zip_path}")
    ui.say("")
    ui.say("Recorded: " + (", ".join(manifest["blocks_recorded"]) or "none") + ".")
    if manifest.get("blocks_that_kept_nothing"):
        ui.say("Kept nothing: " + ", ".join(manifest["blocks_that_kept_nothing"]) + ".")
    if manifest["essential_missing"]:
        ui.say("Essential blocks not recorded yet: " + ", ".join(manifest["essential_missing"])
               + ". You can add them later with  --resume " + session.dir)
    ui.say("")
    ui.say("Please look at it before you send it: run the tool with  --check " + zip_path +
           "  and it shows you everything that is inside.")
    ui.say("Send it by opening a new issue at github.com/itsab1989/ChromIQ/issues and "
           "attaching it (an issue is public), together with the measurement files the "
           "program saved. Nothing is promised, but every recording helps.")
    ui.say("")
    ui.say(f"The session folder {session.dir} holds only your instrument's traffic, but "
           "with the real serial numbers and addresses; it is needed to add blocks or make the "
           "zip again (--remake). Only you can read it. Delete it when you no longer need it.")
    if any(b.get("raw_kept_by_owner") for b in st["blocks"]):
        ui.say(f"You kept the full recording of a block that kept nothing, in {session.full}. "
               "Never send that folder: it holds everything recorded during that block. "
               "Delete it when you no longer need it.")
    return 0 if recorded else 2

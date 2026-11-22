"""Command line: the guided session, --check, --analyze and the helpers.

Exit codes:
  0  done (a zip was made, or a check found nothing)
  1  wrong use (an option or a file that cannot be read)
  2  nothing could be recorded or kept on this computer (the reason is shown)
  3  --check found something that should not be sent
  4  stopped before anything was recorded
"""

from __future__ import annotations

import argparse
import os
import sys

from . import VERSION, analyze, check, discovery, runner, sessions
from .console import Console, StopSession, quick_edit_off

DESCRIPTION = """\
A read-only recorder for colour measuring instruments. Run it while you use
the maker's own program: it listens, keeps only your instrument's traffic,
hides private details, and makes one SEND-THIS zip. It never sends anything
to any device and uploads nothing. Without options it guides you."""

EPILOG = """\
examples:
  instrument_probe.py                        the guided session
  instrument_probe.py --type table --short   a table, only the short set
  instrument_probe.py --resume probe-session-20261122-101500
  instrument_probe.py --check SEND-THIS-20261122-101500.zip
  instrument_probe.py --analyze SEND-THIS-20261122-101500.zip --diff strip cancel-reading
  instrument_probe.py --sessions             what each kind of instrument is asked to record
"""


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="instrument_probe", description=DESCRIPTION, epilog=EPILOG,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"ChromIQ instrument probe {VERSION}")
    g = p.add_argument_group("the guided session")
    g.add_argument("--type", choices=sessions.BUILTIN_ORDER,
                   help="the kind of instrument (otherwise the tool asks)")
    g.add_argument("--session", metavar="FILE", help="a session file for one particular "
                   "instrument (see SESSIONS.md)")
    g.add_argument("--short", action="store_true", default=None,
                   help="only the short set (about 20 minutes, with an untidy ending)")
    g.add_argument("--resume", metavar="FOLDER", help="continue an earlier session folder")
    g.add_argument("--remake", metavar="FOLDER", help="make the zip of a session folder again "
                   "(for example with --hide), without recording anything")
    g.add_argument("--import", dest="import_mode", action="store_true",
                   help="you record with your own recorder (Wireshark, a hardware sniffer) "
                   "and give each block's file to the tool")
    g.add_argument("--keep-instrument-serial", dest="keep_serial", action="store_true",
                   help="keep the instrument's real serial number in the zip")
    g.add_argument("--hide", action="append", metavar="TEXT", default=[],
                   help="also replace this text wherever it appears (repeatable)")
    g.add_argument("--folder", metavar="FOLDER", default=None,
                   help="where the session folder and the zip go (default: next to the tool)")
    g.add_argument("--no-pause", action="store_true",
                   help="do not wait for Enter at the end (the launchers use this)")
    t = p.add_argument_group("looking at recordings (sends nothing, changes nothing)")
    t.add_argument("--check", metavar="ZIP", help="show what is inside a SEND-THIS zip and "
                   "look for anything that should not be sent")
    t.add_argument("--analyze", nargs="+", metavar="PATH",
                   help="timeline and command forms of recordings (files, folders or a zip)")
    t.add_argument("--diff", nargs=2, metavar=("LABEL_A", "LABEL_B"),
                   help="with --analyze: what differs between two labelled recordings")
    t.add_argument("--json", metavar="OUT", help="with --analyze: also write the result as JSON")
    h = p.add_argument_group("helpers")
    h.add_argument("--sessions", action="store_true", help="list the built-in sessions")
    h.add_argument("--validate-session", metavar="FILE", help="check a session file you wrote")
    h.add_argument("--devices", action="store_true",
                   help="list the USB devices this computer sees (read only)")
    return p


def _default_folder() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return here if os.access(here, os.W_OK) else os.getcwd()


def main(argv=None, ui=None, env=None) -> int:
    args = parser().parse_args(argv)
    ui = ui or Console()
    try:
        if args.check:
            if not os.path.isfile(args.check):
                ui.say(f"There is no file {args.check}.")
                return 1
            res = check.check_zip(args.check)
            ui.say(check.render(res, args.check))
            return 3 if res["problems"] else 0
        if args.analyze:
            missing = [p for p in args.analyze if not os.path.exists(p)]
            if missing:
                ui.say("Not found: " + ", ".join(missing))
                return 1
            files = analyze.load_inputs(args.analyze)
            if args.diff:
                ui.say(analyze.render_diff(analyze.diff(files, *args.diff), *args.diff))
            else:
                ui.say(analyze.analyze_blobs(files))
            if args.json:
                with open(args.json, "w", encoding="utf-8") as fh:
                    fh.write(analyze.to_json(files))
                ui.say(f"Wrote {args.json}.")
            return 0
        if args.sessions:
            for d in sessions.all_builtin():
                ess = sessions.short_set(d)
                ui.say(f"{d['id']:9s} {d['title']}: {len(d['blocks'])} blocks, about "
                       f"{sessions.minutes(d['blocks'])} min; short set {len(ess)} blocks, "
                       f"about {sessions.minutes(ess)} min")
            return 0
        if args.validate_session:
            try:
                d = sessions.load(args.validate_session)
            except (OSError, sessions.SessionError) as exc:
                ui.say(f"Not usable yet:\n{exc}")
                return 1
            ui.say(f"Fine: {d['title']}, {len(d['blocks'])} blocks.")
            return 0
        if args.devices:
            devs = discovery.usb_devices()
            if not devs:
                ui.say("No USB devices were found.")
            for d in devs:
                v = d.verdict()
                ui.say(f"{d.label()}" + (f"\n    {v}" if v else ""))
            return 0
        if args.session:
            try:
                sessions.load(args.session)
            except (OSError, sessions.SessionError) as exc:
                ui.say(f"The session file cannot be used:\n{exc}")
                return 1
        folder = args.remake or args.resume
        if folder and not os.path.isfile(os.path.join(folder.rstrip("/\\"), "session.json")):
            ui.say(f"{folder} is not a session folder (it has no session.json).")
            return 1
        restore = quick_edit_off()
        try:
            code = runner.guided(ui, env=env, base=args.folder or _default_folder(),
                                 args={"type": args.type, "session_file": args.session,
                                       "short": args.short, "resume": folder,
                                       "remake": bool(args.remake),
                                       "import_mode": args.import_mode,
                                       "keep_serial": args.keep_serial, "hide": args.hide})
        finally:
            restore()
        if not args.no_pause and isinstance(ui, Console) and sys.stdin and sys.stdin.isatty():
            try:
                ui.ask("\nPress Enter to close this window.")
            except StopSession:
                pass
        return code
    except StopSession:
        return 4

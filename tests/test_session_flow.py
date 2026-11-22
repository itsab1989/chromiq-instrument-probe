"""The whole guided session with a fake recorder and scripted answers: the
zip holds only the instrument, says what was recorded and skipped, and
passes --check; a session can be continued with --resume."""

import json
import os
import zipfile

from chromiq_probe import check, cli, discovery, runner
from chromiq_probe.console import Scripted
from synth import SERIAL, XFER_INT, NetWriter, UsbPcapWriter, eth, tcp, udp
from synth import DEV_IP, DEV_MAC, HOST_IP, HOST_MAC, OTHER_IP, OTHER_MAC
from test_usb_filter import DISK_DATA, EPS, INSTR, PID, TYPED, VID, build

INSTRUMENT = discovery.UsbDevice(VID, PID, "Spectro One", "Maker", "SN7Q4X9Z2K")
KEYBOARD = discovery.UsbDevice(0x046D, 0xC31C, "Keyboard", "Logi",
                               interfaces=[(3, 1, 1)])


class FakeRecorder:
    label = "fake recorder"
    transport = "usb"

    def __init__(self, outdir, make):
        self.outdir, self.make = outdir, make
        self.notes, self.interfaces, self.stem = [], ["fake"], None
        self.started = self.ended = 0

    def session_start(self):
        self.started += 1
        return True

    def session_end(self):
        self.ended += 1

    def start(self, stem):
        self.stem = stem
        return ["fake"]

    def stop(self):
        path = os.path.join(self.outdir, f"{self.stem}-fake-full.pcap")
        self.make(self.stem).save(path)
        return [path]

    def diag_text(self):
        return "fake: ran"


def usb_recording(stem):
    w = build(UsbPcapWriter())
    if "cable-pull" in stem:
        w.describe(9, VID, PID, EPS)
        w.bulk_out(9, 0x02, b"AFTER-REPLUG\r")
    return w


def make_env(transport="usb", make=usb_recording, devices=None, private=None):
    env = runner.Env()
    import tempfile
    priv = private or tempfile.mkdtemp(dir=os.environ["CHROMIQ_PROBE_HOME"])
    env.private_root = lambda: priv
    env.gateways = lambda: ["192.168.178.1"]
    import ipaddress as _ip
    env.network_facts = lambda: {"routes": [("192.168.178.1", "en0")],
                                 "networks": {"en0": [_ip.ip_interface("192.168.178.23/24")]}}
    env.refresh_usb = lambda sel: None
    env.watch_interval = 0.01
    seq = [[KEYBOARD], [KEYBOARD, INSTRUMENT]] if devices is None else devices
    calls = {"n": 0}

    def usb_devices():
        calls["n"] += 1
        return seq[min(calls["n"] - 1, len(seq) - 1)]
    env.usb_devices = usb_devices
    env.readiness = lambda t: {"can": True, "kind": "fake", "lines": ["fake ready"],
                               "options": [], "admin": ""}
    env.recorders = []

    def mk(kind, outdir, sel):
        r = FakeRecorder(outdir, make)
        env.recorders.append(r)
        return r
    env.make_recorder = mk
    t = {"now": 1_800_000_000.0}

    def now():
        t["now"] += 1.5
        return t["now"]
    env.now = now
    env.environment = lambda: {"system": "Testing", "release": "1", "machine": "x",
                               "python": "3"}
    return env


ANSWERS_USB = [
    "",            # connected by USB (default)
    "", "",        # unplug, plug in
    "1",           # choose the one new device (a device list has no default)
    "",            # keep the serial? no
    # H01
    "", "the program showed the model", "e", "it found it by itself", "",
    # H02 skipped
    "s",
    # H03
    "", "e", "", "q",
]


def run_usb(tmp_path, answers=ANSWERS_USB, extra=()):
    ui = Scripted(list(answers))
    env = make_env()
    code = cli.main(["--type", "handheld", "--short", "--folder", str(tmp_path), "--no-pause",
                     *extra], ui=ui, env=env)
    return code, ui, env


def the_zip(tmp_path):
    zips = [p for p in os.listdir(tmp_path) if p.startswith("SEND-THIS-")]
    assert len(zips) == 1, zips
    return os.path.join(tmp_path, zips[0])


def test_usb_session_makes_a_clean_zip(tmp_path):
    code, ui, env = run_usb(tmp_path)
    assert code == 0, ui.text()
    path = the_zip(tmp_path)
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        assert {"MANIFEST.txt", "manifest.json", "session.json", "report.txt",
                "analysis.txt"} <= set(names)
        recs = [n for n in names if n.startswith("recordings/")]
        assert recs == ["recordings/H01-start.pcap", "recordings/H03-strip.pcap"]
        everything = b"".join(z.read(n) for n in names)
        manifest = json.loads(z.read("manifest.json"))
        session = json.loads(z.read("session.json"))
    assert DISK_DATA not in everything and TYPED not in everything
    assert SERIAL.encode() not in everything and SERIAL.encode("utf-16-le") not in everything
    assert b"KBSERIAL99" not in everything
    assert manifest["blocks_recorded"] == ["H01", "H03"]
    assert manifest["blocks_skipped"] == ["H02"]
    assert "H04" in manifest["essential_missing"] and "Q1" in manifest["essential_missing"]
    assert manifest["instrument_serial"] == "replaced by a placeholder"
    h01 = [b for b in session["blocks"] if b["id"] == "H01"][0]
    assert h01["marks"][0]["text"] == "the program showed the model"
    assert h01["notes"] == "it found it by itself"
    assert env.recorders[0].ended == 1          # the recorder was wound up
    res = check.check_zip(path, ids={})
    assert res["problems"] == [], res["problems"]
    from chromiq_probe import sessions
    d = sessions.builtin("handheld")
    assert (f"Block 1 of {len(d['blocks'])} (essential). Essential blocks done: 0 of "
            f"{len(sessions.essential(d))}.") in ui.text()
    assert "GOOD: kept" in ui.text()


def test_keyboard_cannot_be_chosen(tmp_path):
    ui = Scripted(["", "l", "1", "2", "", "q"])
    env = make_env(devices=[[KEYBOARD, INSTRUMENT]])
    cli.main(["--type", "handheld", "--short", "--folder", str(tmp_path), "--no-pause"],
             ui=ui, env=env)
    assert "That cannot be the instrument: it is a keyboard or a mouse" in ui.text()


def test_stop_before_anything_records_nothing(tmp_path):
    ui = Scripted(["q"])
    code = cli.main(["--type", "handheld", "--folder", str(tmp_path), "--no-pause"], ui=ui,
                    env=make_env())
    assert code == 4
    assert not [p for p in os.listdir(tmp_path) if p.startswith("SEND-THIS-")]


def test_resume_adds_blocks_and_one_zip_holds_both_sittings(tmp_path):
    code, _ui, _env = run_usb(tmp_path)
    assert code == 0
    folder = [p for p in os.listdir(tmp_path) if p.startswith("probe-session-")
              and not p.endswith("do-not-send")][0]
    os.remove(the_zip(tmp_path))
    # second sitting: H05 (the next block of the short set) is next; record it, then stop
    ui = Scripted(["", "e", "", "q"])
    code = cli.main(["--resume", os.path.join(tmp_path, folder), "--short", "--folder",
                     str(tmp_path), "--no-pause"], ui=ui, env=make_env())
    assert code == 0, ui.text()
    with zipfile.ZipFile(the_zip(tmp_path)) as z:
        manifest = json.loads(z.read("manifest.json"))
    assert manifest["blocks_recorded"] == ["H01", "H03", "H05"]


def test_cable_pull_block_follows_the_instrument(tmp_path):
    # the full set, straight to H14 by skipping everything before it
    answers = ["", "", "", "1", "", ""] + ["s"] * 16 + ["", "e", "", "q"]
    ui = Scripted(answers)
    code = cli.main(["--type", "handheld", "--folder", str(tmp_path), "--no-pause"],
                    ui=ui, env=make_env())
    assert code == 0, ui.text()
    with zipfile.ZipFile(the_zip(tmp_path)) as z:
        blob = z.read("recordings/H14-cable-pull.pcap")
    assert b"AFTER-REPLUG\r" in blob


def net_recording(stem):
    w = NetWriter()
    w.add(eth(DEV_MAC, HOST_MAC, 0x0800, tcp(HOST_IP, DEV_IP, 50123, 5000, b"*IDN?\r\n")))
    w.add(eth(HOST_MAC, DEV_MAC, 0x0800, tcp(DEV_IP, HOST_IP, 5000, 50123,
                                              b"SPECTRO,1.2\r\n")))
    w.add(eth(HOST_MAC, OTHER_MAC, 0x0800, udp(OTHER_IP, HOST_IP, 9, 9, b"OTHER-HOST-SECRET")))
    return w

def test_network_session_by_typed_address(tmp_path):
    env = make_env(make=lambda stem: _Saver(net_recording(stem)))
    env.neighbours = lambda: [(DEV_IP, "00:c0:ee:11:22:33"), ("192.168.178.1", "e8:df:70:01:02:03")]
    env.connections = lambda: []
    ui = Scripted(["2", DEV_IP, "", "e", "", "q"])    # N01: record, note, quit
    code = cli.main(["--type", "network", "--short", "--folder", str(tmp_path), "--no-pause"],
                    ui=ui, env=env)
    assert code == 0, ui.text()
    path = the_zip(tmp_path)
    with zipfile.ZipFile(path) as z:
        everything = b"".join(z.read(n) for n in z.namelist())
    assert b"SPECTRO,1.2\r\n" in everything and b"OTHER-HOST-SECRET" not in everything
    assert DEV_IP.encode() not in everything and HOST_IP.encode() not in everything
    assert DEV_MAC not in everything and HOST_MAC not in everything
    assert check.check_zip(path, ids={})["problems"] == []


class _Saver:
    def __init__(self, w):
        self.w = w

    def save(self, path):
        with open(path, "wb") as fh:
            fh.write(self.w.pcap())


def test_check_finds_a_planted_foreign_record(tmp_path):
    code, _ui, _env = run_usb(tmp_path)
    assert code == 0
    path = the_zip(tmp_path)
    bad = os.path.join(tmp_path, "planted.zip")
    other = UsbPcapWriter()
    other.describe(INSTR, VID, PID, EPS)
    other.bulk_in(5, 0x81, TYPED, xfer=XFER_INT)       # a keyboard's typed key
    with zipfile.ZipFile(path) as src, zipfile.ZipFile(bad, "w") as dst:
        for n in src.namelist():
            dst.writestr(n, src.read(n))
        dst.writestr("recordings/H99-planted.pcap", other.pcap())
    res = check.check_zip(bad, ids={})
    assert any("do not belong" in p or "typed keys" in p for p in res["problems"])
    assert cli.main(["--check", bad], ui=Scripted([])) == 3


def test_check_finds_this_computers_name(tmp_path):
    code, _ui, _env = run_usb(tmp_path)
    path = the_zip(tmp_path)
    res = check.check_zip(path, ids={"host": "fixture"})       # "fixture" is in no file
    assert res["problems"] == []
    res = check.check_zip(path, ids={"host": "MANIFEST"})      # a word that IS in the zip
    assert any("host" in p for p in res["problems"])


def test_notes_txt_and_saved_file_name_reach_the_zip(tmp_path):
    # short set: H01, H02, H03, H05, H06 skipped, H07 recorded with its saved file
    answers = ["", "", "", "1", ""] + ["s"] * 5 + ["", "e", "rows 1 to 3", "chart-A.txt", "q"]
    ui = Scripted(answers)
    code = cli.main(["--type", "handheld", "--short", "--folder", str(tmp_path), "--no-pause"],
                    ui=ui, env=make_env())
    assert code == 0, ui.text()
    with zipfile.ZipFile(the_zip(tmp_path)) as z:
        notes = z.read("notes.txt").decode()
    assert "H07 reference-chart recorded" in notes
    assert "rows 1 to 3 (saved file: chart-A.txt)" in notes
    assert "H01 start skipped" in notes


def test_user_and_host_names_inside_recorded_bytes_are_replaced(tmp_path):
    def rec(stem):
        w = build(UsbPcapWriter())
        w.bulk_out(INSTR, 0x02, b"OPERATOR=jdoe-user;PC=Studio-PC\r")
        return w
    ui = Scripted(list(ANSWERS_USB))
    env = make_env(make=rec)
    from chromiq_probe import package
    orig = package.privacy.computer_identifiers
    package.privacy.computer_identifiers = lambda: {"user": "jdoe-user", "host": "Studio-PC"}
    try:
        code = cli.main(["--type", "handheld", "--short", "--folder", str(tmp_path),
                         "--no-pause"], ui=ui, env=env)
    finally:
        package.privacy.computer_identifiers = orig
    assert code == 0
    with zipfile.ZipFile(the_zip(tmp_path)) as z:
        everything = b"".join(z.read(n) for n in z.namelist())
    assert b"jdoe-user" not in everything and b"Studio-PC" not in everything
    assert b"OPERATOR=user1____;PC=computer1" in everything


def test_import_route_cleans_a_file_made_by_another_recorder(tmp_path):
    own = tmp_path / "wireshark-take.pcapng"
    build(UsbPcapWriter()).save(own)
    env = make_env()
    env.readiness = lambda t: {"can": False, "kind": None, "lines": ["no recorder here"],
                               "options": [], "admin": "would need admin"}
    out = tmp_path / "out"
    out.mkdir()
    ui = Scripted(["", "", "", "1", "", "", str(own), "e", "", "q"])
    code = cli.main(["--type", "handheld", "--short", "--import", "--folder", str(out),
                     "--no-pause"], ui=ui, env=env)
    assert code == 0, ui.text()
    with zipfile.ZipFile(the_zip(out)) as z:
        blob = z.read("recordings/H01-start.pcap")
    assert b"MEASURE\r" in blob and DISK_DATA not in blob and TYPED not in blob
    assert own.exists()                                  # the owner's file is left alone

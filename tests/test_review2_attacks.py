"""The second (privacy) review's attacks of 2026-11-22 (attack2.py, attack2b.py), each
asserting on the zip's bytes. Made-up bytes only."""

import json
import os
import zipfile

from chromiq_probe import check, cli, package, runner
from chromiq_probe.console import Scripted
from synth import XFER_INT, NetWriter, UsbmonWriter, UsbPcapWriter, arp, eth, tcp, udp
from test_review_attacks import (DEV_IP, DEV_MAC, EPS, HOST_IP, HOST_MAC, NSEL, PID, RTR_IP,
                                 RTR_MAC, STAMP, VID, _W, everything, make_zip, net_zip, usb_sel)

KEY = b"\x00\x00\x13\x00\x00\x00\x00\x00"


def records_of(zp):
    with zipfile.ZipFile(zp) as z:
        return b"".join(z.read(n) for n in z.namelist() if n.endswith(".pcap"))


# ---- S-B1: keystrokes at the system's address, no description -------------------------

def test_sb1_a1_keyboard_at_the_seeded_address_is_held_back(tmp_path):
    w = UsbmonWriter()
    w.bulk_in(3, 0x81, KEY, xfer=XFER_INT)
    w.bulk_in(3, 0x81, b"\x02\x00\x04\x00\x00\x00\x00\x00", xfer=XFER_INT)
    zp, _m, st = make_zip(tmp_path, [("x", w)], usb_sel(addresses=[[1, 3]], serial="FTAB12CD"))
    rec = records_of(zp)
    assert KEY not in rec and b"\x02\x00\x04" not in rec
    lines = " ".join(package.check_lines(st["blocks"][0]["check"], "usb"))
    assert "HELD BACK" in lines and "GOOD" not in lines


def test_sb1_keystrokes_are_dropped_even_when_the_owner_keeps_an_undescribed_device(tmp_path):
    w = UsbmonWriter()
    w.bulk_in(3, 0x81, KEY, xfer=XFER_INT)
    w.bulk_out(3, 0x02, b"MEASURE\r")
    w.bulk_in(3, 0x81, b"\x01\x10\x80", xfer=XFER_INT)          # mouse-shaped
    zp, man, _st = make_zip(tmp_path, [("x", w)],
                            usb_sel(addresses=[[1, 3]], allow_undescribed=True))
    rec = records_of(zp)
    assert KEY not in rec and b"MEASURE\r" in rec and b"\x01\x10\x80" not in rec


def test_sb1_the_owner_is_shown_what_it_looks_like_and_the_check_says_so(tmp_path):
    from test_session_flow import make_env, ANSWERS_USB

    def rec(stem):
        w = UsbmonWriter()
        w.bulk_out(3, 0x02, b"MEASURE\r")
        w.bulk_in(3, 0x81, KEY, xfer=XFER_INT)
        return w
    from chromiq_probe import discovery
    inst = discovery.UsbDevice(VID, PID, "Spectro One", "Maker", address=(1, 3),
                               port_path="1-2")
    env = make_env(make=rec, devices=[[], [inst]])
    answers = list(ANSWERS_USB)
    answers.insert(answers.index("the program showed the model") + 2, "y")   # keep? yes
    ui = Scripted(answers)
    code = cli.main(["--type", "handheld", "--short", "--folder", str(tmp_path), "--no-pause"],
                    ui=ui, env=env)
    assert code == 0, ui.text()
    assert "no USB description of the device there" in ui.text()
    zp = [p for p in tmp_path.iterdir() if p.name.startswith("SEND-THIS")][0]
    rec_bytes = records_of(zp)
    assert b"MEASURE\r" in rec_bytes and KEY not in rec_bytes
    man = json.loads(zipfile.ZipFile(zp).read("manifest.json"))
    assert man["kept_without_description"]
    res = check.check_zip(str(zp), ids={})
    assert res["warnings"] and "LOOK AT THIS FIRST" in check.render(res, str(zp))


def test_sb1_import_never_uses_this_computers_addresses(tmp_path):
    from test_session_flow import make_env
    from chromiq_probe import discovery
    own = tmp_path / "other-machine.pcap"
    w = UsbmonWriter()
    w.bulk_in(3, 0x81, KEY, xfer=XFER_INT)
    w.bulk_out(3, 0x02, b"FROM-ANOTHER-MACHINE")
    with open(own, "wb") as fh:
        fh.write(w.pcap())
    inst = discovery.UsbDevice(VID, PID, "Spectro", "Maker", address=(1, 3), port_path="1-2")
    env = make_env(devices=[[], [inst]])
    env.readiness = lambda t: {"can": False, "kind": None, "lines": ["x"], "options": [],
                               "admin": ""}
    out = tmp_path / "out"
    out.mkdir()
    ui = Scripted(["", "", "", "1", "", "", str(own), "e", "", "q"])
    cli.main(["--type", "handheld", "--short", "--import", "--folder", str(out), "--no-pause"],
             ui=ui, env=env)
    sess = [p for p in out.iterdir() if p.name.startswith("probe-session-")][0]
    st = json.load(open(sess / "session.json"))
    assert "addresses" not in st["selection"]["devices"][0]
    for z in out.glob("SEND-THIS-*.zip"):
        assert b"FROM-ANOTHER-MACHINE" not in everything(z) and KEY not in everything(z)


def test_sb1_check_flags_key_reports_at_an_undescribed_address(tmp_path):
    w = UsbmonWriter()
    w.bulk_out(3, 0x02, b"DATA")
    zp, _m, _s = make_zip(tmp_path, [("x", w)], usb_sel(addresses=[[1, 3]],
                                                       allow_undescribed=True))
    bad = tmp_path / "bad.zip"
    k = UsbmonWriter()
    k.bulk_in(3, 0x81, KEY, xfer=XFER_INT)
    with zipfile.ZipFile(zp) as src, zipfile.ZipFile(bad, "w") as dst:
        for n in src.namelist():
            dst.writestr(n, src.read(n))
        dst.writestr("recordings/B9-x.pcap", k.pcap())
    res = check.check_zip(str(bad), ids={}, secrets={})
    assert any("typed keys" in p for p in res["problems"])
    assert any("WITHOUT a USB description" in x for x in res["warnings"])


# ---- S-M1: clones with the same serial ----------------------------------------------

def test_sm1_a2_two_clones_with_one_serial_keep_neither(tmp_path):
    w = UsbPcapWriter()
    w.describe(3, VID, PID, EPS, serial="A50285BI")
    w.describe(9, VID, PID, EPS, serial="A50285BI")
    w.bulk_in(3, 0x81, b"INSTRUMENT-DATA")
    w.bulk_in(9, 0x81, b"ZIGBEE-HOME-SENSOR")
    zp, _m, st = make_zip(tmp_path, [("x", w)], usb_sel(serial="A50285BI"))
    rec = records_of(zp)
    assert b"ZIGBEE-HOME-SENSOR" not in rec and b"INSTRUMENT-DATA" not in rec
    assert "TWO DEVICES WITH THE SAME NUMBERS" in " ".join(
        package.check_lines(st["blocks"][0]["check"], "usb"))


def test_sm1_clones_told_apart_by_the_systems_address(tmp_path):
    w = UsbmonWriter()
    w.describe(3, VID, PID, EPS, serial="A50285BI")
    w.describe(9, VID, PID, EPS, serial="A50285BI")
    w.bulk_in(3, 0x81, b"INSTRUMENT-DATA")
    w.bulk_in(9, 0x81, b"ZIGBEE-HOME-SENSOR")
    zp, _m, _s = make_zip(tmp_path, [("x", w)], usb_sel(serial="A50285BI", addresses=[[1, 3]]))
    rec = records_of(zp)
    assert b"INSTRUMENT-DATA" in rec and b"ZIGBEE-HOME-SENSOR" not in rec


# ---- S-M2: dual-stack instruments, behind a router, no router known ------------------

import ipaddress  # noqa: E402
import struct  # noqa: E402


def ip6(src, dst, payload, sp=5353, dp=5353):
    seg = struct.pack(">HHHH", sp, dp, 8 + len(payload), 0) + payload
    return struct.pack(">IHBB16s16s", 0x60000000, len(seg), 17, 255,
                       ipaddress.ip_address(src).packed, ipaddress.ip_address(dst).packed) + seg


def test_sm2_na_a_dual_stack_instrument_is_kept_and_its_ipv6_is_said(tmp_path):
    w = NetWriter()
    w.add(eth(DEV_MAC, HOST_MAC, 0x0800, tcp(HOST_IP, DEV_IP, 50000, 5000, b"MEASURE")))
    w.add(eth(HOST_MAC, DEV_MAC, 0x0800, tcp(DEV_IP, HOST_IP, 5000, 50000, b"L=50.1")))
    for a in ("fe80::2c0:eeff:fe11:2233", "2a02:810a:1:2::77", "2a02:810a:1:2:c4f3:1:2:3"):
        w.add(eth(b"\x33\x33\x00\x00\x00\xfb", DEV_MAC, 0x86DD, ip6(a, "ff02::fb", b"\0" * 12)))
    w.add(eth(DEV_MAC, HOST_MAC, 0x86DD, ip6("2a02:810a:1:2::23", "2a02:810a:1:2::77", b"IPP?",
                                              50001, 631)))
    zp, _m, st, rec = net_zip(tmp_path, w)
    c = st["blocks"][0]["check"]
    assert not c["refused"] and b"MEASURE" in rec and b"L=50.1" in rec
    assert b"IPP?" not in rec
    assert "used IPv6" in " ".join(package.check_lines(c, "net"))


def test_sm2_nb_behind_a_router_is_refused_the_same_way_on_every_recorder(tmp_path):
    rem = "10.20.0.50"
    sel = {"transport": "net", "ips": [rem], "macs": [], "gateways": [RTR_IP],
           "gateway_macs": ["e8:df:70:01:02:03"]}
    full = NetWriter()
    full.add(eth(RTR_MAC, HOST_MAC, 0x0800, tcp(HOST_IP, rem, 50000, 5000, b"MEASURE")))
    full.add(eth(HOST_MAC, RTR_MAC, 0x0800, tcp(rem, HOST_IP, 5000, 50000, b"L=50.1")))
    full.add(eth(RTR_MAC, HOST_MAC, 0x0800, tcp(HOST_IP, "142.250.1.1", 50001, 443, b"x")))
    narrowed = NetWriter()
    narrowed.records = full.records[:2]                   # what a BPF capture would hold
    for i, w in enumerate((full, narrowed)):
        d = tmp_path / str(i)
        d.mkdir()
        _zp, _m, st, rec = net_zip(d, w, sel)
        c = st["blocks"][0]["check"]
        assert c["refused"] and "reached through your router" in c["refused"]
        assert b"MEASURE" not in rec


def test_sm3_nc_no_known_router_refuses(tmp_path):
    w = NetWriter()
    w.add(eth(RTR_MAC, HOST_MAC, 0x0800, tcp(HOST_IP, RTR_IP, 50002, 80,
                                              b"GET / HTTP/1.1\r\nAuthorization: Basic "
                                              b"YWRtaW46c2VjcmV0\r\n\r\n")))
    zp, _m, st, _rec = net_zip(tmp_path, w, {"transport": "net", "ips": [RTR_IP], "macs": [],
                                              "gateways": []})
    assert b"YWRtaW46" not in everything(zp) and st["blocks"][0]["check"]["refused"]


def test_sm3_nc_the_menu_refuses_when_the_router_is_unknown(tmp_path):
    from test_session_flow import make_env
    import ipaddress as _ip
    env = make_env()
    # 2.0.1: a full-tunnel VPN (the IPv4 default route goes into utun3) and an address that
    # is on none of this computer's own networks
    env.network_facts = lambda: {"routes": [("", "utun3")],
                                 "networks": {"en0": [_ip.ip_interface("192.168.178.23/24")]}}
    env.neighbours = lambda: []
    ui = Scripted(["2", "10.20.0.50", "q"])
    assert cli.main(["--type", "network", "--folder", str(tmp_path), "--no-pause"], ui=ui,
                    env=env) == 4
    assert "default route goes into a tunnel interface (a VPN)" in ui.text()


def test_sm1_nd_an_extender_phone_is_not_proposed(tmp_path):
    w = NetWriter()
    w.add(eth(DEV_MAC, HOST_MAC, 0x0800, tcp(HOST_IP, DEV_IP, 50000, 5000, b"MEASURE")))
    w.add(eth(HOST_MAC, DEV_MAC, 0x0800, tcp(DEV_IP, HOST_IP, 5000, 50000, b"L=50.1")))
    w.add(eth(b"\xff" * 6, DEV_MAC, 0x0806, arp(1, DEV_MAC, "192.168.178.88", b"\0" * 6, RTR_IP)))
    w.add(eth(b"\xff" * 6, DEV_MAC, 0x0800, udp("192.168.178.88", "239.255.255.250", 50003, 1900,
                                               b"NOTIFY * HTTP/1.1\r\nX-FRIENDLY: Miras iPhone"
                                               b"\r\n\r\n")))
    zp, _m, st, _rec = net_zip(tmp_path, w)
    c = st["blocks"][0]["check"]
    assert c["new_addresses"] == [] and c["unproven_addresses"] == ["192.168.178.88"]
    assert b"Miras iPhone" not in everything(zp)


def test_sm3_ne_a_tls_certificate_after_a_retransmission_stays_masked(tmp_path):
    def tls(ct, body):
        return bytes([ct, 3, 3]) + struct.pack(">H", len(body)) + body
    ch = tls(22, b"\x01\x00\x00\x2c" + b"\x03\x03" + b"\0" * 32 + b"\0" + b"\0\x02\x00\x2f\x01\x00"
             + b"\0" * 2)
    sh = tls(22, b"\x02\x00\x00\x26" + b"\x03\x03" + b"\0" * 34)
    cert = tls(22, b"\x0b\x00\x00\x30" + b"CN=owner-name.example.org O=Mira Studio" + b"\0" * 9)
    w = NetWriter()
    w.add(eth(DEV_MAC, HOST_MAC, 0x0800, tcp(HOST_IP, DEV_IP, 50010, 443, ch)))
    w.add(eth(HOST_MAC, DEV_MAC, 0x0800, tcp(DEV_IP, HOST_IP, 443, 50010, sh[:20], seq=1)))
    w.add(eth(HOST_MAC, DEV_MAC, 0x0800, tcp(DEV_IP, HOST_IP, 443, 50010, sh[:20], seq=1)))
    w.add(eth(HOST_MAC, DEV_MAC, 0x0800, tcp(DEV_IP, HOST_IP, 443, 50010, sh[20:] + cert, seq=21)))
    zp, _m, _s, _rec = net_zip(tmp_path, w)
    assert b"owner-name" not in everything(zp) and b"Mira Studio" not in everything(zp)


def test_sm2b_ssdp_and_ws_discovery_friendly_names_are_masked(tmp_path):
    w = NetWriter()
    w.add(eth(DEV_MAC, HOST_MAC, 0x0800, tcp(HOST_IP, DEV_IP, 50000, 5000, b"MEASURE")))
    w.add(eth(b"\x01\x00\x5e\x7f\xff\xfa", DEV_MAC, 0x0800, udp(DEV_IP, "239.255.255.250", 50003,
          1900, b"NOTIFY * HTTP/1.1\r\nNT: upnp:rootdevice\r\nSERVER: Linux UPnP/1.0\r\n"
                b"X-FRIENDLY: Miras Atelier Spectro\r\n\r\n")))
    w.add(eth(b"\x01\x00\x5e\x7f\xff\xfa", DEV_MAC, 0x0800, udp(DEV_IP, "239.255.255.250", 3702,
          3702, b"<wsd:Hello><wsd:Types>x</wsd:Types><pnpx:FriendlyName>Miras Atelier Spectro"
                b"</pnpx:FriendlyName></wsd:Hello>")))
    zp, _m, _s, rec = net_zip(tmp_path, w)
    assert b"Miras Atelier Spectro" not in everything(zp)
    assert b"NT: upnp:rootdevice" in rec and b"<wsd:Types>x</wsd:Types>" in rec


# ---- the two identifier gaps closed --------------------------------------------------

def test_a5_macs_as_12_hex_digits_and_ipv6_text(tmp_path):
    w = NetWriter()
    w.add(eth(HOST_MAC, DEV_MAC, 0x0800, udp(DEV_IP, HOST_IP, 3000, 3000,
          b"mac=00C0EE112233;host=a4b1c2d3e4f5;v6=fe80::2c0:eeff:fe11:2233;"
          b"v6u=FE80::2C0:EEFF:FE11:2233;time=12:34:56")))
    zp, _m, _s, rec = net_zip(tmp_path, w)
    for gone in (b"00C0EE112233", b"a4b1c2d3e4f5", b"fe80::2c0:eeff:fe11:2233",
                 b"FE80::2C0:EEFF:FE11:2233"):
        assert gone.lower() not in rec.lower(), gone
    assert b"time=12:34:56" in rec                       # not an address: kept


def test_a5_check_finds_a_12_hex_mac_left_in_a_zip(tmp_path):
    w = NetWriter()
    w.add(eth(HOST_MAC, DEV_MAC, 0x0800, udp(DEV_IP, HOST_IP, 3000, 3000, b"x")))
    zp, _m, _s, _r = net_zip(tmp_path, w)
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(zp) as src, zipfile.ZipFile(bad, "w") as dst:
        for n in src.namelist():
            dst.writestr(n, src.read(n))
        dst.writestr("notes-extra.txt", b"seen 00c0ee112233")
    res = check.check_zip(str(bad), ids={}, secrets={"network card": ["00:c0:ee:11:22:33"]})
    assert any("network card" in p for p in res["problems"])


# ---- S-m5: a session running in another window is left alone -------------------------

def test_sm5_tidy_leaves_a_running_sessions_raw_folder_alone(tmp_path):
    import subprocess
    import sys
    root = tmp_path / "priv"
    raw = root / "raw" / "20270101-000000"
    raw.mkdir(parents=True)
    (raw / "B1-x-full.pcap").write_bytes(b"RAW")
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        (raw / "owner.pid").write_text(str(other.pid))
        runner.tidy_leftovers(Scripted([]), str(root))
        assert (raw / "B1-x-full.pcap").exists()
    finally:
        other.kill()
        other.wait()
    runner.tidy_leftovers(Scripted([]), str(root))
    assert not (raw / "B1-x-full.pcap").exists()


def test_sm8_files_are_created_0600(tmp_path):
    import stat
    from chromiq_probe import recorders
    r = recorders.TcpdumpRecorder(["en0"], str(tmp_path), sudo=None, tcpdump="x")
    p = tmp_path / "f.pcap"
    r._prepare(str(p))
    assert stat.S_IMODE(os.stat(p).st_mode) == 0o600


# ---- re-check R-1: binary data passes byte-identical ---------------------------------

def test_r1_megabytes_of_random_binary_data_pass_unchanged(tmp_path):
    import random
    from chromiq_probe import privacy
    rnd = random.Random(1234)
    blob = bytes(rnd.getrandbits(8) for _ in range(3_000_000))
    blob = blob.replace(b"SN7Q4X9Z2K", b"SN7Q4X9Z2L")       # make sure no planted id by chance
    planted = blob[:1000] + b"SN7Q4X9Z2K" + blob[1000:]
    m = privacy.Mapper()
    m.text("serial", "SN7Q4X9Z2K")
    m.ip("192.168.178.23")
    m.mac(bytes.fromhex("a4b1c2d3e4f5"))
    out = m.scrub_bytes(planted, m.byte_rules())              # USB data
    assert out[:1000] + out[1010:] == blob and out[1000:1010] == b"serial1___"
    out_net = m.scrub_bytes(blob, m.byte_rules(binary_ips=True))   # network data
    changed = sum(1 for a, b in zip(out_net, blob) if a != b)
    known = blob.count(bytes.fromhex("c0a8b217")) * 4 + blob.count(bytes.fromhex("a4b1c2d3e4f5")) * 6
    assert changed <= known                                  # only known addresses, if any


def test_r1_ipv6_text_rules_only_in_readable_network_text():
    from chromiq_probe import privacy
    m = privacy.Mapper()
    rules = m.byte_rules(binary_ips=True)
    data = b"\x00\x01::47\x02A::5\x03 std::vec<int> ok; host fe80::2c0:eeff:fe11:2233 up"
    out = m.scrub_bytes(data, rules)
    assert b"::47" in out and b"A::5" in out and b"std::vec" in out
    assert b"fe80::2c0:eeff:fe11:2233" not in out


# ---- re-check R-2: a device kept without a description ---------------------------------

def test_r2_report_id_and_nkro_keyboards_are_left_out_after_a_yes(tmp_path):
    w = UsbmonWriter()
    w.bulk_out(3, 0x02, b"MEASURE\r")
    rid = b"\x01" + KEY                                     # report id + boot report
    nkro = b"\x00\x00\x00\x00\x08" + b"\x00" * 11             # 16-byte key bitmap
    w.bulk_in(3, 0x81, rid, xfer=XFER_INT)
    w.bulk_in(3, 0x81, nkro, xfer=XFER_INT)
    w.bulk_in(3, 0x81, KEY, xfer=XFER_INT)
    for hid in (False, True):
        d = tmp_path / str(hid)
        d.mkdir()
        sel = usb_sel(addresses=[[1, 3]], allow_undescribed=True,
                      **({"interfaces": [[3, 0, 0]]} if hid else {}))
        zp, _m, st = make_zip(d, [("x", w)], sel)
        from chromiq_probe import capture, usb
        with zipfile.ZipFile(zp) as z:
            cap = capture.read_capture_bytes(z.read("recordings/B1-x.pcap"))
        payloads = [usb.record_info(cap.linktype, r)[3] for _t, r in cap.records]
        assert rid not in payloads and nkro not in payloads and KEY not in payloads, hid
        assert b"MEASURE\r" in payloads
        assert "small reports were left out" in " ".join(
            package.check_lines(st["blocks"][0]["check"], "usb"))


def test_r2_the_question_is_honest_and_shows_the_system_class(tmp_path):
    from test_session_flow import make_env, ANSWERS_USB
    from chromiq_probe import discovery

    def rec(stem):
        w = UsbmonWriter()
        w.bulk_out(3, 0x02, b"MEASURE\r")
        return w
    inst = discovery.UsbDevice(VID, PID, "Spectro One", "Maker", address=(1, 3),
                               port_path="1-2", interfaces=[(0xFF, 0, 0)])
    env = make_env(make=rec, devices=[[], [inst]])
    answers = list(ANSWERS_USB)
    answers.insert(answers.index("the program showed the model") + 2, "")      # no
    ui = Scripted(answers)
    cli.main(["--type", "handheld", "--short", "--folder", str(tmp_path), "--no-pause"], ui=ui,
             env=env)
    t = ui.text()
    assert "always" not in t.split("This is what they look like")[1].split("Keep them?")[0]
    assert "no USB keyboard or mouse is plugged into the same computer port group" in t
    assert "vendor-specific" in t
    assert "FIRST, so that the recording can identify your instrument" in t


def test_r2_after_a_replug_in_the_recording_no_question_comes_up(tmp_path):
    from test_session_flow import make_env, ANSWERS_USB
    from chromiq_probe import discovery

    def rec(stem):
        w = UsbmonWriter()
        w.bulk_out(3, 0x02, b"BEFORE-REPLUG")
        w.describe(7, VID, PID, EPS, serial="")              # unplugged and plugged in again
        w.bulk_out(7, 0x02, b"MEASURE\r")
        return w
    inst = discovery.UsbDevice(VID, PID, "Spectro One", "Maker", address=(1, 3), port_path="1-2")
    env = make_env(make=rec, devices=[[], [inst]])
    ui = Scripted(list(ANSWERS_USB))
    code = cli.main(["--type", "handheld", "--short", "--folder", str(tmp_path), "--no-pause"],
                    ui=ui, env=env)
    assert code == 0, ui.text()
    assert "Are these your instrument's" not in ui.text()
    zp = [p for p in tmp_path.iterdir() if p.name.startswith("SEND-THIS")][0]
    rec_bytes = records_of(zp)
    assert b"MEASURE\r" in rec_bytes and b"BEFORE-REPLUG" not in rec_bytes
    sess = [p for p in tmp_path.iterdir() if p.name.startswith("probe-session-")][0]
    assert json.load(open(sess / "session.json"))["described_seen"] is True


# ---- small points -----------------------------------------------------------------------

def test_a_computer_without_any_router_may_record_its_instrument(tmp_path):
    from test_session_flow import make_env, net_recording, _Saver
    env = make_env(make=lambda stem: _Saver(net_recording(stem)))
    env.gateways = lambda: []
    env.network_facts = lambda: {"routes": [], "networks": {}}
    env.neighbours = lambda: [(DEV_IP, "00:c0:ee:11:22:33")]
    env.connections = lambda: []
    ui = Scripted(["2", DEV_IP, "", "e", "", "q"])
    code = cli.main(["--type", "network", "--short", "--folder", str(tmp_path), "--no-pause"],
                    ui=ui, env=env)
    assert code == 0, ui.text()
    assert "no IPv4 default route" in ui.text()
    zp = [p for p in tmp_path.iterdir() if p.name.startswith("SEND-THIS")][0]
    assert b"SPECTRO,1.2" in everything(zp)

"""The independent review's attacks of 2026-11-22 (attack_usb.py, attack_net.py,
attack_flow.py, attack_check.py), each turned into a test that builds the
hostile recording and asserts on the bytes of the zip (or on file modes).
Every byte here is made up."""

import ipaddress
import json
import os
import stat
import struct
import zipfile

import pytest

from chromiq_probe import capture, check, cli, package, recorders, runner
from chromiq_probe.console import Scripted
from synth import (XFER_INT, DarwinWriter, NetWriter, UsbmonWriter, UsbPcapWriter, arp, eth,
                   tcp, udp)

VID, PID = 0x0403, 0x6001                 # a generic FTDI adapter (a serial instrument)
EPS = [(0x81, 2), (0x02, 2)]
SER = "FTAB12CD"
STAMP = "20270101-000000"


def make_zip(tmp, takes, sel, keep_serial=False, hide=(), ids=None, follow=False):
    """The tool's own pipeline: each take filtered into kept files, then the zip."""
    sess = tmp / f"probe-session-{STAMP}"
    kept = sess / "kept"
    blocks = []
    for i, (label, w) in enumerate(takes, 1):
        raw = tmp / f"raw-{i}.pcap"
        with open(raw, "wb") as fh:
            fh.write(w.pcap())
        c = package.process_take([str(raw)], sel, str(kept), f"B{i}-{label}", follow=follow)
        blocks.append({"id": f"B{i}", "label": label, "status": "recorded",
                       "kept": c.pop("kept_files"), "check": c, "started": 1.8e9})
    state = {"stamp": STAMP, "selection": sel, "blocks": blocks, "keep_serial": keep_serial,
             "hide": list(hide), "plan": [], "environment": {}}
    with open(sess / "session.json", "w") as fh:
        json.dump(state, fh)
    zp = tmp / f"SEND-THIS-{STAMP}.zip"
    man = package.build_zip(state, str(sess), None, str(zp), ids=ids or {})
    return str(zp), man, state


def everything(zp):
    with zipfile.ZipFile(zp) as z:
        return b"".join(z.read(n) for n in z.namelist())


def usb_sel(**dev):
    d = {"vid": VID, "pid": PID, "name": "FTDI instrument"}
    d.update(dev)
    return {"transport": "usb", "devices": [d], "name": d["name"]}


# ---- B5: the serial number ----------------------------------------------------

def test_b5_u1_serial_in_a_block_before_the_descriptor(tmp_path):
    w1 = UsbmonWriter()
    w1.bulk_out(3, 0x02, b"GETSN\r")
    w1.bulk_in(3, 0x81, b"SN=" + SER.encode() + b"\r")
    w2 = UsbmonWriter()
    w2.describe(3, VID, PID, EPS, serial=SER)
    w2.bulk_in(3, 0x81, b"SN=" + SER.encode() + b"\r")
    zp, man, _st = make_zip(tmp_path, [("first", w1), ("replug", w2)],
                            usb_sel(addresses=[[1, 3]], allow_undescribed=True))
    blob = everything(zp)
    assert SER.encode() not in blob and SER.encode("utf-16-le") not in blob
    assert man["instrument_serial"] == "replaced by a placeholder"


def test_b5_u1b_no_descriptor_serial_from_the_system_list(tmp_path):
    w = UsbmonWriter()
    w.bulk_in(3, 0x81, b"SN=" + SER.encode() + b"\r")
    zp, man, _st = make_zip(tmp_path, [("first", w)], usb_sel(addresses=[[1, 3]], serial=SER,
                                                              allow_undescribed=True))
    assert SER.encode() not in everything(zp)
    src = json.dumps(man["identifiers_replaced"])
    assert "the system's device list" in src
    assert "cannot know an identifier it has not been told" in man["what_the_tool_cannot_know"]
    assert SER not in json.dumps(man)                    # the zip never carries the real one


def test_b5_without_any_known_serial_the_manifest_says_so(tmp_path):
    w = UsbmonWriter()
    w.bulk_in(3, 0x81, b"DATA")
    _zp, man, _st = make_zip(tmp_path, [("x", w)], usb_sel(addresses=[[1, 3]],
                                                            allow_undescribed=True))
    assert man["instrument_serial"] == "no serial number was known to the tool"


# ---- B6: another unit with the same numbers -------------------------------------

@pytest.mark.parametrize("fmt", ["usbmon", "usbpcap"])
def test_b6_u2_zigbee_stick_with_the_same_numbers(tmp_path, fmt):
    w = UsbmonWriter() if fmt == "usbmon" else UsbPcapWriter()
    w.describe(3, VID, PID, EPS, serial=SER)
    w.describe(9, VID, PID, EPS, serial="OTHERDEV1")
    w.bulk_in(3, 0x81, b"INSTRUMENT-DATA")
    w.bulk_in(9, 0x81, b"ZIGBEE-HOME-SENSOR-LIVINGROOM")
    sel = usb_sel(serial=SER, **({"addresses": [[1, 3]]} if fmt == "usbmon" else {}))
    zp, _man, _st = make_zip(tmp_path, [("x", w)], sel)
    blob = everything(zp)
    assert b"INSTRUMENT-DATA" in blob
    assert b"ZIGBEE-HOME-SENSOR" not in blob
    assert "OTHERDEV1".encode("utf-16-le") not in blob


def test_b6_two_units_the_recording_cannot_tell_apart_keep_neither(tmp_path):
    w = UsbPcapWriter()
    w.describe(3, VID, PID, EPS, serial="")
    w.describe(9, VID, PID, EPS, serial="")
    w.bulk_in(3, 0x81, b"UNIT-A")
    w.bulk_in(9, 0x81, b"UNIT-B")
    zp, _man, st = make_zip(tmp_path, [("x", w)], usb_sel())
    blob = everything(zp)
    assert b"UNIT-A" not in blob and b"UNIT-B" not in blob
    lines = " ".join(package.check_lines(st["blocks"][0]["check"], "usb"))
    assert "TWO DEVICES WITH THE SAME NUMBERS" in lines


def test_b6_the_choice_asks_to_unplug_an_identical_unit(tmp_path):
    from chromiq_probe import discovery
    from test_session_flow import make_env
    a = discovery.UsbDevice(VID, PID, "FT232R", "FTDI")
    b = discovery.UsbDevice(VID, PID, "FT232R", "FTDI", instance="USB\\VID_0403&PID_6001\\7&2")
    env = make_env(devices=[[b], [b, a], [b, a]])
    ui = Scripted(["", "", "", "1", "", "q"])
    code = cli.main(["--type", "serial", "--folder", str(tmp_path), "--no-pause"], ui=ui, env=env)
    assert code == 4
    assert "Another device with the same USB numbers" in ui.text()
    assert "cannot record safely" in ui.text()


def test_b6_darwin_second_unit_left_out_by_location(tmp_path):
    d = DarwinWriter({3: (VID, PID, 0x01100000), 4: (VID, PID, 0x01200000)})
    d.bulk_in(3, 0x81, b"MINE")
    d.bulk_in(4, 0x81, b"OTHER-UNIT")
    zp, _m, _s = make_zip(tmp_path, [("x", d)], usb_sel(location=0x01100000))
    blob = everything(zp)
    assert b"MINE" in blob and b"OTHER-UNIT" not in blob


def test_m4_two_chosen_devices_counted_separately(tmp_path):
    w = UsbPcapWriter()
    w.describe(3, 0x0765, 0x30B0, EPS, serial="")
    w.describe(4, 0x0765, 0x6009, EPS, serial="")
    w.bulk_out(3, 0x02, b"TABLE-MOVE")
    w.bulk_in(4, 0x81, b"READING")
    sel = {"transport": "usb", "name": "table + instrument",
           "devices": [{"vid": 0x0765, "pid": 0x30B0, "name": "table"},
                       {"vid": 0x0765, "pid": 0x6009, "name": "instrument"}]}
    zp, _m, st = make_zip(tmp_path, [("x", w)], sel)
    blob = everything(zp)
    assert b"TABLE-MOVE" in blob and b"READING" in blob
    per = st["blocks"][0]["check"]["per_device"]
    assert per["table"] > 0 and per["instrument"] > 0
    assert "Per device in this block" in " ".join(package.check_lines(st["blocks"][0]["check"],
                                                                      "usb"))


# ---- names in many forms (M2, M11) ------------------------------------------------

def test_m11_u6_names_in_many_encodings(tmp_path):
    ids = {"host": "MIRAS-MBP", "user": "mira", "home": "/Users/mira"}
    w = UsbPcapWriter()
    w.describe(3, VID, PID, EPS, serial=SER)
    variants = [b"user=mira;", b"USER=MIRA;", "C:\\Users\\mira\\x".encode("utf-16-le"),
                "C:\\USERS\\MIRA\\x".encode("utf-16-le"), b"C%3A%5CUsers%5Cmira",
                b"miras-mbp.local", "MIRA".encode("utf-16-be")]
    for v in variants:
        w.bulk_out(3, 0x02, b"<" + v + b">")
    zp, _m, _s = make_zip(tmp_path, [("x", w)], usb_sel(), ids=ids)
    with zipfile.ZipFile(zp) as z:
        rec = b"".join(z.read(n) for n in z.namelist() if n.endswith(".pcap"))
    assert b"mira" not in rec.lower()
    assert "mira".encode("utf-16-le") not in rec.lower()
    assert "MIRA".encode("utf-16-be") not in rec


def test_m11_the_8_3_short_form_of_a_long_user_name(tmp_path):
    w = UsbPcapWriter()
    w.describe(3, VID, PID, EPS)
    w.bulk_out(3, 0x02, b"C:\\Users\\MIRAND~1\\AppData")
    zp, _m, _s = make_zip(tmp_path, [("x", w)], usb_sel(), ids={"user": "miranda.k"})
    assert b"MIRAND~1" not in everything(zp)


def test_m2_u7_u8_hide_in_utf8_utf16_and_any_case(tmp_path):
    w = UsbPcapWriter()
    w.describe(3, VID, PID, EPS, serial=SER)
    w.bulk_out(3, 0x02, "/home/jürgen/m.cxf".encode("utf-8"))
    w.bulk_out(3, 0x02, "Müller GmbH".encode("utf-8"))
    w.bulk_out(3, 0x02, "ACME-LICENSE-1234".encode("utf-16-le"))
    w.bulk_out(3, 0x02, b"acme-license-1234")
    zp, _m, _s = make_zip(tmp_path, [("x", w)], usb_sel(),
                          ids={"user": "jürgen", "home": "/home/jürgen"},
                          hide=["Müller GmbH", "ACME-LICENSE-1234"])
    blob = everything(zp)
    assert "jürgen".encode() not in blob and "Müller GmbH".encode() not in blob
    assert "ACME-LICENSE-1234".encode("utf-16-le") not in blob
    assert b"acme-license-1234" not in blob.lower()


def test_m4_u11_a_crafted_block_id_cannot_leave_the_recordings_folder(tmp_path):
    w = UsbPcapWriter()
    w.describe(3, VID, PID, EPS)
    w.bulk_in(3, 0x81, b"X")
    sess = tmp_path / "s"
    raw = tmp_path / "r.pcap"
    raw.write_bytes(w.pcap())
    c = package.process_take([str(raw)], usb_sel(), str(sess / "kept"), "t")
    state = {"stamp": "x", "selection": usb_sel(), "plan": [], "environment": {},
             "blocks": [{"id": "../../evil", "label": "a", "status": "recorded",
                         "kept": c["kept_files"], "check": c}]}
    zp = tmp_path / "z.zip"
    package.build_zip(state, str(sess), None, str(zp), ids={})
    names = zipfile.ZipFile(zp).namelist()
    assert all(".." not in n for n in names)


# ---- B1, B2, M3, M10, m1, m2: the network ------------------------------------------

HOST_MAC = bytes.fromhex("a4b1c2d3e4f5")
HOST_IP = "192.168.178.23"
DEV_MAC = bytes.fromhex("00c0ee112233")
DEV_IP = "192.168.178.77"
RTR_MAC = bytes.fromhex("e8df70010203")
RTR_IP = "192.168.178.1"
PHONE_IP = "192.168.178.88"
NSEL = {"transport": "net", "ips": [DEV_IP], "macs": ["00:c0:ee:11:22:33"],
        "gateways": [RTR_IP]}


class _W:
    def __init__(self, w):
        self.w = w

    def pcap(self):
        return self.w.pcap()


def net_zip(tmp, w, sel=NSEL, ids=None):
    zp, man, st = make_zip(tmp, [("x", _W(w))], sel, ids=ids)
    with zipfile.ZipFile(zp) as z:
        rec = b"".join(z.read(n) for n in z.namelist() if n.endswith(".pcap"))
    return zp, man, st, rec


def test_b1_n2_the_router_is_refused_and_nothing_of_it_is_kept(tmp_path):
    w = NetWriter()
    dns = b"\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x0bprivatebank\x02de\x00\x00\x01\x00\x01"
    w.add(eth(RTR_MAC, HOST_MAC, 0x0800, udp(HOST_IP, RTR_IP, 53001, 53, dns)))
    for ip in ("142.250.1.1", "17.1.1.1", "8.8.8.8"):
        w.add(eth(HOST_MAC, RTR_MAC, 0x0800, tcp(ip, HOST_IP, 443, 50001, b"x")))
    w.add(eth(RTR_MAC, HOST_MAC, 0x0800, tcp(HOST_IP, RTR_IP, 50002, 80,
                                              b"GET / HTTP/1.1\r\nAuthorization: Basic "
                                              b"YWRtaW46c2VjcmV0\r\n\r\n")))
    for sel in ({"transport": "net", "ips": [RTR_IP], "macs": ["e8:df:70:01:02:03"]},
                {"transport": "net", "ips": [RTR_IP], "macs": [], "gateways": [RTR_IP]}):
        zp, _man, st, rec = net_zip(tmp_path / str(len(sel)), w, sel) if \
            (tmp_path / str(len(sel))).mkdir() is None else (None,) * 4
        blob = everything(zp)
        assert b"privatebank" not in blob and b"YWRtaW46" not in blob
        assert st["blocks"][0]["check"]["refused"]
        assert "KEPT NOTHING" in package.check_lines(st["blocks"][0]["check"], "net")[0]


def test_b1_f5_a_device_list_has_no_default_and_refuses_the_router(tmp_path):
    from test_session_flow import make_env
    env = make_env()
    env.neighbours = lambda: [(RTR_IP, "e8:df:70:01:02:03"), (DEV_IP, "00:c0:ee:11:22:33")]
    env.connections = lambda: []
    env.gateways = lambda: [RTR_IP]
    ui = Scripted(["", "3", "", "1", "3", "2", "q"])
    cli.main(["--type", "network", "--short", "--folder", str(tmp_path), "--no-pause"], ui=ui,
             env=env)
    text = ui.text()
    assert "Pressing Enter alone chooses nothing" in text
    assert "That is your router" in text
    assert f"Only the traffic to and from {DEV_IP}" in text
    assert f"Only the traffic to and from {RTR_IP}" not in text


def test_b2_n3_an_extender_sharing_the_mac_lets_no_other_host_in(tmp_path):
    w = NetWriter()
    w.add(eth(b"\xff" * 6, DEV_MAC, 0x0806, arp(1, DEV_MAC, PHONE_IP, b"\0" * 6, RTR_IP)))
    mdns = (b"\0\0\x84\0\0\0\0\x01\0\0\0\0\x0cMiras-iPhone\x05local\x00\x00\x01\x80\x01"
            b"\0\0\0\x78\0\x04\xc0\xa8\xb2\x58")
    w.add(eth(bytes.fromhex("01005e0000fb"), DEV_MAC, 0x0800,
              udp(PHONE_IP, "224.0.0.251", 5353, 5353, mdns)))
    w.add(eth(DEV_MAC, HOST_MAC, 0x0800, tcp(HOST_IP, DEV_IP, 50000, 5000, b"MEASURE")))
    w.add(eth(HOST_MAC, DEV_MAC, 0x0800, tcp(DEV_IP, HOST_IP, 5000, 50000, b"OK")))
    zp, _m, st, rec = net_zip(tmp_path, w)
    assert b"Miras-iPhone" not in everything(zp)
    assert b"MEASURE" in rec
    assert st["blocks"][0]["check"]["new_addresses"] == []       # never proposed: shared MAC


def test_b2_the_instruments_own_mdns_names_are_masked(tmp_path):
    w = NetWriter()
    mdns = (b"\0\0\x84\0\0\0\0\x01\0\0\0\0\x10SPECTRO-SN12345A\x05local\x00\x00\x01\x80\x01"
            b"\0\0\0\x78\0\x04\xc0\xa8\xb2\x4d")
    w.add(eth(bytes.fromhex("01005e0000fb"), DEV_MAC, 0x0800,
              udp(DEV_IP, "224.0.0.251", 5353, 5353, mdns)))
    zp, _m, _s, rec = net_zip(tmp_path, w)
    assert b"SPECTRO-SN12345A" not in everything(zp) and b"local" in rec


def test_m3_n1_tls_only_from_a_handshake_at_the_start(tmp_path):
    w = NetWriter()
    w.add(eth(DEV_MAC, HOST_MAC, 0x0800, tcp(HOST_IP, DEV_IP, 50000, 5000, b"\x02READ-1\x03")))
    w.add(eth(HOST_MAC, DEV_MAC, 0x0800, tcp(DEV_IP, HOST_IP, 5000, 50000, b"\x02L=50.1\x03")))
    w.add(eth(DEV_MAC, HOST_MAC, 0x0800, tcp(HOST_IP, DEV_IP, 50000, 5000,
                                              b"\x16\x03\x01\x00\x04ABCD")))
    for i in range(5):
        w.add(eth(HOST_MAC, DEV_MAC, 0x0800, tcp(DEV_IP, HOST_IP, 5000, 50000,
                                                  f"\x02L=6{i}.0\x03".encode())))
    _zp, man, _s, rec = net_zip(tmp_path, w)
    assert rec.count(b"L=6") == 5
    assert man["encrypted_connections"] == {}


def test_m10_n4_addresses_inside_the_data(tmp_path):
    w = NetWriter()
    body = (b"myip=" + ipaddress.ip_address(DEV_IP).packed + b";client="
            + ipaddress.ip_address(HOST_IP).packed + b";public=84.150.33.21;text="
            + HOST_IP.encode() + b";fw=1.2.3.4")
    w.add(eth(HOST_MAC, DEV_MAC, 0x0800, udp(DEV_IP, HOST_IP, 3000, 3000, body)))
    zp, _m, _s, rec = net_zip(tmp_path, w)
    assert ipaddress.ip_address(DEV_IP).packed not in rec
    assert ipaddress.ip_address(HOST_IP).packed not in rec
    assert b"84.150.33.21" not in rec and HOST_IP.encode() not in rec
    assert b"fw=1.2.3.4" in rec                        # a version number stays
    assert check.check_zip(zp, ids={})["problems"] == []


def test_m1_n4_check_finds_a_real_address_left_in_a_zip(tmp_path):
    w = NetWriter()
    w.add(eth(HOST_MAC, DEV_MAC, 0x0800, udp(DEV_IP, HOST_IP, 3000, 3000, b"x")))
    zp, _m, _s, _r = net_zip(tmp_path, w)
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(zp) as src, zipfile.ZipFile(bad, "w") as dst:
        for n in src.namelist():
            dst.writestr(n, src.read(n))
        dst.writestr("recordings/B9-x.pcap", w.pcap())          # the raw, unrewritten frames
    os.makedirs(tmp_path / f"probe-session-{STAMP}", exist_ok=True)
    res = check.check_zip(str(bad), ids={})
    assert any("real network address" in p for p in res["problems"])
    assert any("address that should have been replaced" in p for p in res["problems"])


def test_m1_check_finds_the_serial_and_a_second_device(tmp_path):
    w = UsbPcapWriter()
    w.describe(3, VID, PID, EPS, serial=SER)
    w.bulk_in(3, 0x81, b"DATA")
    zp, _m, _s = make_zip(tmp_path, [("x", w)], usb_sel(serial=SER))
    other = UsbPcapWriter()
    other.describe(9, 0x1A86, 0x7523, EPS, serial="")
    other.bulk_in(9, 0x81, b"SN=" + SER.encode())
    bad = tmp_path / f"SEND-THIS-{STAMP}-bad.zip"
    with zipfile.ZipFile(zp) as src, zipfile.ZipFile(bad, "w") as dst:
        for n in src.namelist():
            dst.writestr(n, src.read(n))
        dst.writestr("recordings/B9-x.pcap", other.pcap())
    res = check.check_zip(str(bad), ids={})
    assert any("serial number that should have been replaced" in p for p in res["problems"])
    assert any("not your instrument" in p for p in res["problems"])


def test_m1_check_shows_every_string_and_lists_them_all(tmp_path):
    w = UsbPcapWriter()
    w.describe(3, VID, PID, EPS)
    for i in range(250):
        w.bulk_in(3, 0x81, f"aaaa-reading-{i:03d}".encode())
    for s in (b"iphone-of-mira", b"serialnumber-owner-jane", b"Jane5"):
        w.bulk_in(3, 0x81, s)
    zp, _m, _s = make_zip(tmp_path, [("x", w)], usb_sel())
    res = check.check_zip(zp, ids={})
    for s in ("iphone-of-mira", "serialnumber-owner-jane", "Jane5"):
        assert s in res["strings"]
    text = check.render(res, zp)
    assert "more." in text and res["listing"] in text
    listed = open(res["listing"]).read()
    assert "Jane5" in listed and "aaaa-reading-249" in listed


def test_m1_n8_a_plaintext_e_mail_is_shown_to_the_owner(tmp_path):
    w = NetWriter()
    w.add(eth(DEV_MAC, HOST_MAC, 0x0800, tcp(HOST_IP, DEV_IP, 50000, 80,
                                              b"POST /reg\r\n\r\nemail=owner@example.org")))
    zp, _m, _s, _r = net_zip(tmp_path, w)
    assert any("owner@example.org" in s for s in check.check_zip(zp, ids={})["strings"])


def test_m1_fragments_and_real_duplicates(tmp_path):
    w = NetWriter()
    payload2 = b"FRAGMENT-TWO-DATA-ABCDEFGHIJKLMNOP"
    hdr = struct.pack(">BBHHHBBH4s4s", 0x45, 0, 20 + len(payload2), 7, 0x0003, 64, 17, 0,
                      ipaddress.ip_address(DEV_IP).packed, ipaddress.ip_address(HOST_IP).packed)
    w.add(eth(HOST_MAC, DEV_MAC, 0x0800, hdr + payload2))
    f = eth(HOST_MAC, DEV_MAC, 0x0800, udp(DEV_IP, HOST_IP, 3000, 3000, b"BEEP"))
    w.add(f, dt=0.0005)
    w.add(f, dt=0.0005)
    _zp, _m, _s, rec = net_zip(tmp_path, w)
    assert payload2 in rec                              # review m1
    assert rec.count(b"BEEP") == 2                      # review m2: not pktmon


# ---- B4, M2, M6, M7, M12: the session ---------------------------------------------

def test_b4_f2_private_folders_and_no_full_recording_left(tmp_path):
    from test_session_flow import ANSWERS_USB, make_env
    env = make_env()
    old = os.umask(0o022)
    try:
        code = cli.main(["--type", "handheld", "--short", "--folder", str(tmp_path),
                         "--no-pause"], ui=Scripted(list(ANSWERS_USB)), env=env)
    finally:
        os.umask(old)
    assert code == 0
    sess = [p for p in tmp_path.iterdir() if p.name.startswith("probe-session-")][0]
    raw_root = os.path.join(env.private_root(), "raw")
    for p in [sess, sess / "kept"] + [os.path.join(raw_root, d) for d in os.listdir(raw_root)]:
        assert stat.S_IMODE(os.stat(p).st_mode) == 0o700, p
    for root, _dirs, files in os.walk(tmp_path):
        for f in files:
            assert stat.S_IMODE(os.stat(os.path.join(root, f)).st_mode) & 0o077 == 0, f
    for d in os.listdir(raw_root):
        left = [f for f in os.listdir(os.path.join(raw_root, d)) if f.endswith(".pcap")]
        assert left == [], "full recordings are deleted after each block"


def test_b4_leftovers_of_a_crashed_run_are_checked_then_deleted(tmp_path):
    from test_session_flow import ANSWERS_USB, make_env, build
    env = make_env()
    cli.main(["--type", "handheld", "--short", "--folder", str(tmp_path), "--no-pause"],
             ui=Scripted(list(ANSWERS_USB)), env=env)
    sess = [p for p in tmp_path.iterdir() if p.name.startswith("probe-session-")][0]
    st = json.load(open(sess / "session.json"))
    raw_dir = st["raw_dir"]
    leftover = os.path.join(raw_dir, "H99-crash-fake-full.pcap")
    build(UsbPcapWriter()).save(leftover)
    st["blocks"].append({"id": "H99", "label": "crash", "status": "recorded", "stem": "H99-crash",
                         "raw": ["H99-crash-fake-full.pcap"], "kept": []})
    json.dump(st, open(sess / "session.json", "w"))
    ui = Scripted([])
    runner.tidy_leftovers(ui, env.private_root())
    assert not os.path.exists(leftover)
    st = json.load(open(sess / "session.json"))
    assert st["blocks"][-1]["kept"] and "Tidied up" in ui.text()


def test_m2_f1_hide_given_with_remake_reaches_the_zip(tmp_path):
    from test_session_flow import ANSWERS_USB, build, make_env

    def rec(stem):
        w = build(UsbPcapWriter())
        w.bulk_out(3, 0x02, b"SECRET-LAB-NAME")
        return w
    env = make_env(make=rec)
    cli.main(["--type", "handheld", "--short", "--folder", str(tmp_path), "--no-pause"],
             ui=Scripted(list(ANSWERS_USB)), env=env)
    z1 = [p for p in tmp_path.iterdir() if p.name.startswith("SEND-THIS")][0]
    assert b"SECRET-LAB-NAME" in everything(z1)
    sess = [p for p in tmp_path.iterdir() if p.name.startswith("probe-session-")][0]
    code = cli.main(["--remake", str(sess), "--hide", "SECRET-LAB-NAME", "--no-pause"],
                    ui=Scripted([]), env=env)
    assert code == 0
    assert b"SECRET-LAB-NAME" not in everything(z1)


def test_m7_f3_an_error_in_the_check_ends_with_a_zip_and_the_block_saved(tmp_path, monkeypatch):
    from test_session_flow import ANSWERS_USB, make_env
    orig = package.process_take
    calls = {"n": 0}

    def boom(*a, **k):
        calls["n"] += 1
        if calls["n"] == 2:
            raise MemoryError("simulated")
        return orig(*a, **k)
    monkeypatch.setattr(package, "process_take", boom)
    ui = Scripted(list(ANSWERS_USB))
    code = cli.main(["--type", "handheld", "--short", "--folder", str(tmp_path), "--no-pause"],
                    ui=ui, env=make_env())
    assert code == 0, ui.text()
    sess = [p for p in tmp_path.iterdir() if p.name.startswith("probe-session-")][0]
    st = json.load(open(sess / "session.json"))
    assert [b["status"] for b in st["blocks"] if b["id"] == "H03"] == ["check failed"]
    assert any(p.name.startswith("SEND-THIS") for p in tmp_path.iterdir())


def test_m7_f4_ctrl_c_while_the_recorder_stops_is_no_traceback(tmp_path):
    from test_session_flow import ANSWERS_USB, make_env
    env = make_env()
    mk = env.make_recorder

    def mk2(kind, outdir, sel):
        r = mk(kind, outdir, sel)

        def stop():
            raise KeyboardInterrupt
        r.stop = stop
        return r
    env.make_recorder = mk2
    code = cli.main(["--type", "handheld", "--short", "--folder", str(tmp_path), "--no-pause"],
                    ui=Scripted(list(ANSWERS_USB)), env=env)
    assert code in (0, 2) and env.recorders[0].ended == 1


def test_m6_a_recorder_that_dies_is_noticed_at_once(tmp_path):
    from test_session_flow import make_env
    env = make_env()
    mk = env.make_recorder
    seen = {}

    def mk2(kind, outdir, sel):
        r = mk(kind, outdir, sel)
        r.alive = lambda: False
        r.exit_codes = lambda: [1]
        seen["r"] = r
        return r
    env.make_recorder = mk2
    import time

    def slow_e():
        time.sleep(0.1)
        return "e"
    ui = Scripted(["", "", "", "1", "", "", slow_e, "", "q"])
    cli.main(["--type", "handheld", "--short", "--folder", str(tmp_path), "--no-pause"], ui=ui,
             env=env)
    assert "THE RECORDER STOPPED" in ui.text() and "exit code 1" in ui.text()
    sess = [p for p in tmp_path.iterdir() if p.name.startswith("probe-session-")][0]
    st = json.load(open(sess / "session.json"))
    assert st["blocks"][0]["status"] == "failed"


def test_m7_an_oversized_record_is_skipped_without_reading_it(tmp_path):
    p = tmp_path / "big.pcap"
    with open(p, "wb") as fh:
        fh.write(struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 262144, 249))
        fh.write(struct.pack("<IIII", 1, 0, 2_000_000_000, 2_000_000_000))
        fh.truncate(24 + 16 + 2_000_000_000)              # a sparse 2 GB record
    cf = capture.CaptureFile(str(p))
    assert list(cf.records()) == [] and cf.stats["skipped"] == 1


def test_m12_a_quoted_path_from_copy_as_path_is_accepted(tmp_path):
    from test_session_flow import make_env, build
    own = tmp_path / "my take.pcapng"
    build(UsbPcapWriter()).save(own)
    env = make_env()
    env.readiness = lambda t: {"can": False, "kind": None, "lines": ["x"], "options": [],
                               "admin": ""}
    out = tmp_path / "out"
    out.mkdir()
    ui = Scripted(["", "", "", "1", "", "", f'"{own}"', "e", "", "q"])
    code = cli.main(["--type", "handheld", "--short", "--import", "--folder", str(out),
                     "--no-pause"], ui=ui, env=env)
    assert code == 0, ui.text()
    assert "Got it." in ui.text()


# ---- B3: pktmon must never be left running -------------------------------------------

class FakePktmon:
    def __init__(self):
        self.running = False
        self.calls = []

    def __call__(self, args):
        self.calls.append(" ".join(args))
        if args[0] == "status":
            return 0, "Packet Monitor is running. Logging." if self.running else \
                "Packet Monitor is not running."
        if args[0] == "start":
            self.running = True
            open(args[args.index("--file-name") + 1], "wb").write(b"ETL")
        if args[0] == "stop":
            self.running = False
        if args[0] == "filter":
            return 0, "There are no filters."
        if args[0] == "etl2pcap":
            open(args[args.index("--out") + 1], "wb").write(b"x" * 10)
        return 0, ""


def test_b3_a_killed_run_is_recognised_and_its_pktmon_offered_to_stop(tmp_path):
    fake = FakePktmon()
    r1 = recorders.PktmonRecorder(str(tmp_path), runner=fake)
    assert r1.session_start() and r1.start("N01-connect")
    assert recorders.read_marker("pktmon")["etl"].endswith("N01-connect-full.etl")
    # ... the tool is killed here: nothing stops pktmon
    r2 = recorders.PktmonRecorder(str(tmp_path), runner=fake)
    assert r2.leftover() is not None and r2.leftover().get("etl")
    assert r2.session_start() is False and "pktmon stop" in r2.notes[0]
    assert r2.stop_leftover() and not fake.running
    assert recorders.read_marker("pktmon") is None
    assert not os.path.exists(os.path.join(tmp_path, "N01-connect-full.etl"))


def test_b3_the_emergency_stop_ends_pktmon_and_the_capture_is_capped(tmp_path):
    fake = FakePktmon()
    r = recorders.PktmonRecorder(str(tmp_path), runner=fake, max_mb=1)
    r.session_start()
    r.start("N01-connect")
    start = [c for c in fake.calls if c.startswith("start")][0]
    assert "--log-mode circular" in start and "--file-size 1" in start
    with open(os.path.join(tmp_path, "N01-connect-full.etl"), "wb") as fh:
        fh.write(b"\0" * 1_000_000)
    assert r.over_limit() == "1 MB"
    recorders._emergency_stop()                       # what atexit / a closed window runs
    assert not fake.running and recorders.read_marker("pktmon") is None
    r.session_end()


def test_b3_the_runner_asks_before_stopping_a_leftover(tmp_path):
    from test_session_flow import make_env
    fake = FakePktmon()
    fake.running = True
    recorders.write_marker("pktmon", {"etl": "x", "dir": str(tmp_path)})
    env = make_env()
    env.readiness = lambda t: {"can": True, "kind": "pktmon", "lines": ["ok"], "options": [],
                               "admin": ""}
    env.make_recorder = lambda kind, outdir, sel: recorders.PktmonRecorder(outdir, runner=fake)
    env.neighbours = lambda: [(RTR_IP, "e8:df:70:01:02:03")]
    ui = Scripted(["", "2", DEV_IP, "n"])
    code = cli.main(["--type", "network", "--short", "--folder", str(tmp_path), "--no-pause"],
                    ui=ui, env=env)
    assert code == 2 and fake.running and "pktmon stop" in ui.text()
    ui = Scripted(["", "2", DEV_IP, "y", "q"])
    cli.main(["--type", "network", "--short", "--folder", str(tmp_path), "--no-pause"], ui=ui,
             env=env)
    assert "Stopped." in ui.text()


# ---- M8: what runs as root --------------------------------------------------------------

def test_m8_root_tools_come_from_system_folders_only(tmp_path, monkeypatch):
    fake = tmp_path / "tcpdump"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])
    r = recorders.TcpdumpRecorder(["en0"], str(tmp_path))
    assert r.tcpdump in (None, "/usr/sbin/tcpdump", "/usr/bin/tcpdump", "/sbin/tcpdump")
    assert r.sudo in (None, "/usr/bin/sudo")
    r.sudo = "/usr/bin/sudo"
    r.tcpdump = "/usr/sbin/tcpdump"
    cmd = r.command("en0", "/x.pcap")
    assert cmd[:3] == ["/usr/bin/sudo", "-n", "/usr/sbin/tcpdump"]
    assert "-Z" in cmd and cmd[cmd.index("-Z") + 1] == r.user
    assert recorders.system32("pktmon.exe").lower().endswith(os.path.join("system32",
                                                                           "pktmon.exe"))

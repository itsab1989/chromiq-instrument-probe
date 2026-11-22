"""Analysis: forms, framing guesses, pairs, gaps, the diff of two labels, JSON;
serial bytes from CDC-ACM and FTDI adapters."""

import json
import struct

from chromiq_probe import analyze, capture, serial_decode, usb
from synth import UsbPcapWriter

CDC = (0x2341, 0x0043)


def cdc_recording(with_cancel=False):
    w = UsbPcapWriter()
    w.describe(4, *CDC, [(0x81, 3), (0x82, 2), (0x02, 2)], iclass=0x0A)
    w.control(4, 0x21, 0x20, out=struct.pack("<IBBB", 9600, 0, 0, 8))   # SET_LINE_CODING
    for i in range(4):
        w.bulk_out(4, 0x02, b"M\r")
        w.tick(0.05)
        w.bulk_in(4, 0x82, f"L={50 + i};a=1;b=2\r\n".encode())
        w.tick(0.5)
    if with_cancel:
        w.tick(1.5)
        w.bulk_out(4, 0x02, b"X\r")
    return w


def ftdi_recording():
    w = UsbPcapWriter()
    w.describe(4, 0x0403, 0x6001, [(0x81, 2), (0x02, 2)])
    w.vendor_out(4, 0x03, value=0x4138)            # about 9600 baud on an FT232R
    w.bulk_out(4, 0x02, b"*MEAS\r")
    w.bulk_in(4, 0x81, b"\x31\x60" + b"OK 1 2 3\r")
    return w


def test_cdc_serial_decode_and_line_settings():
    w = cdc_recording()
    cap = capture.read_capture_bytes(w.pcap())
    s = analyze.serial_view(cap)
    assert s["kind"] == "cdc"
    assert s["settings"][0]["text"] == "9600 baud, 8 data bits, parity none, 1 stop"
    assert s["chunks"][0] == {"t": s["chunks"][0]["t"], "dir": "to instrument", "data": b"M\r"}
    assert s["chunks"][1]["data"] == b"L=50;a=1;b=2\r\n"


def test_ftdi_strips_status_bytes_and_reads_baud():
    cap = capture.read_capture_bytes(ftdi_recording().pcap())
    s = analyze.serial_view(cap)
    assert s["kind"] == "ftdi"
    assert [c["data"] for c in s["chunks"]] == [b"*MEAS\r", b"OK 1 2 3\r"]
    assert "about 9600 baud" in s["settings"][0]["text"]
    assert serial_decode.ftdi_strip(b"\x31\x60" + b"A" * 62 + b"\x31\x60BC", 64) == \
        b"A" * 62 + b"BC"


def test_forms_pairs_gaps_and_framing():
    cap = capture.read_capture_bytes(cdc_recording(with_cancel=True).pcap())
    a = analyze.analyze_capture(cap)
    out_forms = [f for f in a["forms"] if f["dir"] == "out" and f["chan"].startswith("ep 02")]
    m_form = [f for f in out_forms if f["example"] == b"M\r".hex()][0]
    assert m_form["count"] == 4 and m_form["varying_bytes"] == []
    in_form = [f for f in a["forms"] if f["dir"] == "in" and f["chan"].startswith("ep 82")][0]
    assert "text lines ending in CR LF" in in_form["framing"]
    assert 3 in in_form["varying_bytes"]
    assert any(p["request"] == b"M\r".hex() for p in a["pairs"])
    assert a["gaps"] and a["gaps"][-1]["seconds"] >= 1.5
    text = analyze.render("x", a)
    assert "Forms (most frequent first)" in text and "Serial adapter (cdc)" in text


def test_framing_checksums():
    def add_sum(b):
        return b + bytes([sum(b) & 0xFF])

    def add_xor(b):
        x = 0
        for c in b:
            x ^= c
        return b + bytes([x])

    def add_modbus(b):
        return b + analyze._crc16(b, 0xA001, 0xFFFF, True).to_bytes(2, "little")
    msgs = [b"\x02\x10\x33", b"\x02\x11\x40", b"\x02\x12\x99\x01"]
    assert "last byte is the sum of the others (mod 256)" in analyze.framing_guesses(
        [add_sum(m) for m in msgs])
    assert "last byte is the XOR of the others" in analyze.framing_guesses(
        [add_xor(m) for m in msgs])
    assert "last two bytes are a CRC-16 (Modbus)" in analyze.framing_guesses(
        [add_modbus(m) for m in msgs])
    assert analyze._crc16(b"123456789", 0xA001, 0xFFFF, True) == 0x4B37   # the check value
    assert analyze._crc16(b"123456789", 0x1021, 0xFFFF, False) == 0x29B1


def test_diff_of_two_labels():
    files = {"recordings/H03-strip.pcap": cdc_recording().pcap(),
             "recordings/H06-cancel-reading.pcap": cdc_recording(with_cancel=True).pcap()}
    d = analyze.diff(files, "strip", "cancel-reading")
    assert any(f["example"] == b"X\r".hex() for f in d["only_b"])
    assert not d["only_a"]
    text = analyze.render_diff(d, "strip", "cancel-reading")
    assert "Only in cancel-reading: 1" in text
    missing = analyze.render_diff(analyze.diff(files, "strip", "nothing"), "strip", "nothing")
    assert "No recording labelled \"nothing\"" in missing


def test_json_export_is_data():
    files = {"a.pcap": ftdi_recording().pcap()}
    data = json.loads(analyze.to_json(files))
    assert data["format"] == "chromiq-probe-analysis/1"
    assert data["recordings"]["a.pcap"]["serial"]["chunks"][1]["text"] == "OK 1 2 3."


def test_usb_events_pair_control_reply():
    w = UsbPcapWriter()
    w.vendor_in(3, 0x22, b"\xde\xad")
    cap = capture.read_capture_bytes(w.pcap())
    evs = usb.usb_events(cap.linktype, cap.records)
    assert evs[0]["req"] == 0x22 and evs[0]["in"] == b"\xde\xad"

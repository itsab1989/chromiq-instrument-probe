"""The USB instrument-only filter, on every recorder's format: a keyboard, a
disk and a hub on the same bus must be gone from the kept copy, asserted on
the bytes of the file that would be sent."""

import struct

import pytest

from chromiq_probe import capture, usb
from chromiq_probe.privacy import Mapper
from synth import (SERIAL, XFER_INT, DarwinWriter, UsbmonWriter, UsbPcapWriter)

VID, PID = 0x1234, 0x5678
INSTR, KEYBOARD, DISK, HUB = 3, 5, 7, 1
EPS = [(0x81, 2), (0x02, 2), (0x83, 3)]
TYPED = b"\x00\x00\x13\x00\x00\x00\x00\x00"          # a typed key on a keyboard
DISK_DATA = b"MY-PRIVATE-DOCUMENT-CONTENTS" * 4
CBW = b"USBC" + b"\x01\x00\x00\x00" + b"\x00\x02\x00\x00" + b"\x80\x00\x0a" + b"\x28" * 16


def build(writer):
    w = writer
    w.describe(HUB, 0x05E3, 0x0610, [(0x81, 3)], iclass=9, serial="")
    w.describe(KEYBOARD, 0x046D, 0xC31C, [(0x81, 3)], iclass=3, sub=1, proto=1,
               serial="KBSERIAL99")
    w.describe(DISK, 0x0781, 0x5581, [(0x81, 2), (0x02, 2)], iclass=8, serial="DISKSERIAL1")
    w.describe(INSTR, VID, PID, EPS)
    w.vendor_out(INSTR, 0x10, b"\x01\x02")
    w.bulk_out(INSTR, 0x02, b"MEASURE\r")
    w.bulk_in(INSTR, 0x81, b"OK 12.5 40.1 -3.2\r")
    w.bulk_in(KEYBOARD, 0x81, TYPED, xfer=XFER_INT)
    w.bulk_out(DISK, 0x02, CBW)
    w.bulk_in(DISK, 0x81, DISK_DATA)
    w.control(HUB, 0xA3, 0, index=2, reply=b"\xa5\x5a\xc3\x3c")   # hub port status
    w.bulk_in(INSTR, 0x83, b"\x05", xfer=XFER_INT)
    return w


def kept_file(writer, tmp_path, sel=None):
    path = build(writer).save(tmp_path / "full.pcap")
    cap = capture.read_capture(path)
    sel = sel or {"vid": VID, "pid": PID}
    res = usb.filter_usb(cap.linktype, cap.records, sel)
    m = Mapper()
    recs = usb.rewrite_usb(cap.linktype, cap.records, res["keep"], m, serial=res["serial"])
    blob = capture.pcap_bytes(cap.linktype, recs)
    return res, blob, m


WRITERS = {
    "usbpcap": lambda: UsbPcapWriter(),
    "usbmon220": lambda: UsbmonWriter(mmapped=True),
    "usbmon189": lambda: UsbmonWriter(mmapped=False),
    "darwin": lambda: DarwinWriter({HUB: (0x05E3, 0x0610, 0x01000000),
                                    KEYBOARD: (0x046D, 0xC31C, 0x01100000),
                                    DISK: (0x0781, 0x5581, 0x01200000),
                                    INSTR: (VID, PID, 0x01300000)}),
}


@pytest.mark.parametrize("fmt", sorted(WRITERS))
def test_only_the_instrument_is_kept(fmt, tmp_path):
    res, blob, _m = kept_file(WRITERS[fmt](), tmp_path)
    assert res["keep"], "the instrument's traffic must be kept"
    assert b"MEASURE\r" in blob and b"OK 12.5 40.1 -3.2\r" in blob
    assert DISK_DATA not in blob and b"USBC" not in blob
    assert TYPED not in blob
    assert "KBSERIAL99".encode("utf-16-le") not in blob
    assert "DISKSERIAL1".encode("utf-16-le") not in blob
    assert b"\xa5\x5a\xc3\x3c" not in blob                  # hub port status
    assert set(res["others"]) >= {"keyboard", "disk / memory stick", "USB hub"}


@pytest.mark.parametrize("fmt", sorted(WRITERS))
def test_instrument_serial_is_replaced_same_length(fmt, tmp_path):
    res, blob, m = kept_file(WRITERS[fmt](), tmp_path)
    assert res["serial"] == SERIAL
    assert SERIAL.encode("utf-16-le") not in blob and SERIAL.encode() not in blob
    tag = "serial1".ljust(len(SERIAL), "_").encode("utf-16-le")
    assert tag in blob
    assert m.counts.get("serial", 0) >= 1


def test_serial_kept_only_when_asked(tmp_path):
    path = build(UsbPcapWriter()).save(tmp_path / "f.pcap")
    cap = capture.read_capture(path)
    res = usb.filter_usb(cap.linktype, cap.records, {"vid": VID, "pid": PID})
    recs = usb.rewrite_usb(cap.linktype, cap.records, res["keep"], Mapper(),
                           serial=res["serial"], keep_serial=True)
    assert SERIAL.encode("utf-16-le") in capture.pcap_bytes(cap.linktype, recs)


def test_stale_address_disk_on_foreign_endpoint_is_dropped(tmp_path):
    """X-Rite probe 1.6.2: a disk's traffic carried the instrument's address."""
    w = UsbPcapWriter()
    w.describe(INSTR, VID, PID, EPS)
    w.bulk_out(INSTR, 0x05, CBW)               # endpoint 0x05 is not the instrument's
    w.bulk_in(INSTR, 0x86, DISK_DATA)
    w.bulk_out(INSTR, 0x02, CBW)               # a disk command on the instrument's endpoint
    w.bulk_out(INSTR, 0x02, b"PING\r")         # inside the disk's data phase: left out too
    w.bulk_in(INSTR, 0x81, b"USBS" + b"\x01" * 9)
    w.bulk_out(INSTR, 0x02, b"PONG\r")
    cap = capture.read_capture(w.save(tmp_path / "s.pcap"))
    res = usb.filter_usb(cap.linktype, cap.records, {"vid": VID, "pid": PID})
    blob = capture.pcap_bytes(cap.linktype, [cap.records[i] for i in res["keep"]])
    assert DISK_DATA not in blob and b"USBC" not in blob and b"USBS" not in blob
    assert b"PING\r" not in blob and b"PONG\r" in blob
    assert res["dropped"]["an endpoint your instrument does not have"] >= 1
    assert res["dropped"]["a disk's commands and data"] >= 3


def test_new_owner_after_replug_is_followed_and_old_address_released(tmp_path):
    """A cable pull: the instrument comes back at a new address, and its old
    address goes to a keyboard. Both facts come from the recording itself."""
    w = UsbPcapWriter()
    w.describe(INSTR, VID, PID, EPS)
    w.bulk_out(INSTR, 0x02, b"BEFORE\r")
    w.describe(9, VID, PID, EPS)                 # back, at address 9
    w.bulk_out(9, 0x02, b"AFTER!\r")
    w.describe(INSTR, 0x046D, 0xC31C, [(0x81, 3)], iclass=3, sub=1, proto=1, serial="")
    w.bulk_in(INSTR, 0x81, TYPED, xfer=XFER_INT)
    cap = capture.read_capture(w.save(tmp_path / "r.pcap"))
    res = usb.filter_usb(cap.linktype, cap.records, {"vid": VID, "pid": PID})
    blob = capture.pcap_bytes(cap.linktype, [cap.records[i] for i in res["keep"]])
    assert b"BEFORE\r" in blob and b"AFTER!\r" in blob and TYPED not in blob


def test_address_zero_never_kept(tmp_path):
    w = UsbPcapWriter()
    w.control(0, 0x80, 6, value=0x0100, length=18, reply=b"\x12\x01" + b"\0" * 16)
    w.describe(INSTR, VID, PID, EPS)
    cap = capture.read_capture(w.save(tmp_path / "z.pcap"))
    res = usb.filter_usb(cap.linktype, cap.records, {"vid": VID, "pid": PID})
    for ri in res["keep"]:
        assert struct.unpack_from("<H", cap.records[ri][1], 19)[0] != 0


def test_usbmon_without_descriptors_uses_the_system_address(tmp_path):
    """Linux recordings carry no description of devices already plugged in:
    the address from /sys is used until the recording names another owner."""
    w = UsbmonWriter()
    w.bulk_out(INSTR, 0x02, b"HELLO\r")
    w.bulk_in(KEYBOARD, 0x81, TYPED, xfer=XFER_INT)
    cap = capture.read_capture(w.save(tmp_path / "u.pcap"))
    none = usb.filter_usb(cap.linktype, cap.records, {"vid": VID, "pid": PID})
    assert none["keep"] == []
    held = usb.filter_usb(cap.linktype, cap.records,
                          {"vid": VID, "pid": PID, "addresses": [[1, INSTR]]})
    assert held["keep"] == [] and held["undescribed"][0]["records"] == 1   # review 2, S-B1
    res = usb.filter_usb(cap.linktype, cap.records,
                         {"vid": VID, "pid": PID, "addresses": [[1, INSTR]],
                          "allow_undescribed": True})
    blob = capture.pcap_bytes(cap.linktype, [cap.records[i] for i in res["keep"]])
    assert b"HELLO\r" in blob and TYPED not in blob


def test_kernel_pointers_are_replaced_by_counters(tmp_path):
    w = UsbPcapWriter()
    w.irp = 0xFFFFA00012345000
    build(w)
    cap = capture.read_capture(w.save(tmp_path / "k.pcap"))
    res = usb.filter_usb(cap.linktype, cap.records, {"vid": VID, "pid": PID})
    recs = usb.rewrite_usb(cap.linktype, cap.records, res["keep"], Mapper())
    for _ts, d in recs:
        assert struct.unpack_from("<Q", d, 2)[0] < 10000


def test_darwin_location_narrows_two_identical_instruments(tmp_path):
    w = DarwinWriter({3: (VID, PID, 0x01300000), 4: (VID, PID, 0x01400000)})
    w.bulk_out(3, 0x02, b"MINE\r")
    w.bulk_out(4, 0x02, b"THEIRS\r")
    cap = capture.read_capture(w.save(tmp_path / "d.pcap"))
    res = usb.filter_usb(cap.linktype, cap.records,
                         {"vid": VID, "pid": PID, "location": 0x01300000})
    blob = capture.pcap_bytes(cap.linktype, [cap.records[i] for i in res["keep"]])
    assert b"MINE\r" in blob and b"THEIRS\r" not in blob

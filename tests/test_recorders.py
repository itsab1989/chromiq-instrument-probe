"""Recorder wrappers against fake recorder programs (no device, no sudo, no
real capture), and the plain answers about what each system can record."""

import os

from chromiq_probe import capture, recorders

FAKE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fake_recorder.py")


def test_usbpcap_lets_usbpcapcmd_create_its_own_file(tmp_path):
    r = recorders.UsbPcapRecorder(FAKE, [r"\\.\USBPcap1"], str(tmp_path))
    r.startup_wait = 0.4
    live = r.start("H01-start")
    assert live == [r"\\.\USBPcap1"], r.diag_text()
    files = r.stop()
    assert len(files) == 1 and files[0].endswith("H01-start-USBPcap1-full.pcap")
    assert b"FAKE-COMMAND\r" in open(files[0], "rb").read()
    assert "-A --inject-descriptors" in r.diag[0]["command"]


def test_a_precreated_file_would_make_usbpcapcmd_fail(tmp_path):
    """The 1.5.3 fault: a file created first makes USBPcapCMD end at once."""
    class Wrong(recorders.UsbPcapRecorder):
        precreate = True
    r = Wrong(FAKE, ["hub"], str(tmp_path))
    r.startup_wait = 0.4
    assert r.start("x") == []
    assert "stopped at once" in r.diag_text()
    assert "invalid write handle" in r.diag_text()


def test_tcpdump_command_and_bpf(tmp_path):
    r = recorders.TcpdumpRecorder(["en0"], str(tmp_path), bpf="host 192.168.1.50", sudo=None,
                                  tcpdump=FAKE)
    r.startup_wait = 0.4
    assert r.transport == "net"
    assert r.session_start() is True
    assert r.start("N01-connect") == ["en0"]
    files = r.stop()
    assert files and capture.read_capture(files[0]).records
    cmd = r.diag[0]["command"]
    assert "-U -s 0 -i en0 -w" in cmd and cmd.endswith("host 192.168.1.50")


def test_tcpdump_usb_on_a_mac_uses_sudo_n_and_marks_usb(tmp_path):
    r = recorders.TcpdumpRecorder(["XHC0", "XHC1"], str(tmp_path), mac_usb=True,
                                  sudo="/usr/bin/sudo", tcpdump="/usr/sbin/tcpdump")
    assert r.transport == "usb"
    assert r.command("XHC0", "/x.pcap")[:3] == ["/usr/bin/sudo", "-n", r.tcpdump]


def test_pktmon_adds_no_filter_and_converts(tmp_path, monkeypatch):
    log = tmp_path / "pktmon.log"
    monkeypatch.setenv("FAKE_PKTMON_LOG", str(log))
    r = recorders.PktmonRecorder(str(tmp_path), exe=FAKE)
    assert r.session_start()
    assert r.start("N01-connect") == ["nics"]
    files = r.stop()
    assert len(files) == 1 and files[0].endswith(".pcapng")
    calls = log.read_text().splitlines()
    assert not any(c.startswith("filter add") for c in calls)
    assert any(c.startswith("start --capture --comp nics --pkt-size 0") for c in calls)
    assert any(c.startswith("etl2pcap") for c in calls)


def test_pktmon_refuses_when_another_recording_runs(tmp_path):
    r = recorders.PktmonRecorder(str(tmp_path), runner=lambda a: (0, "Packet Monitor is "
                                                                    "running. Logging."))
    assert r.session_start() is False
    assert "does not stop other people's recordings" in r.notes[0]


def test_readiness_windows_on_arm_usb_is_honest():
    r = recorders.readiness("usb", "Windows", "ARM64", {"usbpcap": None})
    assert r["can"] is False
    assert "no driver" in r["lines"][0]
    assert any("Linux PC" in o for o in r["options"])


def test_readiness_windows_on_arm_network_works_with_pktmon():
    r = recorders.readiness("net", "Windows", "ARM64", {"pktmon": True, "admin": True})
    assert r["can"] and r["kind"] == "pktmon" and r["admin"] == ""


def test_readiness_windows_needs_admin_said_plainly():
    r = recorders.readiness("usb", "Windows", "AMD64", {"usbpcap": "x", "admin": False})
    assert r["can"] and "Run as administrator" in r["admin"]


def test_readiness_mac_usb_with_sip_on_never_changes_it():
    r = recorders.readiness("usb", "Darwin", "arm64", {"sip": "enabled"})
    assert r["can"] is False
    assert "never changes it" in r["lines"][0]
    r = recorders.readiness("usb", "Darwin", "arm64", {"sip": "disabled", "xhc": ["XHC0"]})
    assert r["can"] and r["kind"] == "tcpdump-usb" and "zero" in " ".join(r["lines"])


def test_readiness_mac_network_needs_no_sip_change():
    r = recorders.readiness("net", "Darwin", "arm64", {"tcpdump": True})
    assert r["can"] and "No change to System Integrity Protection" in r["lines"][0]


def test_parse_csrutil():
    assert recorders.parse_csrutil("System Integrity Protection status: enabled.") == "enabled"
    assert recorders.parse_csrutil("System Integrity Protection status: disabled.") == "disabled"
    assert recorders.parse_csrutil("System Integrity Protection status: unknown (Custom "
                                   "Configuration).") == "partly"
    assert recorders.mac_xhc_interfaces("lo0 gif0 XHC0 en0 XHC20 XHCx") == ["XHC0", "XHC20"]


def test_the_tool_has_no_way_to_send():
    """S1/P8: no socket, no serial port, no USB library, no HTTP anywhere in
    the tool's own code."""
    import re
    base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "chromiq_probe")
    for name in os.listdir(base):
        if not name.endswith(".py"):
            continue
        src = open(os.path.join(base, name), encoding="utf-8").read()
        for bad in (r"\bimport socket\b", r"socket\.socket", r"\.connect\(",
                    r"\.sendto\(", r"urllib", r"http\.client", r"import serial", r"import usb\b",
                    r"pyusb", r"libusb", r"ctypes\.CDLL"):
            assert not re.search(bad, src), f"{name}: {bad}"


def test_a_missing_tcpdump_is_said_not_a_crash(tmp_path):
    """2.0.1: on a system without tcpdump in its own folders, command() met None."""
    r = recorders.TcpdumpRecorder(["en0"], str(tmp_path), sudo=None)
    r.tcpdump = None
    assert r.start("N01-connect") == []
    assert "could not be started: the recording program was not found" in r.notes[0]


def test_the_windows_folder_rights_are_checked(tmp_path, monkeypatch):
    calls = []

    class Done:
        def __init__(self, code):
            self.returncode = code

    fake = tmp_path / "icacls.exe"
    fake.write_text("")
    monkeypatch.setenv("USERNAME", "mira")
    ok = recorders.restrict_to_user(str(tmp_path), windows=True, icacls=str(fake),
                                    run=lambda cmd, **k: calls.append(cmd) or Done(0))
    assert ok and calls[0][1:5] == [str(tmp_path), "/inheritance:r", "/grant:r",
                                    "mira:(OI)(CI)F"]
    assert recorders.restrict_to_user(str(tmp_path), windows=True, icacls=str(fake),
                                      run=lambda cmd, **k: Done(5)) is False
    monkeypatch.delenv("USERNAME")
    assert recorders.restrict_to_user(str(tmp_path), windows=True, icacls=str(fake),
                                      run=lambda cmd, **k: Done(0)) is False


def test_a_folder_that_cannot_be_made_private_stops_the_recording(tmp_path, monkeypatch):
    from chromiq_probe import runner
    monkeypatch.setattr(recorders, "restrict_to_user", lambda path: False)
    import pytest
    with pytest.raises(runner.NotPrivate):
        runner.make_private_dir(str(tmp_path / "x"))

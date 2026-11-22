"""Discovery parsers on sample outputs, and the command line."""

import os

import pytest

from chromiq_probe import cli, discovery
from chromiq_probe.console import Scripted

IOREG = """+-o Root  <class IORegistryEntry>
  +-o Spectro One@01300000  <class IOUSBHostDevice, id 0x100000abc>
  |   {
  |     "idProduct" = 22136
  |     "USB Product Name" = "Spectro One"
  |     "USB Vendor Name" = "Maker"
  |     "locationID" = 19922944
  |     "USB Serial Number" = "SN7Q4X9Z2K"
  |     "idVendor" = 4660
  |   }
  +-o Keyboard@01100000  <class IOUSBHostDevice, id 0x100000abd>
      {
        "idProduct" = 49948
        "idVendor" = 1133
      }
"""

WIN_PNP = r"""USB\VID_1234&PID_5678\SN7Q4X9Z2K|Spectro One|Maker
USB\VID_1234&PID_5678&MI_00\6&1A2B3C4D&0&0000|Spectro One Interface|Maker
USB\VID_046D&PID_C31C\5&2E3F&0&3|USB Input Device|(Standard USB HID)
"""

ARP_MAC = """? (192.168.178.1) at e8:df:70:1:2:3 on en0 ifscope [ethernet]
? (192.168.178.77) at 0:c0:ee:11:22:33 on en0 ifscope [ethernet]
? (224.0.0.251) at 1:0:5e:0:0:fb on en0 ifscope permanent [ethernet]
? (192.168.178.255) at ff:ff:ff:ff:ff:ff on en0 ifscope [ethernet]
"""
ARP_WIN = """Interface: 192.168.178.23 --- 0x5
  Internet Address      Physical Address      Type
  192.168.178.1         e8-df-70-01-02-03     dynamic
  192.168.178.77        00-c0-ee-11-22-33     dynamic
  224.0.0.22            01-00-5e-00-00-16     static
"""
IP_NEIGH = "192.168.178.77 dev eth0 lladdr 00:c0:ee:11:22:33 REACHABLE\n"
NETSTAT_WIN = """  Proto  Local Address          Foreign Address        State
  TCP    192.168.178.23:50123   192.168.178.77:5000    ESTABLISHED
  TCP    0.0.0.0:135            0.0.0.0:0              LISTENING
"""
NETSTAT_MAC = "tcp4       0      0  192.168.178.23.50123   192.168.178.77.5000    ESTABLISHED\n"


def test_parse_ioreg():
    devs = discovery.parse_ioreg(IOREG)
    assert [(d.vid, d.pid) for d in devs] == [(0x1234, 0x5678), (0x046D, 0xC31C)]
    assert devs[0].location == 19922944 and devs[0].name == "Spectro One"
    assert devs[0].selection()["location"] == 19922944
    assert devs[0].selection()["serial"] == "SN7Q4X9Z2K"     # binds the unit (local only)


def test_parse_windows_pnp_ignores_interfaces():
    devs = discovery.parse_windows_pnp(WIN_PNP)
    assert [d.ids for d in devs] == ["1234:5678", "046d:c31c"]


@pytest.mark.skipif(os.name == "nt", reason="sysfs names hold ':', which Windows paths cannot")
def test_linux_sysfs(tmp_path):
    d = tmp_path / "1-2"
    (d / "1-2:1.0").mkdir(parents=True)
    for k, v in {"idVendor": "0403", "idProduct": "6001", "product": "FT232R", "busnum": "1",
                 "devnum": "7"}.items():
        (d / k).write_text(v + "\n")
    (d / "1-2:1.0" / "bInterfaceClass").write_text("ff\n")
    devs = discovery.linux_usb_devices(str(tmp_path))
    assert devs[0].address == (1, 7) and devs[0].interfaces == [(0xFF, 0, 0)]
    assert "serial adapter" in devs[0].verdict()
    assert devs[0].selection()["addresses"] == [[1, 7]]


@pytest.mark.parametrize("text", [ARP_MAC, ARP_WIN, IP_NEIGH])
def test_parse_neighbours(text):
    n = dict(discovery.parse_neighbours(text))
    assert n["192.168.178.77"] == "00:c0:ee:11:22:33"
    assert not any(ip.startswith("224.") or ip.endswith(".255") for ip in n)


@pytest.mark.parametrize("text", [NETSTAT_WIN, NETSTAT_MAC])
def test_parse_connections(text):
    assert discovery.parse_connections(text) == [("tcp", "192.168.178.77", 5000)]


def test_before_and_after_network():
    before = {"neighbours": [("192.168.178.1", "e8:df:70:01:02:03")], "connections": []}
    after = {"neighbours": before["neighbours"] + [("192.168.178.77", "00:c0:ee:11:22:33")],
             "connections": [("tcp", "192.168.178.77", 5000), ("tcp", "142.250.1.1", 443)]}
    rows = discovery.network_candidates(before, after)
    assert rows[0][0] == "192.168.178.77" and rows[0][1] == "00:c0:ee:11:22:33"
    assert "5000" in rows[0][2]
    assert rows[-1][0] == "142.250.1.1"          # internet addresses last


def test_new_usb_devices():
    a = discovery.UsbDevice(1, 2)
    b = discovery.UsbDevice(3, 4)
    assert discovery.new_devices([a], [a, b]) == [b]


def test_help_and_version(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["--help"])
    assert e.value.code == 0
    out = capsys.readouterr().out
    assert "--check" in out and "--analyze" in out and "never sends anything" in out


def test_sessions_list_and_validate(tmp_path):
    ui = Scripted([])
    assert cli.main(["--sessions"], ui=ui) == 0
    assert "table" in ui.text() and "short set" in ui.text()
    bad = tmp_path / "s.json"
    bad.write_text("{not json")
    ui = Scripted([])
    assert cli.main(["--validate-session", str(bad)], ui=ui) == 1
    assert "not valid JSON" in ui.text()
    ui = Scripted([])
    good = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "chromiq_probe", "sessions", "table.json")
    assert cli.main(["--validate-session", good], ui=ui) == 0


def test_exit_codes_for_wrong_use(tmp_path):
    assert cli.main(["--check", str(tmp_path / "nope.zip")], ui=Scripted([])) == 1
    assert cli.main(["--analyze", str(tmp_path / "nope.pcap")], ui=Scripted([])) == 1
    assert cli.main(["--resume", str(tmp_path)], ui=Scripted([])) == 1


def test_cannot_record_here_says_why_and_exits_2(tmp_path):
    from test_session_flow import make_env
    env = make_env()
    env.readiness = lambda t: {"can": False, "kind": None, "lines": ["no recorder here"],
                               "options": ["another way"], "admin": ""}
    ui = Scripted(["", "", "", "", ""])
    code = cli.main(["--type", "handheld", "--folder", str(tmp_path), "--no-pause"], ui=ui,
                    env=env)
    assert code == 2
    assert "no recorder here" in ui.text() and "another way" in ui.text()
    assert "--import" in ui.text()


def test_serial_port_without_adapter_is_explained(tmp_path):
    from test_session_flow import make_env
    ui = Scripted(["3"])
    code = cli.main(["--type", "serial", "--folder", str(tmp_path), "--no-pause"], ui=ui,
                    env=make_env())
    assert code == 4
    assert "cannot be listened to" in ui.text()

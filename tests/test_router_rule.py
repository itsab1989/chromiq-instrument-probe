"""2.0.1: the router rule on real output formats.

The macOS texts are this project's own Mac (macOS 27, SIP on, Wi-Fi on en0, four
utun interfaces), with every address replaced by documentation ranges and
made-up hardware addresses; the line format is kept exactly. The Linux and
Windows texts follow those systems' documented output (`ip -4 route`, `ip -o
addr`, `route print -4`); they could not be run here."""

import ipaddress

from chromiq_probe import cli, discovery
from chromiq_probe.console import Scripted

MAC_NETSTAT = """Routing tables

Internet:
Destination        Gateway            Flags               Netif Expire
default            192.0.2.1          UGScg                 en0
127                127.0.0.1          UCS                   lo0
127.0.0.1          127.0.0.1          UH                    lo0
169.254            link#15            UCS                   en0      !
192.0.2            link#15            UCS                   en0      !
192.0.2.23/32      link#15            UCS                   en0      !
224.0.0/4          link#15            UmCS                  en0      !
255.255.255.255/32 link#15            UCS                   en0      !
"""
# what a full-tunnel VPN adds on a Mac: its own default first, the Wi-Fi's kept as a
# scoped default ("I" flag)
MAC_NETSTAT_VPN = """Internet:
Destination        Gateway            Flags               Netif Expire
default            link#22            UCSg                utun4
default            192.0.2.1          UGScIg                en0
"""
MAC_IFCONFIG = """lo0: flags=8049<UP,LOOPBACK,RUNNING,MULTICAST> mtu 16384
\tinet 127.0.0.1 netmask 0xff000000
\tinet6 ::1 prefixlen 128
en0: flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500
\tether 02:00:5e:10:00:01
\tinet6 fe80::1c2d:3e4f:5a6b:7c8d%en0 prefixlen 64 secured scopeid 0xf
\tinet 192.0.2.23 netmask 0xffffff00 broadcast 192.0.2.255
\tinet6 2001:db8::1c2d:3e4f:5a6b:7c8d prefixlen 64 autoconf secured
utun0: flags=8051<UP,POINTOPOINT,RUNNING,MULTICAST> mtu 1500
\tinet6 fe80::a1b2:c3d4:e5f6:1%utun0 prefixlen 64 scopeid 0x13
utun3: flags=8051<UP,POINTOPOINT,RUNNING,MULTICAST> mtu 1380
\tinet6 fe80::a1b2:c3d4:e5f6:4%utun3 prefixlen 64 scopeid 0x16
"""
LINUX_ROUTES = """default via 192.0.2.1 dev wlp2s0 proto dhcp metric 600
default via 198.51.100.1 dev enp3s0 proto dhcp metric 100
192.0.2.0/24 dev wlp2s0 proto kernel scope link src 192.0.2.23 metric 600
local 192.0.2.23 dev wlp2s0 table local proto kernel scope host src 192.0.2.23
"""
LINUX_ADDRS = """1: lo    inet 127.0.0.1/8 scope host lo\\       valid_lft forever preferred_lft forever
2: enp3s0    inet 198.51.100.7/24 brd 198.51.100.255 scope global dynamic enp3s0\\
3: wlp2s0    inet 192.0.2.23/24 brd 192.0.2.255 scope global dynamic wlp2s0\\
"""
WIN_ROUTE_PRINT = """===========================================================================
IPv4 Route Table
===========================================================================
Active Routes:
Network Destination        Netmask          Gateway       Interface  Metric
          0.0.0.0          0.0.0.0        192.0.2.1      192.0.2.23     35
        127.0.0.0        255.0.0.0         On-link         127.0.0.1    331
        192.0.2.0    255.255.255.0         On-link        192.0.2.23    291
       192.0.2.23  255.255.255.255         On-link        192.0.2.23    291
===========================================================================
"""


def facts(routes, addrs):
    return {"routes": discovery.parse_default_routes(routes),
            "networks": discovery.parse_interface_networks(addrs)}


def test_mac_real_format_parses():
    f = facts(MAC_NETSTAT, MAC_IFCONFIG)
    assert f["routes"] == [("192.0.2.1", "en0")]
    assert f["networks"]["en0"] == [ipaddress.ip_interface("192.0.2.23/24")]
    assert "utun0" not in f["networks"]                   # IPv6 only: never read


def test_mac_normal_network_allows_the_instrument_and_refuses_the_router():
    f = facts(MAC_NETSTAT, MAC_IFCONFIG)
    assert discovery.router_check("192.0.2.77", f)["ok"]
    r = discovery.router_check("192.0.2.1", f)
    assert not r["ok"] and "That is your router" in r["why"]
    r = discovery.router_check("203.0.113.9", f)
    assert not r["ok"] and "reached through your router" in r["why"]


def test_mac_full_tunnel_vpn_keeps_the_lan_and_says_what_it_found():
    f = facts(MAC_NETSTAT_VPN, MAC_IFCONFIG)
    assert ("", "utun4") in f["routes"] and ("192.0.2.1", "en0") in f["routes"]
    assert discovery.router_check("192.0.2.77", f)["ok"]           # on the Wi-Fi's own net
    vpn_only = facts("default            link#22            UCSg                utun4\n",
                     MAC_IFCONFIG)
    r = discovery.router_check("10.20.0.50", vpn_only)
    assert not r["ok"] and "tunnel interface (a VPN)" in r["why"]


def test_no_ipv4_default_route_is_a_direct_cable():
    r = discovery.router_check("192.0.2.77", facts("Internet:\n", MAC_IFCONFIG))
    assert r["ok"] and r["no_router"] and "no IPv4 default route" in r["why"]


def test_linux_two_physical_interfaces_each_with_a_default():
    f = facts(LINUX_ROUTES, LINUX_ADDRS)
    assert f["routes"] == [("192.0.2.1", "wlp2s0"), ("198.51.100.1", "enp3s0")]
    assert discovery.router_check("192.0.2.77", f)["ok"]
    assert discovery.router_check("198.51.100.50", f)["ok"]
    assert not discovery.router_check("198.51.100.1", f)["ok"]


def test_windows_route_print():
    f = facts(WIN_ROUTE_PRINT, WIN_ROUTE_PRINT)
    assert f["routes"] == [("192.0.2.1", "192.0.2.23")]
    assert f["networks"]["192.0.2.23"] == [ipaddress.ip_interface("192.0.2.23/24")]
    assert discovery.router_check("192.0.2.77", f)["ok"]
    assert not discovery.router_check("192.0.2.1", f)["ok"]


def test_the_2_0_0_mac_case_no_neighbour_table_still_records(tmp_path):
    """macOS hid the neighbour table from the binary; 2.0.0 then refused. Now the
    address is typed, the rule needs no hardware address, and the block runs."""
    from test_session_flow import _Saver, make_env, net_recording
    env = make_env(make=lambda stem: _Saver(net_recording(stem)))
    env.network_facts = lambda: {"routes": [("192.168.178.1", "en0")], "networks": {
        "en0": [ipaddress.ip_interface("192.168.178.23/24")]}}
    env.neighbours = lambda: []                            # what macOS showed the binary
    env.connections = lambda: []
    ui = Scripted(["2", "192.168.178.77", "", "e", "", "q"])
    code = cli.main(["--type", "network", "--short", "--folder", str(tmp_path), "--no-pause"],
                    ui=ui, env=env)
    assert code == 0, ui.text()
    assert "could not identify" not in ui.text()
    assert "How is it connected to this computer?" not in ui.text()       # --type network

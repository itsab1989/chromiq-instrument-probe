"""The network filter and its privacy pass, asserted on bytes."""

import ipaddress
import struct

from chromiq_probe import capture, net
from chromiq_probe.privacy import Mapper
from synth import (DEV_IP, DEV_MAC, HOST_IP, HOST_MAC, OTHER_IP, OTHER_MAC, ROUTER_MAC, WEB_IP,
                   NetWriter, arp, dhcp_discover, eth, tcp, tls_record, udp)

SEL = {"ips": [DEV_IP], "macs": [net.mac_text(DEV_MAC)]}
SECRET_WEB = b"GET /my-bank-account HTTP/1.1\r\nHost: bank.example\r\n\r\n"
OTHER_HOST_DATA = b"PRINT JOB OF ANOTHER COMPUTER"


def session():
    w = NetWriter()
    w.add(eth(b"\xff" * 6, HOST_MAC, 0x0806, arp(1, HOST_MAC, HOST_IP, b"\0" * 6, DEV_IP)))
    w.add(eth(HOST_MAC, DEV_MAC, 0x0806, arp(2, DEV_MAC, DEV_IP, HOST_MAC, HOST_IP)))
    w.add(eth(DEV_MAC, HOST_MAC, 0x0800, tcp(HOST_IP, DEV_IP, 50123, 5000,
                                              b"*MEAS:SPOT? host=" + HOST_IP.encode() + b"\r\n")))
    w.add(eth(HOST_MAC, DEV_MAC, 0x0800, tcp(DEV_IP, HOST_IP, 5000, 50123,
                                              b"OK;L=50.1;a=2.0;b=-3.4\r\n")))
    w.add(eth(ROUTER_MAC, HOST_MAC, 0x0800, tcp(HOST_IP, WEB_IP, 50200, 443, SECRET_WEB)))
    w.add(eth(HOST_MAC, OTHER_MAC, 0x0800, udp(OTHER_IP, HOST_IP, 9100, 9100, OTHER_HOST_DATA)))
    w.add(eth(b"\xff" * 6, OTHER_MAC, 0x0806, arp(1, OTHER_MAC, OTHER_IP, b"\0" * 6, HOST_IP)))
    return w


def kept(blob, sel=SEL):
    cap = capture.read_capture_bytes(blob)
    res = net.filter_net(cap.linktype, cap.records, sel)
    m = Mapper()
    recs, enc = net.rewrite_net(cap.linktype, cap.records, res["keep"], m,
                                dict(sel, _learned=res["learned_ips"]))
    return res, capture.pcap_bytes(cap.linktype, recs), m, enc


def test_other_hosts_and_internet_are_gone():
    res, blob, _m, _e = kept(session().pcap())
    assert b"OK;L=50.1;a=2.0;b=-3.4\r\n" in blob
    assert SECRET_WEB not in blob and b"bank" not in blob
    assert OTHER_HOST_DATA not in blob
    assert OTHER_MAC not in blob and ROUTER_MAC not in blob
    assert len(res["keep"]) == 4


def test_every_address_is_replaced_in_headers_and_text():
    _res, blob, m, _e = kept(session().pcap())
    for raw in (HOST_MAC, DEV_MAC):
        assert raw not in blob
    for ip in (HOST_IP, DEV_IP):
        assert ipaddress.ip_address(ip).packed not in blob
        assert ip.encode() not in blob
    assert ipaddress.ip_address("198.51.100.1").packed in blob      # the device
    assert ipaddress.ip_address("192.0.2.1").packed in blob         # the computer
    assert b"host=ip" in blob                                         # same length text
    assert m.counts.get("ip (text)") == 1


def test_checksums_are_valid_after_rewriting():
    _res, blob, _m, _e = kept(session().pcap())
    cap = capture.read_capture_bytes(blob)
    for _ts, d in cap.records:
        f = net.parse_frame(cap.linktype, d)
        if f.ethertype != 0x0800:
            continue
        ip = net.parse_ip(d, f.l3)
        assert net._csum(bytes(d[f.l3:f.l3 + 20])) == 0
        seg = bytes(d[ip[4]:])
        pseudo = ip[1].packed + ip[2].packed + struct.pack(">BBH", 0, ip[3], len(seg))
        assert net._csum(pseudo + seg) == 0


def test_pcapng_options_and_comments_never_reach_the_copy():
    w = session()
    blob_in = w.pcapng(leak=b"SECRET-ADAPTER-NAME MY-PC")
    assert b"SECRET-ADAPTER-NAME" in blob_in
    _res, blob, _m, _e = kept(blob_in)
    assert b"SECRET-ADAPTER-NAME" not in blob and b"MY-PC" not in blob
    assert blob[:4] == b"\xd4\xc3\xb2\xa1"                            # classic pcap


def test_new_address_after_power_cycle_is_learned_from_the_device_mac():
    w = session()
    w.add(eth(b"\xff" * 6, DEV_MAC, 0x0800, dhcp_discover(DEV_MAC)))
    w.add(eth(b"\xff" * 6, DEV_MAC, 0x0806, arp(1, DEV_MAC, "192.168.178.80", b"\0" * 6,
                                                HOST_IP)))
    w.add(eth(DEV_MAC, HOST_MAC, 0x0800, tcp(HOST_IP, "192.168.178.80", 50124, 5000,
                                              b"*IDN?\r\n")))
    res, blob, _m, _e = kept(w.pcap())
    # 2.0 fix round (review B2): a new address is only PROPOSED, never adopted
    # without the owner's yes, so the traffic to it is not kept yet
    na = res["new_addresses"]
    assert [(x["ip"], x["evidence"]) for x in na] == [("192.168.178.80", "its own ARP")]
    assert "1 packet with it on port 5000" in na[0]["talk"]
    assert b"*IDN?\r\n" not in blob
    assert b"SPECTRO-SN7Q4X9Z2K" not in blob                          # DHCP host name masked


def test_a_router_mac_is_not_used_to_match():
    w = NetWriter()
    for i, ip in enumerate((WEB_IP, "8.8.8.8", "1.1.1.1")):
        w.add(eth(HOST_MAC, ROUTER_MAC, 0x0800, udp(ip, HOST_IP, 53, 4000 + i, b"internet")))
    w.add(eth(HOST_MAC, ROUTER_MAC, 0x0800, tcp(DEV_IP, HOST_IP, 5000, 50123, b"DEVICE")))
    res, blob, _m, _e = kept(w.pcap(), {"ips": [DEV_IP], "macs": [net.mac_text(ROUTER_MAC)]})
    assert res["router"] is True and res["refused"]
    assert b"internet" not in blob and b"DEVICE" not in blob       # review B1: refused


def test_tls_bodies_are_zeroed_but_sizes_and_headers_stay():
    w = NetWriter()
    hello = tls_record(22, b"\x01\x00\x00\x10" + b"servername=instrument-SN7Q4X9Z2K.local")
    data = tls_record(23, b"ENCRYPTED-STUFF" * 3)
    w.add(eth(DEV_MAC, HOST_MAC, 0x0800, tcp(HOST_IP, DEV_IP, 50300, 443, hello + data)))
    w.add(eth(HOST_MAC, DEV_MAC, 0x0800, tcp(DEV_IP, HOST_IP, 443, 50300, tls_record(22, b"X" * 40))))
    res, blob, m, enc = kept(w.pcap())
    assert b"servername" not in blob and b"ENCRYPTED" not in blob and b"X" * 40 not in blob
    assert enc and {v["kind"] for v in enc.values()} == {"TLS"}
    cap = capture.read_capture_bytes(blob)
    assert len(cap.records[0][1]) == len(w.records[0][1])
    assert bytes([22, 3, 3]) in cap.records[0][1] and bytes([23, 3, 3]) in cap.records[0][1]
    assert m.counts["encrypted bytes replaced by zeros"] > 0


def test_port_choice_narrows():
    w = session()
    w.add(eth(DEV_MAC, HOST_MAC, 0x0800, udp(HOST_IP, DEV_IP, 5353, 5353, b"MDNS-NOISE")))
    _res, blob, _m, _e = kept(w.pcap(), dict(SEL, ports=[5000]))
    assert b"MDNS-NOISE" not in blob and b"OK;L=50.1" in blob


def test_pktmon_duplicates_are_dropped():
    w = NetWriter()
    f = eth(HOST_MAC, DEV_MAC, 0x0800, tcp(DEV_IP, HOST_IP, 5000, 50123, b"ONCE"))
    w.add(f, dt=0.0001)
    w.add(f, dt=0.0001)
    res, _blob, _m, _e = kept(w.pcap(), dict(SEL, dedupe=True))
    assert len(res["keep"]) == 1
    res, _blob, _m, _e = kept(w.pcap())                  # review m2: other recorders keep both
    assert len(res["keep"]) == 2

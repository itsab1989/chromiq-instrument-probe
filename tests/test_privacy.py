"""Every identifier class of the privacy contract."""

import ipaddress

from chromiq_probe import privacy
from chromiq_probe.privacy import Mapper, same_length, scrub_text

IDS = {"user": "jdoe", "home": "/Users/jdoe", "host": "Studio-PC.local",
       "host_short": "Studio-PC"}


def test_same_value_same_placeholder_and_numbered_by_first_sight():
    m = Mapper()
    a = m.ip("10.77.66.10")
    b = m.ip("10.77.66.11")
    assert m.ip("10.77.66.10") == a != b
    assert str(a) == "192.0.2.1" and str(b) == "192.0.2.2"
    m.device_ips.add(ipaddress.ip_address("10.0.0.5"))
    assert str(m.ip("10.0.0.5")) == "198.51.100.1"


def test_placeholders_are_never_mapped_again():
    m = Mapper()
    fake = m.ip("10.77.66.10")
    assert m.ip(fake) == fake
    mac = m.mac(bytes.fromhex("a4b1c2d3e4f5"))
    assert m.mac(mac) == mac


def test_many_addresses_never_collide():
    m = Mapper()
    fakes = {m.ip(f"10.1.{i // 250}.{i % 250 + 1}") for i in range(700)}
    assert len(fakes) == 700
    assert all(any(f in n for n in privacy.PLACEHOLDER_NETS) for f in fakes)


def test_special_addresses_stay():
    m = Mapper()
    for ip in ("255.255.255.255", "224.0.0.251", "0.0.0.0", "10.77.66.255"):
        assert str(m.ip(ip)) == ip
    assert m.mac(b"\xff" * 6) == b"\xff" * 6
    assert m.mac(bytes.fromhex("01005e0000fb")) == bytes.fromhex("01005e0000fb")


def test_scrub_text_user_home_host_mac_ip_serial_hidden():
    m = Mapper()
    text = ("C:\\Users\\jdoe\\Desktop\\x.txt /Users/jdoe/Documents on Studio-PC.local "
            "(studio-pc) mac a4:b1:c2:d3:e4:f5 ip 192.168.178.23 Serial Number: AB12CD34 "
            "my company ACME-PRINT")
    out = scrub_text(text, m, IDS, hide=["ACME-PRINT"])
    for secret in ("jdoe", "Studio-PC", "studio-pc", "a4:b1:c2:d3:e4:f5", "192.168.178.23",
                   "AB12CD34", "ACME-PRINT"):
        assert secret not in out, secret
    assert "C:\\Users\\USER" in out and "~/Documents" in out
    assert "02:00:00:00:00:01" in out and "192.0.2.1" in out


def test_byte_rules_keep_length_in_ascii_and_utf16():
    m = Mapper()
    m.text("serial", "SN7Q4X9Z2K")
    m.ip("192.168.178.23")
    m.mac(bytes.fromhex("a4b1c2d3e4f5"))
    data = (b"id=SN7Q4X9Z2K;" + "SN7Q4X9Z2K".encode("utf-16-le") + b";192.168.178.23;"
            + bytes.fromhex("a4b1c2d3e4f5") + b";A4-B1-C2-D3-E4-F5")
    out = m.scrub_bytes(data, m.byte_rules())
    assert len(out) == len(data)
    assert b"SN7Q4X9Z2K" not in out and "SN7Q4X9Z2K".encode("utf-16-le") not in out
    assert b"192.168.178.23" not in out and bytes.fromhex("a4b1c2d3e4f5") not in out
    assert b"A4-B1-C2-D3-E4-F5" not in out
    assert b"serial1___" in out


def test_same_length_short_fields():
    assert same_length("serial1", 10) == "serial1___"
    assert same_length("serial1", 3) == "###"
    assert same_length("x", 0) == ""


def test_salted_code_changes_with_the_salt():
    a = privacy.salted_code("AB12CD34")
    assert a == privacy.salted_code("AB12CD34")
    privacy.new_salt()
    assert privacy.salted_code("AB12CD34") != a

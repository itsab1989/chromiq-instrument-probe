"""What is already known about a USB device.

The ArgyllCMS table is carried over from this repository's version 1.1
(extracted from ArgyllCMS 3.5.0 `spectro/insttypes.c`): if a device is in it,
ChromIQ can very likely use it already, and no recording is needed.
The USB numbers are facts listed in ArgyllCMS (GPL, by Graeme Gill); no ArgyllCMS
code is copied.
"""

from __future__ import annotations

ARGYLL_USB_SUPPORTED = {
    (0x04DB, 0x005B): "Colorimtre HCFR",
    (0x0670, 0x0001): "Monaco Optix / i1 Display 1",
    (0x0765, 0x5001): "Huey L",
    (0x0765, 0x5010): "Huey L",
    (0x0765, 0x5020): "i1 Display Pro / ColorMunki Display",
    (0x0765, 0x6003): "ColorMunki Smile",
    (0x0765, 0x6008): "ColorMunki i1Studio",
    (0x0765, 0x6009): "i1Pro 3",
    (0x0765, 0xD020): "DTP20",
    (0x0765, 0xD092): "DTP92Q",
    (0x0765, 0xD094): "DTP94",
    (0x085C, 0x0100): "ColorVision Spyder1",
    (0x085C, 0x0200): "ColorVision Spyder2",
    (0x085C, 0x0300): "Datacolor Spyder3",
    (0x085C, 0x0400): "Datacolor Spyder4",
    (0x085C, 0x0500): "Datacolor Spyder5",
    (0x085C, 0x0A00): "Datacolor SpyderX",
    (0x085C, 0x0A0A): "Datacolor SpyderX2",
    (0x085C, 0x0A0B): "Datacolor Spyder2024",
    (0x0971, 0x2000): "i1Pro / i1Pro 2",
    (0x0971, 0x2001): "i1 Monitor",
    (0x0971, 0x2003): "i1 Display 2",
    (0x0971, 0x2005): "Huey",
    (0x0971, 0x2007): "ColorMunki",
    (0x2457, 0x4000): "Image Engineering EX1",
    (0x04D8, 0xF8DA): "Hughski ColorHug (old firmware)",
    (0x273F, 0x1001): "Hughski ColorHug",
    (0x273F, 0x1004): "Hughski ColorHug2",
}

ARGYLL_KNOWN_UNSUPPORTED = {
    (0x0971, 0x2004): "X-Rite i1iO scanning table",
    (0x0971, 0x2006): "X-Rite i1iSis chart reader",
}

INSTRUMENT_VENDORS = {
    0x0765: "X-Rite / Calibrite",
    0x0971: "GretagMacbeth / X-Rite",
    0x085C: "ColorVision / Datacolor",
    0x0670: "Sequel Imaging",
    0x2457: "Image Engineering",
    0x273F: "Hughski",
    0x132B: "Konica Minolta",
}

SERIAL_BRIDGES = {
    0x0403: "FTDI",
    0x1A86: "WCH CH340 / CH341",
    0x10C4: "Silicon Labs CP210x",
    0x067B: "Prolific PL2303",
}

XRITE_VENDORS = (0x0765, 0x0971)


def verdict(vid: int, pid: int, interfaces=()) -> str:
    key = (vid, pid)
    if key in ARGYLL_USB_SUPPORTED:
        return (f"ArgyllCMS already supports this ({ARGYLL_USB_SUPPORTED[key]}), so ChromIQ "
                "can very likely use it today. A recording is welcome but not needed.")
    if key in ARGYLL_KNOWN_UNSUPPORTED:
        return f"{ARGYLL_KNOWN_UNSUPPORTED[key]}: known, not yet supported. A recording helps."
    if vid in SERIAL_BRIDGES:
        return (f"a USB serial adapter ({SERIAL_BRIDGES[vid]}): often an instrument with a "
                "simple serial protocol behind it.")
    if any(c == 9 for c, _s, _p in interfaces):
        return "a USB hub, not an instrument"
    if any(i in ((3, 1, 1), (3, 1, 2)) for i in interfaces):
        return "a keyboard or mouse, not an instrument"
    if any(c == 8 for c, _s, _p in interfaces):
        return "a disk or memory stick, not an instrument"
    if vid in INSTRUMENT_VENDORS:
        return f"made by {INSTRUMENT_VENDORS[vid]}, a maker of instruments"
    return ""


def is_unsuitable(interfaces) -> str:
    """A reason why a device must not be chosen as the instrument, or ''."""
    if any(c == 9 for c, _s, _p in interfaces):
        return "it is a USB hub"
    if any(i in ((3, 1, 1), (3, 1, 2)) for i in interfaces):
        return "it is a keyboard or a mouse"
    if any(c == 8 for c, _s, _p in interfaces):
        return "it is a disk or a memory stick"
    return ""


CLASS_NAME = {1: "audio", 2: "communications (serial)", 3: "HID (keyboard, mouse or instrument)",
              7: "printer", 8: "disk", 9: "hub", 10: "serial data", 14: "camera",
              224: "wireless", 255: "vendor-specific"}

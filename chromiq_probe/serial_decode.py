"""Serial bytes from a USB serial adapter's traffic (an optional helper).

Many instruments are a serial device behind a USB adapter chip. On the USB
side their bytes travel in bulk transfers; this module turns those back into
the two serial byte streams (computer to instrument, instrument to computer)
and reads the line settings the program chose.

Framing, as the public Linux drivers handle these chips (an assumption,
checked only with made-up recordings):

* CDC-ACM (USB class 0x02 / 0x0A): bulk data is the raw serial bytes;
  SET_LINE_CODING (class request 0x20) carries 7 bytes: rate (4, little
  endian), stop bits (0 = 1, 1 = 1.5, 2 = 2), parity (0 none, 1 odd, 2 even,
  3 mark, 4 space), data bits.
* FTDI (vendor 0x0403): every packet from the chip starts with 2 status
  bytes, once per max-packet chunk (64 bytes at full speed, 512 at high
  speed); data to the chip is raw. Baud rate: vendor request 0x03, an encoded
  divisor in wValue / wIndex (shown raw; decoded for the common FT232R
  form).
* Prolific PL2303 (0x067b), WCH CH340 / CH341 (0x1a86), Silicon Labs CP210x
  (0x10c4): bulk data is raw; line settings are vendor requests, shown raw.
"""

from __future__ import annotations

import struct

BRIDGES = {
    0x0403: "FTDI",
    0x067B: "Prolific PL2303",
    0x1A86: "WCH CH340 / CH341",
    0x10C4: "Silicon Labs CP210x",
}
PARITY = {0: "none", 1: "odd", 2: "even", 3: "mark", 4: "space"}
STOP = {0: "1", 1: "1.5", 2: "2"}


def bridge_kind(vid: int, interfaces=()) -> str | None:
    if vid in BRIDGES:
        return "ftdi" if vid == 0x0403 else "raw"
    if any(c in (0x02, 0x0A) for c, _s, _p in interfaces):
        return "cdc"
    return None


def ftdi_strip(data: bytes, max_packet: int = 64) -> bytes:
    out = bytearray()
    for i in range(0, len(data), max_packet):
        out += data[i + 2:i + max_packet]
    return bytes(out)


def ftdi_baud(wvalue: int, windex: int) -> int | None:
    """FT232R-style divisor: 14 bits integer, 3 bits fraction (0, 1/2, 1/4,
    1/8, 3/8, 5/8, 3/4, 7/8), base clock 3 MHz."""
    frac = {0: 0, 1: 0.5, 2: 0.25, 3: 0.125, 4: 0.375, 5: 0.625, 6: 0.75, 7: 0.875}
    integer = wvalue & 0x3FFF
    code = ((wvalue >> 14) & 3) | ((windex & 1) << 2)
    div = integer + frac[code]
    if integer == 0 and code == 0:
        return 3000000
    if integer == 1 and code == 0:
        return 2000000
    return int(round(3000000 / div)) if div else None


def decode(events, kind: str, max_packet_in: int = 64) -> dict:
    """events: usb.usb_events() of a kept recording. Returns
    {"settings": [...], "chunks": [{"t", "dir", "data"}]} where dir is
    "to instrument" or "from instrument"."""
    settings, chunks = [], []
    for ev in events:
        if ev["kind"] == "control":
            rt, req = ev["rt"], ev["req"]
            if kind == "cdc" and rt == 0x21 and req == 0x20 and len(ev["out"]) >= 7:
                rate, stop, parity, bits = struct.unpack_from("<IBBB", ev["out"], 0)
                settings.append({"t": ev["t"], "text": f"{rate} baud, {bits} data bits, parity "
                                 f"{PARITY.get(parity, parity)}, {STOP.get(stop, stop)} stop"})
            elif kind == "ftdi" and rt == 0x40 and req == 0x03:
                baud = ftdi_baud(ev["wValue"], ev["wIndex"])
                settings.append({"t": ev["t"], "text": f"about {baud} baud (FTDI divisor "
                                 f"{ev['wValue']:#06x}/{ev['wIndex']:#06x})"})
            elif kind == "raw" and ((rt >> 5) & 3) == 2 and not rt & 0x80:
                settings.append({"t": ev["t"], "text": f"vendor request {req:#04x} value "
                                 f"{ev['wValue']:#06x} index {ev['wIndex']:#06x} "
                                 f"data {ev['out'].hex()}"})
            continue
        if ev.get("type") != "bulk":
            continue
        data = ev["data"]
        if ev["dir_in"] and kind == "ftdi":
            data = ftdi_strip(data, max_packet_in)
        if data:
            chunks.append({"t": ev["t"], "dir": "from instrument" if ev["dir_in"]
                           else "to instrument", "data": data})
    return {"settings": settings, "chunks": chunks}

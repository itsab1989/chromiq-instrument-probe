# Changelog

## v2.0.1 (2026-11-22)

From the first real run of 2.0.0, on a Mac:

- **Fixed: on a Mac the network recording refused with "router unknown" on a
  normal network.** macOS (15 and newer, very likely its "Local Network"
  privacy) hides the list of devices on the network from the tool, and 2.0.0
  needed the router's hardware address from that list. The router check now
  uses only the routes and this computer's own network addresses: an address
  is refused when it is a default gateway, or when it is on none of this
  computer's own networks (reached through the router, or through a VPN); a
  computer with no IPv4 default route at all (a direct cable) may record. IPv6
  routes and tunnel interfaces (utun and the like, normal on every Mac) play no
  part. The message names what was found.
- `--type network` no longer asks how the instrument is connected.
- A missing recording program (tcpdump not in the system's folders) gives a
  plain sentence instead of a crash.
- Windows: the four tests that failed there in the 2.0.0 build are made right
  for Windows (the folder rights are checked through icacls, POSIX file modes
  only on POSIX), and the tests block the Windows build again.

## v2.0.0 (2026-11-22)

A new tool in the same place: the **universal recording probe**. Version 1.x
wrote a report of the connected devices; 2.0 records what the maker's own
program says to an instrument of any kind, keeps only that instrument's part,
hides private details and makes one zip to send.

**Built and tested with made-up recordings only. Not yet run with a real
instrument on any system.** An independent review attacked the first build
with hostile recordings; every attack is now a test that asserts on the zip's
bytes (`tests/test_review_attacks.py`).

- **Any instrument, any of these connections:** USB (Windows with USBPcap,
  Linux with usbmon, macOS only with System Integrity Protection off),
  network cable and Wi-Fi (Windows' own pktmon; the system tcpdump on macOS,
  with SIP on, and Linux; IPv4 only), and serial instruments through a USB
  serial adapter (the serial bytes decoded for FTDI and CDC-ACM adapters,
  shown raw for Prolific, CH340 and CP210x).
- **You choose the instrument**, the easy way (unplug and plug in, or connect
  the maker's program), from a list with no default: Enter alone chooses
  nothing. Several devices can be chosen (a table and the instrument in its
  arm). Your router is refused.
- **Bound to ONE physical device:** by its serial number from the system's
  device list, its port on a Mac, its address at the start of each block on
  Linux. A second device with the same USB numbers must be unplugged; when a
  recording cannot tell two apart, it keeps neither and says so.
- **Only the instrument's traffic is kept**, decided record by record in two
  passes before anything is written: on USB by the device's own description,
  its endpoints, and the exclusion of disks (commands and data), typed keys
  and hubs; on the network by IP address, never by a MAC alone, with name
  look-ups (DNS) never kept, other hosts' name announcements dropped and the
  instrument's own masked. A new network address after a restart is kept only
  after the owner says yes.
- **Private details replaced consistently and at the same length**: every
  identifier is collected from all blocks and from the system's device list
  first, then every block is written; names, serial numbers and `--hide`
  texts in any case, UTF-8, UTF-16 and URL-encoded forms; addresses in headers
  and inside the data. Encrypted connections are recognised only from a real
  handshake. The manifest says what was replaced, where it was learned, and
  what the tool cannot know.
- **Full recordings stay private and short-lived:** in a folder only the user
  can open, deleted right after each block (kept only on the owner's yes, for
  a block that kept nothing), leftovers tidied at the next start. pktmon is
  stopped when the tool ends, has a fixed size, and an earlier run's leftover
  is recognised and offered to be stopped.
- **Guided sessions for six kinds of instrument** (handheld, table, sheet-fed,
  network, serial, something else), made from the same files as the
  [SCENARIOS.md](SCENARIOS.md) pages, each with a 20-minute short set holding
  at least one untidy ending. The table list follows the reviewed i1iO 3
  recording plan (23 blocks: every start state, every ending, the way home
  from every part of the bed, every patch length, a timed long idle).
- **A watchdog** says at once when the recorder stops, when a block reaches
  its size or time limit, and when a timed block's time is up. Errors end with
  the session saved and a zip of what exists.
- **`--check ZIP`** does not trust the filter: it searches for the real
  identifiers kept in the session folder, lists every device and host in the
  recordings, and lists all readable text (all of it in a file).
- `--analyze` with forms, framing guesses, pairs, gaps, serial decoding,
  `--diff` and `--json`; `--resume`, `--remake`, `--import`, `--session`,
  `--devices`.
- **Rights:** on Windows the whole tool runs as administrator (said plainly
  in the README); on macOS and Linux only tcpdump and ifconfig, through sudo,
  from the system's own folders, with `tcpdump -Z <user>`.
- **Gone from 1.x:** the question to ArgyllCMS's `spotread` about its ports,
  and v1.1's one-line `--analyze` verdict. `--devices` still says when
  ArgyllCMS already supports a device. The v1.1 downloads stay the "latest
  release" until 2.0 is published.

A second, privacy-only review found one more way for typed keys to reach a zip
and a few smaller gaps; all are closed, each with a test on the zip's bytes
(`tests/test_review2_attacks.py`):

- typed keys are left out always, also from a device the recording does not
  describe; traffic at the system's address without a USB description in the
  recording is kept only after the owner has seen what it looks like and said
  yes; `--import` never uses this computer's USB addresses; `--check` shows
  such traffic under "LOOK AT THIS FIRST";
- two copies of an adapter with the same serial number: only the one at the
  system's own address is kept, otherwise neither;
- a normal dual-stack (IPv4 and IPv6) instrument is no longer taken for a
  router; its IPv6 traffic is left out and said; an instrument behind the
  router is refused on every system alike; with no known router (a VPN) the
  network is not recorded;
- a new address is offered only with evidence that the program talks to it;
  SSDP and WS-Discovery names masked; a TLS stream stays masked after a lost
  segment; MACs as 12 hex digits and IPv6 text replaced;
- files 0600 from the start, the Windows folder ACL checked, free space checked
  before a block, a session running in another window left alone, the Windows
  start file takes Python only from its install places.

A short re-check found two last things, both fixed with tests: the general
IPv6 pattern could change bytes in binary instrument data (it now runs only on
readable network text; 3 MB of random binary data pass byte-identical), and a
device kept without a USB description could still pass keyboard reports with a
report id or multi-key bitmaps (they are now left out too, and counted; on
Linux the first block asks for one replug while recording, so the description is
there and the question rarely comes up). A computer with no router at all may
record; the Windows start file uses only a Python installed for all users.

Ported from the X-Rite sibling
[chromiq-i1io-probe](https://github.com/itsab1989/chromiq-i1io-probe) 1.6.6
(same author, MIT): the capture readers, the USB transfer builders, the
address ownership rules of its 1.6.2 privacy fix (extended here: a disk's
data phase and typed keys are left out too; its 1.6.6 "follow the instrument
under a hub's address" is not ported), the recorder handling per system, the
console lessons and the salted short code.

## v1.1.0

- **New `--analyze` step: check a capture before you send it.** A USB capture
  is a large binary file, and until now there was no way to tell whether it
  actually recorded your instrument or just an empty bus. `--analyze` reads a
  `.pcap` you already made (it sends **nothing** to any device) and prints a
  plain verdict, *"real device traffic captured, good to send"* or *"wrong
  bus, or no measurement was taken"*, plus which device was seen and a
  command timeline. With no path it finds the newest capture next to the tool.
- **The command timeline is deliberately device-agnostic.** It assumes no
  vendor command codes, which is the whole point for an unsupported device,
  and simply shows the raw USB control commands and how much bulk data the
  device streamed. That is exactly what an implementer needs to see what the
  device's own software said to it. (Validated on real hardware: a ColorMunki
  driven through ChromIQ, matched byte-for-byte to ArgyllCMS's own driver.)
- macOS captures are decoded in full; Linux (usbmon) and Windows (USBPcap)
  captures are reported as valid with counts, and are just as useful to send.

## v1.0.0

- First version. A read-only collector for **any** colour measuring
  instrument, not just one model, built so that devices ChromIQ and
  ArgyllCMS do not support yet can be investigated properly.
- **Says straight away whether ArgyllCMS already supports the device.** The
  device table is taken from ArgyllCMS 3.5.0's own source, so "already
  supported", "known but unsupported" (the i1iO and i1iSis) and "unknown
  model from a known maker" are distinguished rather than guessed at. If
  ArgyllCMS is installed, it is also asked directly which ports it detects.
- **Recognises inexpensive instruments behind a USB-to-serial bridge**
  (FTDI, CH340, CP210x, PL2303), which usually means a simple protocol.
- **Guided walkthrough tailored to the kind of instrument**: handheld spot,
  strip reader, automated table, or display colorimeter.
- **Answers the question that decides how hard support would be**, by having
  the same patch measured three times: stable numbers mean the device does
  its own colour maths (a driver is realistic), wobbling numbers mean raw
  sensor data (much harder).
- **USB capture on macOS needs nothing installed**: no Wireshark and no
  ChmodBPF. The tool writes a readable script that uses the `tcpdump` macOS
  already ships, and restores every setting afterwards.
- Serial numbers hashed and personal paths stripped by default, on every
  platform's output format.
- ChromIQ is free and always will be. If it saves you time or ink, a
  coffee on [Ko-fi](https://ko-fi.com/itsab1989) is a kind way to say
  thanks.

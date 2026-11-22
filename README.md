# ChromIQ instrument probe

> **Before anything else, three things:**
>
> 1. **Not yet run with a real instrument on any system.** It only listens: it
>    never sends anything to any device and uploads nothing.
> 2. **It needs administrator rights.** On Windows the whole tool runs as
>    administrator. On a Mac, USB works only with System Integrity Protection
>    switched off ([how to switch it back on](#macos-usb-honestly)). While a block
>    records, everything on that USB bus (or, for a network instrument on Windows,
>    all network traffic), including what you type on a USB keyboard, sits in
>    your private folder until the block ends.
> 3. **The zip goes into a PUBLIC GitHub issue.** Run `--check` and read its text
>    list first. Dates and times, your notes and anything the maker's program
>    sends in plain text stay in the zip.

A small, free, **read-only** recording tool for colour measuring instruments
of any kind: handheld spot and strip instruments, motorised tables, sheet-fed
chart readers, and instruments on a network cable, Wi-Fi or a serial port.

You use your instrument with the maker's own program, exactly as you always
do. The tool **listens** to what that program says to the instrument, keeps
**only your instrument's** part of it, hides private details, and makes one
file, `SEND-THIS-<date>.zip`, that you can look through and send to the
[ChromIQ](https://github.com/itsab1989/ChromIQ) project. From such
recordings ChromIQ learns how an instrument is driven, so that one day it can
drive it itself.

**What to record, for your kind of instrument: [SCENARIOS.md](SCENARIOS.md).**
One ordered list per kind of instrument, a 20-minute short set for each (with
at least one untidy ending), and the same lists are what the tool walks you
through. The maker's manual always wins over these lists.

> **Status of version 2.0.0: built and tested with made-up recordings only.
> It has not yet been run with a real instrument on any system.** If you try
> it, you are among the first, and a report of what happened (good or bad)
> helps as much as a recording.
>
> **Do you own an X-Rite instrument** (i1Pro family, ColorMunki, i1Studio,
> i1iO table, i1iSis)? Then please use the specialised sibling,
> [chromiq-i1io-probe](https://github.com/itsab1989/chromiq-i1io-probe), for
> now: it knows those instruments in detail and has made real recordings with
> testers. This tool is for everything else, and may take over the X-Rite
> instruments once it has proven itself on real hardware.

---

## Is this safe?

Here it is plainly, because it is the most important part. Two independent
reviews attacked this tool with hostile recordings; what they found is fixed,
and every attack is a test that checks the bytes of the zip.

- **It never sends anything to your instrument, to any other device, or on
  the network**, and it has no network code at all, so it cannot upload
  anything. It only starts a recorder that listens, and reads the file it
  writes. It never opens a connection to the instrument, so it cannot take
  it away from the maker's program. One honest detail: on Windows, USBPcap's
  recorder asks every connected USB device for its standard description when
  it starts (the same read-only question Windows asks when you plug a device
  in), so that the recording can tell the devices apart.
- **It keeps only your instrument's traffic.** Every record is judged before
  anything is written into the zip: a USB disk, other computers on the
  network, your router and your web pages are left out; so is a USB device
  that the recording itself describes as something else (a keyboard, a hub).
  Standard keyboard and mouse reports are left out. When the recording cannot
  tell your instrument from another device with the same USB numbers, the
  tool keeps neither and says so; two copies with the same serial number are
  told apart on Linux by the port your instrument is plugged into (only that
  one is kept), elsewhere neither is kept. When the recording holds no
  description of the device at your instrument's address (on Linux when it
  was plugged in before the recording; the tool therefore asks you to plug it
  in again once while the first block records), the tool shows you what that
  traffic looks like and keeps it only if you say yes. Then it also leaves
  out every small report shaped like a keyboard's (and says how many), but
  not every keyboard's reports can be recognised: say yes only if no USB
  keyboard or mouse is plugged in near it. The zip and `--check` then name
  that device.
- **Your router is not recorded.** If the address you choose is your router
  (the computer's way to the internet), or an instrument reached through it,
  the tool refuses it with a plain sentence. If the tool cannot identify your
  router and its network card (for example while a VPN is connected), it does
  not record the network at all. A computer with no router at all (its only
  network is a cable straight to the instrument) may record: there is no
  internet traffic to protect. Name look-ups (DNS) are never kept.
- **What it changes, all of it:**
  - its own private folder (below), readable only by you;
  - on a Mac with SIP off: it switches the Mac's USB recording interfaces
    (XHC...) on for the recording and off again afterwards;
  - on Windows, for a network instrument: during each block it runs Windows'
    own system-wide network recorder, pktmon, and stops it at the end of the
    block. It adds no pktmon filter. If the tool is closed in a way it cannot
    notice (killed, a power cut), pktmon may keep running: the next start of
    the tool recognises its own leftover and offers to stop it. **To stop it
    by hand: open Command Prompt as administrator and type `pktmon stop`.**
    Its file has a fixed size (4 GB) and is converted once at the end of a
    block, so a block needs up to about 8.5 GB of free space; the tool checks
    that before every block. It cannot grow beyond that, also when it is left
    running.
  - It never switches System Integrity Protection on or off on a Mac; it
    only reads whether it is on.
- **Administrator rights, honestly:**
  - **Windows:** the whole tool runs as administrator (you start it with
    "Run as administrator"), because USBPcap and pktmon let only an
    administrator listen, and starting each recorder separately would show a
    Windows question for every block. As administrator the tool sends nothing;
    it writes only its own folders, the session folder and the zip; and it
    starts only these programs, from Windows' own folder (System32) and from
    USBPcap's install folder, never from the current folder or PATH:
    `USBPcapCMD`, `pktmon`, `powershell` (to list USB devices), `arp`,
    `netstat`, `route`, `mode` and `icacls`. The start file takes Python only
    from the Python launcher's install places.
  - **macOS and Linux:** only `tcpdump` (and on a Mac `ifconfig`, for the USB
    recording interfaces) run with administrator rights, through `sudo`, and
    the tool lists them before your password is asked for. They are taken
    only from the system's own folders (`/usr/sbin`, `/usr/bin`, `/sbin`),
    owned by root. `tcpdump` gets `-Z <your user name>`, so it gives the rights
    up right after opening the interface and writes the file as you. The tool
    never sees or stores your password, and ends the `sudo` permission when
    it finishes.

### Where files are, while they exist

- **Full recordings** (everything the recorder saw during a block, for
  example what you typed on a USB keyboard) are written into a private
  folder of your user: `~/.chromiq-probe/raw/` on macOS and Linux (only you
  can open it), `%LOCALAPPDATA%\ChromIQ-probe\raw\` on Windows (inside your
  own profile; the tool limits it to your user with Windows' `icacls`, and
  refuses to record if that does not succeed). Right after each block the
  tool keeps your instrument's part and **deletes the full recording**. Only
  for a block that kept nothing it asks whether you want to keep it for a
  later check, with a warning. A run that ended abruptly is tidied up at the
  next start.
- **The session folder** (`probe-session-<date>`, next to the tool, made
  private to your user in the same way) holds your instrument's traffic, your notes and
  `session.json`, **with the real serial numbers and addresses** (they are
  replaced only in the zip). It is needed to add blocks (`--resume`) or make
  the zip again (`--remake`). Delete it when you no longer need it.
- **The zip** `SEND-THIS-<date>.zip` is what you send.

---

## Who can help

Anyone who owns a colour measuring instrument that ChromIQ cannot use yet,
and the maker's program for it. You do not need to program. You need about
20 minutes for the short set, or one to two hours for a full list (a table's
full list takes longer).

---

## What you need, per system

| Your instrument is connected by | Windows 10 / 11 (Intel or AMD) | Windows on ARM | macOS | Linux |
|---|---|---|---|---|
| **USB** (also a USB serial adapter) | USBPcap (comes with Wireshark), administrator | **not possible** (see below) | **only with SIP switched off** (see below) | `tcpdump` and `usbmon`, `sudo` |
| **Network cable or Wi-Fi** | nothing: Windows' own `pktmon`, administrator | Windows' own `pktmon` (expected to work, not tried) | nothing: the Mac's own `tcpdump`, your password; SIP stays on | `tcpdump`, `sudo` |
| **A serial port of the computer itself** | not possible: please use a USB serial adapter | | | |
| **Bluetooth** | not in this version | | | |

All recorders in this table are **not yet tried with this tool on real
hardware**; they are built from their documentation and from what the X-Rite
sibling learned with real testers.

### Windows: USB

1. Install the free [Wireshark](https://www.wireshark.org). On its page
   **"USB Capture"**, tick **"Install USBPcap"** (it is not ticked by
   default). USBPcap is free and open source, made by its own author, not by
   us; it installs a system driver.
2. Restart Windows (with **Restart**, not Shut down). Plug the instrument in
   **after** the restart: USBPcap joins a USB device only when Windows sets it
   up.
3. Right-click `Start-Windows.bat` (or the tool) and choose **Run as
   administrator**.

**Windows on ARM** (for example a Windows virtual machine on an Apple Silicon
Mac) cannot record USB: USBPcap has no driver for ARM, and Windows never runs
drivers made for other processors. The ways that work: a Windows PC with an
Intel or AMD processor; a Linux PC that runs Windows in a virtual machine
with the instrument passed through to it (record on the Linux side); or a
hardware USB sniffer (record with its own program and give the file to this
tool with `--import`).

### Windows: network

Nothing to install. Windows 10 version 2004 (2020) and newer include
`pktmon`. Start the tool as administrator. (On Windows on ARM pktmon is
expected to work; not tried yet.)

### macOS: network

Nothing to install, and System Integrity Protection stays on. The tool uses
the Mac's own `tcpdump`, which asks for your password through `sudo`.

### macOS: USB, honestly

macOS can record USB with its own `tcpdump` **only while System Integrity
Protection (SIP) is fully switched off**. There is no other software way on a
Mac that we know of. While SIP is off, macOS no longer protects its own system
files, so please keep it off only for the recording and switch it on again
straight after. Also honest: one report from 2021 saw recordings in which
every data byte was zero on an Apple Silicon Mac, and one from 2025 says the
recording interfaces did not appear on macOS 15.6 even with SIP off. The tool
checks every recording for zeros and tells you. The easiest way is still a
Windows PC with an Intel or AMD processor.

To switch SIP **off**, on an Apple Silicon Mac:

1. Choose Apple menu > Shut Down, and wait until the Mac is off.
2. Press and hold the power button until "Loading startup options" appears.
3. Click **Options**, then **Continue** (choose your user and type your
   password if asked).
4. Choose **Utilities > Terminal** in the menu bar.
5. Type `csrutil disable` and press Return (answer `y` if asked).
6. Choose Apple menu > Restart.

On an Intel Mac, steps 1 to 3 are instead: restart and hold **Command and R**
until the Apple logo appears. Steps 4 to 6 are the same.

To switch SIP **back on** afterwards: do steps 1 to 4 again, type
`csrutil enable`, press Return, answer `y` if asked, and restart. Then open
Terminal and type `csrutil status`: it must say "enabled". On an Apple Silicon
Mac, switching SIP off can also lower the startup security; to be sure it is
back to **Full Security**, start into the startup options again, choose
**Utilities > Startup Security Utility**, select the disk and choose **Full
Security**. (We have not yet checked this on a real Mac.)

### Linux

Install `tcpdump` with your package manager. For USB, load the `usbmon`
module yourself first (`sudo modprobe usbmon`; it only lets the system
listen, and is gone after a restart): the tool tells you when it is missing.
Debian and Ubuntu run tcpdump as their own "tcpdump" user and AppArmor may
limit it; the tool passes `-Z <your user name>`, which should let it write the
file as you (not yet tried on a real Ubuntu). The makers' programs rarely run
on Linux, so Linux is mostly useful as the host of a Windows virtual machine
that the instrument is passed through to.

## How to run it

It is plain Python 3.8 or newer with nothing else to install.

- **Windows:** install Python from [python.org](https://www.python.org/downloads/)
  **for all users**: in the installer choose **Customize installation** and
  tick **Install Python for all users** (it then goes into Program Files,
  which only an administrator can change; the start file uses only that
  Python, because the tool runs as administrator). Unpack the tool into a
  folder of its own, not straight into Downloads. Then right-click
  `Start-Windows.bat` and choose **Run as administrator**.
- **macOS:** double-click `Start-macOS.command` (if macOS refuses, right-click
  it and choose Open). If Python is not ready yet, it tells you how to get it
  (`xcode-select --install`).
- **Linux:** run `./Start-Linux.sh` in a terminal.
- **From a terminal anywhere:** `python3 instrument_probe.py`.

Ready-made downloads that need no Python will come with the first published
release.

### What happens

1. You choose what kind of instrument it is and how it is connected. The
   tool says at once whether this computer can record it, and what it needs.
2. The tool finds the instrument. The easy way for USB: unplug it, press
   Enter, plug it in, press Enter, and the tool shows only what is new; type
   its number (Enter alone chooses nothing). **A table is often two USB
   devices** (the table and the instrument in its arm): type both numbers,
   for example `1,2`. If another device with the same USB numbers is plugged
   in, the tool asks you to unplug it. For the network: start the maker's
   program and connect it, and the tool shows the new address (it only reads
   lists your computer already keeps; it sends nothing to find it). You can
   also type the address (IPv4, for example 192.168.1.50).
3. It says exactly what will be kept, and asks whether your instrument's
   serial number may stay in the zip (by default it is replaced).
4. You choose all blocks, or only the short set (about 20 minutes).
5. **Block by block:** the tool shows what to do in the maker's program, one
   action per line. Press Enter to start recording, do the steps, then type
   `e` and press Enter. While recording, any other line you type is saved
   with its time (words like `cancel`, `killed`, `power off` are marked as
   recognised). The tool says at once if the recorder stops, if a block
   reaches its limit (4 GB or 4 hours) and, for a timed block, when the time
   is up. After each block it says what it kept, for this block alone ("GOOD:
   kept 214 records ..."), per device when you chose several; asks for a
   short note (it goes into the zip) and, after a measurement, the name of the
   file the program saved. If the instrument appears at a new network address
   after a restart, and this computer then talks to it on the instrument's
   port, the tool shows you that evidence and asks whether it is yours (the
   answer "no" is the default); only then is that address kept. If the
   recording holds no USB description of the device at your instrument's
   address, the tool shows you what that traffic looks like and asks before
   keeping it. `s` skips a block, `r` records it again, `q` finishes.
6. At the end it makes `SEND-THIS-<date>.zip` next to the tool.

You can stop at any time (`q`, Ctrl-C, or closing the window): everything you
finished is kept. If something goes wrong, the tool still makes a zip of what
exists. To add blocks later, also on another day:
`python3 instrument_probe.py --resume probe-session-<date>`. Both sittings end
up in one zip. To make the zip again without recording (for example to hide
a text): `--remake probe-session-<date> --hide "the text"`.

---

## What is in the zip, and what is not

**In it:**

- `recordings/<block>-<label>.pcap`: one recording per block, holding only
  your instrument's traffic.
- `MANIFEST.txt` (and `manifest.json`): what is in the zip, which blocks were
  recorded, skipped, kept nothing or were not reached, what was left out
  (counts only), what was replaced and where the tool learned it from, and
  which connections were treated as encrypted.
- `session.json` and `notes.txt`: the blocks, their times, your notes, marks
  and answers.
- `report.txt`: your system, the recorder, and your instrument's name. Other
  devices on your computer are counted, never named.
- `analysis.txt`: the tool's own reading of the recordings.

**Replaced in what is kept** (the same value always gets the same
placeholder of the same length, so the recordings can still be read):

- network addresses: every MAC and IP address in the packet headers; inside
  the data, those same addresses as text (MACs also as 12 hex digits) and as
  bytes, any other `aa:bb:cc:dd:ee:ff` text, any dotted IPv4 text from
  `10.0.0.0` up (a version number such as `1.2.3.4` stays) and any valid IPv6
  text;
- your computer's names (also the Mac's "Computer Name"), your user name and
  home folder, the instrument's serial number (from the system's device list
  and from the USB description, unless you agreed to keep it), and any text
  you name with `--hide`: in any upper or lower case, as UTF-8, UTF-16 (both
  byte orders) and URL-encoded, and a user name also in its Windows short form
  (`MIRAND~1`);
- the names in DHCP requests and, in the instrument's own name announcements,
  every name label (mDNS, LLMNR), the header values that can carry a name
  (SSDP: SERVER, USN, LOCATION, X-FRIENDLY ...) and FriendlyName-type entries
  (WS-Discovery); NetBIOS names become zeros;
- for an encrypted connection (recognised only from a real TLS, DTLS or SSH
  start): the contents become zeros; record headers, sizes and times stay.

**Still in it, said honestly:**

- **dates and times**: every recorded packet carries its real date and time,
  and so do the blocks in `session.json` and `notes.txt` (when and how long
  you worked);
- **what you typed**: your marks, notes, answers and the names of saved files,
  as you typed them (your computer's names are replaced in them, nothing else);
- **what the instrument and the program say in plain text**: its calibration
  data, model and firmware, the colour values measured, and anything the
  program sends unencrypted, which may include a login, an account e-mail,
  a licence key or Wi-Fi settings. `--check` lists all readable text so you
  can see it;
- **what the tool cannot know**: an identifier it has not been told and that
  does not appear in a standard field, for example a serial number the
  instrument sends in its own binary format; a name split across two network
  messages; a value shorter than 4 characters inside the data (a user name of
  2 or 3 letters), which `--check` cannot search for either.

**Never in it:** the full recordings (deleted after each block, see above),
and nothing of other devices, other computers or the internet.

**What the tool cannot tell apart, honestly:** on USB, a device that sits at
your instrument's address and has the same endpoints, when the recording
holds no description of it, looks like the instrument. So while you record,
please unplug every other USB device you can do without (disks, memory
sticks, phones, printers, card readers, other serial adapters and radio
sticks), and a USB keyboard too if you can: on Linux the tool cannot always
tell it from the instrument (standard keyboard reports are left out, and you
are asked before anything without a description is kept). Plug a device you pull
out during a block back into **the same port**. On the network, only IPv4 is
kept: an instrument's IPv6 traffic is left out and counted.

---

## Check before you send

```
python3 instrument_probe.py --check SEND-THIS-<date>.zip
```

It does not trust the filter that made the zip. It:

- searches every file for your computer's names and, when the session folder
  is next to the zip, for the real serial numbers, addresses and `--hide`
  texts kept there (in any case, UTF-8, UTF-16, addresses also as bytes);
- lists every device or host that appears in the recordings, and calls it a
  problem when one is not your instrument or this computer;
- filters every recording again;
- shows the readable text inside the recordings: the first 200 pieces on
  screen, and **every one** in a file next to the zip
  (`check-<date>-strings.txt`; it holds only text from the zip itself);
- puts anything kept without a USB description at the top, under "LOOK AT
  THIS FIRST", and calls records that look like typed keys a problem.

If something there is private, make the zip again with
`--remake probe-session-<date> --hide "that text"`. Exit code 0 means nothing
was found, 3 means something was. It cannot find what the tool cannot know
(the list just above), so please read the text list yourself.

## Where to send it

Open a [new issue in the ChromIQ repository](https://github.com/itsab1989/ChromIQ/issues/new),
title it "Recording: <make and model>", and attach the zip and the
measurement files the program saved. An issue is public: attach only what you
are happy to share. If you would rather send it privately, say so in the
issue and we will find a way.

**Nothing is promised.** A recording helps us understand an instrument; whether
ChromIQ can ever drive it is a separate question, and the answer may be no.

---

## Your own recording (`--import`)

If you record with another program (Wireshark, a hardware USB sniffer, the
host of a virtual machine), start the tool with `--import`. It walks you
through the same blocks; at each block you record with your program, save its
file, and type the file's path into the tool. The tool then filters and
cleans it exactly like its own recordings.

## Options

```
python3 instrument_probe.py --help
```

| option | what it does |
|---|---|
| `--type handheld\|table\|sheetfed\|network\|serial\|other` | skip the first question |
| `--short` | only the short set (about 20 minutes) |
| `--session FILE` | a session file for one particular instrument ([SESSIONS.md](SESSIONS.md)) |
| `--resume FOLDER` | continue an earlier session |
| `--remake FOLDER` | make the zip of a session again, without recording (with `--hide`) |
| `--import` | you record with your own recorder |
| `--keep-instrument-serial` | keep the instrument's real serial number |
| `--hide TEXT` | also replace this text (repeatable) |
| `--check ZIP` | show and check what a zip holds |
| `--analyze PATH ...` | timeline and command forms of recordings, zips or folders |
| `--analyze ZIP --diff A B` | what differs between two labelled recordings |
| `--analyze ZIP --json OUT` | the same as data |
| `--sessions` | list the built-in sessions |
| `--validate-session FILE` | check a session file you wrote |
| `--devices` | list the USB devices this computer sees (read only) |

Exit codes: 0 done, 1 wrong use, 2 nothing could be recorded or kept here
(the reason is shown), 3 `--check` found something, 4 stopped before anything
was recorded.

---

## For developers

- `chromiq_probe/` is a small package of plain modules, standard library
  only: `capture` (pcap / pcapng), `usb` and `net` (the instrument-only
  filters), `privacy`, `serial_decode`, `discovery`, `recorders`, `sessions`,
  `runner`, `package` (the zip), `check`, `analyze`.
- Tests run with `CHROMIQ_PROBE_HOME` pointing at a throw-away folder, so
  they never touch your real private folder.
- The session files in `chromiq_probe/sessions/` are the single source of the
  guided sessions **and** of the scenario pages: after editing one, run
  `python3 tools/make_scenarios.py`; a test fails when they differ.
- Tests: `python3 -m pytest -q` (about 130 tests, a few seconds, made-up
  recordings only; nothing captures real traffic). `tests/test_review_attacks.py`
  holds the independent review's attacks, each asserting on the zip's bytes.
- `--analyze` assumes nothing about any maker: it groups messages into forms,
  shows which bytes vary, guesses framing (text lines, a length byte, a sum,
  XOR or CRC-16 at the end), pairs requests with answers, finds quiet gaps,
  decodes USB serial adapters (FTDI, CDC-ACM; others raw), and `--diff`
  compares two labels.

Parts of this tool are ported from the X-Rite sibling (same author, same
licence): the capture readers, the USB transfer builders, the address
ownership rules, the recorder handling per system and the console lessons.

## Version 1.x

Versions 1.0 and 1.1 of this repository wrote a report of the connected
devices. That part lives on as `--devices` (with the same ArgyllCMS table:
it tells you when ArgyllCMS already supports a device, so no recording is
needed).

## Licence

MIT, see [LICENSE](LICENSE).

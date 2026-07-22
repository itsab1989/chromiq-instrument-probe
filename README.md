# ChromIQ — colour instrument probe

<p align="center">
  <a href="https://ko-fi.com/itsab1989"><img src="https://ko-fi.com/img/githubbutton_sm.svg" alt="Support ChromIQ on Ko-fi" height="36"></a>
  <br>
  <sub>ChromIQ is free and always will be. If it's useful to you, a coffee is a kind way to say thanks — completely optional, and the app stays fully featured either way.</sub>
</p>

A small, **read-only** tool that works out what a colour measuring instrument
looks like to your computer — and, crucially, whether
[ArgyllCMS](https://argyllcms.com) already supports it.

It exists so that instruments [ChromIQ](https://github.com/itsab1989/ChromIQ)
and ArgyllCMS don't support yet — an inexpensive spectrophotometer, an
automated table, an unusual chart reader — can be investigated properly
instead of guessed at.

It takes about **two minutes**, and you do **not** need to be technical.

---

## Is this safe?

**Yes — this is the important part, so here it is plainly:**

- It **never sends anything to your instrument.** Not one byte.
- It **cannot operate it** — it does not open, calibrate, or measure.
- It changes nothing and needs no special setup.

All it does is read what your operating system already knows about connected
hardware — the same sort of thing you'd see in Device Manager or System
Information — and, if ArgyllCMS happens to be installed, ask *it* which
instruments it recognises.

Serial numbers are scrambled and personal paths removed by default. You can
open the report it produces and read every line before sending it.

---

## How to run it — the easy way (no Python needed)

Download the one file for your system from the
[**latest release**](../../releases/latest), then run it. Plug your instrument
in and switch it on first.

| Your system | Download |
|-------------|----------|
| **Windows** | `chromiq-instrument-probe-windows.exe` |
| **macOS** (Intel **and** Apple Silicon) | `chromiq-instrument-probe-macos` |
| **Linux** | `chromiq-instrument-probe-linux` |

The macOS download is a single universal build — it runs on both Intel and
Apple-Silicon Macs, so there's only one file to pick.

### Windows

Double-click the `.exe`. Windows will warn you once — click **More info** →
**Run anyway**.

### macOS

Downloaded files aren't marked as runnable, so **double-clicking may appear to
do nothing at all**. Two ways round it:

**In Finder:** **right-click** the file → **Open** → **Open** again in the
dialog. If macOS still refuses, go to **System Settings → Privacy & Security**
and click **Open Anyway**.

**Or in Terminal** (the reliable route):

```bash
cd ~/Downloads
chmod +x chromiq-instrument-probe-macos
./chromiq-instrument-probe-macos
```

`chmod +x` simply marks the file as runnable — downloads never are by default.

### Linux

```bash
cd ~/Downloads
chmod +x chromiq-instrument-probe-linux
./chromiq-instrument-probe-linux
```

> These downloads are **not code-signed** (signing needs a paid certificate),
> so your computer will warn you the first time. That's normal — the full
> source is in this repo if you'd like to read it first.

---

## What it tells you

The first thing it does is give you a straight answer about each instrument it
finds:

- **Already supported by ArgyllCMS** — ChromIQ can very likely use it today,
  and no new work is needed. (Worth knowing before anyone starts.)
- **Known but unsupported** — Argyll knows the device exists but has no driver
  for it. The X-Rite i1iO and i1iSis are both in this category.
- **Unknown model from a known instrument maker** — the interesting case.
- **A USB-to-serial bridge** (FTDI, CH340, CP210x…) — very common in
  inexpensive instruments, and usually good news, because it tends to mean a
  simple serial protocol.

It also asks ArgyllCMS directly which instrument ports it can see, which is
the most authoritative answer available.

---

## The optional advanced step

At the end it offers a guided walkthrough that records what your instrument's
own software says to it. That recording is the one thing that could make
support possible for an unsupported device — but it takes about ten more
minutes, and you are very welcome to skip it.

**On macOS it needs nothing installed.** No Wireshark, no ChmodBPF, no
drivers: macOS already includes `tcpdump`, so the tool writes a short,
readable `start-usb-capture.command` you can double-click. It asks for your
admin password (macOS requires that to listen to USB traffic), records to a
file, and puts every setting back as it found it. It still only listens.

The walkthrough includes one deliberately repetitive part: **measuring the
same patch three times.** That answers the single most important question
about an unknown instrument — whether it does its own colour maths, or sends
raw sensor data. ArgyllCMS's driver for the first kind is around 1,400 lines;
for the second kind, the i1Pro driver is over 13,000 and took years. Knowing
which one you have decides whether support is realistic.

---

## What's in the report

- Your operating system name and version.
- Every connected USB device, with the interesting ones called out.
- Full USB descriptors — interface class and endpoints, which decide how a
  driver would have to talk to the device.
- Serial ports present.
- Which ArgyllCMS version is installed and what it detects.
- Any vendor software found.
- Your three answers, and — if you did the optional step — a timeline.

---

## Running from source

```bash
python3 instrument_probe.py
```

Useful options:

- `--no-redact` — keep serial numbers and paths as-is (not needed).
- `--skip-annotate` — never offer the advanced step.
- `--annotate` — go straight into the advanced step.
- `--capture-setup` — (macOS) just write the capture script and exit.
- `--analyze [FILE …]` — read a USB capture and print a plain verdict (did it
  record real instrument traffic?) plus a device-agnostic command timeline. With
  no path it finds the newest capture next to the tool. Reads only; sends
  nothing to any device.

---

## Privacy

By default, serial numbers are replaced with a short scrambled code and your
username and home-folder path are removed. It collects no documents, images,
profiles or measurements — only descriptions of connected hardware. If you
spot anything you'd rather not share, delete it before sending.

---

## Licence

MIT — see [LICENSE](LICENSE).

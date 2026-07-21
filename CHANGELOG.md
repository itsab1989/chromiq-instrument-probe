# Changelog

## v1.0.0

- First version. A read-only collector for **any** colour measuring
  instrument, not just one model — built so that devices ChromIQ and
  ArgyllCMS do not support yet can be investigated properly.
- **Says straight away whether ArgyllCMS already supports the device.** The
  device table is taken from ArgyllCMS 3.5.0's own source, so "already
  supported", "known but unsupported" (the i1iO and i1iSis) and "unknown
  model from a known maker" are distinguished rather than guessed at. If
  ArgyllCMS is installed, it is also asked directly which ports it detects.
- **Recognises inexpensive instruments behind a USB-to-serial bridge**
  (FTDI, CH340, CP210x, PL2303), which usually means a simple protocol.
- **Guided walkthrough tailored to the kind of instrument** — handheld spot,
  strip reader, automated table, or display colorimeter.
- **Answers the question that decides how hard support would be**, by having
  the same patch measured three times: stable numbers mean the device does
  its own colour maths (a driver is realistic), wobbling numbers mean raw
  sensor data (much harder).
- **USB capture on macOS needs nothing installed** — no Wireshark and no
  ChmodBPF. The tool writes a readable script that uses the `tcpdump` macOS
  already ships, and restores every setting afterwards.
- Serial numbers hashed and personal paths stripped by default, on every
  platform's output format.
- ChromIQ is free and always will be — if it saves you time or ink, a
  coffee on [Ko-fi](https://ko-fi.com/itsab1989) is a kind way to say
  thanks.

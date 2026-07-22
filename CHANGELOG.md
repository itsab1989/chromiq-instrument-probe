# Changelog

## v1.1.0

- **New `--analyze` step: check a capture before you send it.** A USB capture
  is a large binary file, and until now there was no way to tell whether it
  actually recorded your instrument or just an empty bus. `--analyze` reads a
  `.pcap` you already made (it sends **nothing** to any device) and prints a
  plain verdict — *"real device traffic captured, good to send"* or *"wrong
  bus, or no measurement was taken"* — plus which device was seen and a
  command timeline. With no path it finds the newest capture next to the tool.
- **The command timeline is deliberately device-agnostic.** It assumes no
  vendor command codes — which is the whole point for an unsupported device —
  and simply shows the raw USB control commands and how much bulk data the
  device streamed. That is exactly what an implementer needs to see what the
  device's own software said to it. (Validated on real hardware: a ColorMunki
  driven through ChromIQ, matched byte-for-byte to ArgyllCMS's own driver.)
- macOS captures are decoded in full; Linux (usbmon) and Windows (USBPcap)
  captures are reported as valid with counts, and are just as useful to send.

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

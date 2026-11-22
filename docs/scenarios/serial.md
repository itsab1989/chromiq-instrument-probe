# Scenarios: Serial instrument (RS-232)

<!-- Generated from chromiq_probe/sessions/serial.json by tools/make_scenarios.py. Edit the JSON file, not this page. -->

An instrument with a serial port (often older strip readers and bench instruments), connected through a USB serial adapter.

**14 blocks, about 38 minutes in all. 9 are essential; the short set of 8 blocks takes about 20 minutes.**

## What this list is built on: our best reasoning

No recording of a serial instrument has reached us yet. This list is our best reasoning from the handheld and table work. The tool records the USB side of the serial adapter and turns it back into the serial bytes (decoded for FTDI and standard CDC adapters, shown raw for others). A serial port built into the computer, with no USB adapter, cannot be listened to: please use a USB serial adapter for the recording. If your program offers something this list misses, please tell us.

If your program offers something this list misses, please tell us in the GitHub issue where you send your recording: that is how these lists get better.

## Before you start

- The instrument, its serial cable and a USB serial adapter, and the program you normally use, closed for now.
- A sample or chart the instrument can measure.
- Unplug other USB devices you can do without (disks, memory sticks, phones, printers). A keyboard and a mouse may stay.

## If you only have 20 minutes

Do only these blocks, in this order (about 20 minutes). The tool offers this as "the short set". It holds at least one untidy ending, because those are what a first careful drive must recover from.

1. **R01** Start the program and connect (about 3 min)
2. **R02** Calibrate (about 2 min)
3. **R03** One measurement, three times (about 2 min)
4. **R04** A strip or a small job to the end, saved (about 4 min)
5. **R05** A reading that fails on purpose (about 2 min)
6. **R06** Cancel during a reading (about 2 min)
7. **R13** The program ends by force while a reading, then starts again (about 2 min)
8. **Q1** A few questions (about 3 min)

**The maker's manual wins.** If a block contradicts what the maker's manual says about handling your instrument, follow the manual and skip the block.

## All blocks, in the order of one sitting

You can stop after any block: everything you finished goes into the zip, and the zip says which blocks were recorded and which were skipped.

### R01. Start the program and connect

*Priority: essential. About 3 min. Label: `connect`. In the short set. The recording keeps going while the instrument is disconnected.*

1. Make sure the program is closed and the USB serial adapter is unplugged.
2. Start this block (the recording starts now).
3. Plug the adapter in (with the instrument already on its other end, switched on).
4. Start the program and connect to the instrument (choose its port if the program asks).
5. Wait until the program shows the instrument as ready.

**What to note:** Which port and settings did the program show (for example COM3, 9600 baud)? Did it search for the instrument by itself?

**Why we need it:** The connection shows the line settings and the first commands; a program that searches may try several speeds, which tells us which one the instrument uses.

### R02. Calibrate

*Priority: essential. About 2 min. Label: `calibrate`. In the short set.*

If the instrument needs no calibration, record 30 seconds of the program waiting and say so.

1. Start this block.
2. Start the calibration in the program as you normally do, and wait until it is done.

**What to note:** What did you have to do? How long did it take?

**Why we need it:** Calibration is usually the simplest command and answer to understand.

### R03. One measurement, three times

*Priority: essential. About 2 min. Label: `spot`. In the short set.*

1. Start this block.
2. Measure the same patch or sample three times.

**What to note:** Did the program show numbers? Were they the same each time?

**Why we need it:** Three answers to the same question show the message format and whether the instrument does its own colour maths.

### R04. A strip or a small job to the end, saved

*Priority: essential. About 4 min. Label: `job-to-end`. In the short set.*

1. Start this block.
2. Read a strip or a few samples to the end, the normal way.
3. Save the result in the program under a name you will recognise, and send that file together with the zip.

**What to note:** The name of the saved file.

**Why we need it:** A whole job paired with the program's own saved result lets us check every number.

### R05. A reading that fails on purpose

*Priority: essential. About 2 min. Label: `refused`. In the short set.*

1. Start this block.
2. Make one reading fail in a harmless way (for example lift the instrument, or measure nothing).
3. Read the program's message and answer it the normal way.

**What to note:** What exactly did the program say?

**Why we need it:** How the instrument reports a bad reading is what ChromIQ must understand.

### R06. Cancel during a reading

*Priority: essential. About 2 min. Label: `cancel`. In the short set.*

1. Start this block.
2. Start a reading and press Cancel or Stop in the program while it runs.

**What to note:** What did the instrument do?

**Why we need it:** A cancel is an ending ChromIQ must handle cleanly.

### R07. Every other mode

*Priority: important. About 4 min. Label: `modes`.*

Only the modes your program offers.

1. Start this block.
2. For each other mode, filter or measurement condition the program offers, take one reading.
3. Before each one, type the mode's name here and press Enter.

**What to note:** The modes you tried, in order.

**Why we need it:** Each mode may be its own command.

### R08. Measuring from the instrument's own keys

*Priority: nice to have. About 2 min. Label: `instrument-keys`.*

Only if the instrument can measure on its own and send the result.

1. Start this block.
2. Take one measurement with the instrument's own key or display, and let it send the result to the program.

**What to note:** What did you press on the instrument?

**Why we need it:** Some instruments send results without being asked; ChromIQ would have to listen for them.

### R09. Five quiet minutes

*Priority: important. About 5 min. Label: `idle`.*

1. Start this block.
2. With the program connected and idle, do nothing for five minutes.

**What to note:** Did anything happen on its own?

**Why we need it:** Some programs poll a serial instrument all the time; ChromIQ must know whether it needs that.

### R10. Pull the serial cable and plug it back

*Priority: important. About 3 min. Label: `cable-pull`. An untidy ending.*

1. Start this block.
2. With the program idle, pull the serial cable at the instrument (leave the USB adapter plugged in).
3. Wait 10 seconds, plug it back, and see whether the program notices.

**What to note:** Did the program notice the cable was gone?

**Why we need it:** A serial line gives no sign of a pulled cable by itself; how the program notices tells ChromIQ how to.

### R11. Switch the instrument off and on

*Priority: important. About 3 min. Label: `power-cycle`. An untidy ending.*

1. Start this block.
2. With the program open and idle, switch the instrument off, wait 10 seconds, and switch it on again.
3. Connect again in the program if you must.

**What to note:** Did the program reconnect by itself?

**Why we need it:** What an instrument says when it wakes up is often the clearest message it ever sends.

### R12. Close the program

*Priority: essential. About 1 min. Label: `close`.*

1. Start this block.
2. Close the program the normal way, and wait 10 seconds.

**Why we need it:** What the program sends when it closes is what ChromIQ should do when it lets go of the instrument.

### R13. The program ends by force while a reading, then starts again

*Priority: essential. About 2 min. Label: `unexpected-end`. In the short set. An untidy ending.*

1. Start this block.
2. Start a reading in the program.
3. While it is busy, end the program by force (Windows: Task Manager (Ctrl+Shift+Esc), select the program, End task. Mac: Apple menu > Force Quit, select the program, Force Quit.) Type killed.
4. Wait 20 seconds. Start the program again and note what it does with the instrument (a new calibration, a message).

**What to note:** What did the instrument do when the program disappeared, and when it came back?

**Why we need it:** After an unexpected end the instrument is left as the program left it; how the maker's program recovers is what ChromIQ needs after its own unexpected end.

### Q1. A few questions

*Priority: essential. About 3 min. Label: `questions`. In the short set.*

1. No recording now. Answer the questions below; a short line each is fine.

- Which instrument is it exactly?
- Which program and which version did you use, on which system?
- Which USB serial adapter did you use, if you know (the name on it or its box)?
- Does the program offer anything that these blocks did not cover?

**Why we need it:** The recording cannot say which program made it.

## Checklist (one page)

- [ ] **R01** Start the program and connect (essential, 3 min)
- [ ] **R02** Calibrate (essential, 2 min)
- [ ] **R03** One measurement, three times (essential, 2 min)
- [ ] **R04** A strip or a small job to the end, saved (essential, 4 min)
- [ ] **R05** A reading that fails on purpose (essential, 2 min)
- [ ] **R06** Cancel during a reading (essential, 2 min)
- [ ] **R07** Every other mode (important, 4 min)
- [ ] **R08** Measuring from the instrument's own keys (nice to have, 2 min)
- [ ] **R09** Five quiet minutes (important, 5 min)
- [ ] **R10** Pull the serial cable and plug it back (important, 3 min)
- [ ] **R11** Switch the instrument off and on (important, 3 min)
- [ ] **R12** Close the program (essential, 1 min)
- [ ] **R13** The program ends by force while a reading, then starts again (essential, 2 min)
- [ ] **Q1** A few questions (essential, 3 min)
- [ ] Saved measurement files from the program, named in the notes
- [ ] Ran `--check` on the zip and read what it shows

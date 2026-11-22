# Scenarios: Something else

<!-- Generated from chromiq_probe/sessions/other.json by tools/make_scenarios.py. Edit the JSON file, not this page. -->

Any other measuring instrument: a short general frame, and free recordings you label yourself.

**12 blocks, about 40 minutes in all. 7 are essential; the short set of 6 blocks takes about 18 minutes.**

## What this list is built on: our best reasoning

A general frame drawn from all the other lists. You know your instrument best: add free recordings for anything it does that these blocks miss, and tell us what they were.

If your program offers something this list misses, please tell us in the GitHub issue where you send your recording: that is how these lists get better.

## Before you start

- The instrument, its cables, and the program you normally use, closed for now.
- Something the instrument can measure.
- If it is connected by USB: unplug other USB devices you can do without (disks, memory sticks, phones, printers). A keyboard and a mouse may stay.

## If you only have 20 minutes

Do only these blocks, in this order (about 18 minutes). The tool offers this as "the short set". It holds at least one untidy ending, because those are what a first careful drive must recover from.

1. **O01** Start the program and connect (about 3 min)
2. **O02** Calibrate (about 2 min)
3. **O03** A typical measurement, saved (about 5 min)
4. **O04** Cancel during a measurement (about 2 min)
5. **O11** The program ends by force while a measurement, then starts again (about 3 min)
6. **Q1** A few questions (about 3 min)

**The maker's manual wins.** If a block contradicts what the maker's manual says about handling your instrument, follow the manual and skip the block.

## All blocks, in the order of one sitting

You can stop after any block: everything you finished goes into the zip, and the zip says which blocks were recorded and which were skipped.

### O01. Start the program and connect

*Priority: essential. About 3 min. Label: `start`. In the short set. The recording keeps going while the instrument is disconnected.*

1. Make sure the program is closed (and, for a USB instrument, that it is unplugged).
2. Start this block (the recording starts now).
3. Plug the instrument in or switch it on, start the program, and connect.
4. Wait until the program shows the instrument as ready.

**What to note:** Did the program find the instrument by itself?

**Why we need it:** How the program finds and greets the instrument is the first thing ChromIQ must repeat.

### O02. Calibrate

*Priority: essential. About 2 min. Label: `calibrate`. In the short set.*

If the instrument needs no calibration, record 30 seconds of the program waiting and say so.

1. Start this block.
2. Calibrate as the program asks, and wait until it is done.

**What to note:** What did you have to do?

**Why we need it:** Calibration is usually the simplest command and answer to understand.

### O03. A typical measurement, saved

*Priority: essential. About 5 min. Label: `typical-job`. In the short set.*

1. Start this block.
2. Measure the way you always do, to the end.
3. Save the result in the program under a name you will recognise, and send that file together with the zip.

**What to note:** What did you measure, and the name of the saved file.

**Why we need it:** A typical job paired with the program's own result is the most useful single recording.

### O04. Cancel during a measurement

*Priority: essential. About 2 min. Label: `cancel`. In the short set.*

1. Start this block.
2. Start a measurement and press Cancel or Stop in the program while it runs.

**What to note:** What did the instrument do?

**Why we need it:** A cancel is an ending ChromIQ must handle cleanly.

### O05. A measurement that fails on purpose

*Priority: important. About 3 min. Label: `refused`.*

1. Start this block.
2. Make one measurement fail in a harmless way, read the program's message and answer it.

**What to note:** What did you do, and what did the program say?

**Why we need it:** How the instrument reports a problem is what ChromIQ must understand.

### O06. Every other mode

*Priority: important. About 5 min. Label: `modes`.*

Only the modes your program offers.

1. Start this block.
2. For each other mode the program offers, take one measurement.
3. Before each one, type the mode's name here and press Enter.

**What to note:** The modes you tried, in order.

**Why we need it:** Each mode may be its own command.

### O07. Five quiet minutes

*Priority: important. About 5 min. Label: `idle`.*

1. Start this block.
2. With the program connected and idle, do nothing for five minutes.

**What to note:** Did anything happen on its own?

**Why we need it:** Programs often keep talking to an idle instrument.

### O08. Disconnect and reconnect

*Priority: important. About 3 min. Label: `disconnect`. An untidy ending. The recording keeps going while the instrument is disconnected.*

1. Start this block (the recording keeps going).
2. With the program idle, pull the instrument's cable (or switch it off).
3. Wait 10 seconds, connect it again, and wait until the program shows it again.

**What to note:** What did the program say?

**Why we need it:** A lost connection is an ending ChromIQ must survive.

### O09. Anything else, labelled by you

*Priority: nice to have. About 5 min. Label: `free`.*

1. Type a short label for what you will record (for example "lamp test").
2. Start this block and do that one thing in the program.
3. You can do this block as often as you like, with a new label each time.

**What to note:** What did you do?

**Why we need it:** You know what your instrument can do; anything we did not think of is welcome.

### O10. Close the program

*Priority: essential. About 1 min. Label: `close`.*

1. Start this block.
2. Close the program the normal way, and wait 10 seconds.

**Why we need it:** What the program sends when it closes is what ChromIQ should do when it lets go of the instrument.

### O11. The program ends by force while a measurement, then starts again

*Priority: essential. About 3 min. Label: `unexpected-end`. In the short set. An untidy ending.*

1. Start this block.
2. Start a measurement in the program.
3. While it is busy, end the program by force (Windows: Task Manager (Ctrl+Shift+Esc), select the program, End task. Mac: Apple menu > Force Quit, select the program, Force Quit.) Type killed.
4. Wait 20 seconds. Start the program again and note what it does with the instrument (a new calibration, a message).

**What to note:** What did the instrument do when the program disappeared, and when it came back?

**Why we need it:** After an unexpected end the instrument is left as the program left it; how the maker's program recovers is what ChromIQ needs after its own unexpected end.

### Q1. A few questions

*Priority: essential. About 3 min. Label: `questions`. In the short set.*

1. No recording now. Answer the questions below; a short line each is fine.

- Which instrument is it, and what kind (spot, strip, table, sheet reader, something else)?
- Which program and which version did you use, on which system?
- How is it connected?
- What else can it do that these blocks did not cover?

**Why we need it:** The recording cannot say which program made it.

## Checklist (one page)

- [ ] **O01** Start the program and connect (essential, 3 min)
- [ ] **O02** Calibrate (essential, 2 min)
- [ ] **O03** A typical measurement, saved (essential, 5 min)
- [ ] **O04** Cancel during a measurement (essential, 2 min)
- [ ] **O05** A measurement that fails on purpose (important, 3 min)
- [ ] **O06** Every other mode (important, 5 min)
- [ ] **O07** Five quiet minutes (important, 5 min)
- [ ] **O08** Disconnect and reconnect (important, 3 min)
- [ ] **O09** Anything else, labelled by you (nice to have, 5 min)
- [ ] **O10** Close the program (essential, 1 min)
- [ ] **O11** The program ends by force while a measurement, then starts again (essential, 3 min)
- [ ] **Q1** A few questions (essential, 3 min)
- [ ] Saved measurement files from the program, named in the notes
- [ ] Ran `--check` on the zip and read what it shows

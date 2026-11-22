# Scenarios: Network-connected instrument

<!-- Generated from chromiq_probe/sessions/network.json by tools/make_scenarios.py. Edit the JSON file, not this page. -->

A bench, table or inline instrument that is connected by a network cable or Wi-Fi rather than USB.

**14 blocks, about 43 minutes in all. 8 are essential; the short set of 7 blocks takes about 20 minutes.**

## What this list is built on: our best reasoning

No recording of a network instrument has reached us yet. This list is our best reasoning: the same start states, readings and endings as for USB instruments, plus what is special about a network (finding the instrument, a connection that drops, a new address after a restart). If the program's connection is encrypted, the tool can still keep sizes and timing, and says so. If your program offers something this list misses, please tell us.

If your program offers something this list misses, please tell us in the GitHub issue where you send your recording: that is how these lists get better.

## Before you start

- The instrument, connected to your network the way you always use it, and the program you normally use, closed for now.
- A sample or chart the instrument can measure.
- If you know the instrument's network address (the program or the instrument's display may show it), have it ready. If not, the tool helps you find it.
- The tool keeps only traffic to and from the instrument. Your other network traffic (web pages, mail) is left out before anything is written, but it is still a good idea to close programs you do not need.

## If you only have 20 minutes

Do only these blocks, in this order (about 20 minutes). The tool offers this as "the short set". It holds at least one untidy ending, because those are what a first careful drive must recover from.

1. **N01** Start the program and connect (about 3 min)
2. **N02** Calibrate (about 2 min)
3. **N03** One single measurement (about 2 min)
4. **N04** A small job to the end, saved (about 5 min)
5. **N05** Cancel during a measurement (about 2 min)
6. **N14** The program ends by force while a measurement, then starts again (about 3 min)
7. **Q1** A few questions (about 3 min)

**The maker's manual wins.** If a block contradicts what the maker's manual says about handling your instrument, follow the manual and skip the block.

## All blocks, in the order of one sitting

You can stop after any block: everything you finished goes into the zip, and the zip says which blocks were recorded and which were skipped.

### N01. Start the program and connect

*Priority: essential. About 3 min. Label: `connect`. In the short set.*

1. Make sure the program is closed.
2. Start this block (the recording starts now).
3. Start the program and connect it to the instrument the way you always do.
4. Wait until the program shows the instrument as ready, then wait 15 seconds more.

**What to note:** Did the program find the instrument by itself, or did you type its address or pick it from a list?

**Why we need it:** How the program finds and greets the instrument is the first thing ChromIQ must repeat.

### N02. Calibrate

*Priority: essential. About 2 min. Label: `calibrate`. In the short set.*

If the instrument needs no calibration, record 30 seconds of the program waiting and say so.

1. Start this block.
2. Start the calibration in the program as you normally do, and wait until it is done.

**What to note:** What did you have to do (a tile, a reference)? How long did it take?

**Why we need it:** Calibration is the first measurement-like conversation and usually the simplest to understand.

### N03. One single measurement

*Priority: essential. About 2 min. Label: `one-measurement`. In the short set.*

1. Start this block.
2. Take the smallest measurement the program offers (one patch, one sample), three times on the same spot.

**What to note:** Did the program show numbers? Were they the same each time?

**Why we need it:** One short request and answer is the easiest place to learn the instrument's message format.

### N04. A small job to the end, saved

*Priority: essential. About 5 min. Label: `job-to-end`. In the short set.*

1. Start this block.
2. Measure a small chart or a few samples to the end, the normal way.
3. Save the result in the program under a name you will recognise, and send that file together with the zip.

**What to note:** The name of the saved file.

**Why we need it:** A whole job paired with the program's own saved result lets us check every number.

### N05. Cancel during a measurement

*Priority: essential. About 2 min. Label: `cancel`. In the short set.*

1. Start this block.
2. Start a job, and press Cancel or Stop in the program while it is measuring.
3. Wait until the program and the instrument are at rest.

**What to note:** What did the instrument do?

**Why we need it:** A cancel is an ending ChromIQ must handle cleanly.

### N06. The instrument's information page

*Priority: important. About 2 min. Label: `status`.*

1. Start this block.
2. Open the program's page that shows the instrument's details or status (model, firmware, lamp hours), look, and close it. Change nothing.

**What to note:** What did the page show (no serial numbers needed)?

**Why we need it:** Status requests show how the instrument describes itself, which ChromIQ needs to recognise a model.

### N07. Every other mode

*Priority: important. About 5 min. Label: `modes`.*

Only the modes your program offers.

1. Start this block.
2. For each other measurement mode or condition the program offers, take one measurement.
3. Before each one, type the mode's name here and press Enter.

**What to note:** The modes you tried, in order.

**Why we need it:** Each mode may be its own command.

### N08. A warning the program gives

*Priority: important. About 3 min. Label: `warning`.*

1. Start this block.
2. Create one harmless situation the program warns about, only if you are comfortable with it (for example start a measurement with no sample).
3. Read the message and answer it the normal way.

**What to note:** What exactly did the program say?

**Why we need it:** How the instrument reports a problem is what ChromIQ must understand and explain.

### N09. Five quiet minutes

*Priority: important. About 5 min. Label: `idle`.*

1. Start this block.
2. With the program connected and idle, do nothing for five minutes.

**What to note:** Did anything happen on its own?

**Why we need it:** Network programs often send keep-alive messages; without them some instruments drop the connection.

### N10. The network drops for a moment

*Priority: important. About 3 min. Label: `cable-pull`. An untidy ending. The recording keeps going while the instrument is disconnected.*

1. Start this block (the recording keeps going).
2. With the program idle, pull the instrument's network cable (or, for Wi-Fi, switch its Wi-Fi off if it has a switch). Do not pull your computer's own cable.
3. Wait 20 seconds and read what the program says.
4. Connect it again and wait until the program shows it again (or says it cannot).

**What to note:** What did the program say, and did it reconnect by itself?

**Why we need it:** A dropped connection is an ending ChromIQ must survive.

### N11. Switch the instrument off and on

*Priority: important. About 4 min. Label: `power-cycle`. An untidy ending. The recording keeps going while the instrument is disconnected.*

1. Start this block.
2. With the program open and idle, switch the instrument off.
3. Wait 10 seconds, switch it on again, and wait until the program shows it again (connect again by hand if you must).

**What to note:** Did the program notice and reconnect by itself?

**Why we need it:** After a restart an instrument may get a new network address; the tool follows it, and we learn how the program finds it again.

### N13. Close the program

*Priority: essential. About 1 min. Label: `close`.*

1. Start this block.
2. Close the program the normal way, and wait 10 seconds.

**Why we need it:** What the program sends when it closes is what ChromIQ should do when it lets go of the instrument.

### N14. The program ends by force while a measurement, then starts again

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

- Which instrument is it exactly, and which firmware does it show?
- Which program and which version did you use, on which system?
- How is it connected: a cable to your network, a cable straight to the computer, or Wi-Fi?
- Does the program offer anything that these blocks did not cover?

**Why we need it:** The recording cannot say which program made it or how the instrument is wired.

## Checklist (one page)

- [ ] **N01** Start the program and connect (essential, 3 min)
- [ ] **N02** Calibrate (essential, 2 min)
- [ ] **N03** One single measurement (essential, 2 min)
- [ ] **N04** A small job to the end, saved (essential, 5 min)
- [ ] **N05** Cancel during a measurement (essential, 2 min)
- [ ] **N06** The instrument's information page (important, 2 min)
- [ ] **N07** Every other mode (important, 5 min)
- [ ] **N08** A warning the program gives (important, 3 min)
- [ ] **N09** Five quiet minutes (important, 5 min)
- [ ] **N10** The network drops for a moment (important, 3 min)
- [ ] **N11** Switch the instrument off and on (important, 4 min)
- [ ] **N13** Close the program (essential, 1 min)
- [ ] **N14** The program ends by force while a measurement, then starts again (essential, 3 min)
- [ ] **Q1** A few questions (essential, 3 min)
- [ ] Saved measurement files from the program, named in the notes
- [ ] Ran `--check` on the zip and read what it shows

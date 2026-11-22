# Scenarios: Handheld spot and strip instrument

<!-- Generated from chromiq_probe/sessions/handheld.json by tools/make_scenarios.py. Edit the JSON file, not this page. -->

An instrument you hold in your hand: you place it on one patch (spot) or slide it along a row of patches (strip), with or without a ruler.

**21 blocks, about 56 minutes in all. 10 are essential; the short set of 8 blocks takes about 20 minutes.**

## What this list is built on: real recordings

This list is built from real sessions: owners of an i1Pro, i1Pro 2, i1Pro 3 and ColorMunki recorded X-Rite's programs with the earlier X-Rite recording tool, and every block below answers a question that cost us an extra round when it was missing (lights, the ruler, dual scan, the measurement conditions M0, M1 and M2, refused strips, calibration).

If your program offers something this list misses, please tell us in the GitHub issue where you send your recording: that is how these lists get better.

## Before you start

- Your instrument, its USB cable and its calibration tile or cap.
- The program you normally measure with, closed for now.
- One printed test chart that your program can read, with at least one row of 10 or more patches.
- If your program uses a ruler or a backing board for strips: have it ready.
- Unplug other USB devices you can do without (disks, memory sticks, phones, printers). A keyboard and a mouse may stay.

## If you only have 20 minutes

Do only these blocks, in this order (about 20 minutes). The tool offers this as "the short set". It holds at least one untidy ending, because those are what a first careful drive must recover from.

1. **H01** Plug in and start the program (about 2 min)
2. **H02** Calibrate (about 2 min)
3. **H03** One strip at your normal speed (about 2 min)
4. **H05** A strip that fails on purpose (about 3 min)
5. **H06** Cancel while reading (about 2 min)
6. **H07** A small chart to the end, saved (about 3 min)
7. **H16** The program ends unexpectedly, then starts again (about 3 min)
8. **Q1** A few questions (about 3 min)

**The maker's manual wins.** If a block contradicts what the maker's manual says about handling your instrument, follow the manual and skip the block.

## All blocks, in the order of one sitting

You can stop after any block: everything you finished goes into the zip, and the zip says which blocks were recorded and which were skipped.

### H01. Plug in and start the program

*Priority: essential. About 2 min. Label: `start`. In the short set. The recording keeps going while the instrument is disconnected.*

1. Make sure the measuring program is closed and the instrument is unplugged.
2. Start this block (the recording starts now).
3. Plug the instrument in.
4. Start the measuring program.
5. Wait until the program shows the instrument as connected, then wait 15 seconds more without touching anything.

**What to note:** Did the program find the instrument by itself? Did it show anything about the instrument (model, firmware, serial)? What did the instrument's lights do?

**Why we need it:** The first conversation is where the program identifies the instrument and reads its memory, and it is the one ChromIQ must repeat every time.

### H02. Calibrate

*Priority: essential. About 2 min. Label: `calibrate`. In the short set.*

1. Start this block.
2. Start the calibration in the program, exactly as you normally do (white tile, or the instrument's calibration position).
3. Wait until the program says the calibration is done.

**What to note:** How long did it take? Did the program ask you to move a dial, place the instrument on a tile, or press a button? What did the lights do?

**Why we need it:** Calibration is the first thing ChromIQ must do right, and its timing and commands differ between models.

### H03. One strip at your normal speed

*Priority: essential. About 2 min. Label: `strip`. In the short set.*

1. Start this block.
2. In the program, start reading a strip (a row of patches).
3. Read one row at your normal speed, from where you usually start.
4. Wait until the program has accepted the strip.

**What to note:** Which row, and from which end? Which measurement condition did the program show (M0, M1, M2, dual scan, or none)? What did the lights do before, during and after?

**Why we need it:** This is the reading ChromIQ needs most often: how the program starts a strip, how the readings arrive, and how it decides the strip is good.

### H04. One patch, three times (spot)

*Priority: essential. About 2 min. Label: `spot`.*

Skip this block if the program has no way to read one single patch.

1. Start this block.
2. Switch the program to reading single patches (spot mode).
3. Read the same patch three times, lifting the instrument in between.
4. Switch the program back to strips if it does not do so by itself.

**What to note:** Did the program show numbers for each reading? Were they the same each time, or slightly different?

**Why we need it:** A spot reading has its own command, and three readings of one patch show whether the instrument does its own colour maths or sends raw sensor data.

### H05. A strip that fails on purpose

*Priority: essential. About 3 min. Label: `strip-refused`. In the short set.*

1. Start this block.
2. Start a strip as in block H03.
3. Let it fail in one harmless way: lift the instrument halfway along the row, or move much too fast, or read the wrong row.
4. Read what the program says, and confirm its message.
5. If you like, do a second kind of failure the same way.

**What to note:** Which way did you make it fail? What exactly did the program say? Did the lights change?

**Why we need it:** Every ending must be known, not only the good one: how the instrument and the program report a bad strip decides what ChromIQ can tell its users.

### H06. Cancel while reading

*Priority: essential. About 2 min. Label: `cancel-reading`. In the short set.*

1. Start this block.
2. Start a strip in the program.
3. While the instrument is reading (button pressed or reading under way), press Cancel or Stop in the program.
4. Wait until the program is ready again.

**What to note:** At which moment did you cancel? What did the program and the lights do?

**Why we need it:** A cancel in the middle of a reading is an ending ChromIQ must handle cleanly, and only a recording shows what the program sends then.

### H07. A small chart to the end, saved

*Priority: essential. About 3 min. Label: `reference-chart`. In the short set.*

1. Start this block.
2. Read a small chart (or two or three rows of your chart) to the end, the normal way.
3. Save the measurement in the program (for example as a CGATS or text file), under a name you will recognise.
4. Keep that saved file: please send it together with the zip.

**What to note:** The name of the file you saved, and which rows you read.

**Why we need it:** A recording paired with the program's own result of that very measurement lets us check every number; a file saved another day cannot be paired.

### H08. The same strip in dual scan

*Priority: important. About 4 min. Label: `dual-scan`.*

Only if the program offers dual scan (i1Pro 2, i1Pro 3 and others).

1. Start this block.
2. Switch the program to dual scan (or the mode that reads M0, M1 and M2 at once).
3. Read the row of block H03 as the program asks (often twice: forward and back). Type pass 1 and pass 2 when you start each pass.

**What to note:** How many passes did the program ask for, and what did the lights do?

**Why we need it:** A dual scan uses its own commands and a second pass, and ChromIQ can only offer it once it has seen them.

### H18. Each measurement condition on its own

*Priority: important. About 4 min. Label: `conditions`.*

Only the conditions the program offers (M0, M1, M2, UV cut, polarisation).

1. Start this block.
2. For each condition the program offers: switch to it, type its name and press Enter, and read the row of block H03.

**What to note:** The conditions you tried, in order.

**Why we need it:** Each condition may be its own command or its own pass.

### H19. The same strip without the ruler

*Priority: important. About 3 min. Label: `no-ruler`.*

Only if the program offers reading with and without a ruler or backing board.

1. Start this block.
2. Switch the program to reading without the ruler (if it has a setting for it), and read the row of block H03 freehand.

**What to note:** Did the program accept it?

**Why we need it:** Some instruments read the ruler's position; a strip without it shows what the program does when that data is missing.

### H20. Every other reading mode

*Priority: nice to have. About 4 min. Label: `other-modes`.*

Only the modes your program offers that the blocks before did not cover.

1. Start this block.
2. For each other way of reading the program offers (for example patch recognition on or off), type its name, press Enter and read one strip.

**What to note:** The modes you tried, in order.

**Why we need it:** Each mode may use its own commands.

### H09. The same strip from the other end

*Priority: important. About 2 min. Label: `strip-reverse`.*

1. Start this block.
2. Read the row of block H03 again, but starting from the other end.
3. Wait until the program has accepted or refused it.

**What to note:** Did the program accept the strip read backwards?

**Why we need it:** Whether a strip may be read in both directions, and how the program tells, changes how ChromIQ checks a strip.

### H10. The same strip, clearly faster

*Priority: important. About 2 min. Label: `strip-fast`.*

1. Start this block.
2. Read the row of block H03 again, clearly faster than normal (but not so fast that you expect a failure).
3. Wait until the program has accepted or refused it.

**What to note:** Accepted or refused? About how many seconds did the row take?

**Why we need it:** The readings per second and per patch, and the speed limit, come only from strips at different speeds.

### H11. The same strip, slowly

*Priority: important. About 2 min. Label: `strip-slow`.*

1. Start this block.
2. Read the row of block H03 again, about twice as slowly as normal (count the seconds).
3. Wait until the program has accepted or refused it.

**What to note:** Accepted or refused? About how many seconds did the row take?

**Why we need it:** Together with H10 this shows how the instrument copes with speed, which decides ChromIQ's own speed advice.

### H12. The button and the lights

*Priority: nice to have. About 2 min. Label: `buttons-lights`.*

1. Start this block.
2. With the program waiting for a reading, press the instrument's button once without placing it on a patch, and see what happens.
3. If the program has settings for sounds or lights, open them and look, without changing them.

**What to note:** What did the lights and the program do when you pressed the button?

**Why we need it:** The lights and the button are how an instrument talks to its user, and ChromIQ wants to use them the same way the maker's program does.

### H13. Five quiet minutes

*Priority: important. About 5 min. Label: `idle`.*

1. Start this block.
2. Leave the program open and the instrument connected, and do nothing for five minutes.
3. If the program asks for a new calibration during that time, note it, but do not calibrate yet.

**What to note:** Did anything happen on its own (a message, a light, a sound)?

**Why we need it:** Programs often talk to an idle instrument (keep-alive, temperature, a calibration that expires), and ChromIQ must know what keeps the instrument happy.

### H14. Pull the cable and plug it back

*Priority: important. About 2 min. Label: `cable-pull`. An untidy ending. The recording keeps going while the instrument is disconnected.*

1. Start this block (the recording keeps going while the instrument is gone).
2. With the program open and idle, pull the instrument's USB cable.
3. Wait 10 seconds and read what the program says.
4. Plug the cable back in and wait until the program shows the instrument again (or says it cannot).

**What to note:** What did the program say when the cable was pulled, and when it came back? Did it ask for a new calibration?

**Why we need it:** A pulled cable is an ending ChromIQ must survive; the recording shows how the program finds the instrument again.

### H15. Close the program

*Priority: essential. About 1 min. Label: `close`.*

1. Start this block.
2. Close the measuring program the normal way.
3. Wait 10 seconds.

**What to note:** Did the instrument's lights change when the program closed?

**Why we need it:** What the program sends when it closes is what ChromIQ should send when it lets go of the instrument.

### H16. The program ends unexpectedly, then starts again

*Priority: essential. About 3 min. Label: `restart`. In the short set. An untidy ending.*

1. Start this block, with the program open and the instrument plugged in.
2. End the program by force (Windows: Task Manager, select the program, End task. Mac: Apple menu > Force Quit).
3. Start the measuring program again.
4. Wait until it shows the instrument, and calibrate if it asks you to.

**What to note:** Did it ask for a calibration this time? Did the instrument's lights change?

**Why we need it:** After an unexpected end the instrument is left as the program left it; how the program starts again from there is what ChromIQ needs after its own unexpected end.

### H17. Unplug the cable in the middle of a strip

*Priority: important. About 3 min. Label: `unplug-mid-strip`. An untidy ending. The recording keeps going while the instrument is disconnected.*

1. Start this block (the recording keeps going while the instrument is gone).
2. Start reading a strip, and halfway along the row pull the instrument's USB cable. Type pulled.
3. Wait 10 seconds, plug it back in (into the same port) and let the program find it again.

**What to note:** What did the program say, and did it want a new calibration?

**Why we need it:** An instrument that disappears in the middle of a reading is an ending ChromIQ must survive.

### Q1. A few questions

*Priority: essential. About 3 min. Label: `questions`. In the short set.*

1. No recording now. Answer the questions below; a short line each is fine.

- Which instrument is it exactly (model and, if you know it, its generation)?
- Which program and which version did you use?
- On which system (Windows, macOS, Linux, and which version)?
- Does your program offer anything that these blocks did not cover? A short description helps us add it to this list.

**Why we need it:** The recording cannot say which program and version made it, and a missing block is best found by the person who uses the program.

## Checklist (one page)

- [ ] **H01** Plug in and start the program (essential, 2 min)
- [ ] **H02** Calibrate (essential, 2 min)
- [ ] **H03** One strip at your normal speed (essential, 2 min)
- [ ] **H04** One patch, three times (spot) (essential, 2 min)
- [ ] **H05** A strip that fails on purpose (essential, 3 min)
- [ ] **H06** Cancel while reading (essential, 2 min)
- [ ] **H07** A small chart to the end, saved (essential, 3 min)
- [ ] **H08** The same strip in dual scan (important, 4 min)
- [ ] **H18** Each measurement condition on its own (important, 4 min)
- [ ] **H19** The same strip without the ruler (important, 3 min)
- [ ] **H20** Every other reading mode (nice to have, 4 min)
- [ ] **H09** The same strip from the other end (important, 2 min)
- [ ] **H10** The same strip, clearly faster (important, 2 min)
- [ ] **H11** The same strip, slowly (important, 2 min)
- [ ] **H12** The button and the lights (nice to have, 2 min)
- [ ] **H13** Five quiet minutes (important, 5 min)
- [ ] **H14** Pull the cable and plug it back (important, 2 min)
- [ ] **H15** Close the program (essential, 1 min)
- [ ] **H16** The program ends unexpectedly, then starts again (essential, 3 min)
- [ ] **H17** Unplug the cable in the middle of a strip (important, 3 min)
- [ ] **Q1** A few questions (essential, 3 min)
- [ ] Saved measurement files from the program, named in the notes
- [ ] Ran `--check` on the zip and read what it shows

# Scenarios: Motorised table (xy)

<!-- Generated from chromiq_probe/sessions/table.json by tools/make_scenarios.py. Edit the JSON file, not this page. -->

A table with a moving arm that carries an instrument over a sheet lying on it, reading row by row or patch by patch.

**23 blocks, about 97 minutes in all. 13 are essential; the short set of 6 blocks takes about 20 minutes.**

## What this list is built on: real recordings

This list is built from the X-Rite i1iO 2 work, where a table owner recorded X-Rite's i1Profiler for us. Every block answers something that cost an extra round when it was missing: the start of a table that was just switched on, the start with the arm out over the sheet, the alignment, every reading mode, the whole reach of the arm, and every ending (finish, cancel, a pulled cable, a power cycle). Its blocks follow the reviewed recording plan for the X-Rite i1iO 3 (see the example page), made general.

If your program offers something this list misses, please tell us in the GitHub issue where you send your recording: that is how these lists get better.

## Before you start

- The table, its instrument, and the program you normally use, closed for now.
- A small printed chart the program can read (2 or 3 rows), a few copies, and if you have one a larger chart.
- A ruler, for one measurement in the questions at the end.
- Space around the table: the arm must be able to move freely. Keep your hands away from it while it moves; the table's power switch is the way to stop it.
- The maker's manual wins: if a block contradicts it, follow the manual and skip the block.
- A table is often TWO USB devices (the table and the instrument in its arm): choose both when the tool asks.
- Unplug other USB devices you can do without (disks, memory sticks, phones, printers, other adapters). A keyboard and a mouse may stay.

## If you only have 20 minutes

Do only these blocks, in this order (about 20 minutes). The tool offers this as "the short set". It holds at least one untidy ending, because those are what a first careful drive must recover from.

1. **T03** Switch the table on while recording, start and quit the program (about 3 min)
2. **T04** Calibrate (about 2 min)
3. **T05** A small chart in rows, aimed and read to the end, saved (about 5 min)
4. **T07** Cancel in the middle of a row, then quit (about 3 min)
5. **T08** The program ends by force while it waits for an aim, then starts again (about 4 min)
6. **Q1** A few questions (about 3 min)

**The maker's manual wins.** If a block contradicts what the maker's manual says about handling your instrument, follow the manual and skip the block.

## All blocks, in the order of one sitting

You can stop after any block: everything you finished goes into the zip, and the zip says which blocks were recorded and which were skipped.

### T01. The table idle, the program closed

*Priority: important. About 2 min. Label: `table-idle`.*

1. Make sure the program is closed and the table is switched on.
2. Start this block.
3. Wait 30 seconds and touch nothing.

**What to note:** Where does the arm rest? Is the instrument in the arm? Any light on the table?

**Why we need it:** It shows which USB devices the table and the instrument are, which decides almost everything else.

### T02. Start and quit the program, table already on

*Priority: essential. About 3 min. Label: `warm-start`.*

1. Start this block, with the program closed and the table on.
2. Start the program and wait until it shows the table and the instrument, then 20 seconds more.
3. Quit the program normally (its menu, Quit or Exit), and wait 10 seconds.

**What to note:** Did the arm move when the program started or quit?

**Why we need it:** How the program finds the table and lets go of it is the first and the last thing ChromIQ does every time.

### T03. Switch the table on while recording, start and quit the program

*Priority: essential. About 3 min. Label: `cold-start`. In the short set. The recording keeps going while the instrument is disconnected.*

1. Close the program. Start this block.
2. Switch the table off at its power switch, wait 10 seconds, switch it on and wait until it is quiet.
3. Start the program and wait until it has found the table.
4. Quit the program normally and wait 10 seconds.

**What to note:** Did the arm move by itself after switching on, and when the program started?

**Why we need it:** A table that was just switched on needs its own start-up, and ChromIQ must start it the same way the maker's program does.

### T04. Calibrate

*Priority: essential. About 2 min. Label: `calibrate`. In the short set.*

1. Start this block.
2. Start a measurement in the program up to the point where it calibrates, and let it calibrate exactly as it asks.
3. If it then goes on to aiming, press Cancel and let the arm come to rest. Leave the program open.

**What to note:** Where did the arm go for the calibration, and what did the program ask you to do?

**Why we need it:** Where and how a table calibrates decides the first moves ChromIQ makes.

### T05. A small chart in rows, aimed and read to the end, saved

*Priority: essential. About 5 min. Label: `rows-to-end`. In the short set.*

1. Lay a small chart (2 or 3 rows) in the middle of the table, as the program shows.
2. Start this block.
3. Start the measurement in the program's row (scan or strip) mode, with its default speed.
4. Aim at the points it asks for. Before each aim, type which mark it is (for example "top left") and press Enter.
5. Let it read the whole chart without cancelling, and wait until the arm is home and still.
6. Save the measurement under a name you will recognise, and send that file together with the zip.

**What to note:** How many points did you aim at, and how did you confirm each (the instrument's button or a click)? Were the rows read all the same way or back and forth?

**Why we need it:** A whole job, from the first aim to the parked arm, paired with the program's own saved result, is the backbone of everything ChromIQ will drive.

### T06. The same chart patch by patch, saved

*Priority: essential. About 6 min. Label: `patch-by-patch-to-end`.*

Skip this block if the program cannot read patch by patch.

1. Leave the chart where it lies. Switch the program to reading patch by patch (spot), if it offers it.
2. Start this block.
3. Start the measurement, aim as it asks, and let it read the whole chart. For the first five patches type d when the head goes down and u when it goes up.
4. Wait until the arm is home and still, then save the measurement.

**What to note:** How long did one patch take, roughly?

**Why we need it:** Patch by patch is a different drive with its own moves, head movements and timing.

### T07. Cancel in the middle of a row, then quit

*Priority: essential. About 3 min. Label: `cancel-then-quit`. In the short set.*

1. Start this block.
2. Start reading the chart in rows and aim as asked.
3. When the arm starts along the second row, press Cancel in the program and type cancel.
4. Wait until the arm stands still, then quit the program normally and wait 10 seconds.

**What to note:** What did the arm do after Cancel, and after quitting?

**Why we need it:** A cancel with the arm out, and the quit after it, is what ChromIQ must do when a user presses Stop.

### T08. The program ends by force while it waits for an aim, then starts again

*Priority: essential. About 4 min. Label: `force-quit-while-aiming`. In the short set. An untidy ending.*

1. Start this block.
2. Start a measurement and go on until the program asks you to aim at the first point. Do not aim, do not touch the arm.
3. End the program by force (Windows: Task Manager (Ctrl+Shift+Esc), select the program, End task. Mac: Apple menu > Force Quit, select the program, Force Quit.) Type killed.
4. Wait 20 seconds. Start the program again and watch exactly what the arm does when it finds the table.
5. Quit the program normally.

**What to note:** What did the arm do when the program came back (straight home, or somewhere else first)?

**Why we need it:** This is the state an unexpected end leaves a table in, and how the maker's program repairs it. On the first table we supported it was the most expensive state to have missed.

### T09. The program ends by force during a row, then starts again

*Priority: essential. About 4 min. Label: `force-quit-during-row`. An untidy ending.*

1. Start this block.
2. Start reading the chart in rows.
3. While the arm moves along the second row, end the program by force (Windows: Task Manager (Ctrl+Shift+Esc), select the program, End task. Mac: Apple menu > Force Quit, select the program, Force Quit.) Type killed.
4. Watch the arm: it may stop where it is. Keep your hands away; if it keeps moving, switch the table off.
5. Wait 20 seconds, start the program again and note what the arm does. Quit it normally.

**What to note:** Where did the arm stop, and what did the program do with it when it came back?

**Why we need it:** After a crash in the middle of a movement the table is left in a state only the maker's own recovery shows.

### T10. Quit normally while the program waits for an aim

*Priority: essential. About 3 min. Label: `quit-while-aiming`.*

1. Start this block.
2. Start a measurement and go on until the program asks you to aim. Do not aim.
3. Quit the program normally (its menu; confirm if it asks). Type quit.
4. Wait 20 seconds. Start the program again, note what the arm does, quit it.

**What to note:** What did the arm do when the program quit, and when it started again?

**Why we need it:** The maker's tidy-up at this moment is the design ChromIQ copies for its own endings.

### T11. Quit normally with the arm out over the sheet

*Priority: essential. About 3 min. Label: `quit-with-arm-out`.*

1. Start this block.
2. Start reading the chart in rows and aim as asked.
3. As soon as the second row has finished, quit the program normally (do not press Cancel first). Type quit.
4. Wait 20 seconds. Start the program again, note what the arm does, quit it.

**What to note:** What did the arm do when the program quit in the middle of the chart?

**Why we need it:** How the maker's program tidies up when it quits mid-job, with the arm held out, is what ChromIQ must do too.

### T12. The aiming state across a power cycle, with no program running

*Priority: essential. About 4 min. Label: `aiming-across-power-cycle`. An untidy ending. The recording keeps going while the instrument is disconnected.*

1. Start this block.
2. Start a measurement and go on until it asks you to aim, then end the program by force (type killed). Do not touch the arm.
3. Switch the table off, wait 10 seconds, switch it on (type power off and power on). Note what the arm does by itself.
4. Start the program (nothing has run since the power cycle) and note what the arm does. Quit it normally.

**What to note:** What did the arm do after switching on, and when the program found the table?

**Why we need it:** Whether a table remembers its state across a power cycle decides what ChromIQ must check at every start.

### T13. The way home from one part of the table (repeat for each part)

*Priority: essential. About 5 min. Label: `way-home`. An untidy ending.*

1. Lay the small chart (cut to size if needed) in one part of the table: back left, back right, front left, front right, or the middle. Type that part as the label.
2. Start this block. Start a patch by patch measurement there and aim as asked.
3. After two or three patches, while the arm stands still on a patch, end the program by force (type killed).
4. Wait 20 seconds. Start the program again and note exactly the way the arm takes home. Quit it normally.
5. Do this block once for each part of the table.

**What to note:** Which part of the table, and the way the arm took home (straight, or first somewhere else)?

**Why we need it:** The maker's software may bring the arm home by a detour from some parts of the table; on the first table we supported we found those late. Here the program itself puts the arm there: you never push it.

### T14. Switch the table off and on while the program runs

*Priority: important. About 3 min. Label: `power-cycle-program-running`. An untidy ending. The recording keeps going while the instrument is disconnected.*

1. Start this block. With the arm at rest and the program open, switch the table off.
2. Wait 10 seconds, switch it on again, and wait until the program shows it again.

**What to note:** Did the program notice? Did the arm move after switching on?

**Why we need it:** A table switched off under a running program is a start state ChromIQ meets too.

### T15. Pull the USB cable during a measurement

*Priority: important. About 3 min. Label: `cable-pull`. An untidy ending. The recording keeps going while the instrument is disconnected.*

1. Only if you are comfortable with it, and only if the maker's manual does not warn against it.
2. Start this block. Start a measurement and, while the arm moves, pull the table's USB cable. Type pulled.
3. Wait 10 seconds, plug the cable back in (into the same port) and see what the program does.

**What to note:** What did the arm and the program do?

**Why we need it:** A pulled cable is an ending ChromIQ must survive without needing the maker's program.

### T16. Every patch length and speed (repeat for each)

*Priority: important. About 5 min. Label: `patch-length`.*

1. Make small charts of two rows at five patch sizes spread over the whole range the program offers for row reading (the smallest, the largest and three between).
2. For each chart, and then for the fastest and the slowest speed setting: type a label such as length-1 or fastest, start this block, aim, let it read both rows and save the measurement.

**What to note:** The patch size or speed setting, and how long one row took.

**Why we need it:** On the first table we supported the speed depended on the patch length, and every speed not recorded had to be asked for again.

### T17. Every measurement condition

*Priority: important. About 8 min. Label: `conditions`.*

Only the conditions your program offers.

1. For each condition the program offers (M0, M1, M2, dual scan, UV cut): type its name as the label, start this block, let it read one row, and save the measurement.

**What to note:** The conditions you tried, in order, and anything that looked different (an extra pass, other lights).

**Why we need it:** Each condition may use its own commands and its own pass.

### T18. Aiming at the far corners of the table

*Priority: important. About 5 min. Label: `aim-everywhere`.*

1. Start this block. Lay a chart as far out as the program allows, or aim at points near each corner of the table's area if the program lets you.
2. Aim as the program asks and let it read the first and last row.

**What to note:** Where on the table did the chart lie?

**Why we need it:** ChromIQ may move the arm wherever the table can reach; recordings near the edges show the real limits instead of a guess.

### T19. A warning the program gives

*Priority: important. About 3 min. Label: `warning`.*

1. Start this block.
2. Create one harmless situation the program warns about, only if you are comfortable with it: for example start a reading with no sheet on the table, or with the sheet hold off.
3. Read the message and answer it the normal way. Never hold the arm back or force it by hand.

**What to note:** What did you do, and what exactly did the program say?

**Why we need it:** How the table reports a problem is what ChromIQ will have to understand and explain.

### T20. The program's own arm controls

*Priority: nice to have. About 3 min. Label: `program-controls`.*

Only if the program has such controls.

1. Start this block.
2. Use each control the program offers for the arm (Home, Park, Release arm, Move), one after another. Before each one, type its name and press Enter.

**What to note:** Which controls, and what each did.

**Why we need it:** Each control is a command ChromIQ can offer for the same purpose.

### T21. A long quiet time, then one measurement

*Priority: important. About 12 min. Label: `long-idle`. The tool says when 10 minutes have passed.*

1. Start this block with the program open and the arm at rest.
2. Do nothing until the tool says the time is up (10 minutes; longer, up to an hour, is even better: just wait longer).
3. Then start a small measurement and let it read one row.

**What to note:** Did anything happen on its own? Did the program ask for a new calibration?

**Why we need it:** Programs often keep talking to an idle table, and a calibration may expire; ChromIQ must know both.

### T22. Optional extras by hand

*Priority: nice to have. About 5 min. Label: `hand-extras`.*

1. Only if you are comfortable with it, and only what the maker's manual allows (the manual wins over this list).
2. With the table switched OFF, move the arm gently out over the table, then start this block, switch the table on and start the program.
3. Or: start a measurement with the instrument not in the arm, and read what the program says.

**What to note:** Which extra you did, and what the table and the program did.

**Why we need it:** Some states can only be made by hand; they are optional and never needed for the rest.

### Q1. A few questions

*Priority: essential. About 3 min. Label: `questions`. In the short set.*

1. No recording now. Answer the questions below; a short line each is fine.

- Which table, and which instrument is mounted in it?
- Which program and which version did you use, on which system?
- Please measure with a ruler the distance from the centre of the first patch to the centre of the last patch of one row of the small chart, in millimetres.
- Which chart files did you use (the program's own test chart, or one you made)? If you can, send them too.
- Does the program offer anything for the table that these blocks did not cover?

**Why we need it:** The ruler measurement proves the unit of the table's coordinates, and the rest the recording cannot say.

## Checklist (one page)

- [ ] **T01** The table idle, the program closed (important, 2 min)
- [ ] **T02** Start and quit the program, table already on (essential, 3 min)
- [ ] **T03** Switch the table on while recording, start and quit the program (essential, 3 min)
- [ ] **T04** Calibrate (essential, 2 min)
- [ ] **T05** A small chart in rows, aimed and read to the end, saved (essential, 5 min)
- [ ] **T06** The same chart patch by patch, saved (essential, 6 min)
- [ ] **T07** Cancel in the middle of a row, then quit (essential, 3 min)
- [ ] **T08** The program ends by force while it waits for an aim, then starts again (essential, 4 min)
- [ ] **T09** The program ends by force during a row, then starts again (essential, 4 min)
- [ ] **T10** Quit normally while the program waits for an aim (essential, 3 min)
- [ ] **T11** Quit normally with the arm out over the sheet (essential, 3 min)
- [ ] **T12** The aiming state across a power cycle, with no program running (essential, 4 min)
- [ ] **T13** The way home from one part of the table (repeat for each part) (essential, 5 min)
- [ ] **T14** Switch the table off and on while the program runs (important, 3 min)
- [ ] **T15** Pull the USB cable during a measurement (important, 3 min)
- [ ] **T16** Every patch length and speed (repeat for each) (important, 5 min)
- [ ] **T17** Every measurement condition (important, 8 min)
- [ ] **T18** Aiming at the far corners of the table (important, 5 min)
- [ ] **T19** A warning the program gives (important, 3 min)
- [ ] **T20** The program's own arm controls (nice to have, 3 min)
- [ ] **T21** A long quiet time, then one measurement (important, 12 min)
- [ ] **T22** Optional extras by hand (nice to have, 5 min)
- [ ] **Q1** A few questions (essential, 3 min)
- [ ] Saved measurement files from the program, named in the notes
- [ ] Ran `--check` on the zip and read what it shows

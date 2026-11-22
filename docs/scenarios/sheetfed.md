# Scenarios: Sheet-fed chart reader

<!-- Generated from chromiq_probe/sessions/sheetfed.json by tools/make_scenarios.py. Edit the JSON file, not this page. -->

A device that pulls a chart page in by itself, finds the rows and reads them, like the X-Rite i1iSis.

**13 blocks, about 40 minutes in all. 8 are essential; the short set of 6 blocks takes about 20 minutes.**

## What this list is built on: our best reasoning

No recording of a sheet-fed reader has reached us yet. This list is our best reasoning from the table and handheld work: the same start states, readings and endings, adapted to a device that feeds the paper itself. If your program offers something this list misses, please tell us.

If your program offers something this list misses, please tell us in the GitHub issue where you send your recording: that is how these lists get better.

## Before you start

- The reader, its cables, and the program you normally use, closed for now.
- Two printed chart pages the reader can read (a chart of two pages is ideal), and one plain sheet of the same paper.
- Some readers must be switched on before their USB cable is plugged in: do it the way the maker says.
- The maker's manual wins: if a block contradicts it, follow the manual and skip the block.
- Unplug other USB devices you can do without (disks, memory sticks, phones, printers). A keyboard and a mouse may stay.

## If you only have 20 minutes

Do only these blocks, in this order (about 20 minutes). The tool offers this as "the short set". It holds at least one untidy ending, because those are what a first careful drive must recover from.

1. **S01** Switch on and start the program (about 3 min)
2. **S02** Calibrate (about 2 min)
3. **S03** One chart page to the end, saved (about 4 min)
4. **S05** A plain sheet instead of a chart (about 3 min)
5. **S12** The program ends by force while a chart page is being read, then starts again (about 3 min)
6. **Q1** A few questions (about 5 min)

**The maker's manual wins.** If a block contradicts what the maker's manual says about handling your instrument, follow the manual and skip the block.

## All blocks, in the order of one sitting

You can stop after any block: everything you finished goes into the zip, and the zip says which blocks were recorded and which were skipped.

### S01. Switch on and start the program

*Priority: essential. About 3 min. Label: `switch-on`. In the short set. The recording keeps going while the instrument is disconnected.*

1. Make sure the program is closed and the reader is off.
2. Start this block (the recording starts now).
3. Switch the reader on (and plug in its USB cable, if that is the maker's order), and wait until it is quiet.
4. Start the program and wait until it says the reader is ready.

**What to note:** Did the reader do anything by itself at the start (move rollers, light up, calibrate)?

**Why we need it:** The start of a just-switched-on reader is the first thing ChromIQ must repeat exactly.

### S02. Calibrate

*Priority: essential. About 2 min. Label: `calibrate`. In the short set.*

If the program has no separate calibration, record 30 seconds of the program waiting instead and say so in the note.

1. Start this block.
2. Start the calibration in the program, if it has one.
3. Wait until the program says it is done.

**What to note:** Was there a separate calibration, or does the reader calibrate by itself?

**Why we need it:** Where a reader calibrates (an inner tile, a white strip on the page) changes every reading after it.

### S03. One chart page to the end, saved

*Priority: essential. About 4 min. Label: `page-to-end`. In the short set.*

1. Start this block.
2. Feed the first chart page, as the program asks, and let it read the whole page.
3. Let the reader push the page out.
4. Save the measurement in the program under a name you will recognise, and send that file together with the zip.

**What to note:** How did the page go in (by itself, after a button)? The name of the saved file.

**Why we need it:** One whole page, from feeding to the saved result, is the core job ChromIQ would drive, and pairing it with the program's own file lets us check every number.

### S04. The next page of the chart

*Priority: important. About 3 min. Label: `second-page`.*

Only if your chart has more than one page.

1. Start this block.
2. Feed the second page when the program asks for it, and let it be read to the end.

**What to note:** Did the program check that it was the right page (a barcode, a mark)?

**Why we need it:** How the program tells pages apart decides how ChromIQ prints and reads multi-page charts.

### S05. A plain sheet instead of a chart

*Priority: essential. About 3 min. Label: `wrong-sheet`. In the short set.*

1. Start this block.
2. Start a reading, and feed the plain sheet instead of a chart page.
3. Read what the program says, and answer it the normal way.

**What to note:** What exactly did the program say, and what did the reader do with the sheet?

**Why we need it:** A refused sheet is an ending ChromIQ must recognise and explain; only a recording shows how the reader reports it.

### S06. Cancel while a page is being read

*Priority: essential. About 2 min. Label: `cancel-reading`.*

1. Start this block.
2. Feed a chart page and start the reading.
3. While the page is moving through the reader, press Cancel or Stop in the program.
4. Wait until the reader is at rest, and take the page out the way the program says.

**What to note:** What happened to the page? Did the program ask you to do anything?

**Why we need it:** A cancel with paper inside is the ending most likely to leave a device in a strange state.

### S07. Every other reading mode

*Priority: important. About 4 min. Label: `modes`.*

Only the modes your program offers.

1. Start this block.
2. For each other mode or measurement condition the program offers (for example M1, M2, UV, a faster or slower setting), read one page.
3. Before each page, type the setting's name here and press Enter.

**What to note:** The settings you tried, in order.

**Why we need it:** Each mode may be its own set of commands, and ChromIQ can only offer what it has seen.

### S08. The program's eject or feed controls

*Priority: nice to have. About 2 min. Label: `eject`.*

Only if the program has such buttons.

1. Start this block.
2. Use each paper control the program offers (eject, feed, clean) once, with no paper inside.
3. Before each one, type its name here and press Enter.

**What to note:** Which controls, and what each did.

**Why we need it:** Each control is a command ChromIQ could offer for the same purpose, for example to free a page.

### S09. Five quiet minutes

*Priority: important. About 5 min. Label: `idle`.*

1. Start this block.
2. With the program open and no paper inside, do nothing for five minutes.

**What to note:** Did anything happen on its own?

**Why we need it:** Programs often keep talking to an idle device; ChromIQ must know what keeps it ready.

### S10. Pull the cable and plug it back

*Priority: important. About 3 min. Label: `cable-pull`. The recording keeps going while the instrument is disconnected.*

1. Start this block (the recording keeps going while the reader is gone).
2. With no paper inside and the program idle, pull the reader's USB cable.
3. Wait 10 seconds, plug it back in, and wait until the program shows the reader again.

**What to note:** What did the program say?

**Why we need it:** A pulled cable is an ending ChromIQ must survive without needing the maker's program.

### S11. Close the program

*Priority: essential. About 1 min. Label: `close`.*

1. Start this block.
2. Close the program the normal way, and wait 10 seconds.

**What to note:** Did the reader do anything when the program closed?

**Why we need it:** What the program sends when it closes is what ChromIQ should do when it lets go of the reader.

### S12. The program ends by force while a chart page is being read, then starts again

*Priority: essential. About 3 min. Label: `unexpected-end`. In the short set. An untidy ending.*

1. Start this block.
2. Start a chart page is being read in the program.
3. While it is busy, end the program by force (Windows: Task Manager (Ctrl+Shift+Esc), select the program, End task. Mac: Apple menu > Force Quit, select the program, Force Quit.) Type killed.
4. Wait 20 seconds. Start the program again and note what it does with the instrument (a new calibration, a message).
5. Take the page out the way the maker's manual says.

**What to note:** What did the instrument do when the program disappeared, and when it came back?

**Why we need it:** After an unexpected end the instrument is left as the program left it; how the maker's program recovers is what ChromIQ needs after its own unexpected end.

### Q1. A few questions

*Priority: essential. About 5 min. Label: `questions`. In the short set.*

1. No recording now. Answer the questions below; a short line each is fine.

- Which reader is it exactly?
- Which program and which version did you use, on which system?
- Which chart did you use, and what paper size? If you can, send the chart file too.
- What does the printed chart have besides patches (marks, a barcode, a white strip)?
- Does the program offer anything that these blocks did not cover?

**Why we need it:** What is printed around the patches is what ChromIQ must print on its own charts for the reader to accept them.

## Checklist (one page)

- [ ] **S01** Switch on and start the program (essential, 3 min)
- [ ] **S02** Calibrate (essential, 2 min)
- [ ] **S03** One chart page to the end, saved (essential, 4 min)
- [ ] **S04** The next page of the chart (important, 3 min)
- [ ] **S05** A plain sheet instead of a chart (essential, 3 min)
- [ ] **S06** Cancel while a page is being read (essential, 2 min)
- [ ] **S07** Every other reading mode (important, 4 min)
- [ ] **S08** The program's eject or feed controls (nice to have, 2 min)
- [ ] **S09** Five quiet minutes (important, 5 min)
- [ ] **S10** Pull the cable and plug it back (important, 3 min)
- [ ] **S11** Close the program (essential, 1 min)
- [ ] **S12** The program ends by force while a chart page is being read, then starts again (essential, 3 min)
- [ ] **Q1** A few questions (essential, 5 min)
- [ ] Saved measurement files from the program, named in the notes
- [ ] Ran `--check` on the zip and read what it shows

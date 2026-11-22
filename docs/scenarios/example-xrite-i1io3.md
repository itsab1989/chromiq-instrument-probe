# Example: the same plan for one model, the X-Rite i1iO 3

The generic list for motorised tables ([table.md](table.md)) is the frame.
For one particular model, a plan can go much further, because the model's own
program, sheet sizes and speeds are known. ChromIQ's repository has such a
plan for the X-Rite i1iO 3 table: about 28 blocks in four recording runs (the
core with its untidy endings, every state the table can be left in, the
whole bed and every speed and measurement condition, and extras), each with a
label, single actions, what to note and its priority.

- The plan: `docs/recording_plan_i1io3.md` in the
  [ChromIQ repository](https://github.com/itsab1989/ChromIQ) (being
  prepared; it appears there with its release).
- For an i1iO 3, the recordings themselves are best made with the X-Rite
  sibling, [chromiq-i1io-probe](https://github.com/itsab1989/chromiq-i1io-probe),
  until this tool has run on real hardware.

What the model plan adds to the generic list, as an example of what a good
model plan looks like:

- the blocks are grouped into runs that fit one sitting each;
- the sheets to print are named and sized (the smallest and largest patch the
  program offers, a full page, a chart over two pages);
- every state the table can be left in is recorded on its own: quit while the
  program waits for an aim, quit with the arm out, the aiming mode across a
  power cycle, the way home from every part of the bed;
- a reference sheet is read twice, and one block waits an hour before
  measuring again;
- a box says which of the recording tool's own texts do not fit this model,
  and what to do instead.

A session file for one model is written in the format of
[SESSIONS.md](../../SESSIONS.md) and used with `--session`.

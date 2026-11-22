# Writing a session file

A session file is a plain JSON file that tells the tool which blocks to walk
an owner through. The built-in ones are in `chromiq_probe/sessions/`, one per
kind of instrument; they are also the source of the pages in
[SCENARIOS.md](SCENARIOS.md). You can write one for a particular instrument
(for example from a recording plan for one model) and use it with

```
python3 instrument_probe.py --session my-instrument.json
python3 instrument_probe.py --validate-session my-instrument.json
```

`--validate-session` says, in plain sentences, everything that is wrong.

## The format

```json
{
  "format": "chromiq-probe-session/1",
  "id": "my-instrument",
  "title": "Maker Model 3 table",
  "summary": "One sentence: what kind of instrument this is for.",
  "transport": "usb",
  "experience": "reasoned",
  "experience_text": "Where this list comes from, honestly.",
  "before_you_start": ["What to have ready, one item per line."],
  "blocks": [
    {
      "id": "B01", "label": "cold-start", "title": "Switch on while recording",
      "priority": "essential", "minutes": 5, "kind": "record", "disconnects": true,
      "steps": ["One action per line.", "Another action."],
      "note": "What the owner should write down afterwards.",
      "why": "One plain sentence: why we need this block."
    }
  ]
}
```

| field | required | meaning |
|---|---|---|
| `format` | yes | always `chromiq-probe-session/1` |
| `id`, `title` | yes | a short name and the title shown |
| `summary`, `experience_text`, `before_you_start` | no | shown before the first block and on the page |
| `transport` | no | `usb` or `net`: the connection asked first |
| `experience` | no | `real` (built from real recordings) or `reasoned` |
| block `id` | yes | unique, letters and digits only (at most 8), for example `B01` |
| block `label` | yes | small letters, digits and hyphens, at most 40; it names the recording file (`B01-cold-start.pcap`) and is what `--diff` compares |
| block `priority` | yes | `essential`, `important` or `nice to have` |
| block `short` | no | `true` puts an essential block into the 20-minute short set; the short set must fit 20 minutes and hold at least one untidy ending |
| block `ending` | no | `"untidy"` for a force-quit, a pulled cable or a power cycle |
| block `timer_minutes` | no | the tool says when that many minutes have passed (an idle block) |
| block `minutes` | yes | about how long it takes |
| block `kind` | yes | `record` (a recording) or `question` (questions only, no recording; give them in `questions`) |
| block `steps` | yes | the actions, one per line, in the maker's program |
| block `why` | yes | one plain sentence |
| block `note` | no | the question after the block |
| block `only_if` | no | when the block applies ("Only if the program offers ...") |
| block `disconnects` | no | `true` when the instrument is unplugged or switched off during the block: the recording keeps going and the tool finds it again |
| block `ask_saved_file` | no | `true` asks for the name of the file the program saved |
| block `ask_label`, `repeatable` | no | the owner types the label, and may repeat the block |

## Rules for the texts

- Friendly, plain and exact: say what to do, one action per line, and why.
- Name the maker's program's own buttons as it names them.
- No em dash: use a comma, a colon or a full stop. The validator refuses it.
- Never ask for anything that could harm the instrument or the person: no
  forcing a moving part by hand, nothing a maker's manual warns against.
  "Only if you are comfortable with it" for anything unusual.
- Ask for every ending, not only the good one: cancel, a failure, a pulled
  cable, a power cycle, an unexpected end of the program, a normal close.
- The maker's manual wins: say so, and keep anything done by hand optional.
- Never ask the owner to type a password, a login or a licence key while a
  block records (it would be in the recording).
- Ask for a saved measurement file from the program in at least one block,
  so a recording can be paired with the program's own result.

## The built-in pages

After changing a built-in session file, regenerate the pages:

```
python3 tools/make_scenarios.py
```

The test suite fails when a page and its session file differ.

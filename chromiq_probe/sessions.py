"""Guided sessions: plain JSON data files, one per instrument type.

The same files drive the tool's prompts AND the scenario pages in the
repository (SCENARIOS.md and docs/scenarios/*.md are generated from them by
tools/make_scenarios.py, and tests/test_sessions.py fails when they differ),
so the two cannot drift apart. The format is described in SESSIONS.md.
"""

from __future__ import annotations

import json
import os
import re

FORMAT = "chromiq-probe-session/1"
PRIORITIES = ("essential", "important", "nice to have")
KINDS = ("record", "question")
BUILTIN_ORDER = ("handheld", "table", "sheetfed", "network", "serial", "other")
EM_DASH = chr(0x2014)
_ID_RE = re.compile(r"^[A-Za-z0-9]{1,8}$")
_LABEL_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")


def sessions_dir() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "sessions")


class SessionError(ValueError):
    pass


def validate(data: dict, source: str = "session") -> list:
    """Every problem with a session file, as plain sentences (empty: fine)."""
    problems = []
    if data.get("format") != FORMAT:
        problems.append(f"{source}: \"format\" must be \"{FORMAT}\".")
    for key in ("id", "title", "blocks"):
        if not data.get(key):
            problems.append(f"{source}: \"{key}\" is missing.")
    if data.get("transport") not in ("usb", "net", None):
        problems.append(f"{source}: \"transport\" must be \"usb\" or \"net\".")
    if data.get("experience") not in ("real", "reasoned", None):
        problems.append(f"{source}: \"experience\" must be \"real\" or \"reasoned\".")
    seen_ids, seen_labels = set(), set()
    for i, b in enumerate(data.get("blocks") or [], 1):
        where = f"{source}, block {i}"
        for key in ("id", "label", "title", "priority", "minutes", "kind", "steps", "why"):
            if key not in b or b[key] in ("", None, []):
                problems.append(f"{where}: \"{key}\" is missing.")
        if b.get("priority") not in PRIORITIES:
            problems.append(f"{where}: priority must be one of {', '.join(PRIORITIES)}.")
        if b.get("kind") not in KINDS:
            problems.append(f"{where}: kind must be \"record\" or \"question\".")
        if b.get("label") and not _LABEL_RE.match(b["label"]):
            problems.append(f"{where}: label \"{b['label']}\" may use only small letters, "
                            "digits and hyphens (at most 40).")
        if not isinstance(b.get("minutes"), (int, float)) or b.get("minutes", 0) <= 0:
            problems.append(f"{where}: minutes must be a positive number.")
        if b.get("id") and not _ID_RE.match(str(b["id"])):
            problems.append(f"{where}: id \"{b['id']}\" may use only letters and digits "
                            "(at most 8), for example B01.")
        if b.get("timer_minutes") is not None and not (
                isinstance(b["timer_minutes"], (int, float)) and b["timer_minutes"] > 0):
            problems.append(f"{where}: timer_minutes must be a positive number.")
        if b.get("ending") not in (None, "untidy"):
            problems.append(f"{where}: ending may only be \"untidy\".")
        if b.get("id") in seen_ids:
            problems.append(f"{where}: id {b.get('id')} is used twice.")
        if b.get("label") in seen_labels:
            problems.append(f"{where}: label {b.get('label')} is used twice.")
        seen_ids.add(b.get("id"))
        seen_labels.add(b.get("label"))
        for text in [b.get("title", ""), b.get("note", ""), b.get("why", "")] + \
                list(b.get("steps") or []) + list(b.get("questions") or []):
            if EM_DASH in text:
                problems.append(f"{where}: an em dash in \"{text[:40]}...\"; please use a "
                                "comma, a colon or a full stop.")
    short = [b for b in data.get("blocks") or [] if b.get("short")]
    if short:
        if sum(b.get("minutes", 0) for b in short) > 20:
            problems.append(f"{source}: the short set (blocks with \"short\": true) must fit "
                            "20 minutes.")
        if not any(b.get("ending") == "untidy" for b in short):
            problems.append(f"{source}: the short set must hold at least one untidy ending "
                            "(a block with \"ending\": \"untidy\").")
    return problems


def load(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        try:
            data = json.load(fh)
        except json.JSONDecodeError as exc:
            raise SessionError(f"{os.path.basename(path)} is not valid JSON: {exc}") from None
    problems = validate(data, os.path.basename(path))
    if problems:
        raise SessionError("\n".join(problems))
    return data


def builtin(name: str) -> dict:
    return load(os.path.join(sessions_dir(), f"{name}.json"))


def all_builtin() -> list:
    return [builtin(n) for n in BUILTIN_ORDER]


def essential(data: dict) -> list:
    return [b for b in data["blocks"] if b["priority"] == "essential"]


def short_set(data: dict) -> list:
    """The 20-minute set: the blocks marked "short" (at least one untidy ending)."""
    return [b for b in data["blocks"] if b.get("short")]


def minutes(blocks) -> int:
    return int(round(sum(b["minutes"] for b in blocks)))


def progress_line(data: dict, done_ids, index: int) -> str:  # noqa: D401
    """'Block 4 of 17 (essential). Essential blocks done: 3 of 8.'"""
    blocks = data["blocks"]
    b = blocks[index]
    ess = essential(data)
    ess_done = sum(1 for x in ess if x["id"] in done_ids)
    tail = "all essential blocks done" if ess_done == len(ess) else \
        f"essential blocks done: {ess_done} of {len(ess)}"
    return f"Block {index + 1} of {len(blocks)} ({b['priority']}). {tail[0].upper()}{tail[1:]}."


# ---- the scenario pages -------------------------------------------------------

EXPERIENCE_HEADINGS = {"real": "What this list is built on: real recordings",
                       "reasoned": "What this list is built on: our best reasoning"}


def render_page(data: dict) -> str:
    ess = short_set(data)
    lines = [f"# Scenarios: {data['title']}", "",
             "<!-- Generated from chromiq_probe/sessions/" + data["id"] + ".json by "
             "tools/make_scenarios.py. Edit the JSON file, not this page. -->", "",
             data.get("summary", ""), "",
             f"**{len(data['blocks'])} blocks, about {minutes(data['blocks'])} minutes in all. "
             f"{len(essential(data))} are essential; the short set of {len(ess)} blocks takes "
             f"about {minutes(ess)} minutes.**", "",
             f"## {EXPERIENCE_HEADINGS[data.get('experience', 'reasoned')]}", "",
             data.get("experience_text", ""), "",
             "If your program offers something this list misses, please tell us in the "
             "GitHub issue where you send your recording: that is how these lists get better.",
             "", "## Before you start", ""]
    lines += [f"- {x}" for x in data.get("before_you_start", [])]
    lines += ["", "## If you only have 20 minutes", "",
              f"Do only these blocks, in this order (about {minutes(ess)} minutes). The tool "
              "offers this as \"the short set\". It holds at least one untidy ending, "
              "because those are what a first careful drive must recover from.", ""]
    lines += [f"{i}. **{b['id']}** {b['title']} (about {b['minutes']} min)"
              for i, b in enumerate(ess, 1)]
    lines += ["", "**The maker's manual wins.** If a block contradicts what the maker's manual "
              "says about handling your instrument, follow the manual and skip the block."]
    lines += ["", "## All blocks, in the order of one sitting", "",
              "You can stop after any block: everything you finished goes into the zip, "
              "and the zip says which blocks were recorded and which were skipped.", ""]
    for b in data["blocks"]:
        lines += [f"### {b['id']}. {b['title']}", "",
                  f"*Priority: {b['priority']}. About {b['minutes']} min. "
                  f"Label: `{b['label']}`" + (". In the short set" if b.get("short") else "")
                  + (". An untidy ending" if b.get("ending") == "untidy" else "")
                  + (". The recording keeps going while the instrument is disconnected" if
                     b.get("disconnects") else "")
                  + (f". The tool says when {b['timer_minutes']} minutes have passed"
                     if b.get("timer_minutes") else "") + ".*", ""]
        if b.get("only_if"):
            lines += [f"{b['only_if']}", ""]
        lines += [f"{i}. {s}" for i, s in enumerate(b["steps"], 1)]
        if b.get("questions"):
            lines += [""] + [f"- {q}" for q in b["questions"]]
        if b.get("note"):
            lines += ["", f"**What to note:** {b['note']}"]
        lines += ["", f"**Why we need it:** {b['why']}", ""]
    lines += ["## Checklist (one page)", ""]
    lines += [f"- [ ] **{b['id']}** {b['title']} ({b['priority']}, {b['minutes']} min)"
              for b in data["blocks"]]
    lines += ["- [ ] Saved measurement files from the program, named in the notes",
              "- [ ] Ran `--check` on the zip and read what it shows", ""]
    return "\n".join(lines)


def render_index(all_data: list) -> str:
    lines = ["# Which scenarios to record, for every kind of instrument", "",
             "<!-- Generated by tools/make_scenarios.py from chromiq_probe/sessions/*.json. -->",
             "",
             "One sitting with the right set of recordings answers more than many small "
             "rounds. For each kind of instrument there is one ordered list of short blocks, "
             "the most useful first within a sensible order for one sitting. Each block says "
             "what to do in the maker's own program, one action per line, what to note, and "
             "why we need it. The tool's guided session walks you through exactly the same "
             "list (the tool and these pages are made from the same files), shows how far you "
             "are, and writes into the zip which blocks were recorded and which were skipped.",
             "",
             "| Kind of instrument | Blocks | Essential | All, about | Short set, about | "
             "Built on |", "|---|---|---|---|---|---|"]
    for d in all_data:
        ess = essential(d)
        lines.append(f"| [{d['title']}](docs/scenarios/{d['id']}.md) | {len(d['blocks'])} | "
                     f"{len(ess)} | {minutes(d['blocks'])} min | {minutes(short_set(d))} min | "
                     f"{'real recordings' if d.get('experience') == 'real' else 'our reasoning'}"
                     " |")
    lines += ["",
              "Priorities: **essential** (without these a recording answers little), "
              "**important** (each answers a question we have needed before), **nice to "
              "have**. The **short set** is a 20-minute choice from the essential blocks, with "
              "at least one untidy ending.", "",
              "**The maker's manual wins.** If anything here contradicts what the maker's "
              "manual says about handling your instrument, follow the manual and skip the "
              "block. Nothing in these lists asks you to force a moving part by hand.", "",
              "Display colorimeters (the small pucks for screens) are not covered: ArgyllCMS "
              "already supports most of them, and their steps are different.", "",
              "An example of the same plan for one model: "
              "[X-Rite i1iO 3](docs/scenarios/example-xrite-i1io3.md).", "",
              "To write a session file for one particular instrument, see "
              "[SESSIONS.md](SESSIONS.md).", ""]
    return "\n".join(lines)


def generated_files(root: str) -> dict:
    """{path relative to the repository: content} of every generated page."""
    data = all_builtin()
    out = {"SCENARIOS.md": render_index(data)}
    for d in data:
        out[os.path.join("docs", "scenarios", d["id"] + ".md")] = render_page(d)
    return out

"""The session files are the single source: valid, honest, and the scenario
pages in the repository are exactly what they generate."""

import json
import os

import pytest

from chromiq_probe import sessions

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.mark.parametrize("name", sessions.BUILTIN_ORDER)
def test_builtin_session_is_valid(name):
    d = sessions.builtin(name)
    assert d["id"] == name
    assert sessions.short_set(d), "every type has a short set"
    assert sessions.minutes(sessions.short_set(d)) <= 20, "the short set fits 20 minutes"
    assert any(b.get("ending") == "untidy" for b in sessions.short_set(d)), \
        "review M5: the short set holds at least one untidy ending"
    assert all(b["priority"] == "essential" for b in sessions.short_set(d))
    assert d["experience"] in ("real", "reasoned") and d["experience_text"]
    kinds = [b["kind"] for b in d["blocks"]]
    assert kinds[-1] == "question", "the questions come last"


@pytest.mark.parametrize("name", sessions.BUILTIN_ORDER)
def test_every_type_records_every_ending(name):
    """The lessons of the table and handheld work: a start, a cancel, an
    idle time, a lost connection and a normal close are in every list, and a
    saved reference measurement from the maker's program."""
    d = sessions.builtin(name)
    labels = " ".join(b["label"] for b in d["blocks"])
    text = json.dumps(d).lower()
    assert any(k in labels for k in ("start", "switch-on", "connect"))
    assert "cancel" in labels
    assert "idle" in labels
    assert "close" in labels or "quit" in labels
    assert any(b.get("disconnects") or "cable" in b["label"] or "power" in b["label"]
               for b in d["blocks"])
    assert "save" in text and "send that file" in text or "send it together" in text \
        or "together with the zip" in text


def test_experience_is_honest():
    real = {d["id"] for d in sessions.all_builtin() if d["experience"] == "real"}
    assert real == {"handheld", "table"}


def test_handheld_covers_the_handheld_lessons():
    text = json.dumps(sessions.builtin("handheld")).lower()
    for word in ("lights", "ruler", "dual scan", "m1", "m2", "other end", "faster", "slowly",
                 "fail", "spot", "calibrat"):
        assert word in text, word


def test_table_covers_the_table_lessons():
    """Review M5: block by block what the reviewed i1iO 3 plan made essential."""
    d = sessions.builtin("table")
    by_label = {b["label"]: b for b in d["blocks"]}
    for label in ("warm-start", "cold-start", "calibrate", "rows-to-end",
                  "patch-by-patch-to-end", "cancel-then-quit", "force-quit-while-aiming",
                  "force-quit-during-row", "quit-while-aiming", "quit-with-arm-out",
                  "aiming-across-power-cycle", "way-home"):
        assert by_label[label]["priority"] == "essential", label
    assert by_label["way-home"]["repeatable"] and by_label["patch-length"]["repeatable"]
    assert "five patch sizes" in json.dumps(by_label["patch-length"])
    # the quit with the arm out happens INSIDE the recording (it was before the start in 2.0)
    steps = by_label["quit-with-arm-out"]["steps"]
    assert steps[0] == "Start this block." and "quit the program" in steps[2]
    text = json.dumps(d).lower()
    assert "the maker's manual wins" in text
    assert by_label["hand-extras"]["priority"] == "nice to have"
    assert by_label["long-idle"]["timer_minutes"] == 10


def test_generated_pages_match_the_session_files():
    for rel, text in sessions.generated_files(ROOT).items():
        path = os.path.join(ROOT, rel)
        assert os.path.isfile(path), f"{rel} is missing: run tools/make_scenarios.py"
        with open(path, encoding="utf-8") as fh:
            assert fh.read() == text, f"{rel} differs: run tools/make_scenarios.py"


def test_validate_finds_problems():
    bad = {"format": "x", "id": "a", "title": "t", "blocks": [
        {"id": "A", "label": "Bad Label", "title": "t", "priority": "urgent", "minutes": 0,
         "kind": "record", "steps": ["one " + chr(0x2014) + " two"], "why": "w"},
        {"id": "A", "label": "ok", "title": "t", "priority": "essential", "minutes": 1,
         "kind": "dance", "steps": ["s"], "why": "w"}]}
    problems = " ".join(sessions.validate(bad))
    for needle in ("format", "priority", "small letters", "minutes", "used twice", "kind",
                   "em dash"):
        assert needle in problems, needle


def test_progress_line():
    d = sessions.builtin("handheld")
    line = sessions.progress_line(d, {"H01", "H02"}, 3)
    assert line == f"Block 4 of {len(d['blocks'])} (essential). Essential blocks done: 2 of " \
        f"{len(sessions.essential(d))}."
    all_ess = {b["id"] for b in sessions.essential(d)}
    assert "All essential blocks done" in sessions.progress_line(d, all_ess, 16)


def test_no_em_dash_anywhere_user_facing():
    for folder in ("chromiq_probe", "chromiq_probe/sessions", "docs", "docs/scenarios", "."):
        base = os.path.join(ROOT, folder)
        for name in os.listdir(base):
            if name.endswith((".py", ".json", ".md", ".txt", ".bat", ".command", ".sh")):
                with open(os.path.join(base, name), encoding="utf-8") as fh:
                    assert chr(0x2014) not in fh.read(), name

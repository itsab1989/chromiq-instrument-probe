#!/usr/bin/env python3
"""Write SCENARIOS.md and docs/scenarios/<type>.md from the session files.

Run it after editing chromiq_probe/sessions/*.json:

    python3 tools/make_scenarios.py

tests/test_sessions.py fails when the pages and the session files differ.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from chromiq_probe.sessions import generated_files  # noqa: E402


def main() -> int:
    for rel, text in generated_files(ROOT).items():
        path = os.path.join(ROOT, rel)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        print("wrote", rel)
    return 0


if __name__ == "__main__":
    sys.exit(main())

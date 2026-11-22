#!/usr/bin/env python3
"""ChromIQ instrument probe: start here.

A read-only recorder for colour measuring instruments (handheld, tables,
sheet-fed readers, network and serial instruments). Run it while you use the
maker's own program; it never sends anything to any device and uploads
nothing. See README.md. Needs Python 3.8 or newer and nothing else.
"""

import os
import sys

if sys.version_info < (3, 8):
    sys.exit("This tool needs Python 3.8 or newer.")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from chromiq_probe.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())

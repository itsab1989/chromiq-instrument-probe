"""ChromIQ instrument probe: a read-only recorder for colour measuring instruments.

It listens while the maker's own program talks to the instrument, keeps only
that instrument's traffic, hides private details, and writes one zip the
owner can check and send. It never sends anything to any device and never
uploads anything. Standard library only, Python 3.8 or newer.
"""

VERSION = "2.0.0"

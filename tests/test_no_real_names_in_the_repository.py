"""A guard: no tracked file may contain this computer's user name or host
names. They are read at test time, compared case-insensitively, and never
printed (a failure names only the file). Generic names (a CI runner's
"runner", "root", a host called "Mac" ...) are skipped."""

import getpass
import os
import platform
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERIC = {"user", "users", "runner", "root", "admin", "administrator", "test", "tester",
           "ci", "build", "mac", "macbook", "localhost", "pc", "desktop", "laptop", "ubuntu",
           "windows", "home", "guest", "vagrant", "docker", "mira", "jdoe"}


def _names() -> list:
    names = set()
    try:
        names.add(getpass.getuser())
    except Exception:                                     # noqa: BLE001
        pass
    node = platform.node()
    names |= {node, node.split(".")[0]}
    if platform.system() == "Darwin" and os.path.exists("/usr/sbin/scutil"):
        for field in ("ComputerName", "LocalHostName"):
            try:
                out = subprocess.run(["/usr/sbin/scutil", "--get", field],
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     timeout=5).stdout.decode("utf-8", "replace").strip()
            except (OSError, subprocess.TimeoutExpired):
                out = ""
            names.add(out)
    return [n for n in names if n and len(n) >= 4 and n.lower() not in GENERIC]


def _tracked() -> list:
    try:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return []
    if out.returncode != 0:
        return []
    return [p for p in out.stdout.decode("utf-8", "replace").split("\0") if p]


def test_no_tracked_file_holds_this_computers_names():
    files = _tracked()
    if not files:
        pytest.skip("not a git checkout")
    names = [n.lower().encode("utf-8") for n in _names()]
    if not names:
        pytest.skip("only generic names on this computer")
    hits = []
    for rel in files:
        try:
            with open(os.path.join(ROOT, rel), "rb") as fh:
                blob = fh.read().lower()
        except OSError:
            continue
        if any(n in blob for n in names):
            hits.append(rel)
    assert not hits, "these files hold this computer's user or host name: " + ", ".join(hits)

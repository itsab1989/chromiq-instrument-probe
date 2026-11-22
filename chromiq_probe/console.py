"""The console: questions, keys thrown away, and the Windows QuickEdit fix.

Ported from the ChromIQ X-Rite probe 1.6.6: `flush_pending_input` (1.5.5: a
tester pressed Enter several times while the tool was busy, and the extra
Enters started and stopped the next steps at once) and `quick_edit_off`
(1.5.5 review: a click into a classic Windows console starts a selection and
the next Enter only ends it). A recording stops only with a deliberate
"e" and Enter, never with a bare Enter.
"""

from __future__ import annotations

import os
import sys
import textwrap


def _isatty(stream) -> bool:
    try:
        return stream.isatty()
    except (AttributeError, ValueError):
        return False


def flush_pending_input() -> int:
    dropped = 0
    try:
        if os.name == "nt":
            import msvcrt                                 # noqa: PLC0415
            while msvcrt.kbhit():                         # type: ignore[attr-defined]
                msvcrt.getwch()                           # type: ignore[attr-defined]
                dropped += 1
        elif _isatty(sys.stdin):
            import termios                                # noqa: PLC0415
            termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
    except Exception:                                     # noqa: BLE001
        pass
    return dropped


def quick_edit_off():
    if os.name != "nt":
        return lambda: None
    try:
        import ctypes                                     # noqa: PLC0415
        from ctypes import wintypes                       # noqa: PLC0415
        k32 = ctypes.windll.kernel32                      # type: ignore[attr-defined]
        k32.GetStdHandle.restype = wintypes.HANDLE
        handle = k32.GetStdHandle(-10)
        mode = wintypes.DWORD()
        if not k32.GetConsoleMode(handle, ctypes.byref(mode)):
            return lambda: None
        old = mode.value
        new = (old | 0x0080) & ~0x0040
        if new == old or not k32.SetConsoleMode(handle, new):
            return lambda: None
        return lambda: k32.SetConsoleMode(handle, old)
    except Exception:                                     # noqa: BLE001
        return lambda: None


class StopSession(Exception):
    """Ctrl-C or a closed window: end the session with what is finished."""


class Console:
    """The real console."""

    width = 76

    def say(self, text: str = "") -> None:
        for para in text.split("\n"):
            if not para.strip():
                print()
                continue
            indent = len(para) - len(para.lstrip())
            sub = indent + (3 if para.lstrip()[:3].rstrip(".").isdigit() else 0)
            print(textwrap.fill(para.strip(), self.width, initial_indent=" " * indent,
                                subsequent_indent=" " * sub))

    def ask(self, prompt: str, flush: bool = True) -> str:
        if flush:
            flush_pending_input()
        try:
            return input(prompt)
        except EOFError:
            raise StopSession("the input was closed") from None
        except KeyboardInterrupt:
            raise StopSession("Ctrl-C") from None


class Scripted:
    """For tests: answers from a list, everything said kept in .out."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.out: list = []

    def say(self, text: str = "") -> None:
        self.out.append(text)

    def ask(self, prompt: str, flush: bool = True) -> str:
        self.out.append(prompt)
        if not self.answers:
            raise StopSession("no more answers")
        a = self.answers.pop(0)
        if callable(a):
            return a()
        return a

    def text(self) -> str:
        return "\n".join(self.out)

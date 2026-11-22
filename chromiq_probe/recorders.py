"""Recorder wrappers, one per system and transport. NOT YET RUN ON REAL HARDWARE:
each is tested against fake recorder programs only.

Ported from the ChromIQ X-Rite probe 1.6.6 (same author, MIT): `_ProcRecorder`
(one recording program per interface per block, every start written down,
the log of the program's own words, the job object that ends the recorder
with this tool on Windows), `UsbPcapRecorder` (USBPcapCMD creates its OWN
file: it opens it CREATE_NEW and fails if it exists, X-Rite probe 1.5.4) and
`TcpdumpRecorder` (sudo once, a keep-alive for sudo's timestamp, XHC
interfaces brought up and down again on a Mac). New: `PktmonRecorder` for
network recordings on Windows.

Every recorder only LISTENS. None of them can send anything to a device.
"""

from __future__ import annotations

import glob
import os
import platform
import re
import signal
import subprocess
import sys
import threading
import time

RECORDER_STARTUP_WAIT = 2.0
MAX_BLOCK_MB = 4096           # a block stops before its recording passes this size
MAX_BLOCK_MINUTES = 240       # ... or this time


def system32(name: str) -> str:
    """An absolute path in Windows' own folder: never a program of the same name
    in the current folder or on PATH (the tool may run as administrator)."""
    root = os.environ.get("SystemRoot") or r"C:\Windows"
    return os.path.join(root, "System32", name)


def system_tool(candidates) -> str | None:
    """The first of `candidates` (absolute system paths) that exists and that
    only root can change. Never found through PATH: these run as root."""
    for c in candidates:
        try:
            st = os.stat(c)
        except OSError:
            continue
        if os.name != "nt" and (st.st_uid != 0 or st.st_mode & 0o022):
            continue
        return c
    return None


SUDO = ["/usr/bin/sudo"]
TCPDUMP = ["/usr/sbin/tcpdump", "/usr/bin/tcpdump", "/sbin/tcpdump"]
IFCONFIG = ["/sbin/ifconfig", "/usr/sbin/ifconfig"]


def private_root() -> str:
    """This user's own folder for full recordings and markers: 0700 under the
    home folder; on Windows under %LOCALAPPDATA% (inside the user's profile,
    which Windows gives only to the user, SYSTEM and administrators)."""
    if os.environ.get("CHROMIQ_PROBE_HOME"):
        path = os.environ["CHROMIQ_PROBE_HOME"]
    elif os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        path = os.path.join(base, "ChromIQ-probe")
    else:
        path = os.path.join(os.path.expanduser("~"), ".chromiq-probe")
    os.makedirs(path, mode=0o700, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    return path


def restrict_to_user(path: str) -> bool:
    """Windows: remove inherited rights and give the folder to this user only
    (and SYSTEM, which can read everything anyway). Our own folder only.
    Returns False when that could not be done (review 2, S-m4): the caller then
    refuses to record into it."""
    if os.name != "nt":
        return True
    user = os.environ.get("USERNAME")
    icacls = system32("icacls.exe")
    if not user or not os.path.exists(icacls):
        return False
    try:
        p = subprocess.run([icacls, path, "/inheritance:r", "/grant:r", f"{user}:(OI)(CI)F",
                            "/grant:r", "SYSTEM:(OI)(CI)F"], stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return p.returncode == 0


def free_space_ok(folder: str, need_mb: int) -> bool:
    try:
        import shutil as _sh                              # noqa: PLC0415
        return _sh.disk_usage(folder).free >= need_mb * 1024 * 1024
    except OSError:
        return True


def pid_alive(pid: int) -> bool:
    if not pid or pid == os.getpid():
        return False
    if os.name == "nt":
        try:
            import ctypes                                 # noqa: PLC0415
            k32 = ctypes.windll.kernel32                  # type: ignore[attr-defined]
            h = k32.OpenProcess(0x1000, False, pid)       # QUERY_LIMITED_INFORMATION
            if not h:
                return False
            code = ctypes.c_ulong()
            k32.GetExitCodeProcess(h, ctypes.byref(code))
            k32.CloseHandle(h)
            return code.value == 259                      # STILL_ACTIVE
        except Exception:                                 # noqa: BLE001
            return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


# ---- markers: what this tool left running, so the next start can stop it --

def marker_path(name: str) -> str:
    return os.path.join(private_root(), f"running-{name}.json")


def write_marker(name: str, info: dict) -> None:
    import json                                           # noqa: PLC0415
    path = marker_path(name)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(dict(info, pid=os.getpid(), started=time.time()), fh)


def read_marker(name: str):
    import json                                           # noqa: PLC0415
    try:
        with open(marker_path(name), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def clear_marker(name: str) -> None:
    try:
        os.remove(marker_path(name))
    except OSError:
        pass


_EMERGENCY: list = []


def _emergency_stop() -> None:
    for fn in list(_EMERGENCY):
        try:
            fn()
        except Exception:                                 # noqa: BLE001
            pass


def install_emergency_stop(fn) -> None:
    """Run fn when the tool ends in any way Python can see: normal exit,
    an exception, and on Windows a closed console window, a log-off or a
    shut-down (SetConsoleCtrlHandler). A killed process or a power cut
    cannot be caught: the markers let the next start find what is left."""
    import atexit                                         # noqa: PLC0415
    if not _EMERGENCY:
        atexit.register(_emergency_stop)
        if os.name == "nt":
            try:
                import ctypes                             # noqa: PLC0415
                handler_type = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_uint)

                def handler(event):
                    if event in (2, 5, 6):                # CLOSE, LOGOFF, SHUTDOWN
                        _emergency_stop()
                    return 0
                _EMERGENCY_HANDLER.append(handler_type(handler))
                ctypes.windll.kernel32.SetConsoleCtrlHandler(  # type: ignore[attr-defined]
                    _EMERGENCY_HANDLER[0], 1)
            except Exception:                             # noqa: BLE001
                pass
    _EMERGENCY.append(fn)


def remove_emergency_stop(fn) -> None:
    if fn in _EMERGENCY:
        _EMERGENCY.remove(fn)


_EMERGENCY_HANDLER: list = []

USBPCAP_PLACES = [
    r"C:\Program Files\USBPcap\USBPcapCMD.exe",
    r"C:\Program Files\Wireshark\extcap\USBPcapCMD.exe",
    r"C:\Program Files\Wireshark\extcap\wireshark\USBPcapCMD.exe",
]
_EXTCAP_IFACE_RE = re.compile(r"^interface \{value=([^}]*)\}\{display=([^}]*)\}", re.M)


class RecorderError(Exception):
    pass


_JOB: list = []


def _kill_with_us(proc) -> None:
    """Windows: a job object that ends the recorder when this tool ends,
    also when its window is closed (X-Rite probe 1.5.4 review)."""
    if os.name != "nt":
        return
    try:
        import ctypes                                     # noqa: PLC0415
        from ctypes import wintypes                       # noqa: PLC0415
        k32 = ctypes.windll.kernel32                      # type: ignore[attr-defined]
        k32.CreateJobObjectW.restype = wintypes.HANDLE
        k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                                ctypes.c_void_p, wintypes.DWORD]
        k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        if not _JOB:
            job = k32.CreateJobObjectW(None, None)
            if not job:
                return

            class _Basic(ctypes.Structure):
                _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                            ("PerJobUserTimeLimit", ctypes.c_int64),
                            ("LimitFlags", wintypes.DWORD),
                            ("MinimumWorkingSetSize", ctypes.c_size_t),
                            ("MaximumWorkingSetSize", ctypes.c_size_t),
                            ("ActiveProcessLimit", wintypes.DWORD),
                            ("Affinity", ctypes.c_size_t),
                            ("PriorityClass", wintypes.DWORD),
                            ("SchedulingClass", wintypes.DWORD)]

            class _Io(ctypes.Structure):
                _fields_ = [(n, ctypes.c_uint64) for n in ("r", "w", "o", "rb", "wb", "ob")]

            class _Ext(ctypes.Structure):
                _fields_ = [("Basic", _Basic), ("Io", _Io),
                            ("ProcessMemoryLimit", ctypes.c_size_t),
                            ("JobMemoryLimit", ctypes.c_size_t),
                            ("PeakProcessMemoryUsed", ctypes.c_size_t),
                            ("PeakJobMemoryUsed", ctypes.c_size_t)]
            info = _Ext()
            info.Basic.LimitFlags = 0x2000                # KILL_ON_JOB_CLOSE
            if not k32.SetInformationJobObject(job, 9, ctypes.byref(info),
                                               ctypes.sizeof(info)):
                k32.CloseHandle(job)
                return
            _JOB.append(job)
        k32.AssignProcessToJobObject(_JOB[0], int(proc._handle))  # noqa: SLF001
    except Exception:                                     # noqa: BLE001
        pass


def _base(exe: str) -> list:
    # a ".py" stand-in (the tests' fake recorders) runs with this Python
    return [sys.executable, exe] if exe.lower().endswith(".py") else [exe]


class _ProcRecorder:
    """One recording program per interface per block (ported)."""

    label = "recorder"
    precreate = True        # tcpdump: create the file first, so it stays ours, not root's
    stop_hard = False
    startup_wait = RECORDER_STARTUP_WAIT
    transport = "usb"

    def __init__(self, interfaces: list, outdir: str):
        self.interfaces = list(interfaces)
        self.outdir = outdir
        self.procs: dict = {}
        self.files: dict = {}
        self.notes: list = []
        self.diag: list = []
        self.logs: list = []
        self.started_at = 0.0
        self.last_exit: list = []

    def command(self, iface, path) -> list:
        raise NotImplementedError

    def retry_command(self, iface, path, err):
        return None

    def iface_label(self, iface) -> str:
        return re.sub(r"[^A-Za-z0-9]+", "", str(iface)) or "bus"

    def session_start(self) -> bool:
        return True

    def session_end(self) -> None:
        pass

    def _popen(self, cmd, log_path=None):
        log = open(log_path, "wb") if log_path else subprocess.DEVNULL
        kwargs = {"stdin": subprocess.DEVNULL, "stdout": log,
                  "stderr": subprocess.STDOUT if log_path else subprocess.DEVNULL}
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        try:
            proc = subprocess.Popen(cmd, **kwargs)
        finally:
            if log_path:
                log.close()
        _kill_with_us(proc)
        return proc

    @staticmethod
    def _read_log(path) -> str:
        try:
            with open(path, "rb") as fh:
                return fh.read(4000).decode("utf-8", "replace").strip()
        except OSError:
            return ""

    def _prepare(self, path) -> None:
        if os.path.exists(path):
            os.remove(path)
        if self.precreate:            # ours, readable only by this user (review 2, S-m8)
            os.close(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))

    def _launch(self, iface, cmd, path, attempt: str) -> dict:
        entry = {"interface": str(iface), "attempt": attempt, "command": " ".join(cmd),
                 "file": os.path.basename(path)}
        self.diag.append(entry)
        log_path = path + "." + attempt.split()[0] + ".log"
        old_mask = os.umask(0o077)
        try:
            self._prepare(path)
            self.procs[iface] = self._popen(cmd, log_path)
            self.logs.append(log_path)
        except OSError as exc:
            entry["result"] = f"could not be started: {exc}"
            self.notes.append(f"{iface}: could not start ({exc})")
            return entry
        finally:
            os.umask(old_mask)
        time.sleep(self.startup_wait)
        proc = self.procs[iface]
        if proc.poll() is None:
            entry["result"] = "running"
            return entry
        out = self._read_log(log_path)
        entry["result"] = f"stopped at once, exit code {proc.returncode}"
        entry["output"] = out or "(nothing)"
        self.notes.append(f"{iface}: stopped at once (exit code {proc.returncode})"
                          + (": " + " ".join(out.split())[:200] if out else ""))
        return entry

    def start(self, stem: str) -> list:
        """Start recording; returns the interfaces that really record."""
        self.procs, self.files = {}, {}
        self.started_at = time.time()
        live = []
        for iface in self.interfaces:
            path = os.path.join(self.outdir, f"{stem}-{self.iface_label(iface)}-full.pcap")
            self.files[iface] = path
            entry = self._launch(iface, self.command(iface, path), path, "first try")
            if entry.get("result") == "running":
                live.append(iface)
                continue
            retry = self.retry_command(iface, path, entry.get("output", ""))
            if retry:
                entry = self._launch(iface, retry, path, "retry (simpler options)")
                if entry.get("result") == "running":
                    live.append(iface)
        for iface in list(self.files):
            if iface not in self.procs:
                self.files.pop(iface)
        return live

    def stop(self) -> list:
        """Stop every recorder; returns the files that exist and hold data."""
        for _iface, proc in self.procs.items():
            if proc.poll() is not None:
                continue
            try:
                if os.name == "nt" and self.stop_hard:
                    proc.terminate()
                    proc.wait(timeout=6)
                elif os.name == "nt":
                    try:
                        proc.send_signal(signal.CTRL_BREAK_EVENT)   # type: ignore[attr-defined]
                        proc.wait(timeout=4)
                    except (subprocess.TimeoutExpired, OSError, ValueError, AttributeError):
                        proc.terminate()
                        proc.wait(timeout=6)
                else:
                    proc.terminate()
                    proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                    proc.wait(timeout=5)
                except (OSError, subprocess.TimeoutExpired):
                    pass
            except OSError:
                pass
        for path in self.logs:
            try:
                os.remove(path)
            except OSError:
                pass
        self.logs = []
        self.last_exit = [p.returncode for p in self.procs.values()]
        for path in self.files.values():
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
        files = []
        for path in self.files.values():
            if os.path.exists(path) and os.path.getsize(path) > 0:
                files.append(path)
            elif os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
        self.procs, self.files = {}, {}
        return files

    def alive(self) -> bool:
        return all(p.poll() is None for p in self.procs.values()) if self.procs else True

    def exit_codes(self) -> list:
        return [p.returncode for p in self.procs.values() if p.poll() is not None]

    def over_limit(self) -> str:
        total = 0
        for f in self.files.values():
            try:
                total += os.path.getsize(f)
            except OSError:
                pass
        if total > MAX_BLOCK_MB * 1024 * 1024:
            return f"{MAX_BLOCK_MB} MB"
        if self.started_at and time.time() - self.started_at > MAX_BLOCK_MINUTES * 60:
            return f"{MAX_BLOCK_MINUTES} minutes"
        return ""

    def stop_early(self) -> None:
        for p in self.procs.values():
            if p.poll() is None:
                try:
                    p.terminate()
                except OSError:
                    pass

    def diag_text(self) -> str:
        lines = []
        for e in self.diag:
            lines.append(f"{e['interface']} ({e['attempt']}): {e.get('result', '?')}")
            lines.append(f"    command: {e['command']}")
            if "output" in e:
                lines.append("    what the program said: "
                             + " | ".join(x.strip() for x in e["output"].splitlines() if x.strip()))
        return "\n".join(lines)


class UsbPcapRecorder(_ProcRecorder):
    """Windows: USBPcapCMD, one per root hub, with the device descriptions."""

    label = "USBPcap (USBPcapCMD)"
    precreate = False
    stop_hard = True

    def __init__(self, exe: str, interfaces: list, outdir: str):
        super().__init__(interfaces, outdir)
        self.exe = exe

    def command(self, iface, path):
        return _base(self.exe) + ["-d", iface, "-o", path, "-A", "--inject-descriptors"]

    def retry_command(self, iface, path, err):
        return _base(self.exe) + ["-d", iface, "-o", path, "-A"]

    def iface_label(self, iface):
        return str(iface).replace("\\\\.\\", "").replace("\\", "").replace(".", "") or "USBPcap"

    def start(self, stem: str) -> list:
        if not self.interfaces:
            self.notes.append("USBPcap lists no USB hubs yet. That usually means Windows has not "
                              "been restarted since USBPcap was installed: please restart "
                              "Windows with Restart (not Shut down) and start the tool again.")
            return []
        return super().start(stem)


class TcpdumpRecorder(_ProcRecorder):
    """macOS (XHC interfaces with SIP off; or a network interface) and Linux
    (usbmon or a network interface), through sudo. `bpf` narrows a network
    recording to the instrument already while recording (the tool's own
    filter is still the one that decides what is kept)."""

    label = "tcpdump"

    def __init__(self, interfaces: list, outdir: str, mac_usb: bool = False, bpf: str = "",
                 sudo: str | None = "auto", tcpdump: str | None = None):
        super().__init__(interfaces, outdir)
        self.mac_usb = mac_usb
        self.bpf = bpf
        # absolute system paths only: these run as root (review M8)
        self.sudo = system_tool(SUDO) if sudo == "auto" else sudo
        self.tcpdump = tcpdump or system_tool(TCPDUMP)
        self.ifconfig = system_tool(IFCONFIG) or "/sbin/ifconfig"
        self.user = _user_name()
        self.brought_up: list = []
        self.stop_keepalive = threading.Event()
        self.transport = "usb" if (mac_usb or any(str(i).startswith("usbmon")
                                                  for i in interfaces)) else "net"

    def _prefix(self) -> list:
        return [self.sudo, "-n"] if self.sudo else []

    def session_start(self) -> bool:
        if self.sudo is None:
            return True
        if not self.sudo:
            self.notes.append("sudo not found")
            return False
        if not self.tcpdump:
            self.notes.append("tcpdump was not found in the system's own folders "
                              "(/usr/sbin, /usr/bin, /sbin), owned by root")
            return False
        print("\n  Your computer will now ask for your password, for its own \"sudo\" command.")
        print("  It is needed because only an administrator may listen to "
              + ("USB" if self.transport == "usb" else "the network") + ".")
        print("  These, and only these, run with administrator rights:")
        print(f"    {self.tcpdump} (it listens; with -Z {self.user} it gives up the rights")
        print("      right after opening the interface and writes the file as you)")
        if self.mac_usb:
            print(f"    {self.ifconfig} XHC... up / down (the Mac's USB recording interfaces)")
        print("  This tool never sees or stores the password.")
        try:
            if subprocess.call([self.sudo, "-v"]) != 0:
                return False
        except KeyboardInterrupt:
            return False

        def keepalive():
            while not self.stop_keepalive.wait(50):
                subprocess.call([self.sudo, "-n", "true"], stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        threading.Thread(target=keepalive, daemon=True).start()
        install_emergency_stop(self._emergency)
        if self.mac_usb:
            for iface in self.interfaces:
                if not _iface_is_up(self.ifconfig, iface):
                    if subprocess.call(self._prefix() + [self.ifconfig, iface, "up"],
                                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL) == 0:
                        self.brought_up.append(iface)
            write_marker("xhc", {"interfaces": self.brought_up})
        return True

    def _emergency(self) -> None:
        self.stop_early()
        self.session_end()

    def session_end(self) -> None:
        for iface in self.brought_up:
            subprocess.call(self._prefix() + [self.ifconfig, iface, "down"],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
        if self.brought_up:
            print(f"  Switched the USB recording interfaces {', '.join(self.brought_up)} "
                  "off again.")
        self.brought_up = []
        clear_marker("xhc")
        self.stop_keepalive.set()
        if self.sudo:
            subprocess.call([self.sudo, "-k"], stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        remove_emergency_stop(self._emergency)

    def command(self, iface, path):
        cmd = self._prefix() + _base(self.tcpdump) + ["-U", "-s", "0", "-i", str(iface)]
        if self.sudo and self.user:
            cmd += ["-Z", self.user]
        cmd += ["-w", path]
        if self.bpf:
            cmd += [self.bpf]
        return cmd


def _user_name() -> str:
    try:
        import getpass                                    # noqa: PLC0415
        return getpass.getuser()
    except Exception:                                     # noqa: BLE001
        return ""


class PktmonRecorder:
    """Windows 10 version 2004 or newer, also on ARM: the built-in pktmon.

    It runs as a SYSTEM-WIDE session that outlives this tool if nobody stops
    it, so (review B3):
      * a marker file (running-pktmon.json in the user's private folder) is
        written BEFORE `pktmon start` and removed after `pktmon stop`; the next
        start that finds pktmon running AND the marker knows it is its own
        leftover and offers to stop it (the owner says yes; the command is shown);
      * the tool stops it when it ends in any way Python can see, including a
        closed console window (install_emergency_stop);
      * the recording is CIRCULAR with a fixed size (--file-size), so even a
        forgotten session can never fill the disk; the watchdog ends the block
        before the file starts to overwrite itself, and after a time limit.
    The tool adds NO pktmon capture filter: filters are system-wide and can
    only be removed all at once. The tool's own filter keeps only the
    instrument's traffic afterwards."""

    label = "pktmon (built into Windows)"
    transport = "net"
    STOP_BY_HAND = "pktmon stop"

    def __init__(self, outdir: str, exe: str | None = None, runner=None,
                 max_mb: int = MAX_BLOCK_MB, max_minutes: int = MAX_BLOCK_MINUTES):
        self.outdir = outdir
        self.exe = exe or system32("pktmon.exe")
        self.runner = runner or self._run
        self.notes: list = []
        self.diag: list = []
        self.stem = None
        self.interfaces = ["nics"]
        self.running = False
        self.started_at = 0.0
        self.max_mb, self.max_minutes = max_mb, max_minutes
        self._status_at, self._alive = 0.0, True
        self.files = {}

    def _run(self, args: list) -> tuple:
        try:
            p = subprocess.run(_base(self.exe) + args, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
            return p.returncode, p.stdout.decode("utf-8", "replace")
        except (OSError, subprocess.TimeoutExpired) as exc:
            return -1, str(exc)

    @staticmethod
    def _is_running(code, out) -> bool:
        return code == 0 and bool(re.search(r"(?i)\b(running|logging)\b", out)) and \
            not re.search(r"(?i)not running", out)

    def leftover(self):
        """The marker of this tool's own earlier recording if pktmon is still
        running; None otherwise. "certain" says whether pktmon's own status names
        the marker's file (after a power cut a stale marker could otherwise label
        someone else's recording as ours: review 2, S-m6)."""
        code, out = self.runner(["status"])
        if not self._is_running(code, out):
            clear_marker("pktmon")
            return None
        m = read_marker("pktmon")
        if not m:
            return {}
        m["certain"] = bool(m.get("etl")) and os.path.basename(m["etl"]).lower() in out.lower()
        return m

    def stop_leftover(self) -> bool:
        code, out = self.runner(["stop"])
        self.diag.append({"command": "pktmon stop (an earlier run's recording)",
                          "result": out.strip()[:300]})
        info = read_marker("pktmon") or {}
        clear_marker("pktmon")
        for etl in glob.glob(os.path.join(info.get("dir", "-"), "*-full*.etl")):
            try:
                os.remove(etl)
            except OSError:
                pass
        return code == 0

    def session_start(self) -> bool:
        code, out = self.runner(["status"])
        self.diag.append({"command": "pktmon status", "result": out.strip()[:300]})
        if self._is_running(code, out):
            mine = read_marker("pktmon") is not None
            self.notes.append(
                ("a recording this tool started earlier is still running" if mine else
                 "another pktmon recording is running, and this tool does not stop other "
                 "people's recordings")
                + ". To stop it yourself: open Command Prompt as administrator and type  "
                + self.STOP_BY_HAND)
            return False
        code, out = self.runner(["filter", "list"])
        if code == 0 and re.search(r"(?i)\b(ip|mac|port|filter)\b.*\d", out) and \
                not re.search(r"(?i)no filters", out):
            self.notes.append("pktmon has capture filters set by someone else; they may hide "
                              "the instrument's traffic. This tool leaves them as they are.")
        install_emergency_stop(self._emergency)
        return True

    def _emergency(self) -> None:
        if self.running:
            self.runner(["stop"])
            self.running = False
            clear_marker("pktmon")

    def session_end(self) -> None:
        if self.running:
            self.stop()
        remove_emergency_stop(self._emergency)

    def _etl(self):
        return os.path.join(self.outdir, f"{self.stem}-full.etl")

    def start(self, stem: str) -> list:
        self.stem = stem
        etl = self._etl()
        write_marker("pktmon", {"etl": etl, "dir": self.outdir})
        args = ["start", "--capture", "--comp", "nics", "--pkt-size", "0", "--file-name", etl,
                "--file-size", str(self.max_mb), "--log-mode", "circular"]
        code, out = self.runner(args)
        self.diag.append({"command": "pktmon " + " ".join(args), "result": out.strip()[:300]})
        if code != 0:
            clear_marker("pktmon")
            self.notes.append(f"pktmon could not start (code {code}): {' '.join(out.split())[:200]}")
            return []
        self.running = True
        self.started_at = time.time()
        self.files = {"nics": etl}
        return ["nics"]

    def alive(self) -> bool:
        if not self.running:
            return True
        if time.time() - self._status_at > 10:
            self._status_at = time.time()
            code, out = self.runner(["status"])
            self._alive = self._is_running(code, out)
        return self._alive

    def exit_codes(self) -> list:
        return []

    def over_limit(self) -> str:
        try:
            size = os.path.getsize(self._etl())
        except OSError:
            size = 0
        if size > 0.9 * self.max_mb * 1024 * 1024:
            return f"{self.max_mb} MB"
        if self.started_at and time.time() - self.started_at > self.max_minutes * 60:
            return f"{self.max_minutes} minutes"
        return ""

    def stop_early(self) -> None:
        """At a limit: stop pktmon now (the file is converted at the block's end)."""
        if self.running:
            self.runner(["stop"])
            self.running = False
            clear_marker("pktmon")

    def stop(self) -> list:
        if self.running:
            code, out = self.runner(["stop"])
            self.diag.append({"command": "pktmon stop", "result": out.strip()[:300]})
        self.running = False
        clear_marker("pktmon")
        files = []
        base = os.path.join(self.outdir, f"{self.stem}-full")
        for etl in sorted(set(glob.glob(base + "*.etl"))):
            pcapng = etl[:-4] + ".pcapng"
            code, out = self.runner(["etl2pcap", etl, "--out", pcapng])
            self.diag.append({"command": f"pktmon etl2pcap {os.path.basename(etl)}",
                              "result": out.strip()[:300]})
            if code == 0 and os.path.exists(pcapng) and os.path.getsize(pcapng) > 0:
                files.append(pcapng)
            else:
                self.notes.append(f"pktmon could not convert {os.path.basename(etl)}")
            try:
                os.remove(etl)          # it holds all of this computer's traffic
            except OSError:
                pass
        return files

    def diag_text(self) -> str:
        return "\n".join(f"{d['command']}: {d['result']}" for d in self.diag)


class FileRecorder:
    """The import route: the owner records with his own tool (Wireshark, a
    hardware sniffer, a virtual machine's host) and gives the file to us."""

    label = "your own recording"

    def __init__(self, transport: str = "usb"):
        self.transport = transport
        self.notes: list = []
        self.interfaces = []
        self.pending: list = []

    def session_start(self) -> bool:
        return True

    def session_end(self) -> None:
        pass

    def start(self, stem: str) -> list:
        return ["manual"]

    def stop(self) -> list:
        files, self.pending = self.pending, []
        return files

    def alive(self) -> bool:
        return True

    def diag_text(self) -> str:
        return ""


# ---- what this computer can record -------------------------------------------

def _iface_is_up(ifconfig: str, iface: str) -> bool:
    try:
        out = subprocess.run([ifconfig, iface], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             timeout=10).stdout.decode("utf-8", "replace")
    except (OSError, subprocess.TimeoutExpired):
        return False
    first = out.splitlines()[0] if out else ""
    return bool(re.search(r"[<,]UP[,>]", first))


def parse_csrutil(text: str) -> str:
    """'enabled', 'disabled', 'partly' or 'unknown'."""
    t = (text or "").lower()
    if "status: disabled" in t and "enabled" not in t.split("status: disabled", 1)[1][:200]:
        return "disabled"
    if "status: enabled" in t:
        return "enabled"
    if "custom configuration" in t or "unknown (custom" in t:
        return "partly"
    return "unknown"


def mac_xhc_interfaces(ifconfig_list: str) -> list:
    return sorted(n for n in (ifconfig_list or "").split() if re.fullmatch(r"XHC\d+", n))


def find_usbpcapcmd() -> str | None:
    """Only the places USBPcap's and Wireshark's installers use (never PATH:
    it runs as administrator)."""
    for place in USBPCAP_PLACES:
        if os.path.exists(place):
            return place
    return None


def windows_is_admin() -> bool | None:
    try:
        import ctypes                                     # noqa: PLC0415
        return bool(ctypes.windll.shell32.IsUserAnAdmin())  # type: ignore[attr-defined]
    except Exception:                                     # noqa: BLE001
        return None


def is_arm(machine: str) -> bool:
    return (machine or "").lower() in ("arm64", "aarch64", "armv8", "arm")


SIP_OFF_STEPS = [
    "Apple Silicon Mac: choose Apple menu > Shut Down and wait until it is off.",
    "Press and hold the power button until \"Loading startup options\" appears.",
    "Click Options, then Continue (choose your user and type your password if asked).",
    "Choose Utilities > Terminal in the menu bar.",
    "Type  csrutil disable  and press Return (answer y if asked).",
    "Choose Apple menu > Restart.",
    "Intel Mac: instead of the first three steps, restart and hold Command and R until "
    "the Apple logo appears.",
]
SIP_ON_STEPS = [
    "Start the Mac into its startup options again, exactly as above.",
    "Open Utilities > Terminal, type  csrutil enable  and press Return (answer y if asked).",
    "Restart.",
    "Check it: open Terminal and type  csrutil status . It must say \"enabled\".",
    "Apple Silicon: switching SIP off can also lower the Mac's startup security. To be sure "
    "it is back to \"Full Security\": start into the startup options again, choose "
    "Utilities > Startup Security Utility, select the disk and choose Full Security "
    "(not yet checked by us on a real Mac).",
]


def readiness(transport: str, system: str | None = None, machine: str | None = None,
              facts: dict | None = None) -> dict:
    """Can this computer record this transport, and with what? Pure function of
    `facts` (filled from the system when None), so it is tested on every system.

    Returns {"can": bool, "kind": recorder kind, "lines": [plain sentences],
    "options": [other ways], "admin": reason line or ""}."""
    system = system or platform.system()
    machine = machine or platform.machine()
    facts = facts if facts is not None else gather_facts(transport, system)
    lines, options = [], []
    if transport == "net":
        if system == "Windows":
            if facts.get("pktmon"):
                return {"can": True, "kind": "pktmon", "lines": [
                    "Windows' own network recorder (pktmon) is there. Nothing has to be "
                    "installed."], "options": [], "admin": (
                    "Recording needs administrator rights, because Windows lets only an "
                    "administrator listen to the network. Right-click the tool and choose "
                    "\"Run as administrator\".") if facts.get("admin") is False else ""}
            return {"can": False, "kind": None, "lines": [
                "This Windows has no pktmon (it came with Windows 10 version 2004, 2020)."],
                "options": ["Update Windows, or record with Wireshark yourself and give the "
                            "file to this tool (see \"Your own recording\" in the README)."],
                "admin": ""}
        if facts.get("tcpdump"):
            return {"can": True, "kind": "tcpdump-net", "lines": [
                "The system's own tcpdump is there. Nothing has to be installed."
                + (" No change to System Integrity Protection is needed for the network."
                   if system == "Darwin" else "")], "options": [],
                "admin": "Recording needs your administrator password (sudo), because only "
                         "an administrator may listen to the network."}
        return {"can": False, "kind": None, "lines": ["tcpdump was not found."],
                "options": ["Linux: install tcpdump with your package manager."], "admin": ""}
    # USB
    if system == "Windows":
        if is_arm(machine):
            return {"can": False, "kind": None, "lines": [
                "This is Windows on ARM (for example a Windows virtual machine on an Apple "
                "Silicon Mac). The USB recorder, USBPcap, has no driver for it, and Windows "
                "never runs drivers for other processors."], "options": [
                "A Windows PC with an Intel or AMD processor.",
                "A Linux PC that runs Windows in a virtual machine with the instrument passed "
                "through to it: record on the Linux side.",
                "A hardware USB sniffer between the computer and the instrument "
                "(record with its own program and give the file to this tool)."], "admin": ""}
        if not facts.get("usbpcap"):
            return {"can": False, "kind": None, "lines": [
                "USBPcap, the free USB recorder for Windows, is not installed."], "options": [
                "Install Wireshark from wireshark.org and tick \"Install USBPcap\" on its "
                "\"USB Capture\" page (not ticked by default), then restart Windows and start "
                "this tool again. USBPcap installs a system driver; it is free and open "
                "source, made by its own author, not by us."], "admin": ""}
        return {"can": True, "kind": "usbpcap", "lines": [
            "USBPcap is installed."], "options": [], "admin": (
            "Recording needs administrator rights, because USBPcap lets only an administrator "
            "listen to USB. Right-click the tool and choose \"Run as administrator\".")
            if facts.get("admin") is False else ""}
    if system == "Darwin":
        sip = facts.get("sip", "unknown")
        if sip != "disabled":
            return {"can": False, "kind": None, "lines": [
                "On a Mac, USB can only be recorded while System Integrity Protection (SIP) "
                f"is fully switched off. Here it is {sip}. This tool never changes it.",
                "There is no other software way on a Mac that we know of."], "options": [
                "A Windows PC with an Intel or AMD processor (the easiest way).",
                "Switch SIP off only for the recording and on again straight after: the "
                "README's section \"USB on a Mac\" has the steps and the honest risk.",
                "A hardware USB sniffer."], "admin": ""}
        if not facts.get("xhc"):
            return {"can": False, "kind": None, "lines": [
                "SIP is off, but macOS shows no USB recording interfaces (XHC...). One report "
                "says this happens on macOS 15.6 and newer even with SIP off."], "options": [
                "A Windows PC with an Intel or AMD processor."], "admin": ""}
        return {"can": True, "kind": "tcpdump-usb", "lines": [
            f"SIP is off and the USB recording interfaces are there ({', '.join(facts['xhc'])}).",
            "One report saw recordings in which every data byte was zero on an Apple Silicon "
            "Mac; the tool checks every recording for that."], "options": [],
            "admin": "Recording needs your administrator password (sudo), to switch the USB "
                     "recording interfaces on and off and to listen to them."}
    if system == "Linux":
        if not facts.get("tcpdump"):
            return {"can": False, "kind": None, "lines": ["tcpdump was not found."],
                    "options": ["Install tcpdump with your package manager."], "admin": ""}
        if not facts.get("usbmon"):
            return {"can": False, "kind": None, "lines": [
                "Linux's USB recorder (the usbmon module) is not loaded."], "options": [
                "Load it with  sudo modprobe usbmon  (it only lets the system listen; it is "
                "gone again after a restart), then start the tool again."], "admin": ""}
        return {"can": True, "kind": "tcpdump-usbmon", "lines": [
            "usbmon interfaces: " + ", ".join(facts.get("usbmon") or []),
            "Note: Debian and Ubuntu run tcpdump as the user \"tcpdump\" and AppArmor may limit "
            "it; the tool passes -Z with your user name so the file is yours. Not yet tried on a "
            "real Ubuntu."],
            "options": [], "admin": "Recording needs your administrator password (sudo), "
                                    "because only an administrator may listen to USB."}
    return {"can": False, "kind": None, "lines": [f"{system} is not supported."],
            "options": [], "admin": ""}


def gather_facts(transport: str, system: str) -> dict:
    facts = {}
    if system == "Windows":
        facts["admin"] = windows_is_admin()
        if transport == "net":
            facts["pktmon"] = os.path.exists(system32("pktmon.exe"))
        else:
            facts["usbpcap"] = find_usbpcapcmd()
    elif system == "Darwin":
        facts["tcpdump"] = bool(system_tool(TCPDUMP))
        if transport == "usb":
            try:
                out = subprocess.run(["/usr/bin/csrutil", "status"], stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, timeout=10).stdout.decode()
            except (OSError, subprocess.TimeoutExpired):
                out = ""
            facts["sip"] = parse_csrutil(out)
            try:
                lst = subprocess.run([system_tool(IFCONFIG) or "/sbin/ifconfig", "-l"], stdout=subprocess.PIPE,
                                     timeout=10).stdout.decode()
            except (OSError, subprocess.TimeoutExpired):
                lst = ""
            facts["xhc"] = mac_xhc_interfaces(lst)
    elif system == "Linux":
        facts["tcpdump"] = bool(system_tool(TCPDUMP))
        facts["usbmon"] = sorted(os.path.basename(p) for p in glob.glob("/dev/usbmon*")
                                 if re.fullmatch(r"usbmon\d+", os.path.basename(p)))
    return facts


def usbpcap_interfaces(exe: str) -> list:
    try:
        out = subprocess.run(_base(exe) + ["--extcap-interfaces"], stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, timeout=30).stdout.decode("utf-8", "replace")
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [m.group(1) for m in _EXTCAP_IFACE_RE.finditer(out)]


def make_recorder(kind: str, outdir: str, selection: dict, facts: dict | None = None):
    """The recorder for a readiness() kind."""
    facts = facts or {}
    if kind == "usbpcap":
        exe = facts.get("usbpcap") or find_usbpcapcmd()
        return UsbPcapRecorder(exe, usbpcap_interfaces(exe), outdir)
    if kind == "tcpdump-usb":
        return TcpdumpRecorder(facts.get("xhc") or [], outdir, mac_usb=True)
    if kind == "tcpdump-usbmon":
        bus = None
        for b, _a in selection.get("addresses") or []:
            bus = b
        ifaces = [f"usbmon{bus}"] if bus else ["usbmon0"]
        return TcpdumpRecorder(ifaces, outdir)
    if kind == "tcpdump-net":
        from .discovery import capture_interface_for  # noqa: PLC0415
        ips = selection.get("ips") or []
        iface = (capture_interface_for(ips[0]) if ips else None) or "any"
        parts = [f"host {ip}" for ip in ips] + [f"ether host {m}" for m in selection.get("macs", [])]
        return TcpdumpRecorder([iface], outdir, bpf=" or ".join(parts))
    if kind == "pktmon":
        return PktmonRecorder(outdir)
    raise RecorderError(f"no recorder for {kind}")

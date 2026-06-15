#!/usr/bin/env python3
"""
common.py
=========
Cross-pipeline helpers shared by install/plugins/tools/materials.

These live here rather than in install.py (their original home) so any
pipeline can use them without going through install as a side-door.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

CSP_PROCESS = "CLIPStudioPaint.exe"

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@contextmanager
def quiet_stdout():
    """Suppress console output (used when the GUI triggers a switch)."""
    with open(os.devnull, "w", encoding="utf-8") as devnull:
        old = sys.stdout
        sys.stdout = devnull
        try:
            yield
        finally:
            sys.stdout = old


def attach_console() -> None:
    """Give a windowed (PyInstaller) process a console for --keep-open debugging."""
    if os.name != "nt":
        return
    try:
        if ctypes.windll.kernel32.GetConsoleWindow():
            return
        ctypes.windll.kernel32.AllocConsole()
        sys.stdin = open("CONIN$", "r", encoding="utf-8", errors="replace")
        sys.stdout = open("CONOUT$", "w", encoding="utf-8", errors="replace")
        sys.stderr = open("CONERR$", "w", encoding="utf-8", errors="replace")
    except OSError:
        pass


def pause_console(prompt: str = "\nPress Enter to close this window...") -> None:
    """Wait so an elevated/debug console stays readable."""
    if os.name == "nt":
        try:
            import msvcrt

            print(prompt, end="", flush=True)
            while msvcrt.getch() not in (b"\r", b"\n"):
                pass
            return
        except (ImportError, OSError):
            pass
    try:
        input(prompt)
    except (EOFError, RuntimeError, OSError):
        pass


def _elevated_workdir() -> Path:
    entry = Path(sys.argv[0]).resolve()
    if getattr(sys, "frozen", False):
        return entry.parent
    if entry.suffix.lower() in (".py", ".pyw") and entry.parent.name == "src":
        return entry.parent.parent
    return entry.parent


def run_elevated_sync(argv: list[str]) -> tuple[int, str]:
    """Re-launch elevated, wait, hide window. Returns (exit code, error text)."""
    if os.name != "nt":
        return 1, ""
    executable = Path(sys.executable)
    if getattr(sys, "frozen", False):
        args = list(argv)
    else:
        args = [str(Path(sys.argv[0]).resolve()), *argv]

    err_file = Path(tempfile.gettempdir()) / "csp-lang-switch-gui-error.txt"
    try:
        err_file.unlink(missing_ok=True)
    except OSError:
        pass
    args.extend(["--gui-error-file", str(err_file)])

    exe = str(executable).replace("'", "''")
    workdir = str(_elevated_workdir()).replace("'", "''")
    arg_parts = ", ".join("'" + a.replace("'", "''") + "'" for a in args)
    ps = (
        f"$p = Start-Process -FilePath '{exe}' "
        f"-ArgumentList @({arg_parts}) "
        f"-WorkingDirectory '{workdir}' "
        f"-Verb RunAs -Wait -PassThru -WindowStyle Hidden; "
        f"if ($null -eq $p) {{ exit 1 }}; exit $p.ExitCode"
    )
    cp = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
        creationflags=_CREATE_NO_WINDOW,
    )
    if cp.returncode != 0 and err_file.is_file():
        try:
            text = err_file.read_text(encoding="utf-8").strip()
            if text:
                return cp.returncode, text
        except OSError:
            pass
    return int(cp.returncode), ""


# ----------------------------------------------------------------------
# Locating the CSP install
# ----------------------------------------------------------------------
def find_csp_resource(explicit: str | None) -> Path:
    """Return CSP's `resource` folder, or exit with a clear message."""
    if explicit:
        p = Path(explicit)
        if not (p / "english").is_dir():
            sys.exit(f"error: {p} has no 'english' subfolder -- not a CSP "
                     f"resource directory")
        return p

    # Glob the version directory so a CSP update (1.5 -> 1.6 ...) still resolves.
    for base in (Path(r"C:\Program Files\CELSYS"),
                 Path(r"C:\Program Files (x86)\CELSYS")):
        if not base.is_dir():
            continue
        for cand in sorted(base.glob("*/CLIP STUDIO PAINT/resource")):
            if (cand / "english").is_dir():
                return cand

    sys.exit("error: could not find a CSP install. Pass --csp <resource dir>, "
             r"e.g. --csp \"C:\Program Files\CELSYS\CLIP STUDIO 1.5\CLIP "
             r"STUDIO PAINT\resource\"")


def csp_is_running() -> bool:
    """True if CLIPStudioPaint.exe shows up in the Windows task list."""
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {CSP_PROCESS}"],
            capture_output=True, text=True, timeout=15,
            creationflags=_CREATE_NO_WINDOW,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return False  # cannot tell -- do not block on it
    return CSP_PROCESS.lower() in out.lower()


# ----------------------------------------------------------------------
# Administrator elevation
# ----------------------------------------------------------------------
# Writing into C:\Program Files needs Administrator rights. Rather than make the
# user remember to open an elevated terminal, we detect a normal process and
# re-launch the same command through the UAC "runas" verb.
def is_admin() -> bool:
    """True on non-Windows, or when this Windows process is elevated."""
    if os.name != "nt":
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def ensure_admin() -> None:
    """If not elevated, re-launch this exact command via UAC and exit.

    The relaunched copy gets a hidden --keep-open flag so its (separate,
    elevated) console stays open afterwards for the user to read.

    In source mode we invoke `python <script> ...`. In a PyInstaller bundle
    `sys.executable` IS the program, so we must not repeat sys.argv[0] in
    the parameters -- otherwise it'd be passed as a positional arg."""
    if is_admin():
        return
    if getattr(sys, "frozen", False):
        params = subprocess.list2cmdline([*sys.argv[1:], "--keep-open"])
    else:
        params = subprocess.list2cmdline(
            [str(Path(sys.argv[0]).resolve()), *sys.argv[1:], "--keep-open"])
    rc = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, params, str(Path.cwd()), 1)
    if rc <= 32:  # ShellExecuteW returns <=32 on failure (incl. UAC declined)
        sys.exit("\nerror: this needs Administrator rights and the UAC prompt "
                 "was declined.\n       Accept it, or re-run from an "
                 "Administrator terminal.")
    print("Administrator rights needed -- continuing in an elevated window.")
    sys.exit(0)


# ----------------------------------------------------------------------
# User prompts and safety checks
# ----------------------------------------------------------------------
def confirm(prompt: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    try:
        return input(f"{prompt} [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:
        return False


def check_csp_closed(force: bool) -> None:
    if csp_is_running():
        msg = "CSP is running -- close it before changing its resource files."
        if not force:
            sys.exit(f"error: {msg}")
        print(f"warning: {msg} (continuing: --force)")

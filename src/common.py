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
from pathlib import Path

CSP_PROCESS = "CLIPStudioPaint.exe"


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

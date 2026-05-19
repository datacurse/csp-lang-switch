#!/usr/bin/env python3
"""
install.py
==========
Install a language into a live Clip Studio Paint install, in place, without
reinstalling the app.

    python src/install.py russian     <- show the Russian translation
    python src/install.py english     <- put the original English back
    python src/install.py japanese    <- load stock Japanese (for screenshots)
    python src/install.py             <- show what is installed right now

How it works
------------
CSP loads its UI strings from `resource/<language>/`, one folder per language,
and picks the folder by the UI language set in CSP. It has no `russian` slot,
so we overwrite the `english` slot in place: `install.py <language>` copies a
language's resource files onto that slot, and CSP shows them when set to
English.

Where each language comes from:
  * `russian`  -- the translated build in the repo's `russian/` folder
                  (produced by `batch.py pack`)
  * any other  -- the stock originals CSP ships, kept in `resource/<language>/`

So `install.py english` is simply "install the original English" -- it is the
undo. Nothing is backed up into the CSP install: `resource/` already holds the
untouched originals for every stock language.

Usage
-----
  python src/install.py [LANGUAGE]   install LANGUAGE (status if omitted)
  python src/install.py status       show what is installed

Options
  --csp DIR     CSP `resource` folder (auto-detected if omitted)
  --slot NAME   the language slot to overwrite     (default: english)
  --dry-run     print what would happen, change nothing
  --yes         skip the confirmation prompt
  --force       proceed even if CSP appears to be running

Writing into C:\\Program Files needs Administrator rights; if the process is
not elevated it re-launches itself through a UAC prompt automatically.

No external dependencies (standard library only).
"""

from __future__ import annotations

import argparse
import ctypes
import filecmp
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# ----------------------------------------------------------------------
# Project paths
# ----------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
# The untouched original CSP resources, one folder per stock language.
ORIGINALS_DIR = ROOT / "resource"

CSP_PROCESS = "CLIPStudioPaint.exe"

# A resource file is GUID-named with no extension. Matching on this tells a
# real resource/build folder apart from any other directory in the repo.
GUID_RE = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z", re.I)


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
    elevated) console stays open afterwards for the user to read."""
    if is_admin():
        return
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
# Helpers
# ----------------------------------------------------------------------
def resource_files(folder: Path) -> list[Path]:
    """The GUID-named resource files directly inside `folder`.

    Stray files (Thumbs.db, ...) and subfolders are ignored -- so an empty
    result also means 'not a resource/build folder'."""
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir()
                  if p.is_file() and GUID_RE.match(p.name))


def language_sources() -> dict[str, Path]:
    """Installable languages mapped to their source folder, in display order.

    Translated builds at the repo root (e.g. russian/) are listed first; the
    stock originals shipped per language (resource/<lang>/) follow. `other` is
    a misc bucket, not a UI language, so it is skipped."""
    sources: dict[str, Path] = {}
    for d in sorted(ROOT.iterdir()):
        if d.name != "resource" and resource_files(d):
            sources[d.name] = d
    for d in sorted(ORIGINALS_DIR.iterdir()) if ORIGINALS_DIR.is_dir() else []:
        if d.name != "other" and d.name not in sources and resource_files(d):
            sources[d.name] = d
    return sources


def diff_against(folder: Path, reference: Path) -> list[str]:
    """Names of files in `folder` whose content differs from `reference`.

    Files missing on either side are ignored -- callers handle counts."""
    changed = []
    for f in resource_files(folder):
        ref = reference / f.name
        if ref.is_file() and not filecmp.cmp(f, ref, shallow=False):
            changed.append(f.name)
    return changed


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


def copy_over(src_files: list[Path], dst: Path, dry_run: bool) -> None:
    for i, f in enumerate(src_files):
        if dry_run:
            print(f"  [dry-run] {f.name}")
            continue
        try:
            shutil.copy2(f, dst / f.name)
        except PermissionError:
            sys.exit(f"\nerror: permission denied writing to {dst / f.name}\n"
                     f"       {i} of {len(src_files)} file(s) copied before "
                     f"this failed.\n"
                     f"       CSP is most likely still running and holding the "
                     f"file open -- close it and run the command again.")


# ----------------------------------------------------------------------
# Commands
# ----------------------------------------------------------------------
def cmd_status(args) -> None:
    resource_dir = find_csp_resource(args.csp)
    slot = resource_dir / args.slot
    sources = language_sources()

    # The slot "is" a language when every file of that language matches it.
    showing = next((name for name, folder in sources.items()
                    if not diff_against(folder, slot)), None)

    print()
    print(f"  CSP       {resource_dir.parent}")
    if showing:
        print(f"  showing   {showing.capitalize()}   (on the {args.slot} slot)")
    else:
        print(f"  showing   unknown -- the {args.slot} slot matches no "
              f"known language")
    if csp_is_running():
        print(f"  note      CSP is running -- close it before installing")
    print()
    print(f"  install another:  python src/install.py <language>")
    print(f"  languages:        {'  '.join(sources)}")
    print()


def cmd_install(args) -> None:
    resource_dir = find_csp_resource(args.csp)
    slot = resource_dir / args.slot
    sources = language_sources()

    source = sources.get(args.target)
    if source is None:
        sys.exit(f"error: unknown language '{args.target}'.\n"
                 f"       available: {', '.join(sources)}")
    src_files = resource_files(source)
    label = args.target.capitalize()

    check_csp_closed(args.force)
    if not args.dry_run:
        ensure_admin()  # re-launches elevated if needed, then exits this process

    kept = len(resource_files(slot)) - len(src_files)
    print(f"will install {label} ({len(src_files)} files) "
          f"onto the {args.slot} slot")
    print(f"  {source}  ->  {slot}")
    if kept > 0:
        print(f"  ({kept} file(s) not in this build keep their current contents)")

    if args.dry_run:
        copy_over(src_files, slot, dry_run=True)
        print("[dry-run] nothing was changed")
        return
    if not confirm("proceed?", args.yes):
        print("aborted")
        return

    copy_over(src_files, slot, dry_run=False)
    print(f"\ndone -- {label} installed onto the {args.slot} slot.")
    print(f"in CSP, set the UI language to '{args.slot.capitalize()}' and restart.")


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------
def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="install.py",
        description="Install a language into a live CSP install, in place.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="examples:\n"
               "  python src/install.py russian     install the translation\n"
               "  python src/install.py english     put the original back\n"
               "  python src/install.py             show what is installed",
    )
    parser.add_argument("target", nargs="?", default="status", metavar="LANGUAGE",
                        help="language to install (russian, english, japanese, "
                             "...); omit, or use 'status', to show what is "
                             "installed")
    parser.add_argument("--csp", metavar="DIR",
                        help="CSP 'resource' folder (auto-detected if omitted)")
    parser.add_argument("--slot", default="english", metavar="NAME",
                        help="language slot to overwrite (default: english)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print what would happen, change nothing")
    parser.add_argument("--yes", action="store_true",
                        help="skip the confirmation prompt")
    parser.add_argument("--force", action="store_true",
                        help="proceed even if CSP appears to be running")
    # Set automatically on the elevated relaunch; keeps that console open.
    parser.add_argument("--keep-open", action="store_true",
                        help=argparse.SUPPRESS)

    args = parser.parse_args(argv)
    try:
        if args.target == "status":
            cmd_status(args)
        else:
            cmd_install(args)
    finally:
        if args.keep_open:
            try:
                input("\npress Enter to close this window...")
            except EOFError:
                pass


if __name__ == "__main__":
    main()

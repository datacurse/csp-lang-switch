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
CSP loads its UI strings from `resource/<language>/` inside its install, one
folder per language, and picks the folder by the UI language set in CSP. It
has no `russian` slot, so we overwrite the `english` slot in place:
`install.py <language>` copies a language's resource files onto that slot, and
CSP shows them when set to English.

Each installable language is a folder under the repo's `langs/`, with the
main-UI resource files at `langs/<language>/ui/`:
  * `russian`  -- the translated build (produced by `batch.py pack`)
  * `english`  -- the untouched stock English snapshot

So `install.py english` is simply "install the original English" -- it is the
undo. Nothing is backed up into the CSP install: `langs/english/ui/` already
holds the untouched stock English.

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
import filecmp
import re
import shutil
import sys
from pathlib import Path

# Cross-pipeline helpers (originally defined here; now shared in common.py).
# Re-imported into install's namespace so external callers using
# `install.find_csp_resource` etc. continue to work as a stable facade.
from common import (
    CSP_PROCESS,
    csp_is_running,
    is_admin,
    ensure_admin,
    check_csp_closed,
    confirm,
    find_csp_resource,
)
from version import LANGS_ROOT, ROOT

# ----------------------------------------------------------------------
# Project paths
# ----------------------------------------------------------------------
# One folder per language, each a complete tree: langs/<lang>/ui/ (main UI
# resource files) plus optional plugins/ for languages we patch ourselves.
LANGS_DIR = LANGS_ROOT

# A resource file is GUID-named with no extension. Matching on this tells a
# real resource/build folder apart from any other directory in the repo.
GUID_RE = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z", re.I)


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
    """Installable languages mapped to their main-UI source folder.

    Every language is a folder under `langs/`; its installable main UI lives
    at `langs/<lang>/ui/<GUID files>`. A folder without a populated `ui/` is
    skipped (so an incomplete language is simply not offered)."""
    sources: dict[str, Path] = {}
    for d in sorted(LANGS_DIR.iterdir()) if LANGS_DIR.is_dir() else []:
        if not d.is_dir():
            continue
        ui = d / "ui"
        if ui.is_dir() and resource_files(ui):
            sources[d.name] = ui
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

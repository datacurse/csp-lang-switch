#!/usr/bin/env python3
"""
install.py
==========
Install a language into a live Clip Studio install, in place, without
reinstalling the app.

    python src/install.py russian     <- show the Russian translation
    python src/install.py english     <- put the original English back
    python src/install.py japanese    <- load stock Japanese (for screenshots)
    python src/install.py             <- show what is installed right now

How it works
------------
A Clip Studio install actually contains two apps -- CLIP STUDIO PAINT (the
editor) and CLIP STUDIO (the launcher / hub window). Each ships an independent
`resource/<language>/` tree, and each picks a tree by the UI language set in
its preferences. Neither has a `russian` slot, so we overwrite the `english`
slot in place in *both* apps: `install.py <language>` copies that language's
resource files onto each app's English slot, and Clip Studio shows them when
set to English.

Where each language's files come from (one source folder per app):

  paint     russian      ROOT/russian/                   (batch.py pack)
            english/...  ROOT/resource/<lang>/           (CSP originals)

  launcher  russian      ROOT/russian-launcher/          (batch.py pack)
            english/...  ROOT/resource-launcher/<lang>/  (CSP originals)

If only one app's source folder exists for the chosen language (e.g.
`russian/` is packed but `russian-launcher/` is not yet), the other app is
skipped with a message -- the install is still useful, the launcher just
stays on its previous language.

So `install.py english` is simply "install the original English" -- it is the
undo. Nothing is backed up into the CSP install: the repo already holds the
untouched originals for every stock language.

Usage
-----
  python src/install.py [LANGUAGE]   install LANGUAGE (status if omitted)
  python src/install.py status       show what is installed

Options
  --app NAME    only paint or launcher (default: both, if detected)
  --csp DIR     CSP PAINT 'resource' folder (auto-detected if omitted)
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
# Project paths -- one per app (paint / launcher).
# ----------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent

# Per-app configuration. `originals` is the in-repo mirror of the app's stock
# resources (one folder per stock language); `russian` is the packed
# translation; `install_subpath` is the relative path from a CSP install root
# (e.g. .../CLIP STUDIO 1.5/) to the app's resource folder. Adding a third app
# later is just another dict.
APPS: list[dict] = [
    {
        "name": "paint",
        "label": "CLIP STUDIO PAINT",
        "originals": ROOT / "resource",
        "russian":   ROOT / "russian",
        "process":   "CLIPStudioPaint.exe",
        "install_subpath": "CLIP STUDIO PAINT/resource",
    },
    {
        "name": "launcher",
        "label": "CLIP STUDIO (launcher)",
        "originals": ROOT / "resource-launcher",
        "russian":   ROOT / "russian-launcher",
        "process":   "CLIPStudio.exe",
        "install_subpath": "CLIP STUDIO/resource",
    },
]


def app_by_name(name: str) -> dict:
    for a in APPS:
        if a["name"] == name:
            return a
    sys.exit(f"error: unknown app '{name}' (choose one of "
             f"{', '.join(a['name'] for a in APPS)})")

# A resource file is GUID-named with no extension. Matching on this tells a
# real resource/build folder apart from any other directory in the repo.
GUID_RE = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z", re.I)


# ----------------------------------------------------------------------
# Locating the CSP install on disk
# ----------------------------------------------------------------------
def find_install_root(explicit_paint_resource: str | None) -> Path | None:
    """Return the `CLIP STUDIO <ver>/` folder that contains both apps.

    `--csp` historically pointed at the PAINT resource folder, so honor that
    by walking up from it. With no override, glob CELSYS for the versioned
    folder. Returns None when nothing is found -- callers decide whether that
    is fatal."""
    if explicit_paint_resource:
        p = Path(explicit_paint_resource).resolve()
        # explicit may be either the install root itself or PAINT's resource/
        if p.name == "resource" and p.parent.name == "CLIP STUDIO PAINT":
            return p.parent.parent
        return p
    for base in (Path(r"C:\Program Files\CELSYS"),
                 Path(r"C:\Program Files (x86)\CELSYS")):
        if not base.is_dir():
            continue
        for cand in sorted(base.glob("*/CLIP STUDIO PAINT/resource")):
            if (cand / "english").is_dir():
                return cand.parent.parent
    return None


def resolve_app_slot(app: dict, install_root: Path | None,
                     slot: str) -> Path | None:
    """The `<install_root>/<app subpath>/<slot>` folder, if it exists."""
    if install_root is None:
        return None
    p = install_root / app["install_subpath"] / slot
    return p if p.is_dir() else None


def csp_is_running() -> list[str]:
    """Names of running CSP processes (paint / launcher). Empty list = none."""
    procs = [a["process"] for a in APPS]
    try:
        out = subprocess.run(
            ["tasklist"],
            capture_output=True, text=True, timeout=15,
        ).stdout.lower()
    except (OSError, subprocess.SubprocessError):
        return []  # cannot tell -- do not block on it
    return [p for p in procs if p.lower() in out]


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


def language_sources(app: dict) -> dict[str, Path]:
    """Installable languages mapped to their source folder, for one app.

    The translated build at the repo root (e.g. russian/ for paint,
    russian-launcher/ for launcher) -- if it exists -- is listed first under
    its language name; the stock originals shipped per language
    (resource/<lang>/ or resource-launcher/<lang>/) follow. `other` is a misc
    bucket, not a UI language, so it is skipped."""
    sources: dict[str, Path] = {}
    russian = app["russian"]
    if resource_files(russian):
        sources["russian"] = russian
    originals = app["originals"]
    if originals.is_dir():
        for d in sorted(originals.iterdir()):
            if d.name != "other" and d.name not in sources and resource_files(d):
                sources[d.name] = d
    return sources


def all_languages() -> list[str]:
    """Union of language names across both apps, in stable order."""
    seen: dict[str, None] = {}
    for app in APPS:
        for name in language_sources(app):
            seen.setdefault(name, None)
    return list(seen)


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
    running = csp_is_running()
    if running:
        msg = (f"{', '.join(running)} is running -- close it before changing "
               f"its resource files.")
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
def _selected_apps(args) -> list[dict]:
    return [app_by_name(args.app)] if args.app else list(APPS)


def cmd_status(args) -> None:
    install_root = find_install_root(args.csp)
    if install_root is None:
        sys.exit("error: could not find a CSP install. Pass --csp <resource dir>, "
                 r"e.g. --csp \"C:\Program Files\CELSYS\CLIP STUDIO 1.5\CLIP "
                 r"STUDIO PAINT\resource\"")

    print()
    print(f"  CSP       {install_root}")
    for app in _selected_apps(args):
        slot = resolve_app_slot(app, install_root, args.slot)
        sources = language_sources(app)
        if slot is None:
            print(f"  {app['name']:8}  not installed on disk "
                  f"(no {app['install_subpath']}/{args.slot})")
            continue
        # The slot "is" a language when every file of that language matches it.
        showing = next((name for name, folder in sources.items()
                        if not diff_against(folder, slot)), None)
        if showing:
            print(f"  {app['name']:8}  showing {showing.capitalize()} "
                  f"(on the {args.slot} slot)")
        else:
            print(f"  {app['name']:8}  showing unknown -- the {args.slot} slot "
                  f"matches no known language")
    running = csp_is_running()
    if running:
        print(f"  note      {', '.join(running)} is running -- close it before "
              f"installing")
    print()
    print(f"  install another:  python src/install.py <language>")
    print(f"  languages:        {'  '.join(all_languages())}")
    print()


def cmd_install(args) -> None:
    install_root = find_install_root(args.csp)
    if install_root is None:
        sys.exit("error: could not find a CSP install. Pass --csp <resource dir>, "
                 r"e.g. --csp \"C:\Program Files\CELSYS\CLIP STUDIO 1.5\CLIP "
                 r"STUDIO PAINT\resource\"")

    # Resolve every (app, source_dir, slot_dir) we are going to write, before
    # asking for confirmation -- so the user sees the full picture once.
    plan: list[tuple[dict, Path, Path]] = []
    skipped: list[tuple[dict, str]] = []
    for app in _selected_apps(args):
        sources = language_sources(app)
        slot = resolve_app_slot(app, install_root, args.slot)
        if slot is None:
            skipped.append((app, f"no {args.slot} slot on disk"))
            continue
        source = sources.get(args.target)
        if source is None:
            skipped.append((app, f"no {args.target} build "
                                 f"(expected {app['russian'].name}/ or "
                                 f"{app['originals'].name}/{args.target}/)"))
            continue
        plan.append((app, source, slot))

    if not plan:
        for app, why in skipped:
            print(f"skip {app['name']}: {why}")
        sys.exit(f"error: nothing to install for '{args.target}'")

    check_csp_closed(args.force)
    if not args.dry_run:
        ensure_admin()  # re-launches elevated if needed, then exits this process

    label = args.target.capitalize()
    print(f"will install {label} onto the {args.slot} slot:")
    for app, source, slot in plan:
        n = len(resource_files(source))
        kept = max(0, len(resource_files(slot)) - n)
        print(f"  {app['name']:8} {source}  ->  {slot}  ({n} files)")
        if kept > 0:
            print(f"           ({kept} file(s) not in this build keep their "
                  f"current contents)")
    for app, why in skipped:
        print(f"  skip {app['name']}: {why}")

    if args.dry_run:
        for app, source, slot in plan:
            print(f"  [dry-run] {app['name']}:")
            copy_over(resource_files(source), slot, dry_run=True)
        print("[dry-run] nothing was changed")
        return
    if not confirm("proceed?", args.yes):
        print("aborted")
        return

    for app, source, slot in plan:
        print(f"\n[{app['name']}] copying {len(resource_files(source))} files...")
        copy_over(resource_files(source), slot, dry_run=False)
    print(f"\ndone -- {label} installed onto the {args.slot} slot "
          f"({len(plan)} app(s)).")
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
    parser.add_argument("--app", choices=[a["name"] for a in APPS],
                        help="install into only one app (default: both)")
    parser.add_argument("--csp", metavar="DIR",
                        help="CSP PAINT 'resource' folder or install root "
                             "(auto-detected if omitted)")
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

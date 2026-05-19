#!/usr/bin/env python3
"""
tools.py
========
Translate the tool / sub-tool names shown in CSP's left-hand Tool palette.

Those names -- the tool groups (`Sketch`, `Decoration`...), the tools (`Pen`,
`Pencil`, `Brush`, `Eraser`...) and every sub-tool (`G-pen`, `Charcoal`,
`Watercolor`...) -- are NOT in the resource bundles `batch.py` / `repack.py`
handle, nor in the filter plug-in DLLs `plugins.py` handles. They live in
**SQLite databases**; each tool node's displayed name is the `Node.NodeName`
column.

Two places hold those DBs, and BOTH must be patched:

  * **install seed** -- `<CSP>/Settings/PAINT/{Tool,MixPalette,BrushPreset}/
    english/*` -- the factory defaults a *fresh* CSP profile is built from.
  * **user data** -- `%APPDATA%/CELSYSUserData/CELSYS/CLIPStudioPaintVer*/
    {Tool,MixPalette,BrushPreset}/*` -- the live working copy CSP actually
    reads. CSP copies the seed here on first run, then never re-reads the seed,
    so patching the seed alone leaves an existing profile English.

A tool name is a plain label: the same English name always maps to the same
Russian name, in every DB and every node. So the worksheet
(`translation/tools.csv`) is a **dictionary** (`source,japanese,target`), and
`apply` translates by `NodeName` lookup -- which copes with the user DB having
different row ids and extra (downloaded) tools.

Pipeline (run from the repo root: python src/tools.py <cmd>)
--------
  backup    copy the seed + user-data tool DBs into the repo -> tools/
  extract   collect every distinct tool name -> translation/tools.csv
  ...translate the `target` column of tools.csv...
  apply     write the translations into patched DBs -> russian-tools/
  install   copy the patched DBs back into the live CSP install + user data
  restore   copy the original DBs back

`install` / `restore` self-elevate via UAC (reusing install.py) for the
Program Files seed; the user-data copies need no elevation but ride along.
Only the Python standard library is needed.
"""

from __future__ import annotations

import argparse
import csv
import os
import shutil
import sqlite3
import sys
from pathlib import Path

import install  # reuse find_csp_resource / ensure_admin / check_csp_closed / confirm

# ----------------------------------------------------------------------
# Project paths
# ----------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = ROOT / "tools"                 # original DBs -- the backup
BUILD_DIR = ROOT / "russian-tools"         # patched DBs -- the Russian build
WORKSHEET = ROOT / "translation" / "tools.csv"

# A backup lives at  tools/<tag>/<relpath>  ;  <tag> says which root it
# came from and where `install` must copy it back to.
SEED = "install"       # the install's per-language seed (english slot)
USER = "userdata"      # the live per-user working copy


# ----------------------------------------------------------------------
# Locating the two roots
# ----------------------------------------------------------------------
def seed_root(explicit: str | None) -> Path:
    """`<CSP install>/Settings/PAINT` -- holds the per-language tool seeds."""
    p = install.find_csp_resource(explicit).parent / "Settings" / "PAINT"
    if not p.is_dir():
        sys.exit(f"error: settings folder not found: {p}")
    return p


def user_root() -> Path | None:
    """The live per-user CSP data dir, or None if CSP has never been run.

    `%APPDATA%/CELSYSUserData/CELSYS/CLIPStudioPaintVer<v>` -- the newest
    version dir if several exist."""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    base = Path(appdata) / "CELSYSUserData" / "CELSYS"
    vers = sorted(base.glob("CLIPStudioPaintVer*")) if base.is_dir() else []
    return vers[-1] if vers else None


def roots(explicit: str | None) -> dict[str, Path]:
    """{tag: root_path} for every root present on this machine."""
    out = {SEED: seed_root(explicit)}
    u = user_root()
    if u:
        out[USER] = u
    return out


# ----------------------------------------------------------------------
# SQLite tool DBs
# ----------------------------------------------------------------------
def has_node_names(db: Path) -> bool:
    """True if `db` is a SQLite file with a Node table carrying tool names."""
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    except sqlite3.Error:
        return False
    try:
        if not con.execute("select name from sqlite_master "
                           "where type='table' and name='Node'").fetchone():
            return False
        return con.execute("select count(*) from Node "
                           "where NodeName is not null and NodeName<>''"
                           ).fetchone()[0] > 0
    except sqlite3.Error:
        return False
    finally:
        con.close()


def node_names(db: Path) -> dict[int, str]:
    """{_PW_ID: NodeName} for the named nodes of a tool DB, read-only."""
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return {pid: name for pid, name in con.execute(
            "select _PW_ID, NodeName from Node "
            "where NodeName is not null and NodeName<>'' order by _PW_ID")}
    finally:
        con.close()


def has_cyrillic(s: str) -> bool:
    return any(0x0400 <= ord(c) <= 0x04FF for c in s)


def discover(root: Path, tag: str) -> list[tuple[Path, Path]]:
    """[(abs_path, relpath)] for every name-bearing tool DB under `root`.

    Seed DBs sit in per-language folders (we take the `english` slot); the
    user-data DBs sit one level down in fixed subfolders."""
    globs = ["*/english/*"] if tag == SEED \
        else ["Tool/*", "MixPalette/*", "BrushPreset/*"]
    out = []
    for g in globs:
        for db in sorted(root.glob(g)):
            if db.is_file() and has_node_names(db):
                out.append((db, db.relative_to(root)))
    return out


# ----------------------------------------------------------------------
# Worksheet -- a source->target dictionary
# ----------------------------------------------------------------------
def load_dict() -> dict[str, str]:
    """{source: target} from tools.csv -- blank targets dropped."""
    if not WORKSHEET.exists():
        sys.exit(f"error: {WORKSHEET} not found -- run 'extract' first")
    out = {}
    for r in csv.DictReader(open(WORKSHEET, encoding="utf-8-sig")):
        if r.get("target", "").strip():
            out[r["source"]] = r["target"]
    return out


def existing_targets() -> dict[str, str]:
    """{source: target} already in tools.csv (any column layout)."""
    if not WORKSHEET.exists():
        return {}
    return {r["source"]: r.get("target", "")
            for r in csv.DictReader(open(WORKSHEET, encoding="utf-8-sig"))
            if r.get("source")}


def backed_up() -> list[tuple[str, Path]]:
    """[(tag, relpath)] for every DB saved under tools/<install|userdata>/."""
    out = []
    for db in sorted(p for p in TOOLS_DIR.rglob("*") if p.is_file()):
        rel = db.relative_to(TOOLS_DIR)
        if rel.parts[0] in (SEED, USER):
            out.append((rel.parts[0], Path(*rel.parts[1:])))
    return out


# ----------------------------------------------------------------------
# Commands
# ----------------------------------------------------------------------
def cmd_backup(args) -> None:
    copied, kept, patched = [], [], []
    for tag, root in roots(args.csp).items():
        for abs_path, rel in discover(root, tag):
            dst = TOOLS_DIR / tag / rel
            if dst.exists():
                kept.append(f"{tag}/{rel}")     # never overwrite an original
            elif any(has_cyrillic(n) for n in node_names(abs_path).values()):
                patched.append(f"{tag}/{rel}")  # a patched DB is not original
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(abs_path, dst)
                copied.append(f"{tag}/{rel}")

    print(f"backup -> {TOOLS_DIR}")
    print(f"  copied {len(copied)} original tool DB(s)")
    if kept:
        print(f"  kept {len(kept)} already in tools/ (left untouched)")
    if patched:
        print(f"  SKIPPED {len(patched)} already-patched DB(s) -- need the "
              f"stock original:")
        for p in patched:
            print(f"    {p}")


def cmd_extract(args) -> None:
    dbs = backed_up()
    if not dbs:
        sys.exit(f"error: nothing in {TOOLS_DIR} -- run 'backup' first")

    # Japanese oracle: pair each clean seed DB with the install's japanese
    # slot by _PW_ID -> {english name: japanese name}.
    ja_map: dict[str, str] = {}
    paint = seed_root(args.csp)
    for tag, rel in dbs:
        if tag != SEED:
            continue
        ja_db = paint / rel.parts[0] / "japanese" / rel.name
        if not ja_db.is_file():
            continue
        en, ja = node_names(TOOLS_DIR / tag / rel), node_names(ja_db)
        for pid, name in en.items():
            if pid in ja and name not in ja_map:
                ja_map[name] = ja[pid]

    # Every distinct tool name across every backed-up DB.
    names: set[str] = set()
    for tag, rel in dbs:
        names |= set(node_names(TOOLS_DIR / tag / rel).values())

    keep = existing_targets()
    rows = [(n, ja_map.get(n, ""), keep.get(n, "")) for n in sorted(names)]

    WORKSHEET.parent.mkdir(exist_ok=True)
    with open(WORKSHEET, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["source", "japanese", "target"])
        w.writerows(rows)

    done = sum(1 for *_, t in rows if t.strip())
    print(f"extract -> {WORKSHEET}")
    print(f"  {len(rows)} distinct tool names from {len(dbs)} DB(s)")
    print(f"  {done} translated, {len(rows) - done} to go")


def cmd_apply(args) -> None:
    table = load_dict()
    dbs = backed_up()
    if not dbs:
        sys.exit(f"error: nothing in {TOOLS_DIR} -- run 'backup' first")

    patched_n = strings_n = 0
    untranslated: set[str] = set()
    for tag, rel in dbs:
        src = TOOLS_DIR / tag / rel
        dst = BUILD_DIR / tag / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        os.chmod(dst, 0o644)               # Program Files copies arrive read-only

        updates = {}
        for pid, name in node_names(src).items():
            if name in table:
                updates[pid] = table[name]
            else:
                untranslated.add(name)

        con = sqlite3.connect(dst)
        try:
            con.executemany("update Node set NodeName=? where _PW_ID=?",
                            [(t, pid) for pid, t in updates.items()])
            con.commit()
        finally:
            con.close()

        got = node_names(dst)              # round-trip check
        for pid, tgt in updates.items():
            if got.get(pid) != tgt:
                sys.exit(f"error: round-trip check failed for {tag}/{rel} "
                         f"node {pid}")
        patched_n += 1
        strings_n += len(updates)

    print(f"apply -> {BUILD_DIR}")
    print(f"  patched {patched_n} DB(s), {strings_n} tool names translated")
    if untranslated:
        print(f"  note: {len(untranslated)} name(s) have no translation and "
              f"stay as-is (downloaded / custom tools):")
        for n in sorted(untranslated):
            print(f"    {n!r}")


def _deploy(src_root: Path, label: str, args) -> None:
    """Copy every DB under `src_root` back to its original root + relpath."""
    dst_roots = roots(args.csp)
    jobs = []                              # (src_file, dst_file)
    for db in sorted(p for p in src_root.rglob("*") if p.is_file()):
        rel = db.relative_to(src_root)
        tag, sub = rel.parts[0], Path(*rel.parts[1:])
        if tag not in dst_roots:
            continue
        dst = dst_roots[tag] / sub
        if not dst.parent.is_dir():
            sys.exit(f"error: target folder missing: {dst.parent}")
        jobs.append((db, dst))
    if not jobs:
        sys.exit(f"error: nothing to install from {src_root}")

    install.check_csp_closed(args.force)
    if not args.dry_run:
        install.ensure_admin()  # re-launches elevated if needed, then exits

    print(f"will install {len(jobs)} {label} tool DB(s)")
    for src, dst in jobs:
        print(f"  {src.relative_to(src_root).as_posix()}  ->  {dst}")
    if args.dry_run:
        print("[dry-run] nothing was changed")
        return
    if not install.confirm("proceed?", args.yes):
        print("aborted")
        return

    for src, dst in jobs:
        shutil.copy2(src, dst)
    print(f"\ndone -- {len(jobs)} {label} tool DB(s) installed.")


def cmd_install(args) -> None:
    _deploy(BUILD_DIR, "patched", args)
    print("restart CSP; the Tool palette names are now Russian.")
    print("run 'python src/tools.py restore' to undo.")


def cmd_restore(args) -> None:
    _deploy(TOOLS_DIR, "original", args)
    print("restart CSP; the Tool palette names are English again.")


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------
def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="tools.py",
        description="Translate CSP Tool-palette names (the .todb SQLite DBs).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--csp", metavar="DIR",
                        help="CSP 'resource' folder (auto-detected if omitted)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print what would happen, change nothing")
    parser.add_argument("--yes", action="store_true",
                        help="skip the confirmation prompt")
    parser.add_argument("--force", action="store_true",
                        help="proceed even if CSP appears to be running")
    # Set automatically on the elevated relaunch; keeps that console open.
    parser.add_argument("--keep-open", action="store_true",
                        help=argparse.SUPPRESS)
    parser.add_argument("command",
                        choices=("backup", "extract", "apply",
                                 "install", "restore"),
                        help="pipeline step to run")

    args = parser.parse_args(argv)
    try:
        {"backup": cmd_backup, "extract": cmd_extract, "apply": cmd_apply,
         "install": cmd_install, "restore": cmd_restore}[args.command](args)
    finally:
        if args.keep_open:
            try:
                input("\npress Enter to close this window...")
            except EOFError:
                pass


if __name__ == "__main__":
    main()

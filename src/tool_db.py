#!/usr/bin/env python3
"""
tool_db.py
==========
Deploy translated tool-palette SQLite databases.

Main tool / sub-tool labels (Pen, Sketch, G-pen, …) are **not** in the UI
resource pack — they live in Settings/PAINT/*.todb files. CSP keeps two copies:

  * **install seed** — factory defaults under ``<CSP>/Settings/PAINT/…/english/``
  * **user data** — live working copy under
    ``%APPDATA%/CELSYSUserData/CELSYS/CLIPStudioPaintVer*/…``

After first launch CSP reads the user-data copy and ignores the seed.

**User data must be patched in place** (``UPDATE Node SET NodeName`` only).
Replacing the live ``EditImageTool.todb`` with a stock build drops downloaded
brushes from custom tool groups. See ``docs/TOOL_TRANSLATION.md``.
"""

from __future__ import annotations

import csv
import os
import shutil
import sqlite3
from pathlib import Path

from version import ROOT, langs_root

SEED = "install"
USER = "userdata"
WORKSHEET = ROOT / "translation" / "tools.csv"


def _backup_root() -> Path:
    local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return local / "csp-lang-switch" / "tools"


def paint_root(resource_dir: Path) -> Path:
    root = resource_dir.parent / "Settings" / "PAINT"
    if not root.is_dir():
        raise FileNotFoundError(f"settings folder not found: {root}")
    return root


def user_root() -> Path | None:
    """Newest ``CLIPStudioPaintVer*`` folder under CELSYS user data."""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    base = Path(appdata) / "CELSYSUserData" / "CELSYS"
    if not base.is_dir():
        return None
    vers = sorted(base.glob("CLIPStudioPaintVer*"))
    return vers[-1] if vers else None


def live_roots(resource_dir: Path) -> dict[str, Path]:
    out = {SEED: paint_root(resource_dir)}
    u = user_root()
    if u:
        out[USER] = u
    return out


def bundle_root(language: str) -> Path:
    return langs_root() / language / "tools"


def load_translation_dict() -> dict[str, str]:
    """``{english NodeName: russian NodeName}`` from ``translation/tools.csv``."""
    if not WORKSHEET.is_file():
        return {}
    out: dict[str, str] = {}
    with WORKSHEET.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            src = (row.get("source") or "").strip()
            tgt = (row.get("target") or "").strip()
            if src and tgt and tgt != src:
                out[src] = tgt
    return out


def reverse_translation_dict() -> dict[str, str]:
    """``{russian NodeName: english NodeName}`` — inverse of ``load_translation_dict``."""
    fwd = load_translation_dict()
    return {tgt: src for src, tgt in fwd.items()}


def _has_node_names(db: Path) -> bool:
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    except sqlite3.Error:
        return False
    try:
        if not con.execute(
            "select name from sqlite_master where type='table' and name='Node'"
        ).fetchone():
            return False
        return con.execute(
            "select count(*) from Node "
            "where NodeName is not null and NodeName<>''"
        ).fetchone()[0] > 0
    except sqlite3.Error:
        return False
    finally:
        con.close()


def _node_names(db: Path) -> dict[int, str]:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return {
            pid: name
            for pid, name in con.execute(
                "select _PW_ID, NodeName from Node "
                "where NodeName is not null and NodeName<>'' order by _PW_ID"
            )
        }
    finally:
        con.close()


def _has_cyrillic(text: str) -> bool:
    return any(0x0400 <= ord(c) <= 0x04FF for c in text)


def discover_live(root: Path, tag: str) -> list[tuple[Path, Path]]:
    """[(abs_path, relpath)] for every tool DB under a live CSP root."""
    globs = ["*/english/*"] if tag == SEED else ["Tool/*", "MixPalette/*", "BrushPreset/*"]
    out: list[tuple[Path, Path]] = []
    for pattern in globs:
        for db in sorted(root.glob(pattern)):
            if db.is_file() and _has_node_names(db):
                out.append((db, db.relative_to(root)))
    return out


def _collect_deploy_jobs(
    src_root: Path, dst_roots: dict[str, Path]
) -> list[tuple[Path, Path]]:
    jobs: list[tuple[Path, Path]] = []
    for db in sorted(p for p in src_root.rglob("*") if p.is_file()):
        rel = db.relative_to(src_root)
        if not rel.parts or rel.parts[0] not in dst_roots:
            continue
        tag = rel.parts[0]
        sub = Path(*rel.parts[1:])
        jobs.append((db, dst_roots[tag] / sub))
    return jobs


def _backup_live(resource_dir: Path, *, dry_run: bool) -> None:
    """Snapshot live tool DBs before the first language switch."""
    backup = _backup_root()
    copied = 0
    for tag, root in live_roots(resource_dir).items():
        for abs_path, rel in discover_live(root, tag):
            dst = backup / tag / rel
            if dst.is_file():
                continue
            if tag == SEED and any(
                _has_cyrillic(n) for n in _node_names(abs_path).values()
            ):
                continue
            if dry_run:
                print(f"  [dry-run] would back up {tag}/{rel.as_posix()}")
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(abs_path, dst)
            copied += 1
    if copied and not dry_run:
        print(f"  tool DBs: backed up {copied} stock file(s) -> {backup}")


def deploy_bundle(
    resource_dir: Path,
    src_root: Path,
    *,
    dry_run: bool,
    label: str,
) -> int:
    """Copy ``install/`` and ``userdata/`` trees from *src_root* into CSP."""
    dst_roots = live_roots(resource_dir)
    jobs = _collect_deploy_jobs(src_root, dst_roots)
    if not jobs:
        return 0

    wants_user = any(src.relative_to(src_root).parts[0] == USER for src, _dst in jobs)
    if wants_user and USER not in dst_roots:
        jobs = [
            (src, dst)
            for src, dst in jobs
            if src.relative_to(src_root).parts[0] != USER
        ]

    print(f"will install {len(jobs)} {label} tool DB(s)")
    for src, dst in jobs:
        rel = src.relative_to(src_root).as_posix()
        print(f"  {rel}  ->  {dst}")
        if dry_run:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    if dry_run:
        print("[dry-run] tool DB install skipped")
    else:
        print(f"\ndone -- {len(jobs)} {label} tool DB(s) installed.")
    return len(jobs)


def deploy_install_seed(
    resource_dir: Path,
    src_root: Path,
    *,
    dry_run: bool,
    label: str,
) -> int:
    """Copy only the bundled install seed — never the userdata tree."""
    install_src = src_root / SEED
    if not install_src.is_dir():
        return 0
    seed_dst = live_roots(resource_dir)[SEED]
    jobs = [
        (src, seed_dst / src.relative_to(install_src))
        for src in sorted(install_src.rglob("*"))
        if src.is_file()
    ]
    if not jobs:
        return 0

    print(f"will install {len(jobs)} {label} install seed file(s)")
    for src, dst in jobs:
        rel = src.relative_to(install_src).as_posix()
        print(f"  install/{rel}  ->  {dst}")
        if dry_run:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    if dry_run:
        print("[dry-run] install seed skipped")
    elif jobs:
        print(f"  tool DBs: installed {len(jobs)} install seed file(s)")
    return len(jobs)


def patch_node_names(
    db: Path,
    table: dict[str, str],
    *,
    dry_run: bool,
) -> int:
    """Translate stock ``NodeName`` values in one live DB, in place."""
    updates = {
        pid: table[name]
        for pid, name in _node_names(db).items()
        if name in table and table[name] != name
    }
    if not updates:
        return 0
    if dry_run:
        return len(updates)
    con = sqlite3.connect(db)
    try:
        con.executemany(
            "update Node set NodeName=? where _PW_ID=?",
            [(tgt, pid) for pid, tgt in updates.items()],
        )
        con.commit()
    finally:
        con.close()
    return len(updates)


def patch_live_dbs(
    resource_dir: Path,
    table: dict[str, str],
    tag: str,
    *,
    dry_run: bool,
) -> int:
    """Patch tool DBs under one live root (install seed or userdata)."""
    roots = live_roots(resource_dir)
    if tag not in roots:
        return 0
    if not table:
        return 0

    total = 0
    for abs_path, rel in discover_live(roots[tag], tag):
        try:
            n = patch_node_names(abs_path, table, dry_run=dry_run)
        except OSError as e:
            print(f"  tool DBs: WARNING — could not patch {tag}/{rel.as_posix()}: {e}")
            continue
        except sqlite3.OperationalError as e:
            if "readonly" in str(e).lower() or "read-only" in str(e).lower():
                print(
                    f"  tool DBs: WARNING — {tag}/{rel.as_posix()} is read-only "
                    f"(run as administrator to patch install seed)"
                )
                continue
            raise
        if n:
            total += n
            action = "would patch" if dry_run else "patched"
            print(f"  tool DBs: {action} {n} name(s) in {tag}/{rel.as_posix()}")
    return total


def patch_userdata(
    resource_dir: Path,
    table: dict[str, str],
    *,
    dry_run: bool,
) -> int:
    """Patch live user-data tool DBs without replacing the tool tree."""
    if USER not in live_roots(resource_dir):
        return 0
    if not table:
        print("  tool DBs: no translation dictionary — skipping userdata patch")
        return 0
    return patch_live_dbs(resource_dir, table, USER, dry_run=dry_run)


def restore_english_tool_dbs(
    resource_dir: Path,
    *,
    dry_run: bool,
) -> None:
    """Put stock English tool names back without wiping custom tool layout."""
    table = reverse_translation_dict()
    if not table:
        print("  tool DBs: no translation dictionary — skipping restore")
        return

    print("  tool DBs: reversing tool-name translations in place")
    patch_live_dbs(resource_dir, table, USER, dry_run=dry_run)
    patch_live_dbs(resource_dir, table, SEED, dry_run=dry_run)


def sync_tool_dbs(
    resource_dir: Path,
    *,
    language: str,
    dry_run: bool = False,
) -> None:
    """Install or restore tool-palette databases for *language*."""
    if language == "english":
        restore_english_tool_dbs(resource_dir, dry_run=dry_run)
        if not dry_run:
            print("  restart CSP; tool palette names are English again.")
        return

    src = bundle_root(language)
    if not (src.is_dir() and any(src.rglob("*"))):
        print(f"  tool DBs: no {language} bundle at {src} — skipping")
        return

    if user_root() is None:
        print("  tool DBs: WARNING — CSP user data not found.")
        print("           Launch Clip Studio Paint once, then switch again.")
        print("           Only the install seed will be patched this time.")

    if not dry_run:
        _backup_live(resource_dir, dry_run=False)

    table = load_translation_dict()
    deploy_install_seed(resource_dir, src, dry_run=dry_run, label="patched")
    patch_userdata(resource_dir, table, dry_run=dry_run)

    if not dry_run:
        print("  restart CSP; tool palette names now use the selected pack.")

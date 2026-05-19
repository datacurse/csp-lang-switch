#!/usr/bin/env python3
"""
materials.py
============
Translate the names of CSP's built-in materials -- the paper textures, tones,
patterns, 3D primitives, speech balloons, frame templates and pose presets
shown in the Material palette and the "select material" dialogs.

Those names live in CSP's per-user material data, in **two layers**:

  1. The **catalog index** -- a SQLite DB
     `%APPDATA%/CELSYSUserData/CELSYS/CLIPStudioCommon/MaterialDB/CatalogMaterial.cmdb`.
     CSP draws the picker's **tag filter chips** from its `Tag.Title` column.
     (Its `MaterialModifier.MaterialName` is only a search / user-rename field --
     NOT the displayed material name, so it is left alone.)

  2. The **per-pack catalog files** -- every material is one pack folder under
     `.../CLIPStudioCommon/Material/Install/` and `.../Install2/` (1,573 packs),
     each holding a `catalog.xml` (manifest) and a `catalogMaterial.cac` (the
     binary catalog cache CSP actually reads). The **displayed material name**
     is the `<name>` element / `.cac` string here.

So translating materials means: patch `Tag.Title` in the `.cmdb`, and patch the
`<name>` in every pack's `catalog.xml` + `catalogMaterial.cac`.

The `.cac` is a sequential binary stream with no offset table, and each name is
stored as `[uint16-LE byte-length][UTF-8 bytes]`; a name is therefore patched by
an exact `[len][old]` -> `[len][new]` byte substitution -- safe even though the
Russian text is longer (the file simply grows).

All materials are **built-in** -- the catalog reports `Downloaded = 0` for every
row. A name with no translation in the worksheet (a user-created / imported
material) is left as-is.

Pipeline (run from the repo root: python src/materials.py <cmd>)
--------
  backup    copy the catalog DB + every pack's catalog files -> materials/
  extract   collect every material + tag name -> translation/materials.csv
  ...translate the `target` column of materials.csv...
  apply     write the translations into patched copies -> russian-materials/
  install   copy the patched files into the live CSP user data
  restore   copy the originals back

`install` / `restore` write into `%APPDATA%` (no elevation needed) and refuse to
run while CSP is open -- CSP locks the files. Standard library only.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import shutil
import sqlite3
import struct
import sys
from pathlib import Path

import install  # reuse check_csp_closed / confirm

# ----------------------------------------------------------------------
# Project paths
# ----------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
MATERIALS_DIR = ROOT / "materials"             # originals -- the backup
BUILD_DIR = ROOT / "russian-materials"         # patched -- the Russian build
WORKSHEET = ROOT / "translation" / "materials.csv"

DB_NAME = "CatalogMaterial.cmdb"
# Catalog files live under materials/<CATALOG>/<rel-to-Material-dir>/...
CATALOG = "catalog"
PACK_FILES = ("catalog.xml", "catalogMaterial.cac")
INSTALL_DIRS = ("Install", "Install2")
NAME_RE = re.compile(r"<name>([^<]*)</name>")


# ----------------------------------------------------------------------
# Locating the live CSP material data
# ----------------------------------------------------------------------
def common_dir() -> Path:
    """`%APPDATA%/CELSYSUserData/CELSYS/CLIPStudioCommon`, or exit."""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        sys.exit("error: %APPDATA% is not set -- cannot locate CSP user data")
    p = Path(appdata) / "CELSYSUserData" / "CELSYS" / "CLIPStudioCommon"
    if not p.is_dir():
        sys.exit(f"error: CSP user data not found:\n       {p}\n"
                 f"       (run CSP at least once)")
    return p


def catalog_db() -> Path:
    return common_dir() / "MaterialDB" / DB_NAME


def material_dir() -> Path:
    return common_dir() / "Material"


def live_packs() -> list[Path]:
    """Every material-pack folder (holding both catalog files) in the install."""
    md = material_dir()
    out = []
    for sub in INSTALL_DIRS:
        base = md / sub
        if base.is_dir():
            for xml in base.rglob("catalog.xml"):
                if (xml.parent / "catalogMaterial.cac").is_file():
                    out.append(xml.parent)
    return sorted(out)


# ----------------------------------------------------------------------
# Names
# ----------------------------------------------------------------------
def xml_names(xml: Path) -> list[str]:
    """The non-empty <name> values in a catalog.xml, in order."""
    return [n for n in NAME_RE.findall(xml.read_text("utf-8")) if n.strip()]


def tag_titles(db: Path) -> dict[int, str]:
    """{_PW_ID: Title} of the Tag table, read-only."""
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return {pid: t for pid, t in con.execute(
            "select _PW_ID, Title from Tag where Title is not null and Title<>''")}
    finally:
        con.close()


def has_cyrillic(s: str) -> bool:
    return any(0x0400 <= ord(c) <= 0x04FF for c in s)


# CSP marks the per-pack .cac files *hidden*; open('wb') (which shutil uses)
# fails on an existing hidden file on Windows. Clear the attributes to copy
# over it, then restore them.
_GETATTR = _SETATTR = None
if os.name == "nt":
    import ctypes
    _GETATTR = ctypes.windll.kernel32.GetFileAttributesW
    _SETATTR = ctypes.windll.kernel32.SetFileAttributesW
_FILE_ATTRIBUTE_NORMAL = 0x80
_INVALID_ATTRS = (None, -1, 0xFFFFFFFF)


def copy_over(src: Path, dst: Path) -> None:
    """Copy src onto dst, restoring dst's original hidden/read-only attributes."""
    orig = _GETATTR(str(dst)) if (_GETATTR and dst.exists()) else None
    if orig not in _INVALID_ATTRS:
        _SETATTR(str(dst), _FILE_ATTRIBUTE_NORMAL)
    shutil.copy2(src, dst)
    if orig not in _INVALID_ATTRS:
        _SETATTR(str(dst), orig)


# ----------------------------------------------------------------------
# Worksheet -- a source->target dictionary
# ----------------------------------------------------------------------
def load_dict() -> dict[str, str]:
    """{source: target} from materials.csv -- blank / identical targets dropped."""
    if not WORKSHEET.exists():
        sys.exit(f"error: {WORKSHEET} not found -- run 'extract' first")
    out = {}
    for r in csv.DictReader(open(WORKSHEET, encoding="utf-8-sig")):
        t = r.get("target", "").strip()
        if t and t != r["source"]:
            out[r["source"]] = t
    return out


def existing_targets() -> dict[str, str]:
    if not WORKSHEET.exists():
        return {}
    return {r["source"]: r.get("target", "")
            for r in csv.DictReader(open(WORKSHEET, encoding="utf-8-sig"))
            if r.get("source")}


# ----------------------------------------------------------------------
# .cac patching -- exact [uint16-LE len][UTF-8] substitution
# ----------------------------------------------------------------------
def cac_record(text: str) -> bytes:
    b = text.encode("utf-8")
    return struct.pack("<H", len(b)) + b


def patch_cac(data: bytes, table: dict[str, str], names: list[str]) -> bytes:
    """Replace every length-prefixed catalog name in a .cac with its Russian.

    Only the names belonging to this pack (`names`, from its catalog.xml) are
    touched, and each is matched together with its exact 2-byte length prefix --
    so a short name can never match inside a longer one."""
    for en in names:
        ru = table.get(en)
        if ru and ru != en:
            data = data.replace(cac_record(en), cac_record(ru))
    return data


def patch_xml(text: str, table: dict[str, str]) -> str:
    """Replace <name>EN</name> with <name>RU</name> for every translated name."""
    def repl(m: re.Match) -> str:
        ru = table.get(m.group(1))
        return f"<name>{ru}</name>" if ru else m.group(0)
    return NAME_RE.sub(repl, text)


# ----------------------------------------------------------------------
# Commands
# ----------------------------------------------------------------------
def cmd_backup(args) -> None:
    # --- catalog index DB ---
    db_dst = MATERIALS_DIR / DB_NAME
    if db_dst.exists():
        print(f"  cmdb: kept (already saved)")
    else:
        live = catalog_db()
        if not live.is_file():
            sys.exit(f"error: catalog DB not found: {live}")
        if any(has_cyrillic(t) for t in tag_titles(live).values()):
            sys.exit("error: the live catalog DB already holds Cyrillic tags -- "
                     "it is patched, not a clean original. Restore it first.")
        MATERIALS_DIR.mkdir(exist_ok=True)
        shutil.copy2(live, db_dst)
        print(f"  cmdb: copied")

    # --- per-pack catalog files ---
    md = material_dir()
    packs = live_packs()
    copied = kept = 0
    for pack in packs:
        rel = pack.relative_to(md)
        for fn in PACK_FILES:
            dst = MATERIALS_DIR / CATALOG / rel / fn
            if dst.exists():
                kept += 1
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(pack / fn, dst)
                copied += 1
    print(f"backup -> {MATERIALS_DIR}")
    print(f"  catalog files: copied {copied}, kept {kept} ({len(packs)} packs)")


def cmd_extract(args) -> None:
    db = MATERIALS_DIR / DB_NAME
    cat = MATERIALS_DIR / CATALOG
    if not db.is_file() or not cat.is_dir():
        sys.exit(f"error: nothing in {MATERIALS_DIR} -- run 'backup' first")

    names: set[str] = set(tag_titles(db).values())
    n_packs = 0
    for xml in cat.rglob("catalog.xml"):
        names |= set(xml_names(xml))
        n_packs += 1

    keep = existing_targets()
    rows = [(n, keep.get(n, "")) for n in sorted(names, key=str.lower)]

    WORKSHEET.parent.mkdir(exist_ok=True)
    with open(WORKSHEET, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["source", "target"])
        w.writerows(rows)

    done = sum(1 for _s, t in rows if t.strip())
    print(f"extract -> {WORKSHEET}")
    print(f"  {len(rows)} distinct names (tags + {n_packs} pack catalogs)")
    print(f"  {done} translated, {len(rows) - done} to go")


def cmd_apply(args) -> None:
    table = load_dict()
    db = MATERIALS_DIR / DB_NAME
    cat = MATERIALS_DIR / CATALOG
    if not db.is_file() or not cat.is_dir():
        sys.exit(f"error: nothing in {MATERIALS_DIR} -- run 'backup' first")
    BUILD_DIR.mkdir(exist_ok=True)

    # --- catalog index DB: translate Tag.Title ---
    db_dst = BUILD_DIR / DB_NAME
    shutil.copy2(db, db_dst)
    os.chmod(db_dst, 0o644)
    before = tag_titles(db)
    con = sqlite3.connect(db_dst)
    try:
        updates = [(table[t], pid) for pid, t in before.items() if t in table]
        con.executemany("update Tag set Title=? where _PW_ID=?", updates)
        con.commit()
    finally:
        con.close()
    after = tag_titles(db_dst)                 # round-trip check
    for pid, t in before.items():
        if t in table and after.get(pid) != table[t]:
            sys.exit(f"error: cmdb round-trip check failed for tag #{pid}")
    tags_n = len(updates)

    # --- per-pack catalog files ---
    packs = names_n = cac_fail = 0
    untranslated: set[str] = set()
    for xml_src in sorted(cat.rglob("catalog.xml")):
        pack_rel = xml_src.parent.relative_to(cat)
        cac_src = xml_src.parent / "catalogMaterial.cac"
        names = xml_names(xml_src)
        untranslated |= {n for n in names if n not in table}
        names_n += sum(1 for n in names if n in table)

        out_dir = BUILD_DIR / CATALOG / pack_rel
        out_dir.mkdir(parents=True, exist_ok=True)

        # catalog.xml
        new_xml = patch_xml(xml_src.read_text("utf-8"), table)
        (out_dir / "catalog.xml").write_text(new_xml, encoding="utf-8")

        # catalogMaterial.cac
        raw = cac_src.read_bytes()
        new_cac = patch_cac(raw, table, names)
        (out_dir / "catalogMaterial.cac").write_bytes(new_cac)

        # verify: every translated name's English record is gone, Russian present
        for n in set(names):
            ru = table.get(n)
            if ru and ru != n:
                if cac_record(n) in new_cac or cac_record(ru) not in new_cac:
                    cac_fail += 1
        packs += 1

    if cac_fail:
        sys.exit(f"error: {cac_fail} .cac round-trip check(s) failed")

    print(f"apply -> {BUILD_DIR}")
    print(f"  cmdb: {tags_n} tag(s) translated")
    print(f"  catalog: {packs} packs patched, {names_n} material-name "
          f"occurrence(s) translated")
    if untranslated:
        print(f"  note: {len(untranslated)} name(s) have no translation and "
              f"stay as-is (user-created / imported materials)")


def _deploy(src_root: Path, label: str, args) -> None:
    db_src = src_root / DB_NAME
    cat_src = src_root / CATALOG
    if not db_src.is_file() or not cat_src.is_dir():
        sys.exit(f"error: nothing in {src_root} -- run the earlier step first")

    install.check_csp_closed(args.force)
    md = material_dir()
    jobs = [(db_src, catalog_db())]
    for f in sorted(cat_src.rglob("*")):
        if f.is_file():
            jobs.append((f, md / f.relative_to(cat_src)))

    print(f"will install the {label} material data "
          f"({len(jobs)} files: catalog DB + {len(jobs) - 1} pack files)")
    if args.dry_run:
        for s, d in jobs[:6]:
            print(f"  {s}  ->  {d}")
        print(f"  ... ({len(jobs)} total)")
        print("[dry-run] nothing was changed")
        return
    if not install.confirm("proceed?", args.yes):
        print("aborted")
        return
    for s, d in jobs:
        if not d.parent.is_dir():
            sys.exit(f"error: target folder missing: {d.parent}")
        copy_over(s, d)
    print(f"\ndone -- {label} material data installed ({len(jobs)} files).")


def cmd_install(args) -> None:
    _deploy(BUILD_DIR, "patched", args)
    print("restart CSP; material names are now Russian.")
    print("run 'python src/materials.py restore' to undo.")


def cmd_restore(args) -> None:
    _deploy(MATERIALS_DIR, "original", args)
    print("restart CSP; material names are English again.")


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------
def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="materials.py",
        description="Translate CSP material-catalog names.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="print what would happen, change nothing")
    parser.add_argument("--yes", action="store_true",
                        help="skip the confirmation prompt")
    parser.add_argument("--force", action="store_true",
                        help="proceed even if CSP appears to be running")
    parser.add_argument("command",
                        choices=("backup", "extract", "apply",
                                 "install", "restore"),
                        help="pipeline step to run")

    args = parser.parse_args(argv)
    {"backup": cmd_backup, "extract": cmd_extract, "apply": cmd_apply,
     "install": cmd_install, "restore": cmd_restore}[args.command](args)


if __name__ == "__main__":
    main()

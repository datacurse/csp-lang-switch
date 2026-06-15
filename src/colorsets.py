#!/usr/bin/env python3
"""
colorsets.py
============
Translate the names shown in CSP's Color Set palette and the "Edit color sets"
dialog.

Those names ("Default color set", "Additional color set", …) are NOT in the
main UI resource bundles that `batch.py` translates. They live inside:

  * **install seed** -- `<CSP>/Settings/PAINT/ColorSet/english/*.cls`
  * **user data** -- `%APPDATA%/.../CLIPStudioPaintVer*/ColorSet/default.pcs`
    (SQLite table `colorset`, column `colorsetname`, plus names embedded in
    `colorsetdata` blobs)

CSP copies the seed into user data on first run, then keeps using the profile
copy — the same trap as `tools.py`.

Pipeline (run from the repo root: python src/colorsets.py <cmd>)
--------
  backup    copy seed .cls + user default.pcs -> langs/english/colorsets/
  extract   collect distinct set names -> translation/colorsets.csv
  ...translate the `target` column...
  apply     write patched copies -> langs/<language>/colorsets/
  install   deploy into the live CSP install + user data
  restore   copy the English originals back
"""

from __future__ import annotations

import argparse
import csv
import os
import shutil
import sqlite3
import sys
from pathlib import Path

from common import find_csp_resource, ensure_admin, check_csp_closed, confirm
from version import LANGS_ROOT, ROOT

COLORSETS_DIR = LANGS_ROOT / "english" / "colorsets"
BUILD_DIR = LANGS_ROOT / "russian" / "colorsets"
WORKSHEET = ROOT / "translation" / "colorsets.csv"

SEED = "install"
USER = "userdata"
SEED_LANG = "english"
CLS_MAGIC = b"SLCC"
NAME_OFFSET = 12


def configure_language(language: str) -> None:
    global BUILD_DIR
    BUILD_DIR = LANGS_ROOT / language / "colorsets"


def seed_root(explicit: str | None) -> Path:
    p = find_csp_resource(explicit).parent / "Settings" / "PAINT" / "ColorSet"
    if not p.is_dir():
        sys.exit(f"error: ColorSet folder not found: {p}")
    return p


def user_root() -> Path | None:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    base = Path(appdata) / "CELSYSUserData" / "CELSYS"
    vers = sorted(base.glob("CLIPStudioPaintVer*")) if base.is_dir() else []
    return vers[-1] if vers else None


def roots(explicit: str | None) -> dict[str, Path]:
    out = {SEED: seed_root(explicit)}
    u = user_root()
    if u:
        out[USER] = u / "ColorSet"
    return out


def is_cls(path: Path) -> bool:
    if not path.is_file() or path.suffix.lower() != ".cls":
        return False
    try:
        return path.read_bytes()[:4] == CLS_MAGIC
    except OSError:
        return False


def is_pcs(path: Path) -> bool:
    if not path.is_file() or path.suffix.lower() != ".pcs":
        return False
    try:
        return path.read_bytes()[:15] == b"SQLite format 3"
    except OSError:
        return False


def read_cls_name(data: bytes) -> str | None:
    if len(data) < NAME_OFFSET + 1 or data[:4] != CLS_MAGIC:
        return None
    end = data.find(b"\x00", NAME_OFFSET)
    if end < NAME_OFFSET:
        return None
    raw = data[NAME_OFFSET:end]
    for enc in ("utf-8", "cp932"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return None


def discover(root: Path, tag: str) -> list[tuple[Path, Path]]:
    out: list[tuple[Path, Path]] = []
    if tag == SEED:
        lang_dir = root / SEED_LANG
        if lang_dir.is_dir():
            for f in sorted(lang_dir.glob("*.cls")):
                if is_cls(f):
                    out.append((f, Path(SEED_LANG) / f.name))
    else:
        for f in sorted(root.glob("*.pcs")):
            if is_pcs(f):
                out.append((f, f.name))
    return out


def pcs_names(path: Path) -> list[str]:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        if not con.execute(
            "select name from sqlite_master where type='table' and name='colorset'"
        ).fetchone():
            return []
        return [r[0] for r in con.execute(
            "select colorsetname from colorset "
            "where colorsetname is not null and colorsetname<>'' "
            "order by _PW_ID")]
    finally:
        con.close()


def has_cyrillic(s: str) -> bool:
    return any(0x0400 <= ord(c) <= 0x04FF for c in s)


def patch_utf8_name(data: bytes, old: str, new: str) -> bytes:
    """Replace length-prefixed and raw UTF-8 name occurrences."""
    ob, nb = old.encode("utf-8"), new.encode("utf-8")
    out = data
    for width in (2, 4):
        old_p = len(ob).to_bytes(width, "little") + ob
        new_p = len(nb).to_bytes(width, "little") + nb
        out = out.replace(old_p, new_p)
    out = out.replace(ob, nb)
    return out


def patch_cls(data: bytes, table: dict[str, str]) -> bytes:
    name = read_cls_name(data)
    if not name or name not in table:
        return data
    return patch_utf8_name(data, name, table[name])


def patch_pcs(path: Path, table: dict[str, str]) -> None:
    """Patch display names via SQLite only -- never edit the .pcs bytes directly."""
    con = sqlite3.connect(path)
    try:
        for src, tgt in table.items():
            con.execute(
                "update colorset set colorsetname=? where colorsetname=?",
                (tgt, src),
            )
        rows = con.execute(
            "select _PW_ID, colorsetdata from colorset "
            "where colorsetdata is not null"
        ).fetchall()
        for row_id, blob in rows:
            patched = blob
            for src, tgt in table.items():
                patched = patch_utf8_name(patched, src, tgt)
            if patched != blob:
                con.execute(
                    "update colorset set colorsetdata=? where _PW_ID=?",
                    (patched, row_id),
                )
        con.commit()
    finally:
        con.close()


def load_dict() -> dict[str, str]:
    if not WORKSHEET.exists():
        sys.exit(f"error: {WORKSHEET} not found -- run 'extract' first")
    out: dict[str, str] = {}
    for r in csv.DictReader(open(WORKSHEET, encoding="utf-8-sig")):
        t = r.get("target", "").strip()
        if t:
            out[r["source"]] = t
    return out


def restore_dict() -> dict[str, str]:
    """Map translated names back to English for restore."""
    return {tgt: src for src, tgt in load_dict().items()}


def _paired_names_from_build() -> dict[str, str]:
    """English -> patched names by comparing the backup tree to BUILD_DIR."""
    table: dict[str, str] = {}
    if not BUILD_DIR.is_dir():
        return table
    for ru_path in sorted(p for p in BUILD_DIR.rglob("*") if p.is_file()):
        rel = ru_path.relative_to(BUILD_DIR)
        en_path = COLORSETS_DIR / rel
        if not en_path.is_file():
            continue
        if is_cls(ru_path):
            en = read_cls_name(en_path.read_bytes())
            ru = read_cls_name(ru_path.read_bytes())
            if en and ru:
                table[en] = ru
        elif is_pcs(ru_path):
            en_names = pcs_names(en_path)
            ru_names = pcs_names(ru_path)
            if len(en_names) == len(ru_names):
                for en, ru in zip(en_names, ru_names):
                    if en and ru:
                        table[en] = ru
    return table


def deploy_table(*, to_russian: bool) -> dict[str, str]:
    """Name map for install/restore; falls back to backup vs build when no CSV."""
    if WORKSHEET.is_file():
        return load_dict() if to_russian else restore_dict()
    paired = _paired_names_from_build()
    if not paired:
        sys.exit(f"error: {WORKSHEET} not found -- run 'extract' first")
    if to_russian:
        return paired
    return {tgt: src for src, tgt in paired.items()}


def existing_targets() -> dict[str, str]:
    if not WORKSHEET.exists():
        return {}
    return {r["source"]: r.get("target", "")
            for r in csv.DictReader(open(WORKSHEET, encoding="utf-8-sig"))
            if r.get("source")}


def backed_up() -> list[tuple[str, Path]]:
    out: list[tuple[str, Path]] = []
    for tag in (SEED, USER):
        base = COLORSETS_DIR / tag
        if not base.is_dir():
            continue
        for f in sorted(p for p in base.rglob("*") if p.is_file()):
            rel = f.relative_to(base)
            out.append((tag, rel))
    return out


def cmd_backup(args) -> None:
    copied, kept, skipped = [], [], []
    for tag, root in roots(args.csp).items():
        for abspath, rel in discover(root, tag):
            dst = COLORSETS_DIR / tag / rel
            if dst.exists():
                kept.append(f"{tag}/{rel}")
                continue
            if tag == SEED and is_cls(abspath):
                name = read_cls_name(abspath.read_bytes())
                if name and has_cyrillic(name):
                    skipped.append(f"{tag}/{rel}")
                    continue
            if tag == USER and is_pcs(abspath):
                if any(has_cyrillic(n) for n in pcs_names(abspath)):
                    skipped.append(f"{tag}/{rel}")
                    continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(abspath, dst)
            copied.append(f"{tag}/{rel}")

    print(f"backup -> {COLORSETS_DIR}")
    print(f"  copied {len(copied)} file(s)")
    if kept:
        print(f"  kept {len(kept)} already in colorsets/ (left untouched)")
    if skipped:
        print(f"  SKIPPED {len(skipped)} already-patched file(s):")
        for p in skipped:
            print(f"    {p}")


def cmd_extract(args) -> None:
    files = backed_up()
    if not files:
        sys.exit(f"error: nothing in {COLORSETS_DIR} -- run 'backup' first")

    ja_map: dict[str, str] = {}
    paint = seed_root(args.csp)
    for tag, rel in files:
        if tag != SEED:
            continue
        ja_path = paint / "japanese" / rel.name
        if not ja_path.is_file():
            continue
        en = read_cls_name((COLORSETS_DIR / tag / rel).read_bytes())
        ja = read_cls_name(ja_path.read_bytes())
        if en and ja and en not in ja_map:
            ja_map[en] = ja

    names: set[str] = set()
    for tag, rel in files:
        path = COLORSETS_DIR / tag / rel
        if is_cls(path):
            n = read_cls_name(path.read_bytes())
            if n:
                names.add(n)
        elif is_pcs(path):
            names.update(pcs_names(path))

    keep = existing_targets()
    rows = [(n, ja_map.get(n, ""), keep.get(n, "")) for n in sorted(names)]

    WORKSHEET.parent.mkdir(exist_ok=True)
    with open(WORKSHEET, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["source", "japanese", "target"])
        w.writerows(rows)

    done = sum(1 for *_, t in rows if t.strip())
    print(f"extract -> {WORKSHEET}")
    print(f"  {len(rows)} distinct color-set name(s)")
    print(f"  {done} translated, {len(rows) - done} to go")


def cmd_apply(args) -> None:
    table = load_dict()
    files = backed_up()
    if not files:
        sys.exit(f"error: nothing in {COLORSETS_DIR} -- run 'backup' first")

    patched_n = 0
    untranslated: set[str] = set()
    for tag, rel in files:
        src = COLORSETS_DIR / tag / rel
        dst = BUILD_DIR / tag / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        os.chmod(dst, 0o644)

        if is_cls(dst):
            data = dst.read_bytes()
            name = read_cls_name(data)
            if name and name not in table:
                untranslated.add(name)
            new_data = patch_cls(data, table)
            if new_data != data:
                dst.write_bytes(new_data)
                patched_n += 1
        elif is_pcs(dst):
            names = pcs_names(src)
            untranslated.update(n for n in names if n not in table)
            patch_pcs(dst, table)
            patched_n += 1

    print(f"apply -> {BUILD_DIR}")
    print(f"  patched {patched_n} file(s)")
    if untranslated:
        print(f"  note: {len(untranslated)} name(s) have no translation:")
        for n in sorted(untranslated):
            print(f"    {n!r}")


def _deploy(src_root: Path, label: str, args, *, to_russian: bool) -> None:
    """Deploy color-set translations.

    * install seed ``.cls`` files are copied (needs admin).
    * the live ``default.pcs`` is patched in place via SQLite so we never
      replace the user's profile DB wholesale.
    """
    dst_roots = roots(args.csp)
    table = deploy_table(to_russian=to_russian)
    copies: list[tuple[Path, Path, str]] = []
    pcs_dst = dst_roots.get(USER, Path()) / "default.pcs"

    for src in sorted(p for p in src_root.rglob("*") if p.is_file()):
        rel = src.relative_to(src_root)
        tag = rel.parts[0]
        sub = Path(*rel.parts[1:])
        if tag not in dst_roots:
            continue
        if tag == USER and sub.name == "default.pcs":
            continue  # handled below
        if tag == SEED:
            copies.append((src, dst_roots[tag] / sub, rel.as_posix()))

    if not copies and not pcs_dst:
        sys.exit(f"error: nothing to install from {src_root}")

    check_csp_closed(args.force)
    needs_admin = bool(copies)
    if not args.dry_run and needs_admin:
        ensure_admin()

    n = len(copies) + (1 if pcs_dst else 0)
    print(f"will install {n} {label} color-set change(s)")
    for src, dst, rel in copies:
        print(f"  {rel}  ->  {dst}")
    if pcs_dst:
        names = "Russian" if to_russian else "English"
        print(f"  userdata/default.pcs  ->  patch {names} names in place ({pcs_dst})")
    if args.dry_run:
        print("[dry-run] nothing was changed")
        return
    if not confirm("proceed?", args.yes):
        print("aborted")
        return
    for src, dst, _rel in copies:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    if pcs_dst.is_file():
        patch_pcs(pcs_dst, table)
    elif pcs_dst.parent.is_dir():
        seed_pcs = src_root / USER / "default.pcs"
        if seed_pcs.is_file():
            pcs_dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(seed_pcs, pcs_dst)
            patch_pcs(pcs_dst, table)
    print(f"\ndone -- {n} {label} color-set change(s) installed.")


def cmd_install(args) -> None:
    _deploy(BUILD_DIR, "patched", args, to_russian=True)
    print("restart CSP; color-set names now use the selected pack.")
    print("run 'python src/colorsets.py restore' to undo.")


def cmd_restore(args) -> None:
    _deploy(COLORSETS_DIR, "original", args, to_russian=False)
    print("restart CSP; color-set names are English again.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="colorsets.py",
        description="Translate CSP Color Set palette names.",
    )
    parser.add_argument("--csp", metavar="DIR", help="CSP resource directory")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--language", default="russian",
                        help="community pack under langs/ (default: russian)")
    parser.add_argument("--keep-open", action="store_true",
                        help=argparse.SUPPRESS)
    parser.add_argument("command",
                        choices=("backup", "extract", "apply",
                                 "install", "restore"))
    args = parser.parse_args(argv)
    configure_language(args.language)
    try:
        {"backup": cmd_backup, "extract": cmd_extract, "apply": cmd_apply,
         "install": cmd_install, "restore": cmd_restore}[args.command](args)
    finally:
        if args.keep_open:
            try:
                input("\nPress Enter to close this window...")
            except EOFError:
                pass


if __name__ == "__main__":
    main()

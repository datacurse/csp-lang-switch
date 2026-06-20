#!/usr/bin/env python3
"""
batch.py
========
Orchestrator for translating CSP5 resource files across the whole project.

The per-file tools are already file-agnostic and stay unchanged:
  repack.py    -- export a worksheet / apply a translation
  audit.py     -- translation-consistency audit
  roundtrip.py -- byte-for-byte serialize(parse(f)) == f check

This script adds the layer above them: it knows the *set* of files to
translate (`translation/manifest.csv`), gives each one its own worksheet
folder, and folds the two manual glue steps from `TRANSLATION_WORKFLOW.md` --
dedupe (Step 2) and join (Step 5) -- into real subcommands.

Layout it manages
-----------------
  translation/manifest.csv               the file list (short,guid,slug,...)
  translation/files/<short>-<slug>/
      strings.csv         key,source,target worksheet (repack.py export output)
      unique.csv          one row per distinct source (translate this)
      word_frequency.csv  term-frequency aid for the glossary
  langs/<language>/ui/<guid>             patched build (repack.py apply output)

Subcommands  (run from the repo root: python src/batch.py <cmd> ...)
-----------
  status               progress table over every manifest file
  export   <id>...     export worksheet(s); skips files already exported
  export-all           export every not-yet-exported target file
  dedupe   <id>        build unique.csv + word_frequency.csv from strings.csv
  join     <id>        merge unique.csv translations back into strings.csv
  join-all             join every target worksheet that has unique.csv
  pack     <id>...     apply translation -> langs/<language>/ui, then round-trip
  pack-all             pack every target file that has a worksheet
  audit    [<id>]      consistency audit of one worksheet, or all of them

<id> is a file's short GUID or slug (e.g. 742DEA58 or main-ui). Use --force
with export to overwrite an existing worksheet.

No external dependencies (standard library only).
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import tempfile
from pathlib import Path

import csp5            # noqa: F401  (kept for parity / future use)
import repack
import roundtrip
import audit
from version import LANGS_ROOT, ROOT, DEFAULT_VERSION, SUPPORTED_VERSIONS, set_active_version


# ----------------------------------------------------------------------
# Project paths
# ----------------------------------------------------------------------
MANIFEST = ROOT / "translation" / "manifest.csv"
FILES_DIR = ROOT / "translation" / "files"
RESOURCE_DIR = LANGS_ROOT / "english" / "ui"
# The finished Japanese resources are the oracle for what is translatable UI
# text: export emits a record only where English and Japanese differ.
REFERENCE_DIR = LANGS_ROOT / "japanese" / "ui"
DEFAULT_LANGUAGE = "russian"


def configure_version(version: str) -> None:
    """Point batch paths at versions/<version>/langs/."""
    global LANGS_ROOT, RESOURCE_DIR, REFERENCE_DIR
    set_active_version(version)
    import version as ver
    LANGS_ROOT = ver.LANGS_ROOT
    RESOURCE_DIR = LANGS_ROOT / "english" / "ui"
    REFERENCE_DIR = LANGS_ROOT / "japanese" / "ui"

# Word tokenizer for the frequency aid: alpha runs only, lowercased. Digits are
# dropped on purpose (so "3D" contributes "d", matching the original glossary
# build documented in GLOSSARY.md).
_WORD = re.compile(r"[a-z']+")


# ----------------------------------------------------------------------
# Never-translate guard -- material-palette folder-tree LOCALE COPIES ONLY
# ----------------------------------------------------------------------
# 7F9F9530 stores the same category taxonomy three times:
#   block 6 (`6/1/`) -- English -- TRANSLATE (shown in the English UI slot)
#   block 5 (`5/1/`) -- Japanese parallel (261 nodes) -- NEVER TRANSLATE
#   block 7 (`7/1/`) -- Chinese parallel (141 nodes) -- NEVER TRANSLATE
#
# VERIFIED DANGER: writing Russian into block 5 makes CSP rebuild
# MaterialFolderTag.mfta on launch and delete all custom user material folders.
# Block 6 can be translated safely when 5/ and 7/ stay at stock JP/CN.
# See docs/VERIFIED_METHOD.md -> "Material palette folder tree in 7F9F9530".
#
# `_material_folder_sources()` still blocks the same English category names
# from being translated in OTHER resource files via source-text mapping.
NEVER_TRANSLATE: dict[str, tuple[str, ...]] = {
    "7F9F9530": ("5/1/", "7/1/"),
}

MATERIAL_FOLDER_GUID = "7F9F9530-3EF0-4be4-8E6B-1C3BF59C3754"
_material_folder_source_cache: frozenset[str] | None = None


def _material_folder_sources() -> frozenset[str]:
    """English category names from 7F9F9530 block 6.

    Used to stop `pack` from applying Russian folder-name translations to the
    same English source text in other resource files (e.g. 742DEA58). Block 6
    keys in 7F9F9530 itself are exempt via `_is_protected`.
    """
    global _material_folder_source_cache
    if _material_folder_source_cache is not None:
        return _material_folder_source_cache
    import csp5 as _csp5
    from repack import iter_records as _iter_records

    for ver in SUPPORTED_VERSIONS:
        stock = ROOT / "versions" / ver / "langs" / "english" / "ui" / MATERIAL_FOLDER_GUID
        if not stock.is_file():
            continue
        sources = {
            _lf(t)
            for k, _, t in _iter_records(_csp5.parse(stock.read_bytes()))
            if k.startswith("6/1/")
        }
        _material_folder_source_cache = frozenset(sources)
        return _material_folder_source_cache
    sys.exit("ERROR: cannot load material folder sources -- no stock 7F9F9530 found")


def _protected_prefixes(rec: dict) -> tuple[str, ...]:
    """Key prefixes that must never be translated for this resource file."""
    return NEVER_TRANSLATE.get(rec["short"], ())


def _is_protected(rec: dict, row: dict) -> bool:
    """True when this worksheet row must keep its English source."""
    if any(row["key"].startswith(p) for p in _protected_prefixes(rec)):
        return True
    if rec.get("short") == "7F9F9530" and row["key"].startswith("6/1/"):
        return False
    return _lf(row.get("source", "")) in _material_folder_sources()


def _drop_protected(rec: dict, rows: list[dict]) -> list[dict]:
    """Drop rows that must never be translated (by key prefix or source text).

    Removing the row entirely (rather than blanking its target) means `apply`
    never touches that string, so it keeps the English source from the stock
    resource it was exported from.
    """
    return [r for r in rows if not _is_protected(rec, r)]


def _target_for_source(source: str, trans: dict[str, str]) -> str:
    new = trans.get(_lf(source))
    if new is None:
        return source
    if "\r\n" in source:
        new = _lf(new).replace("\n", "\r\n")
    elif "\n" in source:
        new = _lf(new)
    return new


def _append_block6_tree_rows(
    rec: dict,
    rows: list[dict],
    trans: dict[str, str] | None = None,
) -> list[dict]:
    """Ensure every block-6 folder-tree key is present in the worksheet.

    repack export with --reference skips 6/1/ rows whose English text equals
    the Japanese resource at the same slot (short labels like "All").
    """
    if rec.get("short") != "7F9F9530":
        return rows
    src = resource_for(rec)
    if not src.is_file():
        return rows
    import csp5 as _csp5
    from repack import iter_records as _iter_records

    present = {r["key"] for r in rows}
    extra: list[dict] = []
    mapping = trans or {}
    for key, _, source in _iter_records(_csp5.parse(src.read_bytes())):
        if not key.startswith("6/1/") or key in present:
            continue
        extra.append({
            "key": key,
            "source": source,
            "target": _target_for_source(source, mapping) if mapping else source,
        })
    if not extra:
        return rows
    return rows + extra


# ----------------------------------------------------------------------
# Manifest
# ----------------------------------------------------------------------
def load_manifest() -> list[dict]:
    """Return the manifest rows in file order (one dict per resource file)."""
    if not MANIFEST.exists():
        sys.exit(f"ERROR: manifest not found at {MANIFEST}")
    with MANIFEST.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def resolve(manifest: list[dict], ident: str) -> dict:
    """Find a manifest row by short GUID, slug or full GUID (case-insensitive)."""
    low = ident.lower()
    for rec in manifest:
        if low in (rec["short"].lower(), rec["slug"].lower(), rec["guid"].lower()):
            return rec
    sys.exit(f"ERROR: '{ident}' matches no manifest file (try `batch.py status`).")


def folder_for(rec: dict) -> Path:
    """The per-file worksheet folder, translation/files/<short>-<slug>/."""
    return FILES_DIR / f"{rec['short']}-{rec['slug']}"


def worksheet_for(rec: dict) -> Path:
    return folder_for(rec) / "strings.csv"


def unique_for(rec: dict) -> Path:
    return folder_for(rec) / "unique.csv"


def freq_for(rec: dict) -> Path:
    return folder_for(rec) / "word_frequency.csv"


def resource_for(rec: dict) -> Path:
    return RESOURCE_DIR / rec["guid"]


def reference_for(rec: dict) -> Path:
    return REFERENCE_DIR / rec["guid"]


def output_dir(language: str) -> Path:
    return LANGS_ROOT / language / "ui"


def output_for(rec: dict, language: str = DEFAULT_LANGUAGE) -> Path:
    return output_dir(language) / rec["guid"]


# ----------------------------------------------------------------------
# CSV helpers -- always read/write UTF-8 with BOM, so Excel keeps Cyrillic.
# Whole files are read into memory before any write (a crash mid-write would
# otherwise destroy the worksheet -- see TRANSLATION_WORKFLOW.md gotchas).
# ----------------------------------------------------------------------
def _read_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _write_rows(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def _lf(s: str) -> str:
    """Normalize CRLF/CR to LF -- a line-ending-agnostic match key."""
    return s.replace("\r\n", "\n").replace("\r", "\n")


# ----------------------------------------------------------------------
# Subcommand: export
# ----------------------------------------------------------------------
def _export_one(rec: dict, force: bool) -> bool:
    """Export one file's worksheet. Return True if it ran, False if skipped."""
    ws = worksheet_for(rec)
    if ws.exists() and not force:
        print(f"SKIP   {rec['short']}-{rec['slug']}  "
              f"(worksheet exists; use --force to overwrite)")
        return False
    src = resource_for(rec)
    if not src.exists():
        print(f"SKIP   {rec['short']}-{rec['slug']}  "
              f"(resource file not found: {src})")
        return False
    ref = reference_for(rec)
    if not ref.exists():
        print(f"SKIP   {rec['short']}-{rec['slug']}  "
              f"(Japanese reference not found: {ref})")
        return False
    ws.parent.mkdir(parents=True, exist_ok=True)
    print(f"export {rec['short']}-{rec['slug']}")
    rc = repack.main(["export", str(src), str(ws), "--reference", str(ref)])
    if rc == 0:
        rows = _read_rows(ws)
        pruned = _drop_protected(rec, rows)
        kept = _append_block6_tree_rows(rec, pruned)
        if len(kept) != len(rows):
            _write_rows(ws, ["key", "source", "target"], kept)
            dropped = len(rows) - len(pruned)
            added = len(kept) - len(pruned)
            print(f"  worksheet: {len(rows)} export row(s) -> {len(kept)} "
                  f"({dropped} locale-copy dropped, {added} block-6 added)")
    return rc == 0


def cmd_export(args: argparse.Namespace) -> int:
    manifest = load_manifest()
    recs = [resolve(manifest, i) for i in args.ids]
    ran = sum(_export_one(r, args.force) for r in recs)
    print(f"\nExported {ran}/{len(recs)} worksheet(s).")
    return 0


def cmd_export_all(args: argparse.Namespace) -> int:
    manifest = load_manifest()
    targets = [r for r in manifest if r["target"] == "yes"]
    ran = sum(_export_one(r, args.force) for r in targets)
    print(f"\nExported {ran} new worksheet(s) "
          f"({len(targets) - ran} already present or skipped).")
    return 0


# ----------------------------------------------------------------------
# Subcommand: dedupe  (TRANSLATION_WORKFLOW.md Step 2 + Step 3 frequency pass)
# ----------------------------------------------------------------------
def cmd_dedupe(args: argparse.Namespace) -> int:
    rec = resolve(load_manifest(), args.id)
    ws = worksheet_for(rec)
    if not ws.exists():
        sys.exit(f"ERROR: no worksheet at {ws} -- run `batch.py export` first.")
    rows = _read_rows(ws)

    # Carry over any translations already done, keyed by source text. A source
    # is considered translated when its target differs from the English source.
    uniq = unique_for(rec)
    known: dict[str, str] = {}
    if uniq.exists():
        for r in _read_rows(uniq):
            if r.get("target"):
                known[r["source"]] = r["target"]
    for r in rows:
        if r["source"] not in known and r["target"] and r["target"] != r["source"]:
            known[r["source"]] = r["target"]

    # One row per distinct source, in first-seen order.
    seen: dict[str, str] = {}
    for r in rows:
        seen.setdefault(r["source"], known.get(r["source"], ""))
    _write_rows(uniq, ["source", "target"],
                [{"source": s, "target": t} for s, t in seen.items()])

    # Word-frequency aid for refining the glossary.
    counts: dict[str, int] = {}
    for r in rows:
        for w in _WORD.findall(r["source"].lower()):
            counts[w] = counts.get(w, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    _write_rows(freq_for(rec), ["word", "count"],
                [{"word": w, "count": c} for w, c in ranked])

    done = sum(1 for t in seen.values() if t)
    print(f"{rec['short']}-{rec['slug']}: {len(rows)} rows -> "
          f"{len(seen)} unique sources ({done} already translated)")
    print(f"  wrote {uniq}")
    print(f"  wrote {freq_for(rec)}  ({len(ranked)} distinct words)")
    print(f"  -> translate the empty `target` cells in {uniq.name}, "
          f"then `batch.py join {rec['short']}`")
    return 0


# ----------------------------------------------------------------------
# Subcommand: join  (TRANSLATION_WORKFLOW.md Step 5)
# ----------------------------------------------------------------------
def cmd_join(args: argparse.Namespace) -> int:
    rec = resolve(load_manifest(), args.id)
    ws, uniq = worksheet_for(rec), unique_for(rec)
    if not ws.exists():
        sys.exit(f"ERROR: no worksheet at {ws}.")
    if not uniq.exists():
        sys.exit(f"ERROR: no unique list at {uniq} -- run `batch.py dedupe` first.")

    # Read everything before writing -- never truncate the worksheet first.
    # Match by LF-normalized source: an editor (or a translator) may rewrite
    # unique.csv with different line endings than the worksheet, and an exact
    # match would then silently miss every multi-line string.
    trans = {_lf(r["source"]): r["target"] for r in _read_rows(uniq)}
    rows = _read_rows(ws)
    protected = _material_folder_sources()

    changed = 0
    for r in rows:
        if _is_protected(rec, r):
            if r["target"] != r["source"]:
                r["target"] = r["source"]
                changed += 1
            continue
        new = trans.get(_lf(r["source"]))
        if new is None:
            continue
        # Emit the translation with the worksheet source's newline style, so a
        # CRLF original keeps CRLF line breaks in the patched file.
        if "\r\n" in r["source"]:
            new = _lf(new).replace("\n", "\r\n")
        elif "\n" in r["source"]:
            new = _lf(new)
        if new != r["target"]:
            r["target"] = new
            changed += 1
    rows = _append_block6_tree_rows(rec, rows, trans)
    _write_rows(ws, ["key", "source", "target"], rows)

    print(f"{rec['short']}-{rec['slug']}: mapped {len(trans)} unique "
          f"translations into {len(rows)} worksheet rows ({changed} changed).")
    print(f"  wrote {ws}")
    return 0


def cmd_join_all(args: argparse.Namespace) -> int:
    manifest = load_manifest()
    targets = [r for r in manifest
               if r["target"] == "yes" and worksheet_for(r).exists()]
    if not targets:
        print("No exported target worksheets to join.")
        return 0
    ok = 0
    for rec in targets:
        try:
            sub = argparse.Namespace(id=rec["short"])
            cmd_join(sub)
            ok += 1
        except SystemExit:
            print(f"  FAIL: join failed for {rec['short']}-{rec['slug']}")
    print(f"\nJoined {ok}/{len(targets)} worksheet(s).")
    return 0 if ok == len(targets) else 1


# ----------------------------------------------------------------------
# Subcommand: pack  (repack.py apply + roundtrip.py verification)
# ----------------------------------------------------------------------
def _translations_by_source(rec: dict) -> dict[str, str]:
    """Return finished translations keyed by normalized English source text."""
    protected = _material_folder_sources()
    allow_folder_names = rec.get("short") == "7F9F9530"
    trans: dict[str, str] = {}
    uniq = unique_for(rec)
    if uniq.exists():
        for r in _read_rows(uniq):
            src = _lf(r["source"])
            if src in protected and not allow_folder_names:
                continue
            t = r.get("target")
            if t is not None and t != "":
                trans[src] = t
    if not trans:
        ws = worksheet_for(rec)
        if ws.exists():
            for r in _read_rows(ws):
                src = _lf(r["source"])
                if src in protected and not allow_folder_names:
                    continue
                t = (r.get("target") or "").strip()
                if t and t != r["source"]:
                    trans[src] = t
    return trans


def _worksheet_for_version(rec: dict) -> Path | None:
    """Build a pack worksheet with keys from the active version's stock.

    Translation `key` columns are version-specific. Re-export from the
    current RESOURCE_DIR and map targets by `source` so one shared
    unique.csv can pack both 5.0.0 and 5.0.4 correctly.
    """
    src, ref = resource_for(rec), reference_for(rec)
    if not src.exists() or not ref.exists():
        return None
    fd, tmp_name = tempfile.mkstemp(
        suffix=".csv", prefix=f"{rec['short']}-pack-")
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        if repack.main(["export", str(src), str(tmp), "--reference", str(ref)]) != 0:
            return None
        trans = _translations_by_source(rec)
        # Locale-copy keys (JP/CN blocks) are dropped so `apply` leaves them
        # at stock text -- see NEVER_TRANSLATE.
        rows = _drop_protected(rec, _read_rows(tmp))
        for r in rows:
            new = trans.get(_lf(r["source"]))
            if new is None:
                continue
            r["target"] = _target_for_source(r["source"], trans)
        rows = _append_block6_tree_rows(rec, rows, trans)
        _write_rows(tmp, ["key", "source", "target"], rows)
        return tmp
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def _pack_one(rec: dict, language: str) -> bool:
    """Apply a translation and round-trip-check the output. Return True on pass."""
    src, out = resource_for(rec), output_for(rec, language)
    if not src.exists():
        print(f"SKIP   {rec['short']}-{rec['slug']}  (resource file not found)")
        return False
    ws = _worksheet_for_version(rec)
    cleanup = ws is not None
    if ws is None:
        ws = worksheet_for(rec)
        cleanup = False
        if not ws.exists():
            print(f"SKIP   {rec['short']}-{rec['slug']}  (no worksheet)")
            return False
    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"pack   {rec['short']}-{rec['slug']}")
    try:
        if repack.main(["apply", str(src), str(ws), str(out)]) != 0:
            print(f"  FAIL: apply failed for {rec['short']}")
            return False
        ok, msg = roundtrip.check_file(out)
        print(f"  round-trip: {msg}")
        if not ok:
            print(f"  FAIL: {out} does not round-trip")
        return ok
    finally:
        if cleanup:
            ws.unlink(missing_ok=True)


def cmd_pack(args: argparse.Namespace) -> int:
    manifest = load_manifest()
    recs = [resolve(manifest, i) for i in args.ids]
    ok = sum(_pack_one(r, args.language) for r in recs)
    print(f"\nPacked {ok}/{len(recs)} file(s).")
    return 0 if ok == len(recs) else 1


def cmd_pack_all(args: argparse.Namespace) -> int:
    manifest = load_manifest()
    targets = [r for r in manifest
               if r["target"] == "yes"
               and (worksheet_for(r).exists() or unique_for(r).exists())]
    if not targets:
        print("No exported target worksheets to pack.")
        return 0
    ok = sum(_pack_one(r, args.language) for r in targets)
    print(f"\nPacked {ok}/{len(targets)} file(s).")
    return 0 if ok == len(targets) else 1


# ----------------------------------------------------------------------
# Subcommand: audit
# ----------------------------------------------------------------------
def cmd_audit(args: argparse.Namespace) -> int:
    manifest = load_manifest()
    if args.id:
        recs = [resolve(manifest, args.id)]
    else:
        recs = [r for r in manifest if worksheet_for(r).exists()]
    if not recs:
        print("No worksheets to audit.")
        return 0
    for rec in recs:
        ws = worksheet_for(rec)
        if not ws.exists():
            print(f"SKIP {rec['short']}-{rec['slug']} (no worksheet)\n")
            continue
        print(f"===== audit: {rec['short']}-{rec['slug']} =====")
        audit.main(str(ws))
        print()
    return 0


# ----------------------------------------------------------------------
# Subcommand: status
# ----------------------------------------------------------------------
def _translated_pct(ws: Path) -> tuple[int, int]:
    """(translated, total) over rows with a non-empty source."""
    rows = _read_rows(ws)
    total = sum(1 for r in rows if r["source"])
    done = sum(1 for r in rows if r["source"] and r["target"] != r["source"])
    return done, total


def cmd_status(args: argparse.Namespace) -> int:
    language = getattr(args, "language", DEFAULT_LANGUAGE)
    manifest = load_manifest()
    targets = [r for r in manifest if r["target"] in ("yes", "maybe")]
    skipped = [r for r in manifest if r["target"] == "no"]

    print(f"CSP translation status  --  {len(manifest)} resource files "
          f"({sum(r['target'] == 'yes' for r in manifest)} targets, "
          f"{sum(r['target'] == 'maybe' for r in manifest)} maybe, "
          f"{len(skipped)} skipped)\n")
    print(f"  {'short':9} {'slug':22} {'text':>6}  {'exported':9} "
          f"{'translated':12} packed")
    print(f"  {'-'*9} {'-'*22} {'-'*6}  {'-'*9} {'-'*12} {'-'*6}")

    packed_count = 0
    for rec in targets:
        ws = worksheet_for(rec)
        if ws.exists():
            done, total = _translated_pct(ws)
            pct = f"{100*done//total if total else 0:3d}% ({done})"
            exported = "yes"
        else:
            pct, exported = "-", "no"
        out = output_for(rec, language)
        if out.exists():
            stale = ws.exists() and out.stat().st_mtime < ws.stat().st_mtime
            packed = "stale" if stale else "yes"
            packed_count += 1
        else:
            packed = "no"
        flag = " " if rec["target"] == "yes" else "?"
        print(f" {flag}{rec['short']:9} {rec['slug']:22} "
              f"{rec['text_count']:>6}  {exported:9} {pct:12} {packed}")

    print(f"\n  {packed_count} file(s) packed into {output_dir(language)}.")
    if skipped:
        print(f"  skipped (non-target): "
              f"{', '.join(r['short'] for r in skipped)}")
    print("  '?' = `maybe` target (translate only for a fully localized build).")
    return 0


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------
def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--version", default=DEFAULT_VERSION, choices=SUPPORTED_VERSIONS,
        help="CSP version under versions/<ver>/langs/ (default: 5.0.0)",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("status", help="progress table over every manifest file")
    p.add_argument("--language", default=DEFAULT_LANGUAGE,
                   help="packed-build language to check (default: russian)")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("export", help="export worksheet(s) for the given files")
    p.add_argument("ids", nargs="+", help="file id(s): short GUID or slug")
    p.add_argument("--force", action="store_true",
                   help="overwrite an existing worksheet")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("export-all", help="export every not-yet-exported target")
    p.add_argument("--force", action="store_true",
                   help="overwrite existing worksheets")
    p.set_defaults(func=cmd_export_all)

    p = sub.add_parser("dedupe", help="build unique.csv + word_frequency.csv")
    p.add_argument("id", help="file id: short GUID or slug")
    p.set_defaults(func=cmd_dedupe)

    p = sub.add_parser("join", help="merge unique.csv translations into strings.csv")
    p.add_argument("id", help="file id: short GUID or slug")
    p.set_defaults(func=cmd_join)

    p = sub.add_parser("join-all",
                       help="join every target worksheet that has unique.csv")
    p.set_defaults(func=cmd_join_all)

    p = sub.add_parser("pack", help="apply translation -> langs/<language>/ui, then round-trip")
    p.add_argument("ids", nargs="+", help="file id(s): short GUID or slug")
    p.add_argument("--language", default=DEFAULT_LANGUAGE,
                   help="output language under langs/ (default: russian)")
    p.set_defaults(func=cmd_pack)

    p = sub.add_parser("pack-all", help="pack every target file that has a worksheet")
    p.add_argument("--language", default=DEFAULT_LANGUAGE,
                   help="output language under langs/ (default: russian)")
    p.set_defaults(func=cmd_pack_all)

    p = sub.add_parser("audit", help="consistency audit of one worksheet or all")
    p.add_argument("id", nargs="?", help="file id (default: every worksheet)")
    p.set_defaults(func=cmd_audit)

    args = ap.parse_args(argv)
    configure_version(args.version)
    try:
        return args.func(args)
    except csp5.CSPFormatError as e:
        print(f"FORMAT ERROR: {e}")
        return 1
    except OSError as e:
        print(f"ERROR: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

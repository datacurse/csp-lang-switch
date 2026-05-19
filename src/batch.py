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
  russian/<guid>                         patched build (repack.py apply output)

Subcommands  (run from the repo root: python src/batch.py <cmd> ...)
-----------
  status               progress table over every manifest file
  export   <id>...     export worksheet(s); skips files already exported
  export-all           export every not-yet-exported target file
  dedupe   <id>        build unique.csv + word_frequency.csv from strings.csv
  join     <id>        merge unique.csv translations back into strings.csv
  pack     <id>...     apply translation -> russian/<guid>, then round-trip
  pack-all             pack every target file that has a worksheet
  audit    [<id>]      consistency audit of one worksheet, or all of them

<id> is a file's short GUID or slug (e.g. 742DEA58 or main-ui). Use --force
with export to overwrite an existing worksheet.

No external dependencies (standard library only).
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

import csp5            # noqa: F401  (kept for parity / future use)
import repack
import roundtrip
import audit


# ----------------------------------------------------------------------
# Project paths
# ----------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "translation" / "manifest.csv"
FILES_DIR = ROOT / "translation" / "files"
RESOURCE_DIR = ROOT / "resource" / "english"
RUSSIAN_DIR = ROOT / "russian"

# Word tokenizer for the frequency aid: alpha runs only, lowercased. Digits are
# dropped on purpose (so "3D" contributes "d", matching the original glossary
# build documented in GLOSSARY.md).
_WORD = re.compile(r"[a-z']+")


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


def output_for(rec: dict) -> Path:
    return RUSSIAN_DIR / rec["guid"]


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
    ws.parent.mkdir(parents=True, exist_ok=True)
    print(f"export {rec['short']}-{rec['slug']}")
    rc = repack.main(["export", str(src), str(ws), "--kind", "text"])
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
    trans = {r["source"]: r["target"] for r in _read_rows(uniq)}
    rows = _read_rows(ws)

    changed = 0
    for r in rows:
        new = trans.get(r["source"], r["target"])
        if new != r["target"]:
            r["target"] = new
            changed += 1
    _write_rows(ws, ["key", "source", "target"], rows)

    print(f"{rec['short']}-{rec['slug']}: mapped {len(trans)} unique "
          f"translations into {len(rows)} worksheet rows ({changed} changed).")
    print(f"  wrote {ws}")
    return 0


# ----------------------------------------------------------------------
# Subcommand: pack  (repack.py apply + roundtrip.py verification)
# ----------------------------------------------------------------------
def _pack_one(rec: dict) -> bool:
    """Apply a translation and round-trip-check the output. Return True on pass."""
    ws, src, out = worksheet_for(rec), resource_for(rec), output_for(rec)
    if not ws.exists():
        print(f"SKIP   {rec['short']}-{rec['slug']}  (no worksheet)")
        return False
    if not src.exists():
        print(f"SKIP   {rec['short']}-{rec['slug']}  (resource file not found)")
        return False
    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"pack   {rec['short']}-{rec['slug']}")
    if repack.main(["apply", str(src), str(ws), str(out)]) != 0:
        print(f"  FAIL: apply failed for {rec['short']}")
        return False
    ok, msg = roundtrip.check_file(out)
    print(f"  round-trip: {msg}")
    if not ok:
        print(f"  FAIL: {out} does not round-trip")
    return ok


def cmd_pack(args: argparse.Namespace) -> int:
    manifest = load_manifest()
    recs = [resolve(manifest, i) for i in args.ids]
    ok = sum(_pack_one(r) for r in recs)
    print(f"\nPacked {ok}/{len(recs)} file(s).")
    return 0 if ok == len(recs) else 1


def cmd_pack_all(args: argparse.Namespace) -> int:
    manifest = load_manifest()
    targets = [r for r in manifest
               if r["target"] == "yes" and worksheet_for(r).exists()]
    if not targets:
        print("No exported target worksheets to pack.")
        return 0
    ok = sum(_pack_one(r) for r in targets)
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
        out = output_for(rec)
        if out.exists():
            stale = ws.exists() and out.stat().st_mtime < ws.stat().st_mtime
            packed = "stale" if stale else "yes"
            packed_count += 1
        else:
            packed = "no"
        flag = " " if rec["target"] == "yes" else "?"
        print(f" {flag}{rec['short']:9} {rec['slug']:22} "
              f"{rec['text_count']:>6}  {exported:9} {pct:12} {packed}")

    print(f"\n  {packed_count} file(s) packed into russian/.")
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
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("status", help="progress table over every manifest file")
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

    p = sub.add_parser("pack", help="apply translation -> russian/, then round-trip")
    p.add_argument("ids", nargs="+", help="file id(s): short GUID or slug")
    p.set_defaults(func=cmd_pack)

    p = sub.add_parser("pack-all", help="pack every target file that has a worksheet")
    p.set_defaults(func=cmd_pack_all)

    p = sub.add_parser("audit", help="consistency audit of one worksheet or all")
    p.add_argument("id", nargs="?", help="file id (default: every worksheet)")
    p.set_defaults(func=cmd_audit)

    args = ap.parse_args(argv)
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

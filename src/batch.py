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
  translation/manifest.csv               the file list (short,guid,slug,...,source)

  Paint (the main CSP app):
    resource/<lang>/<guid>               pristine CSP originals
    translation/files/<short>-<slug>/    per-file worksheets
        strings.csv         key,source,target worksheet (repack.py export output)
        unique.csv          one row per distinct source (translate this)
        word_frequency.csv  term-frequency aid for the glossary
    russian/<guid>                       patched build (repack.py apply output)

  Launcher (the separate "CLIP STUDIO" hub app):
    resource-launcher/<lang>/<guid>      pristine launcher originals
    translation/files-launcher/...       per-file worksheets (same layout)
    russian-launcher/<guid>              patched build

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

<id> is a file's short GUID or slug (e.g. 742DEA58 or main-ui). Paint and
launcher both ship the same GUIDs in many cases, so disambiguate with a
`<source>:` prefix when needed (e.g. `launcher:material-catalog`). With no
prefix, paint wins. Use --force with export to overwrite an existing worksheet.

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

# Paint (the main CSP app) vs. launcher (the separate "CLIP STUDIO" hub app).
# Each is a full, independent set of GUID-named resource files, located under
# its own pair of folders in the repo. The manifest's `source` column picks
# which set each row belongs to; the paths below are derived from that.
#
#   source=paint     -> resource/<lang>/      russian/      translation/files/
#   source=launcher  -> resource-launcher/    russian-launcher/  files-launcher/
#
# The finished Japanese resources are the oracle for what is translatable UI
# text: export emits a record only where English and Japanese differ.
_PAINT = {
    "originals":  ROOT / "resource",
    "russian":    ROOT / "russian",
    "worksheets": ROOT / "translation" / "files",
}
_LAUNCHER = {
    "originals":  ROOT / "resource-launcher",
    "russian":    ROOT / "russian-launcher",
    "worksheets": ROOT / "translation" / "files-launcher",
}


def _paths(rec: dict) -> dict[str, Path]:
    return _LAUNCHER if rec.get("source") == "launcher" else _PAINT

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
    """Find a manifest row by short GUID, slug or full GUID (case-insensitive).

    Paint and launcher both ship a file under the same GUID (e.g. E79C2AC5
    appears twice). Disambiguate with a `<source>:` prefix --
    ``launcher:material-catalog`` or ``paint:E79C2AC5``. With no prefix,
    paint wins (backward compat with the original paint-only manifest)."""
    src = None
    if ":" in ident:
        head, _, tail = ident.partition(":")
        if head.lower() in ("paint", "launcher"):
            src, ident = head.lower(), tail
    low = ident.lower()
    matches = [rec for rec in manifest
               if low in (rec["short"].lower(),
                          rec["slug"].lower(),
                          rec["guid"].lower())
               and (src is None or rec.get("source", "paint") == src)]
    if not matches:
        sys.exit(f"ERROR: '{ident}' matches no manifest file "
                 f"(try `batch.py status`).")
    if len(matches) == 1:
        return matches[0]
    # Multiple matches across sources -- prefer paint, warn the user.
    paint = next((r for r in matches if r.get("source", "paint") == "paint"), None)
    if paint is not None:
        others = ", ".join(f"{r.get('source','paint')}:{r['short']}"
                           for r in matches if r is not paint)
        print(f"note: '{ident}' is ambiguous; picking paint "
              f"(also matches {others}). Use `launcher:{ident}` to override.",
              file=sys.stderr)
        return paint
    return matches[0]


def folder_for(rec: dict) -> Path:
    """The per-file worksheet folder.

    Paint:    translation/files/<short>-<slug>/
    Launcher: translation/files-launcher/<short>-<slug>/
    """
    return _paths(rec)["worksheets"] / f"{rec['short']}-{rec['slug']}"


def worksheet_for(rec: dict) -> Path:
    return folder_for(rec) / "strings.csv"


def unique_for(rec: dict) -> Path:
    return folder_for(rec) / "unique.csv"


def freq_for(rec: dict) -> Path:
    return folder_for(rec) / "word_frequency.csv"


def resource_for(rec: dict) -> Path:
    return _paths(rec)["originals"] / "english" / rec["guid"]


def reference_for(rec: dict) -> Path:
    return _paths(rec)["originals"] / "japanese" / rec["guid"]


def output_for(rec: dict) -> Path:
    return _paths(rec)["russian"] / rec["guid"]


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

    changed = 0
    for r in rows:
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
    print(f"  {'src':8} {'short':9} {'slug':22} {'text':>6}  {'exported':9} "
          f"{'translated':12} packed")
    print(f"  {'-'*8} {'-'*9} {'-'*22} {'-'*6}  {'-'*9} {'-'*12} {'-'*6}")

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
        src = rec.get("source", "paint")
        print(f" {flag}{src:8} {rec['short']:9} {rec['slug']:22} "
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

#!/usr/bin/env python3
"""
repack.py
=========
Extract translatable strings from a CSP5 resource file, and apply a translated
string set back into a new (patched) file.

Built on csp5.py, whose round-trip test is verified byte-for-byte on every file
in the resource tree -- so applying a translation is "parse, substitute the
StringStreamNode text, serialize", with the index and footer carried verbatim.

Each string is addressed by a STABLE KEY: the entry-id path from the root of
block 1 to the string leaf, plus the record index within that leaf, e.g.
"2/1/17#0". The block-1 tree shape is identical across all languages, so a key
exported from the English file applies cleanly to the English file you patch.

Subcommands
-----------
  export   Dump strings to a CSV worksheet (one row per string).
  apply    Read a translated CSV and write a patched resource file.
  stats    Print a structural + classification breakdown (no files written).

The CSV has three columns: `key`, `source`, `target`. `key` ties a row back to
its place in the resource file -- don't edit it. `source` is the untranslated
reference -- leave it. `target` is the only column a translator changes. The
CSV is just an overlay: `apply` re-parses the original binary and substitutes
text by `key`, so the worksheet needs no structural information of its own.

Usage
-----
  python repack.py export <resource_file> <out.csv> [--kind text [key url]]
  python repack.py apply  <resource_file> <translated.csv> <out_file>
  python repack.py stats  <resource_file>

Translation workflow
--------------------
  1.  python repack.py export english/742DEA58-... strings.csv --kind text
  2.  Edit the "target" column of each row in strings.csv (leave "source").
  3.  python repack.py apply english/742DEA58-... strings.csv patched/742DEA58-...
  4.  Put the patched file in CSP's resource/english/ folder and test.

No external dependencies (standard library only).
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import csp5
from extract_csp_strings import classify   # reuse the text/key/url classifier


# ----------------------------------------------------------------------
# String addressing
# ----------------------------------------------------------------------
def leaf_key(path: tuple[int, ...], index: int) -> str:
    """Stable key for a string record: 'id/id/.../id#recordindex'."""
    return "/".join(str(p) for p in path) + f"#{index}"


def iter_records(container: csp5.Container):
    """Yield (key, kind, text) for every string record in block 1, in order."""
    for path, node in csp5.iter_string_nodes(container.block1):
        for i, text in enumerate(node.strings):
            yield leaf_key(path, i), classify(text), text


# ----------------------------------------------------------------------
# Translation worksheet I/O -- a CSV of key, source, target
# ----------------------------------------------------------------------
# Columns kept deliberately minimal: `key` addresses the string, `source` is
# the untranslated reference, `target` is the only field a translator edits.
_CSV_COLUMNS = ["key", "source", "target"]


def _write_csv(path: Path, records: list[dict]) -> None:
    """Write export records as a CSV (key, source, target).

    Encoded as UTF-8 with a BOM so Excel opens non-ASCII text correctly;
    `newline=""` lets the csv module own line endings and quote embedded
    commas, quotes and newlines.
    """
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(_CSV_COLUMNS)
        for r in records:
            writer.writerow([r["key"], r["source"], r["target"]])


def _load_targets(path: Path) -> dict[str, str]:
    """Return {key: target} from a translated CSV worksheet.

    The CSV needs at least `key` and `target` columns; extra columns (such as
    `source`) are ignored. Raises ValueError on a malformed file.
    """
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError("CSV translation file has no data rows.")
    cols = rows[0].keys()
    if "key" not in cols or "target" not in cols:
        raise ValueError("CSV must have 'key' and 'target' columns.")
    return {r["key"]: (r.get("target") or "") for r in rows if r.get("key")}


# ----------------------------------------------------------------------
# Greedy blob scan -- used by `stats` to confirm no UI text hides in blobs
# ----------------------------------------------------------------------
def _scan_blob_strings(blob: bytes) -> list[str]:
    """Greedy [uint32 len][UTF-8] scan of opaque blob bytes."""
    found: list[str] = []
    pos, n = 0, len(blob)
    while pos + 4 <= n:
        ln = int.from_bytes(blob[pos:pos + 4], "big")
        if 1 <= ln <= 8000 and pos + 4 + ln <= n:
            chunk = blob[pos + 4:pos + 4 + ln]
            try:
                text = chunk.decode("utf-8")
            except UnicodeDecodeError:
                pos += 1
                continue
            if all(ord(c) >= 32 or c in "\n\t" for c in text):
                found.append(text)
                pos += 4 + ln
                continue
        pos += 1
    return found


def _collect_blobs(node: csp5.Node, out: list[bytes]) -> None:
    if isinstance(node, csp5.BlobNode):
        out.append(node.data)
    elif isinstance(node, csp5.DirectoryNode):
        for _, child in node.children:
            _collect_blobs(child, out)


# ----------------------------------------------------------------------
# Subcommand: export
# ----------------------------------------------------------------------
def cmd_export(args: argparse.Namespace) -> int:
    data = Path(args.file).read_bytes()
    container = csp5.parse(data)

    wanted = set(args.kind) if args.kind else None
    records = []
    for key, kind, text in iter_records(container):
        if wanted is not None and kind not in wanted:
            continue
        records.append({
            "key": key,
            "kind": kind,
            "source": text,
            "target": text,        # translator edits this column
        })

    out = Path(args.out)
    _write_csv(out, records)

    counts: dict[str, int] = {}
    for r in records:
        counts[r["kind"]] = counts.get(r["kind"], 0) + 1
    breakdown = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
    print(f"Exported {len(records)} string records to {out}")
    print(f"  by kind: {breakdown}")
    print('  Edit the "target" column of each row, then use: repack.py apply')
    return 0


# ----------------------------------------------------------------------
# Subcommand: apply
# ----------------------------------------------------------------------
def cmd_apply(args: argparse.Namespace) -> int:
    data = Path(args.file).read_bytes()
    container = csp5.parse(data)

    try:
        targets = _load_targets(Path(args.translations))
    except (ValueError, csv.Error) as e:
        print(f"ERROR: {e}")
        return 1

    applied = 0
    seen: set[str] = set()
    for path, node in csp5.iter_string_nodes(container.block1):
        for i in range(len(node.strings)):
            key = leaf_key(path, i)
            if key in targets:
                seen.add(key)
                if node.strings[i] != targets[key]:
                    node.strings[i] = targets[key]
                    applied += 1

    rebuilt = csp5.serialize(container)
    # Sanity check: the patched file must still parse cleanly.
    try:
        csp5.parse(rebuilt)
    except csp5.CSPFormatError as e:
        print(f"ERROR: patched file failed to re-parse ({e}); not written.")
        return 1

    out = Path(args.out)
    out.write_bytes(rebuilt)
    print(f"Applied {applied} changed strings; wrote {out} "
          f"({len(rebuilt):,} bytes, was {len(data):,}).")

    missing = sorted(set(targets) - seen)
    if missing:
        print(f"WARNING: {len(missing)} key(s) in the translation file were "
              f"not found in the resource file (stale or wrong file?):")
        for key in missing[:10]:
            print(f"  {key}")
        if len(missing) > 10:
            print(f"  ... and {len(missing) - 10} more")
    return 0


# ----------------------------------------------------------------------
# Subcommand: stats
# ----------------------------------------------------------------------
def cmd_stats(args: argparse.Namespace) -> int:
    data = Path(args.file).read_bytes()
    container = csp5.parse(data)
    stats = csp5.tree_stats(container.block1)

    print(f"File: {args.file}  ({len(data):,} bytes)")
    print(f"  block 1 (strings) : tree of {stats['directories']} directories, "
          f"max depth {stats['max_depth']}")
    print(f"  block 2 (index)   : {len(container.block2):,} bytes (verbatim)")
    print(f"  block 3 (footer)  : {len(container.block3):,} bytes (verbatim)")
    print()

    counts: dict[str, int] = {}
    unique_text: set[str] = set()
    total = 0
    for _key, kind, text in iter_records(container):
        counts[kind] = counts.get(kind, 0) + 1
        total += 1
        if kind == "text":
            unique_text.add(text)
    print(f"Structured string records (StringStreamNode leaves): {total}")
    for kind in ("text", "key", "url"):
        if kind in counts:
            print(f"  {kind:4s}: {counts[kind]:6d}")
    print(f"  -> translatable UI text: {counts.get('text', 0)} "
          f"({len(unique_text)} unique)")
    print()

    # Confirm no translatable UI text is hidden inside opaque blob nodes.
    blobs: list[bytes] = []
    _collect_blobs(container.block1, blobs)
    blob_bytes = sum(len(b) for b in blobs)
    blob_text_kinds: dict[str, int] = {}
    blob_text_samples: list[str] = []
    for b in blobs:
        for s in _scan_blob_strings(b):
            k = classify(s)
            blob_text_kinds[k] = blob_text_kinds.get(k, 0) + 1
            if k == "text" and len(blob_text_samples) < 12:
                blob_text_samples.append(s)
    print(f"Blob leaves: {stats['blob_leaves']} nodes, {blob_bytes:,} bytes "
          f"(PNG assets + symbolic sub-containers, NOT translated)")
    if blob_text_kinds:
        bd = ", ".join(f"{k}={v}" for k, v in sorted(blob_text_kinds.items()))
        print(f"  greedy scan inside blobs finds: {bd}")
        if blob_text_samples:
            print("  sample 'text'-classified strings found inside blobs:")
            for s in blob_text_samples:
                print(f"    {s!r}")
        else:
            print("  (no 'text'-classified strings inside blobs -- "
                  "blobs carry only identifiers/URLs)")
    return 0


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------
def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_exp = sub.add_parser("export", help="dump strings to a CSV worksheet")
    p_exp.add_argument("file", help="CSP5 resource file to read")
    p_exp.add_argument("out", help="output .csv path")
    p_exp.add_argument("--kind", nargs="+", choices=["text", "key", "url"],
                       help="only export these kinds (recommend: --kind text)")
    p_exp.set_defaults(func=cmd_export)

    p_app = sub.add_parser("apply", help="apply a translated CSV, write a patched file")
    p_app.add_argument("file", help="original CSP5 resource file")
    p_app.add_argument("translations", help="translated .csv (from `export`)")
    p_app.add_argument("out", help="output patched resource file")
    p_app.set_defaults(func=cmd_apply)

    p_st = sub.add_parser("stats", help="print a structural/classification breakdown")
    p_st.add_argument("file", help="CSP5 resource file to inspect")
    p_st.set_defaults(func=cmd_stats)

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

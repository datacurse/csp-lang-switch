#!/usr/bin/env python3
"""
extract_csp_strings.py
======================
Extracts UI strings from a Clip Studio Paint 5 resource file (the GUID-named
files in resource/<language>/, e.g. 742DEA58-ED6B-4402-BC11-20DFC6D08040).

CSP 5 resource file format (reverse-engineered):
  * Big-endian throughout.
  * Top level: [uint32 count=3] + 3 x [uint32 id, uint32 offset, uint32 length].
    - block id=1 : string data (a nested container of length-prefixed strings)
    - block id=2 : index table
    - block id=3 : ~48-byte footer
  * Strings are stored as [uint32 byte_length][UTF-8 bytes], concatenated into
    a stream that is paginated by nested directory structures.

This tool greedy-scans block 1 for every [uint32 len][valid UTF-8] record. That
reliably recovers the strings for inspection / translation scoping. It does NOT
rebuild the file (that needs the index decoded — a separate step).

Outputs:
  <prefix>.json  - list of records, machine-readable
  <prefix>.tsv   - id <tab> offset <tab> kind <tab> text, easy to review

Usage:
  python extract_csp_strings.py 742DEA58-ED6B-4402-BC11-20DFC6D08040
  python extract_csp_strings.py <file> --out-prefix japanese_strings
"""

import sys
import json
import struct
import argparse
from pathlib import Path

MIN_LEN = 1
MAX_LEN = 8000  # generous upper bound for a single UI string


def u32(buf: bytes, off: int) -> int:
    return struct.unpack(">I", buf[off:off + 4])[0]


def parse_header(data: bytes):
    """Return list of (id, offset, length) for the 3 top-level blocks."""
    count = u32(data, 0)
    blocks = []
    pos = 4
    for _ in range(count):
        blocks.append((u32(data, pos), u32(data, pos + 4), u32(data, pos + 8)))
        pos += 12
    return count, blocks


def is_clean_text(s: str) -> bool:
    """Reject records containing control characters (likely false positives)."""
    return all(ord(c) >= 32 or c in "\n\t" for c in s)


def classify(text: str) -> str:
    """Rough bucket: url / key / text."""
    if text.startswith(("http://", "https://")):
        return "url"
    ascii_only = all(ord(c) < 128 for c in text)
    if ascii_only and " " not in text and len(text) <= 40:
        # widget class names, format keys, identifiers (PWView, %s, etc.)
        return "key"
    return "text"


def extract(data: bytes):
    count, blocks = parse_header(data)
    if count != 3:
        print(f"WARNING: expected 3 top-level blocks, got {count}")
    # block id=1 is the string container
    string_block = next((b for b in blocks if b[0] == 1), blocks[0])
    _, b_off, b_len = string_block
    blob = data[b_off:b_off + b_len]

    records = []
    pos = 0
    while pos + 4 <= len(blob):
        ln = u32(blob, pos)
        if MIN_LEN <= ln <= MAX_LEN and pos + 4 + ln <= len(blob):
            chunk = blob[pos + 4:pos + 4 + ln]
            try:
                text = chunk.decode("utf-8")
            except UnicodeDecodeError:
                pos += 1
                continue
            if is_clean_text(text):
                records.append({
                    "offset": b_off + pos,        # absolute file offset
                    "block_offset": pos,          # offset within string block
                    "byte_len": ln,
                    "char_len": len(text),
                    "kind": classify(text),
                    "ascii_only": all(ord(c) < 128 for c in text),
                    "text": text,
                })
                pos += 4 + ln
                continue
        pos += 1
    return blocks, records


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file", help="CSP resource file (GUID-named)")
    ap.add_argument("--out-prefix", default=None,
                    help="output filename prefix (default: <file>_strings)")
    args = ap.parse_args()

    path = Path(args.file)
    if not path.is_file():
        print(f"ERROR: file not found: {path}")
        sys.exit(1)

    data = path.read_bytes()
    print(f"File: {path}  ({len(data):,} bytes)")

    blocks, records = extract(data)
    print("\nTop-level blocks (id, offset, length):")
    for bid, off, ln in blocks:
        print(f"  id={bid}  offset={off:,}  length={ln:,}")

    kinds = {}
    for r in records:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    uniq_text = len({r["text"] for r in records if r["kind"] == "text"})

    print(f"\nExtracted {len(records):,} string records")
    print(f"  text : {kinds.get('text', 0):,}  ({uniq_text:,} unique) <- translatable UI text")
    print(f"  key  : {kinds.get('key', 0):,}  <- widget/format identifiers, do NOT translate")
    print(f"  url  : {kinds.get('url', 0):,}  <- URLs, do NOT translate")

    prefix = args.out_prefix or f"{path.name}_strings"
    Path(f"{prefix}.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(f"{prefix}.tsv", "w", encoding="utf-8") as f:
        f.write("idx\toffset\tkind\tbyte_len\ttext\n")
        for i, r in enumerate(records):
            safe = r["text"].replace("\t", "\\t").replace("\n", "\\n")
            f.write(f"{i}\t{r['offset']}\t{r['kind']}\t{r['byte_len']}\t{safe}\n")

    print(f"\nWrote {prefix}.json and {prefix}.tsv")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Merge gap_translations.csv targets into per-file unique.csv worksheets."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT / "translation" / "gap_translations.csv"


def lf(s: str) -> str:
    return s.replace("\r\n", "\n").replace("\r", "\n")


def adapt_newlines(source: str, target: str) -> str:
    if "\r\n" in source:
        return lf(target).replace("\n", "\r\n")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, default=DEFAULT_INPUT,
        help="CSV with columns file,source,target",
    )
    args = parser.parse_args()

    if not args.input.is_file():
        sys.exit(f"error: {args.input} not found")

    by_file: dict[str, dict[str, str]] = {}
    with args.input.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            file = (row.get("file") or "").strip()
            src = row.get("source", "")
            tgt = (row.get("target") or "").strip()
            if not file or not src or not tgt:
                continue
            by_file.setdefault(file, {})[lf(src)] = tgt

    updated = 0
    for file, trans in sorted(by_file.items()):
        uniq = ROOT / "translation" / "files" / file / "unique.csv"
        if not uniq.is_file():
            print(f"skip {file}: unique.csv missing")
            continue
        rows = list(csv.DictReader(uniq.open(encoding="utf-8-sig", newline="")))
        changed = 0
        for row in rows:
            key = lf(row["source"])
            new = trans.get(key)
            if new is None:
                continue
            new = adapt_newlines(row["source"], new)
            if row.get("target") != new:
                row["target"] = new
                changed += 1
        with uniq.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["source", "target"])
            w.writeheader()
            w.writerows(rows)
        print(f"{file}: applied {changed} translation(s)")
        updated += changed

    print(f"\nTotal targets applied: {updated}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

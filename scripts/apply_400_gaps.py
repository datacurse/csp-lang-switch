#!/usr/bin/env python3
"""Append 4.0.0 gap translations into per-file unique.csv worksheets."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INPUT = ROOT / "translation" / "gap_translations_400.csv"


def lf(s: str) -> str:
    return s.replace("\r\n", "\n").replace("\r", "\n")


def main() -> int:
    if not INPUT.is_file():
        sys.exit(f"error: {INPUT} not found — run scripts/fill_400_gaps.py first")

    by_file: dict[str, list[tuple[str, str]]] = {}
    with INPUT.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            file = (row.get("file") or "").strip()
            src = row.get("source", "")
            tgt = (row.get("target") or "").strip()
            if not file or not src or not tgt or tgt == src:
                continue
            by_file.setdefault(file, []).append((src, tgt))

    added = 0
    for file, pairs in sorted(by_file.items()):
        uniq = ROOT / "translation" / "files" / file / "unique.csv"
        if not uniq.is_file():
            print(f"skip {file}: unique.csv missing")
            continue
        rows = list(csv.DictReader(uniq.open(encoding="utf-8-sig", newline="")))
        known = {lf(r["source"]) for r in rows}
        file_added = 0
        for src, tgt in pairs:
            if lf(src) in known:
                continue
            rows.append({"source": src, "target": tgt})
            known.add(lf(src))
            file_added += 1
        if file_added:
            with uniq.open("w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["source", "target"])
                w.writeheader()
                w.writerows(rows)
        print(f"{file}: appended {file_added} translation(s)")
        added += file_added

    print(f"\nTotal appended: {added}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

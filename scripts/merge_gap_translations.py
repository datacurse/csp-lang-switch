#!/usr/bin/env python3
"""Merge part CSVs and identity-fill non-UI gaps."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GAPS = ROOT / "translation" / "gap_sources.csv"
OUT = ROOT / "translation" / "gap_translations.csv"
PARTS = [
    ROOT / "translation" / "gap_translations_part1.csv",
    ROOT / "translation" / "gap_translations_part2.csv",
    ROOT / "translation" / "gap_translations_part3.csv",
    ROOT / "translation" / "gap_translations_auto.csv",
    ROOT / "translation" / "gap_translations_504.csv",
    ROOT / "translation" / "gap_translations_workspace.csv",
]


def lf(s: str) -> str:
    return s.replace("\r\n", "\n").replace("\r", "\n")


def main() -> int:
    merged: dict[tuple[str, str], dict[str, str]] = {}
    for path in PARTS:
        if not path.is_file():
            continue
        with path.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                file = (row.get("file") or "").strip()
                src = row.get("source", "")
                tgt = (row.get("target") or "").strip()
                if not file or not src or not tgt:
                    continue
                merged[(file, lf(src))] = {
                    "file": file,
                    "source": src,
                    "target": tgt,
                }

    # Identity-fill paths, urls, shaders so they are explicitly handled.
    with GAPS.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if row["kind"] == "ui":
                continue
            key = (row["file"], lf(row["source"]))
            if key not in merged:
                merged[key] = {
                    "file": row["file"],
                    "source": row["source"],
                    "target": row["source"],
                }

    rows = list(merged.values())
    rows.sort(key=lambda r: (r["file"], r["source"]))
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["file", "source", "target"])
        w.writeheader()
        w.writerows(rows)
    print(f"merged {len(rows)} translation(s) -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Propagate existing translations to gap variants (e.g. trailing newlines)."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GAPS = ROOT / "translation" / "gap_sources.csv"
OUT = ROOT / "translation" / "gap_translations.csv"


def lf(s: str) -> str:
    return s.replace("\r\n", "\n").replace("\r", "\n")


def load_known() -> dict[str, str]:
    known: dict[str, str] = {}
    files_dir = ROOT / "translation" / "files"
    for uniq in files_dir.glob("*/unique.csv"):
        with uniq.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                src = row["source"]
                tgt = (row.get("target") or "").strip()
                if tgt and tgt != src:
                    known[lf(src)] = tgt
    return known


def adapt(source: str, target: str) -> str:
    src = lf(source)
    tgt = lf(target)
    if src.endswith("\n") and not tgt.endswith("\n"):
        tgt += "\n"
    if "\r\n" in source:
        return tgt.replace("\n", "\r\n")
    return tgt


def main() -> int:
    known = load_known()
    rows_out = []
    auto = 0
    with GAPS.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if row["kind"] != "ui":
                continue
            src = row["source"]
            key = lf(src)
            if key in known:
                continue
            base = key.rstrip(" \t\n\r")
            hit = known.get(base)
            if hit is None and base.endswith("\n"):
                hit = known.get(base[:-1])
            if hit is None:
                continue
            rows_out.append({
                "file": row["file"],
                "source": src,
                "target": adapt(src, hit),
            })
            auto += 1

    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["file", "source", "target"])
        w.writeheader()
        w.writerows(rows_out)

    print(f"auto-propagated {auto} translation(s) -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

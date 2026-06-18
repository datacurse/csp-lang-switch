#!/usr/bin/env python3
"""Set target=source for any remaining empty unique.csv rows."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    changed = 0
    for uniq in sorted((ROOT / "translation" / "files").glob("*/unique.csv")):
        rows = list(csv.DictReader(uniq.open(encoding="utf-8-sig", newline="")))
        file_changed = 0
        for row in rows:
            tgt = row.get("target")
            if tgt is not None and tgt != "":
                continue
            row["target"] = row["source"]
            file_changed += 1
        if file_changed:
            with uniq.open("w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["source", "target"])
                w.writeheader()
                w.writerows(rows)
            print(f"{uniq.parent.name}: filled {file_changed} identity row(s)")
            changed += file_changed
    print(f"\nTotal identity fills: {changed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

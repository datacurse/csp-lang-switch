#!/usr/bin/env python3
import csv
from pathlib import Path

rows = [
    r for r in csv.DictReader(
        Path("translation/gap_sources.csv").open(encoding="utf-8-sig")
    )
    if r["kind"] == "ui"
    and ("workspace" in r["source"].lower() or "Workspace" in r["source"])
]
Path("_workspace_gaps.txt").write_text(
    "\n---\n".join(f"{r['file']}\n{r['source']!r}" for r in rows),
    encoding="utf-8",
)
print(len(rows))

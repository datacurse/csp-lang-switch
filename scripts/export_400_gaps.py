#!/usr/bin/env python3
"""Export untranslated UI strings for CSP 4.0.0."""

from __future__ import annotations

import csv
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

import repack  # noqa: E402
from version import langs_root, set_active_version  # noqa: E402

MANIFEST = ROOT / "translation" / "manifest.csv"
OUT = ROOT / "translation" / "gap_400.csv"


def lf(s: str) -> str:
    return s.replace("\r\n", "\n").replace("\r", "\n")


def read_unique(rec: dict) -> dict[str, str]:
    path = ROOT / "translation" / "files" / f"{rec['short']}-{rec['slug']}" / "unique.csv"
    out: dict[str, str] = {}
    if path.is_file():
        with path.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                out[row["source"]] = (row.get("target") or "").strip()
    return out


def export_stock(rec: dict) -> list[dict] | None:
    eng = langs_root("4.0.0") / "english" / "ui" / rec["guid"]
    jpn = langs_root("4.0.0") / "japanese" / "ui" / rec["guid"]
    if not eng.is_file() or not jpn.is_file():
        return None
    fd, tmp = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    tmp_path = Path(tmp)
    try:
        if repack.main(["export", str(eng), str(tmp_path), "--reference", str(jpn)]) != 0:
            return None
        with tmp_path.open(encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))
    finally:
        tmp_path.unlink(missing_ok=True)


def main() -> int:
    with MANIFEST.open(encoding="utf-8-sig", newline="") as f:
        manifest = [r for r in csv.DictReader(f) if r.get("target") == "yes"]

    set_active_version("4.0.0")
    gaps: list[dict[str, str]] = []
    for rec in manifest:
        rows = export_stock(rec)
        if rows is None:
            continue
        trans = read_unique(rec)
        slug = f"{rec['short']}-{rec['slug']}"
        for row in rows:
            src = row["source"]
            tgt = trans.get(src, trans.get(lf(src), "")).strip()
            if tgt and tgt != src:
                continue
            gaps.append({"file": slug, "source": src, "target": ""})

    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["file", "source", "target"])
        w.writeheader()
        w.writerows(gaps)
    print(f"4.0.0 gaps: {len(gaps)} -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

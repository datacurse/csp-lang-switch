#!/usr/bin/env python3
"""Add version-specific strings missing from unique.csv."""

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
from version import langs_root  # noqa: E402

UNIQ = ROOT / "translation" / "files" / "742DEA58-main-ui" / "unique.csv"
NEEDLES = ("QUMALib", "Restoring multiple canvases", "The app may have closed")


def lf(s: str) -> str:
    return s.replace("\r\n", "\n").replace("\r", "\n")


def export_missing() -> dict[str, str]:
    eng = langs_root("5.0.0") / "english/ui/742DEA58-ED6B-4402-BC11-20DFC6D08040"
    jpn = langs_root("5.0.0") / "japanese/ui/742DEA58-ED6B-4402-BC11-20DFC6D08040"
    fd, tmp = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    tmp_path = Path(tmp)
    try:
        repack.main(["export", str(eng), str(tmp_path), "--reference", str(jpn)])
        out: dict[str, str] = {}
        with tmp_path.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                if any(n in row["source"] for n in NEEDLES):
                    out[lf(row["source"])] = row["source"]
        return out
    finally:
        tmp_path.unlink(missing_ok=True)


TRANSLATIONS = {
    "Restoring multiple canvases. It may take some time for the process to finish.": (
        "Восстановление нескольких холстов. Процесс может занять некоторое время."
    ),
    "The app may have closed before saving the project.": (
        "Приложение могло закрыться до сохранения проекта."
    ),
}


def main() -> None:
    stock = export_missing()
    rows = list(csv.DictReader(UNIQ.open(encoding="utf-8-sig", newline="")))
    known = {lf(r["source"]) for r in rows}
    added = 0
    for key, src in stock.items():
        if key in known:
            continue
        if "QUMALib" in src:
            tgt = src
        else:
            plain = src.replace("\r\n", "\n").replace("\r", "\n")
            tgt = TRANSLATIONS.get(plain, src)
        rows.append({"source": src, "target": tgt})
        added += 1
    with UNIQ.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["source", "target"])
        w.writeheader()
        w.writerows(rows)
    print(f"added {added} row(s) to {UNIQ}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Report missing vs identity vs translated coverage per CSP version."""

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
from version import SUPPORTED_VERSIONS, langs_root  # noqa: E402


def lf(s: str) -> str:
    return s.replace("\r\n", "\n").replace("\r", "\n")


def load_known() -> dict[tuple[str, str], str]:
    known: dict[tuple[str, str], str] = {}
    for uniq in (ROOT / "translation" / "files").glob("*/unique.csv"):
        slug = uniq.parent.name
        with uniq.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                tgt = row.get("target")
                if tgt is not None and tgt != "":
                    known[(slug, lf(row["source"]))] = tgt
    return known


def main() -> int:
    known = load_known()
    manifest = list(csv.DictReader(
        (ROOT / "translation" / "manifest.csv").open(encoding="utf-8-sig")
    ))
    any_missing = False
    for ver in SUPPORTED_VERSIONS:
        missing: list[tuple[str, str]] = []
        identity = 0
        translated = 0
        for rec in manifest:
            if rec.get("target") != "yes":
                continue
            slug = f"{rec['short']}-{rec['slug']}"
            eng = langs_root(ver) / "english" / "ui" / rec["guid"]
            jpn = langs_root(ver) / "japanese" / "ui" / rec["guid"]
            if not eng.is_file() or not jpn.is_file():
                continue
            fd, tmp = tempfile.mkstemp(suffix=".csv")
            os.close(fd)
            tmp_path = Path(tmp)
            try:
                if repack.main(["export", str(eng), str(tmp_path),
                                 "--reference", str(jpn)]) != 0:
                    continue
                with tmp_path.open(encoding="utf-8-sig", newline="") as f:
                    for row in csv.DictReader(f):
                        src = row["source"]
                        tgt = known.get((slug, lf(src)))
                        if tgt is None:
                            missing.append((slug, src))
                        elif tgt == src:
                            identity += 1
                        else:
                            translated += 1
            finally:
                tmp_path.unlink(missing_ok=True)
        print(f"{ver}: translated={translated} identity={identity} "
              f"missing={len(missing)}")
        if missing:
            any_missing = True
            for slug, src in missing[:8]:
                preview = src.replace("\n", " / ")[:100]
                print(f"  MISSING [{slug}] {preview}")
    return 1 if any_missing else 0


if __name__ == "__main__":
    sys.exit(main())

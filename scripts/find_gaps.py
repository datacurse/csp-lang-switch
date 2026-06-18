#!/usr/bin/env python3
"""Find exportable UI strings missing Russian translations across CSP versions."""

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
from version import SUPPORTED_VERSIONS, langs_root, set_active_version  # noqa: E402

MANIFEST = ROOT / "translation" / "manifest.csv"


def lf(s: str) -> str:
    return s.replace("\r\n", "\n").replace("\r", "\n")


def read_unique(rec: dict) -> dict[str, str]:
    path = ROOT / "translation" / "files" / f"{rec['short']}-{rec['slug']}" / "unique.csv"
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            out[row["source"]] = (row.get("target") or "").strip()
    return out


def export_stock(rec: dict, ver: str) -> list[dict] | None:
    eng = langs_root(ver) / "english" / "ui" / rec["guid"]
    jpn = langs_root(ver) / "japanese" / "ui" / rec["guid"]
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

    gaps: dict[str, dict] = {}
    for ver in SUPPORTED_VERSIONS:
        set_active_version(ver)
        for rec in manifest:
            rows = export_stock(rec, ver)
            if rows is None:
                print(f"skip {ver} {rec['short']}: missing stock", file=sys.stderr)
                continue
            trans = read_unique(rec)
            slug = f"{rec['short']}-{rec['slug']}"
            for row in rows:
                src = row["source"]
                tgt = trans.get(src, trans.get(lf(src), "")).strip()
                if tgt and tgt != src:
                    continue
                key = lf(src)
                if key not in gaps:
                    gaps[key] = {
                        "source": src,
                        "files": set(),
                        "versions": set(),
                    }
                gaps[key]["files"].add(slug)
                gaps[key]["versions"].add(ver)

    out = ROOT / "_gap_report.txt"
    lines: list[str] = []
    for _, info in sorted(gaps.items(), key=lambda x: (-len(x[1]["versions"]), x[0])):
        vers = ",".join(sorted(info["versions"]))
        files = ",".join(sorted(info["files"]))
        preview = info["source"].replace("\n", " / ")[:160]
        lines.append(f"VER={vers} FILES={files}")
        lines.append(preview)
        lines.append("")

    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"total gaps: {len(gaps)}")
    for ver in SUPPORTED_VERSIONS:
        count = sum(1 for g in gaps.values() if ver in g["versions"])
        print(f"  {ver}: {count}")
    print(f"report: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

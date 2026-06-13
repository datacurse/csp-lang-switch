#!/usr/bin/env python3
"""
capture_stock.py
================
Capture stock English + Japanese oracle snapshots from a live CSP install
into versions/<ACTIVE_VERSION>/langs/.

Prerequisites:
  * CSP installed (Ver. 5.0.0 for the current active version)
  * UI language set to English
  * CSP launched at least once (materials user data populated)
  * CSP closed before running backup steps

Usage (from repo root):
  python scripts/capture_stock.py
  python scripts/capture_stock.py --csp "C:\\Program Files\\...\\resource"
  python scripts/capture_stock.py --official-langs   # also copy all resource/<lang>/ui
"""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

import install  # noqa: E402
from version import (  # noqa: E402
    ACTIVE_VERSION,
    GUARD_GUID,
    LANGS_ROOT,
    english_ui_dir,
    japanese_ui_dir,
)

GUID_RE = re.compile(
    r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z", re.I)


def _resource_files(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir()
                  if p.is_file() and GUID_RE.match(p.name))


def copy_ui(src: Path, dst: Path, label: str) -> int:
    files = _resource_files(src)
    if not files:
        print(f"  skip {label}: no resource files in {src}")
        return 0
    dst.mkdir(parents=True, exist_ok=True)
    for f in files:
        shutil.copy2(f, dst / f.name)
    print(f"  {label}: {len(files)} file(s) -> {dst}")
    return len(files)


def update_version_guard() -> None:
    """Write GUARD_SIZE and GUARD_SHA256 into src/version.py after capture."""
    path = english_ui_dir() / GUARD_GUID
    if not path.is_file():
        print("  warning: guard file missing; version guard not updated")
        return
    data = path.read_bytes()
    size = len(data)
    digest = hashlib.sha256(data).hexdigest()
    version_py = SRC / "version.py"
    text = version_py.read_text(encoding="utf-8")
    text = re.sub(
        r"^GUARD_SIZE: int \| None = .*$",
        f"GUARD_SIZE: int | None = {size}",
        text,
        flags=re.M,
    )
    text = re.sub(
        r"^GUARD_SHA256: str \| None = .*$",
        f'GUARD_SHA256: str | None = "{digest}"',
        text,
        flags=re.M,
    )
    version_py.write_text(text, encoding="utf-8")
    print(f"  version guard updated: {GUARD_GUID} size={size:,} sha256={digest[:16]}...")


def run_pipeline_backup(script: str, csp: str | None) -> None:
    cmd = [sys.executable, str(SRC / script), "backup"]
    if csp:
        cmd.extend(["--csp", csp])
    cmd.append("--yes")
    print(f"\n  running: {' '.join(cmd)}")
    subprocess.run(cmd, cwd=ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture CSP stock snapshots")
    parser.add_argument("--csp", help="CSP resource directory")
    parser.add_argument(
        "--official-langs",
        action="store_true",
        help="Copy every official resource/<lang>/ui folder (dev convenience)",
    )
    args = parser.parse_args()

    resource = install.find_csp_resource(args.csp)
    print(f"Capturing stock for CSP {ACTIVE_VERSION}")
    print(f"  resource: {resource}")
    print(f"  output:   {LANGS_ROOT}")

    LANGS_ROOT.mkdir(parents=True, exist_ok=True)

    print("\nMain UI:")
    copy_ui(resource / "english", english_ui_dir(), "english")
    copy_ui(resource / "japanese", japanese_ui_dir(), "japanese")

    if args.official_langs:
        print("\nOptional official language UI folders:")
        for d in sorted(resource.iterdir()):
            if d.name in ("english", "japanese", "other") or not d.is_dir():
                continue
            if not _resource_files(d):
                continue
            copy_ui(d, LANGS_ROOT / d.name / "ui", d.name)

    print("\nPlug-ins, tools, materials, color sets:")
    run_pipeline_backup("plugins.py", args.csp)
    run_pipeline_backup("tools.py", args.csp)
    run_pipeline_backup("materials.py", None)
    run_pipeline_backup("colorsets.py", args.csp)

    print("\nVersion guard:")
    update_version_guard()

    print("\nDone. Next: python src/roundtrip.py versions/"
          f"{ACTIVE_VERSION}/langs/english/ui")
    return 0


if __name__ == "__main__":
    sys.exit(main())

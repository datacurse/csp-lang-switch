#!/usr/bin/env python3
"""
capture_stock.py
================
Capture stock English + Japanese oracle snapshots from a live CSP install
into versions/<version>/langs/.

Prerequisites:
  * CSP installed (supported version: 4.2.0, 5.0.0, 5.0.2, or 5.0.4)
  * UI language set to English
  * CSP closed before running backup steps

Usage (from repo root):
  python scripts/capture_stock.py --version 5.0.4
  python scripts/capture_stock.py --csp "C:\\Program Files\\...\\resource"
  python scripts/capture_stock.py --official-langs   # also copy all resource/<lang>/ui
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

import install  # noqa: E402

GUID_RE = re.compile(
    r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z", re.I)


def _resource_files(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir()
                  if p.is_file() and GUID_RE.match(p.name))


def resource_lang_dir(resource: Path, lang: str) -> Path:
    """Return the folder holding GUID resource files for *lang*.

    CSP 5.x stores files under resource/<lang>/ui/; CSP 4.x uses a flat
    resource/<lang>/ layout. Try ui/ first, then fall back to the lang root.
    """
    ui = resource / lang / "ui"
    if _resource_files(ui):
        return ui
    flat = resource / lang
    if _resource_files(flat):
        return flat
    return ui if ui.is_dir() else flat


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


def run_pipeline_backup(script: str, csp: str | None, version: str) -> None:
    cmd = [sys.executable, str(SRC / script), "backup", "--version", version]
    if csp:
        cmd.extend(["--csp", csp])
    cmd.append("--yes")
    print(f"\n  running: {' '.join(cmd)}")
    subprocess.run(cmd, cwd=ROOT, check=True)


def main() -> int:
    from version import (  # noqa: E402
        DEFAULT_VERSION,
        GUARD_GUID,
        SUPPORTED_VERSIONS,
        english_ui_dir,
        japanese_ui_dir,
        langs_root,
        set_active_version,
        write_guard_profile,
    )

    parser = argparse.ArgumentParser(description="Capture CSP stock snapshots")
    parser.add_argument(
        "--version", default=DEFAULT_VERSION, choices=SUPPORTED_VERSIONS,
        help="CSP version to capture into versions/<ver>/langs/",
    )
    parser.add_argument("--csp", help="CSP resource directory")
    parser.add_argument(
        "--official-langs",
        action="store_true",
        help="Copy every official resource/<lang>/ui folder (dev convenience)",
    )
    args = parser.parse_args()

    set_active_version(args.version)
    langs_root_path = langs_root(args.version)

    resource = install.find_csp_resource(args.csp)
    print(f"Capturing stock for CSP {args.version}")
    print(f"  resource: {resource}")
    print(f"  output:   {langs_root_path}")

    langs_root_path.mkdir(parents=True, exist_ok=True)

    print("\nMain UI:")
    copy_ui(resource_lang_dir(resource, "english"),
            english_ui_dir(args.version), "english")
    copy_ui(resource_lang_dir(resource, "japanese"),
            japanese_ui_dir(args.version), "japanese")

    if args.official_langs:
        print("\nOptional official language UI folders:")
        for d in sorted(resource.iterdir()):
            if d.name in ("english", "japanese", "other") or not d.is_dir():
                continue
            src = resource_lang_dir(resource, d.name)
            if not _resource_files(src):
                continue
            copy_ui(src, langs_root_path / d.name / "ui", d.name)

    print("\nPlug-ins:")
    run_pipeline_backup("plugins.py", args.csp, args.version)

    print("\nVersion guard:")
    guard_path = english_ui_dir(args.version) / GUARD_GUID
    if not guard_path.is_file():
        print("  warning: guard file missing; version guard not updated")
    else:
        data = guard_path.read_bytes()
        write_guard_profile(args.version, len(data),
                            __import__("hashlib").sha256(data).hexdigest())

    print("\nDone. Next: python src/roundtrip.py versions/"
          f"{args.version}/langs/english/ui")
    return 0


if __name__ == "__main__":
    sys.exit(main())

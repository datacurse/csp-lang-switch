#!/usr/bin/env python3
"""
version.py
==========
Active CSP build version and language-data paths.

Community/stock language trees live under `versions/<ACTIVE_VERSION>/langs/`.
Translation worksheets stay shared at `translation/` (source text is stable
across minor builds; `key` columns are refreshed on re-export).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ACTIVE_VERSION = "5.0.0"
LANGS_ROOT = ROOT / "versions" / ACTIVE_VERSION / "langs"

# Main-UI resource file used to detect a matching CSP install at runtime.
GUARD_GUID = "742DEA58-ED6B-4402-BC11-20DFC6D08040"
# Filled when stock is captured from a verified 5.0.0 install.
GUARD_SIZE: int | None = 3467072
GUARD_SHA256: str | None = "383463d7b274bf55c764fe955fc39de96853fa71252654cbdd8f4420a4ade815"


def langs_dir(language: str) -> Path:
    """Root folder for one language under the active version."""
    return LANGS_ROOT / language


def english_ui_dir() -> Path:
    return langs_dir("english") / "ui"


def japanese_ui_dir() -> Path:
    return langs_dir("japanese") / "ui"


def guard_profile() -> tuple[int, str] | None:
    """Return (size, sha256) of the bundled guard file, or None if missing."""
    path = english_ui_dir() / GUARD_GUID
    if not path.is_file():
        return None
    data = path.read_bytes()
    return len(data), hashlib.sha256(data).hexdigest()


def fingerprint_guard_file(path: Path) -> tuple[int, str] | None:
    """Size + sha256 of a live CSP resource file."""
    if not path.is_file():
        return None
    data = path.read_bytes()
    return len(data), hashlib.sha256(data).hexdigest()


def install_matches_active_version(guard_path: Path) -> bool:
    """True when the live CSP main-UI guard file matches our bundled 5.0.0 stock."""
    expected = guard_profile()
    if expected is None:
        return True  # dev tree without captured stock — do not block
    actual = fingerprint_guard_file(guard_path)
    return actual == expected

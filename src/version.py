#!/usr/bin/env python3
"""
version.py
==========
Supported CSP build versions and language-data paths.

Community/stock language trees live under `versions/<ver>/langs/`.
Translation worksheets stay shared at `translation/` (source text is stable
across minor builds; `key` columns are refreshed on re-export).
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SUPPORTED_VERSIONS: tuple[str, ...] = ("4.2.0", "5.0.0", "5.0.2", "5.0.4")
DEFAULT_VERSION = "5.0.0"
ACTIVE_VERSION = DEFAULT_VERSION

# Main-UI resource file used to detect a matching CSP install at runtime.
# Compare against `resource/other/` — CSP keeps stock UI there. Community
# packs install into `resource/english/`, so that slot must not be used here.
GUARD_GUID = "742DEA58-ED6B-4402-BC11-20DFC6D08040"
GUARD_SLOT = "other"

VERSION_PROFILES: dict[str, dict[str, int | str | None]] = {
    "4.2.0": {
        "guard_size": 3459409,
        "guard_sha256": "96fbd0b5e748fb24e482bc8a3d50ff64a60ec52fc6fc7f2b5022e73e2ee93a5f",
    },
    "5.0.0": {
        "guard_size": 3467072,
        "guard_sha256": "383463d7b274bf55c764fe955fc39de96853fa71252654cbdd8f4420a4ade815",
    },
    "5.0.2": {
        "guard_size": 3467072,
        "guard_sha256": "c847ae740570c85816497b79dfcbb7e0f49c5cff0ca57cc4de85d5b4c7d9c66e",
    },
    "5.0.4": {
        "guard_size": 3489410,
        "guard_sha256": "2860f3d671fdf23a00f05bfebbe4177b71779572c3838c9af2a15f3d9630efb9",
    },
}

# Backward-compatible aliases for the default version.
GUARD_SIZE: int | None = VERSION_PROFILES["5.0.0"]["guard_size"]  # type: ignore[assignment]
GUARD_SHA256: str | None = VERSION_PROFILES["5.0.0"]["guard_sha256"]  # type: ignore[assignment]

_active_version: str = DEFAULT_VERSION


def langs_root(version: str | None = None) -> Path:
    """Return `versions/<ver>/langs` for a supported CSP version."""
    ver = version or _active_version
    if ver not in SUPPORTED_VERSIONS:
        raise ValueError(f"unsupported CSP version: {ver}")
    return ROOT / "versions" / ver / "langs"


LANGS_ROOT = langs_root()


def set_active_version(version: str) -> str:
    """Select the active CSP version and refresh module-level LANGS_ROOT."""
    global _active_version, LANGS_ROOT
    if version not in SUPPORTED_VERSIONS:
        raise ValueError(f"unsupported CSP version: {version}")
    _active_version = version
    LANGS_ROOT = langs_root(version)
    return version


def active_version() -> str:
    return _active_version


def langs_dir(language: str, version: str | None = None) -> Path:
    """Root folder for one language under a CSP version."""
    return langs_root(version) / language


def english_ui_dir(version: str | None = None) -> Path:
    return langs_dir("english", version) / "ui"


def japanese_ui_dir(version: str | None = None) -> Path:
    return langs_dir("japanese", version) / "ui"


def guard_profile(version: str | None = None) -> tuple[int, str] | None:
    """Return (size, sha256) of the bundled guard file for *version*."""
    ver = version or _active_version
    prof = VERSION_PROFILES.get(ver, {})
    size = prof.get("guard_size")
    sha = prof.get("guard_sha256")
    if size is not None and sha is not None:
        return int(size), str(sha)
    path = english_ui_dir(ver) / GUARD_GUID
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


def install_matches_version(guard_path: Path, version: str | None = None) -> bool:
    """True when the live CSP main-UI guard file matches bundled stock."""
    expected = guard_profile(version)
    if expected is None:
        return True  # dev tree without captured stock — do not block
    actual = fingerprint_guard_file(guard_path)
    return actual == expected


def install_matches_active_version(guard_path: Path) -> bool:
    return install_matches_version(guard_path, _active_version)


def write_guard_profile(version: str, size: int, digest: str) -> None:
    """Persist guard fingerprint for *version* into this module and version.py."""
    if version not in SUPPORTED_VERSIONS:
        raise ValueError(f"unsupported CSP version: {version}")
    VERSION_PROFILES[version]["guard_size"] = size
    VERSION_PROFILES[version]["guard_sha256"] = digest

    path = Path(__file__)
    text = path.read_text(encoding="utf-8")
    text = re.sub(
        rf'("{re.escape(version)}": \{{\n\s+"guard_size": )[^,\n]+',
        rf"\g<1>{size}",
        text,
        count=1,
    )
    text = re.sub(
        rf'("{re.escape(version)}": \{{\n\s+"guard_size": \d+,\n\s+"guard_sha256": )(?:None|"[^"]*")',
        rf'\g<1>"{digest}"',
        text,
        count=1,
    )
    path.write_text(text, encoding="utf-8")
    print(f"  version guard updated ({version}): "
          f"{GUARD_GUID} size={size:,} sha256={digest[:16]}...")

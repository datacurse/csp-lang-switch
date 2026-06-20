#!/usr/bin/env python3
"""
material_folders.py
===================
Copy MaterialFolderTag.mfta before a language switch and replace it on demand.

CSP may rebuild this file after UI resources change. A full-file restore keeps
the folder tree exactly as it was when the copy was taken.
"""

from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MFTA_REL = (
    "AppData/Roaming/CELSYSUserData/CELSYS/CLIPStudioCommon/MaterialDB"
    "/MaterialFolderTag.mfta"
)
BACKUP_NAME = "MaterialFolderTag.mfta.backup"


def live_mfta_path() -> Path:
    return Path.home() / Path(MFTA_REL)


def mfta_path() -> Path | None:
    path = live_mfta_path()
    return path if path.is_file() else None


def mfta_dir() -> Path | None:
    path = mfta_path()
    return path.parent if path is not None else None


def backup_file(data_root: Path) -> Path:
    return data_root / BACKUP_NAME


def has_backup(data_root: Path) -> bool:
    return backup_file(data_root).is_file()


def count_user_folders(path: Path | None = None) -> int:
    """Count IsEditable rows in an mfta file (live path when omitted)."""
    mfta = path or mfta_path()
    if mfta is None:
        return 0
    conn = sqlite3.connect(f"file:{mfta}?mode=ro", uri=True)
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM TagCloudList WHERE IsEditable=1"
        ).fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()


def backup_info(data_root: Path) -> dict[str, Any]:
    live = mfta_path()
    backup = backup_file(data_root)
    saved_at: str | None = None
    if backup.is_file():
        ts = backup.stat().st_mtime
        saved_at = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    return {
        "has_backup": backup.is_file(),
        "saved_at": saved_at,
        "live_count": count_user_folders(live),
        "backup_count": count_user_folders(backup) if backup.is_file() else 0,
        "live_size": live.stat().st_size if live else 0,
        "backup_size": backup.stat().st_size if backup.is_file() else 0,
        "path": backup,
        "live_path": live,
    }


def backup_mfta(data_root: Path, *, dry_run: bool = False) -> bool:
    """Copy the live MaterialFolderTag.mfta into the switcher data folder."""
    src = mfta_path()
    if src is None:
        return False
    dst = backup_file(data_root)
    if dry_run:
        return True
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def restore_mfta(data_root: Path, *, dry_run: bool = False) -> bool:
    """Replace the live MaterialFolderTag.mfta with the saved copy."""
    src = backup_file(data_root)
    if not src.is_file():
        return False
    dst = live_mfta_path()
    if dry_run:
        return True
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True

#!/usr/bin/env python3
"""
ui_groups.py
============
Investigation toggles: which CSP5 resource bundles to install when switching.

The main-ui pipeline normally copies every GUID file under langs/<pack>/ui/.
These groups let you install a subset to see which bundle triggers side effects
(such as CSP rebuilding MaterialFolderTag.mfta on launch).

7F9F9530 is split by string-key block prefix for investigation. Block 6 (`6/1/`)
is the English folder tree (translate). Blocks 5 and 7 are JP/CN locale copies —
never translate; see docs/VERIFIED_METHOD.md.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

# Short GUID prefixes for bundles most relevant to material folders.
EXPLICIT_SHORTS: dict[str, str] = {
    "core-ui": "742DEA58",
    "material-catalog": "E79C2AC5",
    "folder-tree": "7F9F9530",
}

# Safe-to-toggle blocks inside 7F9F9530 for partial install testing.
# Blocks 5 (`5/1/`) and 7 (`7/1/`) are JP/CN locale copies — never exposed in
# the GUI and never translated in the pack; see docs/VERIFIED_METHOD.md.
MFT_BLOCK_IDS: tuple[str, ...] = (
    "mft-1",
    "mft-2",
    "mft-3",
    "mft-4",
    "mft-8",
    "mft-9",
    "mft-10",
)

MFT_BLOCK_PREFIXES: dict[str, str] = {
    "mft-1": "1/",
    "mft-2": "2/",
    "mft-3": "3/",
    "mft-4": "4/",
    "mft-8": "8/",
    "mft-9": "9/",
    "mft-10": "10/",
}

EXPLICIT_SHORTS.update({block_id: "7F9F9530" for block_id in MFT_BLOCK_IDS})

UI_GROUP_IDS: tuple[str, ...] = (
    "core-ui",
    "material-catalog",
    *MFT_BLOCK_IDS,
    "folder-tree",
    "other-ui",
)

PIPELINE_PLUGINS = "plugins"
PIPELINE_MAIN_UI = "main-ui"

MFT_SHORT = "7F9F9530"
FOLDER_TREE_KEY_PREFIX = "6/1/"
ALL_MFT_PARTS: frozenset[str] = frozenset(MFT_BLOCK_IDS) | {"folder-tree"}

_manifest_cache: dict[str, str] | None = None


@dataclass(frozen=True)
class PartialMerge:
    """Merge overlay onto English stock instead of copying the whole file."""

    include_prefixes: tuple[str, ...] | None = None
    exclude_prefixes: tuple[str, ...] | None = None


def _load_manifest(data_root: Path) -> dict[str, str]:
    """Map manifest short id -> full GUID filename (target=yes only)."""
    global _manifest_cache
    if _manifest_cache is not None:
        return _manifest_cache

    path = data_root / "translation" / "manifest.csv"
    out: dict[str, str] = {}
    if path.is_file():
        with path.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                if (row.get("target") or "").lower() not in ("yes", "maybe"):
                    continue
                short = (row.get("short") or "").strip()
                guid = (row.get("guid") or "").strip()
                if short and guid:
                    out[short] = guid

    _manifest_cache = out
    return out


def mft_guid(data_root: Path) -> str | None:
    return _load_manifest(data_root).get(MFT_SHORT)


def default_ui_groups() -> set[str]:
    return set(UI_GROUP_IDS)


def ui_files_for_groups(data_root: Path, group_ids: set[str]) -> set[str]:
    """Resolve checked UI groups to full CSP resource filenames."""
    manifest = _load_manifest(data_root)
    if not manifest:
        return set()

    explicit_values = set(EXPLICIT_SHORTS.values())
    files: set[str] = set()

    for group_id, short in EXPLICIT_SHORTS.items():
        if group_id in group_ids and short in manifest:
            files.add(manifest[short])

    if "other-ui" in group_ids:
        for short, guid in manifest.items():
            if short not in explicit_values:
                files.add(guid)

    return files


def partial_merges_for_groups(
    data_root: Path,
    group_ids: set[str],
) -> dict[str, PartialMerge]:
    """Merge only selected 7F9F9530 blocks onto English stock."""
    selected_parts = (set(group_ids) & ALL_MFT_PARTS)
    if not selected_parts:
        return {}
    if selected_parts == ALL_MFT_PARTS:
        return {}

    prefixes: list[str] = []
    for block_id in MFT_BLOCK_IDS:
        if block_id in selected_parts:
            prefixes.append(MFT_BLOCK_PREFIXES[block_id])
    if "folder-tree" in selected_parts:
        prefixes.append(FOLDER_TREE_KEY_PREFIX)

    guid = mft_guid(data_root)
    if not guid or not prefixes:
        return {}

    return {
        guid: PartialMerge(include_prefixes=tuple(prefixes)),
    }

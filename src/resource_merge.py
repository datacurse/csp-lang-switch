#!/usr/bin/env python3
"""
resource_merge.py
=================
Merge translated strings from one CSP5 resource file onto another by key prefix.

Used to install selected blocks of 7F9F9530 onto English stock for investigation.
"""

from __future__ import annotations

from pathlib import Path

import csp5
from repack import leaf_key


def _key_selected(
    key: str,
    *,
    include_prefixes: tuple[str, ...] | None,
    exclude_prefixes: tuple[str, ...] | None,
) -> bool:
    if include_prefixes is not None:
        if not any(key.startswith(prefix) for prefix in include_prefixes):
            return False
    if exclude_prefixes is not None:
        if any(key.startswith(prefix) for prefix in exclude_prefixes):
            return False
    return True


def overlay_string_map(container: csp5.Container) -> dict[str, str]:
    out: dict[str, str] = {}
    for path, node in csp5.iter_string_nodes(container.block1):
        for index, text in enumerate(node.strings):
            out[leaf_key(path, index)] = text
    return out


def merge_resource_file(
    base_path: Path,
    overlay_path: Path,
    out_path: Path,
    *,
    include_prefixes: tuple[str, ...] | None = None,
    exclude_prefixes: tuple[str, ...] | None = None,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Copy selected strings from overlay onto base. Returns (changed, considered)."""
    base = csp5.parse(base_path.read_bytes())
    overlay = csp5.parse(overlay_path.read_bytes())
    overlay_map = overlay_string_map(overlay)

    changed = 0
    considered = 0
    for path, node in csp5.iter_string_nodes(base.block1):
        for index in range(len(node.strings)):
            key = leaf_key(path, index)
            if not _key_selected(
                key,
                include_prefixes=include_prefixes,
                exclude_prefixes=exclude_prefixes,
            ):
                continue
            considered += 1
            new_text = overlay_map.get(key)
            if new_text is None or node.strings[index] == new_text:
                continue
            node.strings[index] = new_text
            changed += 1

    if dry_run:
        return changed, considered

    rebuilt = csp5.serialize(base)
    csp5.parse(rebuilt)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(rebuilt)
    return changed, considered

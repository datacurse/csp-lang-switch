#!/usr/bin/env python3
"""Read MaterialFolderTag.mfta and list folder entries."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

DEFAULT_DIR = Path.home() / (
    "AppData/Roaming/CELSYSUserData/CELSYS/CLIPStudioCommon/MaterialDB"
)
CUSTOM_NEEDLES = ("папк", "мои", "еще", "folder", "my ", "Material Folder")


def inspect_mfta(path: Path) -> None:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    cur = conn.cursor()
    print(f"File: {path} ({path.stat().st_size:,} bytes)")

    print("\n=== TagCloudList summary ===")
    for row in cur.execute(
        "SELECT IsSystem, IsEditable, COUNT(*) "
        "FROM TagCloudList GROUP BY IsSystem, IsEditable ORDER BY 1, 2"
    ):
        print(f"  IsSystem={row[0]} IsEditable={row[1]} count={row[2]}")

    user_rows = cur.execute(
        "SELECT _PW_ID, ParentId, Title, IsEditable, IsSystem, IconId "
        "FROM TagCloudList WHERE IsSystem=0 OR IsEditable=1 "
        "ORDER BY _PW_ID"
    ).fetchall()
    print(f"\nNon-system or editable folders: {len(user_rows)}")
    for row in user_rows:
        print(f"  {row}")

    print("\n=== Possible custom folder names ===")
    hits = 0
    for row in cur.execute(
        "SELECT _PW_ID, ParentId, Title, IsSystem, IsEditable, IconId "
        "FROM TagCloudList ORDER BY _PW_ID"
    ):
        title = (row[2] or "").lower()
        if any(n in title for n in CUSTOM_NEEDLES):
            print(f"  {row}")
            hits += 1
    if hits == 0:
        print("  (none matching screenshot names like 'мои папки', 'еще больше папок')")

    conn.close()


def inspect_cmdb(path: Path) -> None:
    if not path.is_file():
        print(f"\nCatalogMaterial.cmdb not found: {path}")
        return
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    cur = conn.cursor()
    tables = [
        r[0]
        for r in cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        if not r[0].startswith("sqlite_")
    ]
    print(f"\n=== CatalogMaterial.cmdb ({path.stat().st_size:,} bytes) ===")
    print(f"Tables: {tables}")
    for tname in tables:
        cols = [r[1] for r in cur.execute(f"PRAGMA table_info({tname})")]
        n = cur.execute(f"SELECT COUNT(*) FROM [{tname}]").fetchone()[0]
        print(f"  {tname}: {n} rows, columns={cols}")
        if "Title" in cols or "Name" in cols or "Folder" in "".join(cols):
            name_col = next(
                c for c in ("Title", "Name", "FolderName") if c in cols
            ) if any(c in cols for c in ("Title", "Name", "FolderName")) else cols[1]
            for row in cur.execute(
                f"SELECT * FROM [{tname}] LIMIT 3"
            ):
                print(f"    sample: {row}")
    conn.close()


def inspect_sqlite_file(path: Path, label: str) -> None:
    if not path.is_file():
        print(f"\n{label}: not found ({path})")
        return
    print(f"\n=== {label} ===")
    print(f"File: {path} ({path.stat().st_size:,} bytes)")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    cur = conn.cursor()
    tables = [
        r[0]
        for r in cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    ]
    print(f"Tables: {tables}")
    for tname in tables:
        cols = [r[1] for r in cur.execute(f"PRAGMA table_info({tname})")]
        n = cur.execute(f"SELECT COUNT(*) FROM [{tname}]").fetchone()[0]
        print(f"  {tname}: {n} rows, columns={cols}")
        for row in cur.execute(f"SELECT * FROM [{tname}]"):
            print(f"    {row}")
    conn.close()


def scan_all_celsys_userdata() -> None:
    root = Path.home() / "AppData/Roaming/CELSYSUserData"
    terms = [
        "мои папки",
        "еще больше папок",
        "папка в папке",
        "Моя папка",
        "Manga material",
    ]
    paths = sorted(set(root.rglob("*.mfts")) | set(root.rglob("*.mfta")))
    print("\n=== Scan all palette/folder DB files ===")
    for path in paths:
        data = path.read_bytes()
        raw_hits = [t for t in terms if t.encode("utf-8") in data]
        if not raw_hits:
            continue
        print(f"\n{path}")
        print(f"  raw byte hits: {raw_hits}")
        if not data.startswith(b"SQLite format 3"):
            continue
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        cur = conn.cursor()
        tables = [
            r[0]
            for r in cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            if not r[0].startswith("sqlite_")
        ]
        active: list[str] = []
        for tname in tables:
            cols = [r[1] for r in cur.execute(f"PRAGMA table_info({tname})")]
            for col in ("TagPath", "Title"):
                if col not in cols:
                    continue
                for (val,) in cur.execute(f"SELECT [{col}] FROM [{tname}]"):
                    if val and any(h in val for h in terms):
                        active.append(f"{tname}.{col}={val!r}")
        if active:
            print("  ACTIVE rows:")
            for line in active:
                print(f"    {line}")
        else:
            print("  ACTIVE rows: none (hits are only in deleted/orphan pages)")
        conn.close()


def main() -> int:
    db_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DIR
    mfta = db_dir / "MaterialFolderTag.mfta"
    if not mfta.is_file():
        print(f"ERROR: not found: {mfta}")
        return 1

    inspect_mfta(mfta)
    inspect_cmdb(db_dir / "CatalogMaterial.cmdb")

    palette = (
        Path.home()
        / "AppData/Roaming/CELSYSUserData/CELSYS/CLIPStudioPaintVer1_5_0/Material"
        / "MaterialPalette00.mfts"
    )
    inspect_sqlite_file(palette, "MaterialPalette00.mfts")
    scan_all_celsys_userdata()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

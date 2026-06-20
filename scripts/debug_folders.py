#!/usr/bin/env python3
"""Debug material folder DB vs CSP tree."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import material_folders as mf


def main() -> int:
    path = mf.mfta_path()
    if not path:
        print("mfta not found")
        return 1
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    cur = conn.cursor()
    rows = mf._rows(conn)
    by_id = mf._by_id(rows)

    print("=== System roots (Download, 3D) ===")
    for row in rows:
        if row.get("IconId") in ("Download", "3D") or row.get("Title") in ("Download", "3D"):
            print(row)

    for label, pid in (("Download", 117), ("3D", 74), ("user 118", 118)):
        print(f"\n=== Children of {label} ({pid}) ===")
        for row in rows:
            if row.get("ParentId") == pid:
                title = row.get("Title")
                ppath = mf._parent_path(int(row["ParentId"]), by_id)
                print(f"  id={row['_PW_ID']} title={title!r} editable={row.get('IsEditable')} path={ppath}")

    print("\n=== All editable rows with full path ===")
    for row in rows:
        if not row.get("IsEditable"):
            continue
        pid = row.get("ParentId")
        ppath = mf._parent_path(int(pid) if pid is not None else None, by_id)
        full = (*ppath, ("user", str(row.get("Title", ""))))
        print(f"  {full}")

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

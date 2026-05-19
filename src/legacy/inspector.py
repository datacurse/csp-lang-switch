#!/usr/bin/env python3
"""
csp_resource_inspect.py
=======================
Inventories the Clip Studio Paint `resource` directory so the UI string file
format can be reverse-engineered for a translation patch.

It writes a single shareable file, `output.txt`, containing:
  1. A summary of every language folder (file count + total size)
  2. A cross-folder size matrix (does every language have the same files?)
  3. A byte-identity report (which language folders are identical per file?)
  4. A header hex dump of every file in the `english` folder (magic numbers?)
  5. A header hex dump of the largest files in `japanese` (for comparison)
  6. An english-vs-japanese size delta (hints at the string encoding)

No external dependencies. Works on Windows / macOS / Linux.

Usage:
    python csp_resource_inspect.py
    python csp_resource_inspect.py "C:\\path\\to\\resource"
"""

import sys
import hashlib
import datetime
from pathlib import Path
from collections import defaultdict

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
DEFAULT_RESOURCE_DIR = (
    r"C:\Program Files\CELSYS\CLIP STUDIO 1.5\CLIP STUDIO PAINT\resource"
)
OUTPUT_FILE = "output.txt"
HEADER_BYTES = 32          # leading bytes hex-dumped per file
BIG_FILE_THRESHOLD = 20_000  # bytes; files >= this also get a japanese dump

# Short codes keep the size matrix narrow enough to read/paste.
SHORT = {
    "japanese": "ja", "english": "en", "french": "fr", "german": "de",
    "indonesian": "id", "korean": "ko", "chinese_sc": "sc", "chinese_tc": "tc",
    "portuguese": "pt", "spanish": "es", "thai": "th", "other": "ot",
}
# Preferred column order for the matrix.
FOLDER_ORDER = [
    "japanese", "english", "french", "german", "spanish", "portuguese",
    "korean", "chinese_sc", "chinese_tc", "indonesian", "thai", "other",
]


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def short_code(name: str) -> str:
    return SHORT.get(name.lower(), name[:3].lower())


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def read_header(path: Path, n: int) -> bytes:
    with open(path, "rb") as f:
        return f.read(n)


def hexdump(data: bytes) -> str:
    hex_part = " ".join(f"{b:02x}" for b in data)
    ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in data)
    return f"{hex_part:<{HEADER_BYTES * 3}} | {ascii_part}"


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main() -> None:
    resource = Path(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_RESOURCE_DIR)

    if not resource.is_dir():
        print(f"ERROR: resource directory not found:\n  {resource}")
        print("Pass the correct path as an argument, e.g.:")
        print('  python csp_resource_inspect.py "C:\\...\\resource"')
        sys.exit(1)

    print(f"Scanning: {resource}")

    # data[folder_name] = { relative_path : {size, sha, header} }
    data: dict[str, dict[str, dict]] = {}
    for folder in sorted(p for p in resource.iterdir() if p.is_dir()):
        entries: dict[str, dict] = {}
        for fp in sorted(folder.rglob("*")):
            if fp.is_file():
                rel = fp.relative_to(folder).as_posix()
                try:
                    entries[rel] = {
                        "size": fp.stat().st_size,
                        "sha": sha256_of(fp),
                        "header": read_header(fp, HEADER_BYTES),
                    }
                except OSError as e:
                    entries[rel] = {"size": -1, "sha": "READ_ERROR",
                                    "header": b"", "error": str(e)}
        data[folder.name] = entries
        print(f"  {folder.name}: {len(entries)} files")

    if not data:
        print("ERROR: no subfolders found inside the resource directory.")
        sys.exit(1)

    # Ordered list of folders actually present.
    folders = [f for f in FOLDER_ORDER if f in data]
    folders += [f for f in sorted(data) if f not in folders]

    # Union of every relative file path across all folders.
    all_files = sorted({rel for entries in data.values() for rel in entries})

    out: list[str] = []
    w = out.append

    w("=" * 78)
    w("CSP RESOURCE DIRECTORY INSPECTION")
    w(f"Generated : {datetime.datetime.now().isoformat(timespec='seconds')}")
    w(f"Resource  : {resource}")
    w(f"Folders   : {len(folders)}    Unique file paths: {len(all_files)}")
    w("=" * 78)
    w("")

    # --- Section 1: folder summary ------------------------------------
    w("=== SECTION 1: LANGUAGE FOLDER SUMMARY ===")
    w(f"{'folder':<14}{'code':<6}{'files':>8}{'total bytes':>16}{'total KB':>12}")
    w("-" * 56)
    for f in folders:
        entries = data[f]
        total = sum(e["size"] for e in entries.values() if e["size"] >= 0)
        w(f"{f:<14}{short_code(f):<6}{len(entries):>8}"
          f"{total:>16,}{total / 1024:>11,.1f}")
    w("")

    # --- Section 2: cross-folder size matrix --------------------------
    w("=== SECTION 2: CROSS-FOLDER SIZE MATRIX (bytes) ===")
    w("Legend: " + "  ".join(f"{short_code(f)}={f}" for f in folders))
    w("A dash (-) means the file is absent from that folder.")
    w("")
    header = f"{'file':<40}" + "".join(f"{short_code(f):>9}" for f in folders)
    w(header)
    w("-" * len(header))
    for rel in all_files:
        row = f"{rel:<40}"
        for f in folders:
            e = data[f].get(rel)
            row += f"{e['size']:>9}" if e else f"{'-':>9}"
        w(row)
    w("")

    # --- Section 3: byte-identity groups ------------------------------
    w("=== SECTION 3: BYTE-IDENTITY GROUPS ===")
    w("For each file, language folders are grouped by identical SHA-256.")
    w("e.g. 'en=fr | ja | other' means english and french are byte-identical,")
    w("japanese and other each differ. This reveals which folders share data.")
    w("")
    for rel in all_files:
        by_hash: dict[str, list[str]] = defaultdict(list)
        for f in folders:
            e = data[f].get(rel)
            if e:
                by_hash[e["sha"]].append(short_code(f))
        groups = sorted(by_hash.values(), key=lambda g: (-len(g), g))
        present = sum(len(g) for g in groups)
        if len(by_hash) == 1 and present == len(folders):
            verdict = "ALL IDENTICAL"
        elif all(len(g) == 1 for g in groups):
            verdict = "all unique"
        else:
            verdict = " | ".join("=".join(g) for g in groups)
        w(f"{rel:<40} {verdict}")
    w("")

    # --- Section 4: english header hex dump ---------------------------
    dump_folder = "english" if "english" in data else folders[0]
    w(f"=== SECTION 4: HEADER HEX DUMP - '{dump_folder}' folder ===")
    w(f"First {HEADER_BYTES} bytes of every file. Look for shared magic numbers.")
    w("")
    for rel in sorted(data[dump_folder]):
        e = data[dump_folder][rel]
        w(f"{rel}  ({e['size']} bytes)")
        w("  " + hexdump(e["header"]))
    w("")

    # --- Section 5: japanese header dump (large files) ----------------
    if "japanese" in data:
        w("=== SECTION 5: HEADER HEX DUMP - 'japanese' folder (large files) ===")
        w(f"Files >= {BIG_FILE_THRESHOLD:,} bytes only, for format comparison.")
        w("")
        big = [(rel, e) for rel, e in sorted(data["japanese"].items())
               if e["size"] >= BIG_FILE_THRESHOLD]
        for rel, e in big:
            w(f"{rel}  ({e['size']} bytes)")
            w("  " + hexdump(e["header"]))
        w("")

    # --- Section 6: english vs japanese size delta --------------------
    if "english" in data and "japanese" in data:
        w("=== SECTION 6: ENGLISH vs JAPANESE SIZE DELTA ===")
        w("Size differences hint at the string encoding (UTF-8 / UTF-16 / SJIS).")
        w("")
        w(f"{'file':<40}{'english':>12}{'japanese':>12}{'delta':>10}{'ratio':>9}")
        w("-" * 83)
        common = sorted(set(data["english"]) & set(data["japanese"]))
        for rel in common:
            en = data["english"][rel]["size"]
            ja = data["japanese"][rel]["size"]
            delta = en - ja
            ratio = (en / ja) if ja else 0.0
            w(f"{rel:<40}{en:>12}{ja:>12}{delta:>+10}{ratio:>9.3f}")
        w("")

    w("=" * 78)
    w("END OF REPORT")
    w("=" * 78)

    report = "\n".join(out)
    Path(OUTPUT_FILE).write_text(report, encoding="utf-8")
    print(f"\nDone. Wrote {OUTPUT_FILE} "
          f"({len(report.encode('utf-8')) / 1024:.1f} KB, {len(out)} lines)")
    print(f"Location: {Path(OUTPUT_FILE).resolve()}")


if __name__ == "__main__":
    main()
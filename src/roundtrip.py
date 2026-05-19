#!/usr/bin/env python3
"""
roundtrip.py
============
Verification harness for csp5.py.

The round-trip test is:  serialize(parse(file)) == file, byte for byte.
Because the parser stores no absolute offsets and serialize() recomputes them
all, a passing round-trip proves the structural model is correct and complete.

Usage:
    python roundtrip.py                # test the two bundled 742DEA58 samples
    python roundtrip.py <file>         # test one file
    python roundtrip.py <directory>    # test every file under a directory
    python roundtrip.py <path> ...     # any mix of files and directories

Exit code is 0 only if every tested file round-trips exactly.
"""

import sys
from pathlib import Path

import csp5


def _hex_context(data: bytes, off: int, width: int = 16) -> str:
    """A hex window around byte `off`, for diagnosing a mismatch."""
    start = max(0, off - width)
    end = min(len(data), off + width)
    hexs = " ".join(f"{b:02x}" for b in data[start:end])
    return f"[{start}:{end}] {hexs}"


def check_file(path: Path) -> tuple[bool, str]:
    """Round-trip one file. Return (ok, message)."""
    try:
        original = path.read_bytes()
    except OSError as e:
        return False, f"READ ERROR: {e}"

    try:
        container = csp5.parse(original)
        rebuilt = csp5.serialize(container)
    except csp5.CSPFormatError as e:
        return False, f"FORMAT ERROR: {e}"
    except Exception as e:                       # surface any unexpected failure
        return False, f"{type(e).__name__}: {e}"

    if rebuilt == original:
        stats = csp5.tree_stats(container.block1)
        return True, (f"OK  {len(original):,} bytes  "
                      f"({stats['directories']} dirs, "
                      f"{stats['string_records']} strings, "
                      f"{stats['blob_leaves']} blobs, "
                      f"depth {stats['max_depth']})")

    # Locate and report the first divergence.
    n = min(len(original), len(rebuilt))
    div = next((i for i in range(n) if original[i] != rebuilt[i]), n)
    lines = [f"MISMATCH at byte {div}"]
    if len(original) != len(rebuilt):
        lines.append(f"  (size {len(original):,} -> {len(rebuilt):,})")
    lines.append("\n      original: " + _hex_context(original, div))
    lines.append("\n      rebuilt : " + _hex_context(rebuilt, div))
    return False, "".join(lines)


def _gather(target: Path) -> list[Path]:
    """Expand a path argument into a sorted list of files to test."""
    if target.is_file():
        return [target]
    if target.is_dir():
        return sorted(p for p in target.rglob("*") if p.is_file())
    return []


def _default_samples(repo_root: Path) -> list[Path]:
    """The two known 742DEA58 samples used when no arguments are given."""
    candidates = {
        "english": (repo_root / "resource" / "english"
                    / "742DEA58-ED6B-4402-BC11-20DFC6D08040"),
        "japanese": (repo_root / "resource" / "japanese"
                     / "742DEA58-ED6B-4402-BC11-20DFC6D08040"),
    }
    files = []
    for label, path in candidates.items():
        if path.exists():
            files.append(path)
        else:
            print(f"WARNING: {label} sample not found at {path}")
    return files


def main(argv: list[str]) -> int:
    repo_root = Path(__file__).resolve().parent.parent

    if argv:
        files: list[Path] = []
        for arg in argv:
            found = _gather(Path(arg))
            if not found:
                print(f"WARNING: nothing to test at {arg}")
            files += found
    else:
        files = _default_samples(repo_root)

    if not files:
        print("No files to test.")
        return 1

    verbose = len(files) <= 12
    passed = 0
    failed: list[tuple[Path, str]] = []

    for path in files:
        ok, msg = check_file(path)
        if ok:
            passed += 1
            if verbose:
                print(f"PASS  {path}\n      {msg}")
        else:
            failed.append((path, msg))
            print(f"FAIL  {path}\n      {msg}")

    print(f"\n{passed}/{len(files)} files round-trip byte-for-byte.")
    if failed:
        print(f"{len(failed)} failed:")
        for path, msg in failed:
            print(f"  {path}  --  {msg.splitlines()[0]}")
        return 1
    print("All files round-trip exactly.  Round-trip gate PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""
plugins.py
==========
Translate the strings embedded in CSP's filter plug-in DLLs.

CSP's new Filter menu -- the categories (Blur, Correction, Distort, Effect,
Render, Sharpen), the filter names, and their dialog parameters -- is NOT in the
resource bundles that `batch.py` / `repack.py` handle. It lives inside the ~37
plug-in DLLs in `<CSP install>/PlugIn/PAINT/`, stored as standard Windows
`RT_STRING` resources with one `LANG` entry per language. CSP ships no Russian
entry, so those menus fall back to English in the Russian build.

This tool patches the **English (LANG 9)** `RT_STRING` entry of each DLL with
the selected community pack -- the same "English slot = our translation" idea
the resource tooling uses.

Layout of one DLL's English strings: a `RT_STRING` block is 16 consecutive
`[uint16 length][UTF-16LE text]` slots. Each filter plug-in uses a handful:
slot order is `[category name][filter name][parameter labels...]`.

Pipeline (run from the repo root: python src/plugins.py <cmd>)
--------
  backup    copy the install's PlugIn/PAINT/*.dll into the repo -> plugins/
  extract   read every DLL's English strings -> translation/plugins.csv
  ...translate the `target` column of plugins.csv...
  apply     write the translations into patched DLLs -> langs/<language>/plugins/
  install   copy the patched DLLs into the live CSP install
  restore   copy the original DLLs back into the live CSP install

`install` / `restore` write into C:\\Program Files and self-elevate via UAC
(via common.py). `extract` / `apply` need `pefile` (`pip install pefile`).
"""

from __future__ import annotations

import argparse
import csv
import ctypes
import shutil
import struct
import sys
from ctypes import wintypes
from pathlib import Path

try:
    import pefile
except ImportError:
    sys.exit("error: this tool needs 'pefile' -- install it with:\n"
             "       pip install pefile")

from common import find_csp_resource, ensure_admin, check_csp_closed, confirm
from version import LANGS_ROOT, ROOT

# ----------------------------------------------------------------------
# Project paths
# ----------------------------------------------------------------------
PLUGINS_DIR = LANGS_ROOT / "english" / "plugins"   # original DLLs (English)
BUILD_DIR = LANGS_ROOT / "russian" / "plugins"     # patched DLLs
WORKSHEET = ROOT / "translation" / "plugins.csv"

ENGLISH_LANG = 9                           # RT_STRING LANG id for English
RT_STRING = 6                              # resource type id
RSRC = pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_RESOURCE"]


def configure_language(language: str) -> None:
    """Select which langs/<language>/plugins build directory to use."""
    global BUILD_DIR
    BUILD_DIR = LANGS_ROOT / language / "plugins"


# ----------------------------------------------------------------------
# RT_STRING reading (pefile)
# ----------------------------------------------------------------------
def parse_block(data: bytes) -> list[str]:
    """A RT_STRING block = 16 consecutive [uint16 len][len UTF-16LE wchars]."""
    out, o = [], 0
    for _ in range(16):
        if o + 2 > len(data):
            out.append("")
            continue
        n = int.from_bytes(data[o:o + 2], "little")
        o += 2
        out.append(data[o:o + 2 * n].decode("utf-16le", "replace"))
        o += 2 * n
    return out


def read_string_blocks(dll: Path) -> dict[tuple[int, int], list[str]]:
    """{(block_id, lang_id): [16 strings]} for every RT_STRING resource in dll."""
    pe = pefile.PE(str(dll), fast_load=True)
    pe.parse_data_directories(directories=[RSRC])
    blocks: dict[tuple[int, int], list[str]] = {}
    res = getattr(pe, "DIRECTORY_ENTRY_RESOURCE", None)
    if res:
        for t in res.entries:
            if t.id != RT_STRING:
                continue
            for nm in t.directory.entries:
                for lg in nm.directory.entries:
                    s = lg.data.struct
                    blocks[(nm.id, lg.id)] = parse_block(
                        pe.get_data(s.OffsetToData, s.Size))
    pe.close()
    return blocks


def english_strings(dll: Path) -> dict[int, list[str]]:
    """{block_id: [16 strings]} for the English (LANG 9) entries only."""
    return {bid: strs for (bid, lang), strs in read_string_blocks(dll).items()
            if lang == ENGLISH_LANG}


def has_cyrillic(s: str) -> bool:
    return any(0x0400 <= ord(c) <= 0x04FF for c in s)


def looks_patched(dll: Path) -> bool:
    """True if the DLL's English entry already holds Cyrillic -- i.e. it has
    been patched before and is not a clean original."""
    return any(has_cyrillic(s)
               for strs in english_strings(dll).values() for s in strs)


# ----------------------------------------------------------------------
# RT_STRING writing (Windows UpdateResource API)
# ----------------------------------------------------------------------
def pack_block(slots: list[str]) -> bytes:
    """16 strings -> RT_STRING block bytes (the inverse of parse_block)."""
    return b"".join(struct.pack("<H", len(s)) + s.encode("utf-16le")
                    for s in slots)


def write_english_blocks(dll_path: str, blocks: dict[int, list[str]]) -> None:
    """Replace the English (LANG 9) RT_STRING blocks of dll_path in place.

    Uses the Windows UpdateResource API -- it rebuilds .rsrc and copes with
    size changes (Russian text is longer than English)."""
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.BeginUpdateResourceW.restype = wintypes.HANDLE
    k.BeginUpdateResourceW.argtypes = [wintypes.LPCWSTR, wintypes.BOOL]
    k.UpdateResourceW.argtypes = [wintypes.HANDLE, wintypes.LPVOID,
                                  wintypes.LPVOID, wintypes.WORD,
                                  wintypes.LPVOID, wintypes.DWORD]
    k.EndUpdateResourceW.argtypes = [wintypes.HANDLE, wintypes.BOOL]

    h = k.BeginUpdateResourceW(dll_path, False)
    if not h:
        raise OSError(ctypes.get_last_error(), "BeginUpdateResource")
    for bid, slots in blocks.items():
        data = pack_block(slots)
        buf = ctypes.create_string_buffer(data, len(data))
        if not k.UpdateResourceW(h, RT_STRING, bid, ENGLISH_LANG, buf, len(data)):
            raise OSError(ctypes.get_last_error(), f"UpdateResource block {bid}")
    if not k.EndUpdateResourceW(h, False):
        raise OSError(ctypes.get_last_error(), "EndUpdateResource")


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def csp_plugin_dir(explicit: str | None) -> Path:
    """The live install's PlugIn/PAINT folder (sibling of resource/)."""
    p = find_csp_resource(explicit).parent / "PlugIn" / "PAINT"
    if not p.is_dir():
        sys.exit(f"error: plug-in folder not found: {p}")
    return p


def load_worksheet() -> dict[str, str]:
    """{key: target} from plugins.csv -- blank targets dropped."""
    if not WORKSHEET.exists():
        sys.exit(f"error: {WORKSHEET} not found -- run 'extract' first")
    out = {}
    for r in csv.DictReader(open(WORKSHEET, encoding="utf-8-sig")):
        if r["target"].strip():
            out[r["key"]] = r["target"]
    return out


def existing_targets() -> dict[str, str]:
    """Existing translations keyed by worksheet key or English source text."""
    if not WORKSHEET.exists():
        return {}
    out: dict[str, str] = {}
    for r in csv.DictReader(open(WORKSHEET, encoding="utf-8-sig")):
        t = r.get("target", "").strip()
        if not t:
            continue
        out[r["key"]] = t
        out.setdefault(r["source"], t)
    return out


# ----------------------------------------------------------------------
# Commands
# ----------------------------------------------------------------------
def cmd_backup(args) -> None:
    src = csp_plugin_dir(args.csp)
    PLUGINS_DIR.mkdir(exist_ok=True)

    copied, kept, patched = [], [], []
    for dll in sorted(src.glob("*.dll")):
        dst = PLUGINS_DIR / dll.name
        if dst.exists():
            kept.append(dll.name)            # never overwrite a saved original
        elif looks_patched(dll):
            patched.append(dll.name)         # a patched DLL is not an original
        else:
            shutil.copy2(dll, dst)
            copied.append(dll.name)

    print(f"backup -> {PLUGINS_DIR}")
    print(f"  copied {len(copied)} original DLL(s)")
    if kept:
        print(f"  kept {len(kept)} already in {PLUGINS_DIR} (left untouched)")
    if patched:
        print(f"  SKIPPED {len(patched)} already-patched DLL(s) -- need the "
              f"stock original: {', '.join(patched)}")


def cmd_extract(args) -> None:
    dlls = sorted(PLUGINS_DIR.glob("*.dll"))
    if not dlls:
        sys.exit(f"error: no DLLs in {PLUGINS_DIR} -- run 'backup' first")

    keep = existing_targets()
    rows, no_english = [], []
    for dll in dlls:
        en = english_strings(dll)
        if not en:
            no_english.append(dll.name)
            continue
        for bid in sorted(en):
            for slot, text in enumerate(en[bid]):
                if text.strip():
                    key = f"{dll.name}:{bid}:{slot}"
                    target = keep.get(key, keep.get(text, ""))
                    rows.append((key, text, target))

    WORKSHEET.parent.mkdir(exist_ok=True)
    with open(WORKSHEET, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["key", "source", "target"])
        w.writerows(rows)

    uniq = len({src for _k, src, _t in rows})
    done = sum(1 for _k, _s, t in rows if t.strip())
    print(f"extract -> {WORKSHEET}")
    print(f"  {len(rows)} strings ({uniq} unique) from "
          f"{len(dlls) - len(no_english)} DLL(s)")
    print(f"  {done} translated, {len(rows) - done} to go")
    if no_english:
        print(f"  ({len(no_english)} DLL(s) had no English RT_STRING: "
              f"{', '.join(no_english)})")


def cmd_apply(args) -> None:
    sheet = load_worksheet()
    dlls = sorted(PLUGINS_DIR.glob("*.dll"))
    if not dlls:
        sys.exit(f"error: no DLLs in {PLUGINS_DIR} -- run 'backup' first")
    BUILD_DIR.mkdir(exist_ok=True)

    patched_n = strings_n = 0
    untranslated = []
    for dll in dlls:
        blocks = english_strings(dll)
        new_blocks: dict[int, list[str]] = {}
        for bid, slots in blocks.items():
            out = list(slots)
            for i, text in enumerate(slots):
                if not text.strip():
                    continue
                tgt = sheet.get(f"{dll.name}:{bid}:{i}")
                if tgt:
                    out[i] = tgt
                    strings_n += 1
                else:
                    untranslated.append(f"{dll.name}:{bid}:{i}")
            new_blocks[bid] = out

        dst = BUILD_DIR / dll.name
        shutil.copy2(dll, dst)
        if new_blocks:
            write_english_blocks(str(dst), new_blocks)
            # round-trip check: the patched English entry must read back equal
            got = english_strings(dst)
            if got != new_blocks:
                sys.exit(f"error: round-trip check failed for {dll.name}")
        patched_n += 1

    print(f"apply -> {BUILD_DIR}")
    print(f"  patched {patched_n} DLL(s), {strings_n} strings translated")
    if untranslated:
        print(f"  WARNING: {len(untranslated)} string(s) had no translation "
              f"and stay English:")
        for k in untranslated[:10]:
            print(f"    {k}")
        if len(untranslated) > 10:
            print(f"    ... and {len(untranslated) - 10} more")


def cmd_install(args) -> None:
    plugin_dir = csp_plugin_dir(args.csp)
    builds = sorted(BUILD_DIR.glob("*.dll"))
    if not builds:
        sys.exit(f"error: no patched DLLs in {BUILD_DIR} -- run 'apply' first")

    check_csp_closed(args.force)
    if not args.dry_run:
        ensure_admin()  # re-launches elevated if needed, then exits

    print(f"will install {len(builds)} patched plug-in DLL(s)")
    print(f"  {BUILD_DIR}  ->  {plugin_dir}")
    if args.dry_run:
        for b in builds:
            print(f"  [dry-run] {b.name}")
        print("[dry-run] nothing was changed")
        return
    if not confirm("proceed?", args.yes):
        print("aborted")
        return

    for b in builds:
        shutil.copy2(b, plugin_dir / b.name)
    print(f"\ndone -- {len(builds)} plug-in DLL(s) installed.")
    print("restart CSP; the Filter menu plug-ins now use the selected pack.")
    print("run 'python src/plugins.py restore' to undo.")


def cmd_restore(args) -> None:
    plugin_dir = csp_plugin_dir(args.csp)
    originals = sorted(PLUGINS_DIR.glob("*.dll"))
    if not originals:
        sys.exit(f"error: no originals in {PLUGINS_DIR} -- nothing to restore")

    check_csp_closed(args.force)
    if not args.dry_run:
        ensure_admin()

    print(f"will restore {len(originals)} original plug-in DLL(s)")
    print(f"  {PLUGINS_DIR}  ->  {plugin_dir}")
    if args.dry_run:
        print("[dry-run] nothing was changed")
        return
    if not confirm("proceed?", args.yes):
        print("aborted")
        return

    for o in originals:
        shutil.copy2(o, plugin_dir / o.name)
    print(f"\ndone -- {len(originals)} original plug-in DLL(s) restored.")


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------
def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="plugins.py",
        description="Translate CSP filter plug-in DLLs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--csp", metavar="DIR",
                        help="CSP 'resource' folder (auto-detected if omitted)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print what would happen, change nothing")
    parser.add_argument("--yes", action="store_true",
                        help="skip the confirmation prompt")
    parser.add_argument("--force", action="store_true",
                        help="proceed even if CSP appears to be running")
    parser.add_argument("--language", default="russian",
                        help="community pack under langs/ (default: russian)")
    # Set automatically on the elevated relaunch; keeps that console open.
    parser.add_argument("--keep-open", action="store_true",
                        help=argparse.SUPPRESS)
    parser.add_argument("command",
                        choices=("backup", "extract", "apply",
                                 "install", "restore"),
                        help="pipeline step to run")

    args = parser.parse_args(argv)
    configure_language(args.language)
    try:
        {"backup": cmd_backup, "extract": cmd_extract, "apply": cmd_apply,
         "install": cmd_install, "restore": cmd_restore}[args.command](args)
    finally:
        if args.keep_open:
            try:
                input("\npress Enter to close this window...")
            except EOFError:
                pass


if __name__ == "__main__":
    main()

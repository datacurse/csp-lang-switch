#!/usr/bin/env python3
"""
lang.py
=======
Top-level "change the language of my CSP install" switcher.

    python src/lang.py russian      <- show the Russian translation everywhere
    python src/lang.py original     <- restore whatever was there before we ran
    python src/lang.py status       <- per-pipeline current state
    python src/lang.py              <- (interactive: show a numbered menu)

This is the user-facing entrypoint. It wraps the four per-subsystem pipelines:

    main UI       src/install.py          (resource bundles in C:\\Program Files)
    plug-ins      src/plugins.py          (filter DLLs in C:\\Program Files)
    tool palette  src/tools.py            (SQLite DBs in C:\\Program Files + %APPDATA%)
    materials     src/materials.py        (SQLite catalog in %APPDATA%)

Two states are exposed to the user:

  * `russian`   -- the patched build for every pipeline
  * `original`  -- whatever was on this machine before we ever ran. For the
                   main UI that is the stock English CSP ships in
                   `langs/english/ui/`; for the other three it is the local
                   backup snapshot the pipelines maintain under
                   `langs/english/` (in source mode) or
                   `%LOCALAPPDATA%/csp-russian/` (in the bundled exe).

The four backup snapshots are taken automatically the first time `lang.py
russian` runs, so the user never has to remember an ordering of `backup` then
`install`. If a snapshot already exists it is left untouched (the per-pipeline
`backup` commands refuse to overwrite an original with a patched file).

Source mode vs bundled exe
--------------------------
This module runs in two layouts:

  * **Source mode**: `python src/lang.py ...` from a git checkout. Paths are
    repo-relative (langs/russian/, langs/english/, ...). State lives at the
    repo root.

  * **Bundled exe** (PyInstaller / csp-russian.spec): patched builds are
    read-only inside the extracted bundle (`sys._MEIPASS`). The writeable
    backup snapshots and state file live in `%LOCALAPPDATA%/csp-russian/` --
    persistent across runs, survives "exe in a new folder", no admin needed
    to write. The pipeline modules' own path constants are monkey-patched
    once at startup so they read/write in the right places without any other
    changes to their code.

Direct calls, not subprocess
----------------------------
We import the four pipeline modules and call their cmd_* functions directly.
That keeps everything in one process (one UAC prompt, one console window) and
is what makes the PyInstaller bundle work -- subprocesses would try to
re-launch the bundled exe instead of running scripts.

No external dependencies beyond what the pipeline modules already need
(`pefile` for plugins; otherwise standard library).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

import install  # for ensure_admin, check_csp_closed, find_csp_resource, etc.


# ----------------------------------------------------------------------
# Paths -- source mode vs bundled exe
# ----------------------------------------------------------------------
FROZEN = getattr(sys, "frozen", False)

if FROZEN:
    # PyInstaller extracts the bundle's contents here (read-only, ephemeral
    # per-process -- fine for the patched builds we ship inside the exe).
    DATA_ROOT = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    # Persistent per-user state and writeable backup snapshots.
    _localappdata = os.environ.get("LOCALAPPDATA") or \
        str(Path.home() / "AppData" / "Local")
    USER_DATA = Path(_localappdata) / "csp-russian"
    USER_DATA.mkdir(parents=True, exist_ok=True)
    STATE_FILE = USER_DATA / "state.json"
else:
    DATA_ROOT = Path(__file__).resolve().parent.parent
    USER_DATA = DATA_ROOT
    STATE_FILE = DATA_ROOT / ".lang-state.json"

# Bundled read-only references. Every language is a tree under `langs/`, both
# on disk and inside the .exe.
RUSSIAN_BUILD     = DATA_ROOT / "langs" / "russian" / "ui"
RUSSIAN_PLUGINS   = DATA_ROOT / "langs" / "russian" / "plugins"
RUSSIAN_TOOLS     = DATA_ROOT / "langs" / "russian" / "tools"
RUSSIAN_MATERIALS = DATA_ROOT / "langs" / "russian" / "materials"
ENGLISH_STOCK     = DATA_ROOT / "langs" / "english" / "ui"

# Writeable backup snapshots (per-machine). In bundled mode these live at
# %LOCALAPPDATA%/csp-russian/{plugins,tools,materials}/; the path is kept
# stable across versions so existing user backups are not stranded. In source
# mode these constants are unused (each pipeline module's own ROOT-relative
# paths under langs/english/ apply).
PLUGINS_BACKUP    = USER_DATA / "plugins"
TOOLS_BACKUP      = USER_DATA / "tools"
MATERIALS_BACKUP  = USER_DATA / "materials"

PIPELINES = ("main-ui", "plugins", "tools", "materials")


# Lazy module loaders. Lazy so the wrapper itself loads even on an environment
# where a pipeline module would sys.exit at import time (no %APPDATA% layout,
# missing pefile in a stripped install, etc.).
def _tools_module():
    import tools
    return tools


def _materials_module():
    import materials
    return materials


def _plugins_module():
    import plugins
    return plugins


# ----------------------------------------------------------------------
# Pipeline path overrides (bundled mode only)
# ----------------------------------------------------------------------
_pipelines_configured = False


def _configure_pipelines() -> None:
    """In bundled mode, point each pipeline module's path constants at the
    right places: russian build inside the read-only bundle, backups in
    %LOCALAPPDATA%. In source mode this is a no-op (their own ROOT-relative
    paths are already correct)."""
    global _pipelines_configured
    if _pipelines_configured or not FROZEN:
        _pipelines_configured = True
        return
    install.ROOT = DATA_ROOT
    install.LANGS_DIR = DATA_ROOT / "langs"
    p = _plugins_module()
    p.PLUGINS_DIR = PLUGINS_BACKUP
    p.BUILD_DIR = RUSSIAN_PLUGINS
    t = _tools_module()
    t.TOOLS_DIR = TOOLS_BACKUP
    t.BUILD_DIR = RUSSIAN_TOOLS
    m = _materials_module()
    m.MATERIALS_DIR = MATERIALS_BACKUP
    m.BUILD_DIR = RUSSIAN_MATERIALS
    _pipelines_configured = True


# ----------------------------------------------------------------------
# State file
# ----------------------------------------------------------------------
def load_state() -> dict:
    if not STATE_FILE.is_file():
        return {"version": 1, "pipelines": {}}
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "pipelines": {}}
    if not isinstance(data, dict) or "pipelines" not in data:
        return {"version": 1, "pipelines": {}}
    return data


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def set_pipeline_state(state: dict, pipeline: str, current: str,
                       fingerprint: str) -> None:
    state.setdefault("pipelines", {})[pipeline] = {
        "current": current,
        "fingerprint": fingerprint,
    }


# ----------------------------------------------------------------------
# Fingerprinting
# ----------------------------------------------------------------------
def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fingerprint_dir(folder: Path, patterns: tuple[str, ...] = ("*",),
                    recursive: bool = False) -> str | None:
    """sha256 over "<relpath>\\t<sha256>\\n" lines for files matching `patterns`.

    Returns None if the folder is missing or contains no matching files."""
    if not folder.is_dir():
        return None
    files: set[Path] = set()
    for pat in patterns:
        it = folder.rglob(pat) if recursive else folder.glob(pat)
        for p in it:
            if p.is_file():
                files.add(p)
    if not files:
        return None
    h = hashlib.sha256()
    for p in sorted(files):
        rel = p.relative_to(folder).as_posix()
        h.update(f"{rel}\t{_hash_file(p)}\n".encode("utf-8"))
    return h.hexdigest()


def fingerprint_files(files: list[Path]) -> str | None:
    """Same shape as fingerprint_dir but for an explicit file list."""
    real = [p for p in files if p.is_file()]
    if not real:
        return None
    h = hashlib.sha256()
    for p in sorted(real):
        h.update(f"{p.name}\t{_hash_file(p)}\n".encode("utf-8"))
    return h.hexdigest()


# ----------------------------------------------------------------------
# Per-pipeline locators (read-only -- used by status + fingerprinting)
#
# We deliberately reuse the per-pipeline scripts' own path resolvers, so the
# wrapper can't drift from what they actually read and write.
# ----------------------------------------------------------------------
def main_ui_install_dir(csp: str | None, slot: str) -> Path:
    return install.find_csp_resource(csp) / slot


def main_ui_resource_files(folder: Path) -> list[Path]:
    return install.resource_files(folder)


def plugin_install_dir(csp: str | None) -> Path:
    res = install.find_csp_resource(csp)
    return res.parent / "PlugIn" / "PAINT"


def tool_install_files(csp: str | None) -> list[Path]:
    try:
        t = _tools_module()
        out: list[Path] = []
        for tag, root in t.roots(csp).items():
            for abspath, _rel in t.discover(root, tag):
                out.append(abspath)
        return out
    except SystemExit:
        return []


def material_install_files() -> list[Path]:
    try:
        m = _materials_module()
        out: list[Path] = []
        cat = m.catalog_db()
        if cat.is_file():
            out.append(cat)
        for pack in m.live_packs():
            for fname in m.PACK_FILES:
                p = pack / fname
                if p.is_file():
                    out.append(p)
        return out
    except SystemExit:
        return []


# ----------------------------------------------------------------------
# Pipeline plumbing
# ----------------------------------------------------------------------
def _pipe_args(**kwargs) -> argparse.Namespace:
    """An argparse.Namespace with the defaults every pipeline cmd_* expects.
    `yes=True` because the wrapper does its own confirmation at the top."""
    defaults = dict(csp=None, dry_run=False, yes=True, force=False,
                    keep_open=False)
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def _files_equal(slot_dir: Path, ref_dir: Path,
                 names: set[str]) -> bool | None:
    """True iff every `name` exists in both folders with identical content.
    None if `names` is empty (nothing to compare -- 'unknown')."""
    if not names:
        return None
    for name in names:
        a, b = slot_dir / name, ref_dir / name
        if not (a.is_file() and b.is_file()):
            return False
        if a.stat().st_size != b.stat().st_size:
            return False
        if _hash_file(a) != _hash_file(b):
            return False
    return True


class Pipeline:
    """One swappable subsystem: how to identify its 'current' state, and how
    to switch it between `original` and `russian`.

    Subclasses implement `is_state(csp, state)` returning True/False/None
    (None = can't tell; the reference for that state is missing). They also
    implement `install_fingerprint` -- an opaque content hash of the live
    install location -- which is used only as the cache key (drift detection),
    never as the truth source for which state we're in."""

    def __init__(self, name: str):
        self.name = name

    def install_fingerprint(self, csp: str | None) -> str | None:
        raise NotImplementedError

    def is_state(self, csp: str | None, state: str) -> bool | None:
        raise NotImplementedError

    def switch_to(self, target: str, csp: str | None, dry_run: bool) -> None:
        raise NotImplementedError


class MainUIPipeline(Pipeline):
    """Main UI bundles. `langs/english/ui/` (stock) is `original`;
    `langs/russian/ui/` (a 32-file subset of the 39 stock files) is `russian`."""

    def install_fingerprint(self, csp):
        return fingerprint_files(
            main_ui_resource_files(main_ui_install_dir(csp, "english")))

    def is_state(self, csp, state):
        slot = main_ui_install_dir(csp, "english")
        ref = RUSSIAN_BUILD if state == "russian" else ENGLISH_STOCK
        ref_names = {p.name for p in main_ui_resource_files(ref)}
        return _files_equal(slot, ref, ref_names)

    def switch_to(self, target, csp, dry_run):
        target_lang = "russian" if target == "russian" else "english"
        install.cmd_install(_pipe_args(
            target=target_lang, slot="english", csp=csp, dry_run=dry_run))


class PluginsPipeline(Pipeline):
    """Filter-menu plug-in DLLs."""

    def install_fingerprint(self, csp):
        return fingerprint_dir(plugin_install_dir(csp), ("*.dll",))

    def is_state(self, csp, state):
        slot = plugin_install_dir(csp)
        ref = RUSSIAN_PLUGINS if state == "russian" else PLUGINS_BACKUP
        ref_names = {p.name for p in ref.glob("*.dll")} if ref.is_dir() else set()
        return _files_equal(slot, ref, ref_names)

    def switch_to(self, target, csp, dry_run):
        p = _plugins_module()
        if target == "russian":
            self._ensure_backup(dry_run)
            p.cmd_install(_pipe_args(csp=csp, dry_run=dry_run))
        else:
            p.cmd_restore(_pipe_args(csp=csp, dry_run=dry_run))

    def _ensure_backup(self, dry_run):
        p = _plugins_module()
        if p.PLUGINS_DIR.is_dir() and any(p.PLUGINS_DIR.glob("*.dll")):
            return
        print(f"\n(no plug-in backup at {p.PLUGINS_DIR} -- snapshotting first)")
        p.cmd_backup(_pipe_args(dry_run=dry_run))


class ToolsPipeline(Pipeline):
    """Tool-palette SQLite DBs (install seed + per-user data). State detection
    only compares the *install seed* -- the per-user copy is mutated by CSP at
    runtime so byte-equality there is unreliable. Patching still covers both."""

    def install_fingerprint(self, csp):
        return fingerprint_files(tool_install_files(csp))

    def is_state(self, csp, state):
        try:
            t = _tools_module()
            ref_root = RUSSIAN_TOOLS if state == "russian" else TOOLS_BACKUP
            if not ref_root.is_dir():
                return None
            seed = t.roots(csp).get(t.SEED)
            if seed is None:
                return None
            saw_any = False
            for abspath, rel in t.discover(seed, t.SEED):
                saw_any = True
                rf = ref_root / t.SEED / rel
                if not rf.is_file():
                    return False
                if abspath.stat().st_size != rf.stat().st_size:
                    return False
                if _hash_file(abspath) != _hash_file(rf):
                    return False
            return True if saw_any else None
        except SystemExit:
            return None

    def switch_to(self, target, csp, dry_run):
        t = _tools_module()
        if target == "russian":
            self._ensure_backup(dry_run, csp)
            t.cmd_install(_pipe_args(csp=csp, dry_run=dry_run))
        else:
            t.cmd_restore(_pipe_args(csp=csp, dry_run=dry_run))

    def _ensure_backup(self, dry_run, csp):
        t = _tools_module()
        if t.TOOLS_DIR.is_dir() and any(p.is_file() for p in t.TOOLS_DIR.rglob("*")):
            return
        print(f"\n(no tool-DB backup at {t.TOOLS_DIR} -- snapshotting first)")
        t.cmd_backup(_pipe_args(csp=csp, dry_run=dry_run))


class MaterialsPipeline(Pipeline):
    """Material catalog: .cmdb + per-pack catalog.xml / .cac files. State
    detection compares the per-pack files only -- the .cmdb is mutated by CSP
    at runtime. Patching still covers the .cmdb."""

    def install_fingerprint(self, csp):
        return fingerprint_files(material_install_files())

    def is_state(self, csp, state):
        try:
            m = _materials_module()
            ref_root = RUSSIAN_MATERIALS if state == "russian" else MATERIALS_BACKUP
            if not ref_root.is_dir():
                return None
            md = m.material_dir()
            packs = m.live_packs()
            if not packs:
                return None
            for pack in packs:
                rel_pack = pack.relative_to(md)
                for fname in m.PACK_FILES:
                    sf = pack / fname
                    if not sf.is_file():
                        continue
                    rf = ref_root / m.CATALOG / rel_pack / fname
                    if not rf.is_file():
                        return False
                    if sf.stat().st_size != rf.stat().st_size:
                        return False
                    if _hash_file(sf) != _hash_file(rf):
                        return False
            return True
        except (SystemExit, ValueError):
            return None

    def switch_to(self, target, csp, dry_run):
        m = _materials_module()
        if target == "russian":
            self._ensure_backup(dry_run)
            m.cmd_install(_pipe_args(dry_run=dry_run))
        else:
            m.cmd_restore(_pipe_args(dry_run=dry_run))

    def _ensure_backup(self, dry_run):
        m = _materials_module()
        if m.MATERIALS_DIR.is_dir() and any(
                p.is_file() for p in m.MATERIALS_DIR.rglob("*")):
            return
        print(f"\n(no material backup at {m.MATERIALS_DIR} -- snapshotting first)")
        m.cmd_backup(_pipe_args(dry_run=dry_run))


def all_pipelines() -> dict[str, Pipeline]:
    return {
        "main-ui":   MainUIPipeline("main-ui"),
        "plugins":   PluginsPipeline("plugins"),
        "tools":     ToolsPipeline("tools"),
        "materials": MaterialsPipeline("materials"),
    }


# ----------------------------------------------------------------------
# State classification
# ----------------------------------------------------------------------
def classify(pipe: Pipeline, csp: str | None,
             cached: dict | None) -> tuple[str, str | None]:
    """Return (current_state, fingerprint). `current_state` ∈ {russian, original,
    unknown}. The cache is the fast path; if the install's fingerprint matches
    what we saw last time, we trust the cached label. Otherwise we recompute by
    asking each pipeline whether its install matches `russian` or `original`."""
    fp = pipe.install_fingerprint(csp)
    if cached and cached.get("fingerprint") == fp and \
            cached.get("current") in ("russian", "original"):
        return cached["current"], fp
    if pipe.is_state(csp, "russian") is True:
        return "russian", fp
    if pipe.is_state(csp, "original") is True:
        return "original", fp
    return "unknown", fp


# ----------------------------------------------------------------------
# Commands
# ----------------------------------------------------------------------
_LABELS = {"main-ui": "main UI", "plugins": "plug-ins",
           "tools": "tool palette", "materials": "materials"}

_MARKERS = {"russian": "RU", "original": "EN", "unknown": "??"}


def cmd_status(args) -> None:
    state = load_state()
    pipes = all_pipelines()
    cached_all = state.get("pipelines", {})

    print()
    print("  Current state:")
    width = max(len(_LABELS[n]) for n in pipes)
    for name, pipe in pipes.items():
        current, fp = classify(pipe, args.csp, cached_all.get(name))
        if fp is not None:
            set_pipeline_state(state, name, current, fp)
        label = _LABELS[name].ljust(width)
        print(f"    {label}   {_MARKERS[current]}   ({current})")
    save_state(state)

    if not FROZEN:
        print()
        print("  switch:  python src/lang.py russian   |   python src/lang.py original")
    print()


def cmd_switch(args) -> None:
    target = args.target
    if target not in ("russian", "original"):
        sys.exit(f"error: unknown target '{target}' "
                 f"(expected 'russian' or 'original')")

    state = load_state()
    pipes = all_pipelines()
    cached_all = state.get("pipelines", {})

    # Plan: which pipelines actually need to move?
    plan: list[tuple[str, Pipeline, str]] = []
    for name, pipe in pipes.items():
        current, _fp = classify(pipe, args.csp, cached_all.get(name))
        if current == target:
            print(f"  {_LABELS[name]}: already {target} -- skipping")
        else:
            plan.append((name, pipe, current))

    if not plan:
        print(f"\nAll subsystems already on '{target}'. Nothing to do.")
        return

    print(f"\nWill switch {len(plan)} subsystem(s) to '{target}':")
    for name, _pipe, current in plan:
        print(f"  - {_LABELS[name]}  ({current} -> {target})")

    if not args.dry_run:
        install.check_csp_closed(args.force)
        install.ensure_admin()  # one prompt; pipelines re-enter it as no-op

    for name, pipe, _current in plan:
        try:
            pipe.switch_to(target, args.csp, args.dry_run)
        except SystemExit as e:
            # Pipeline modules sys.exit on errors; surface that as our own exit.
            sys.exit(f"\nerror: subsystem '{_LABELS[name]}' failed: {e}")

    # Re-fingerprint everything afterwards so the cache reflects reality.
    if not args.dry_run:
        for name, pipe in pipes.items():
            current, fp = classify(pipe, args.csp, None)
            if fp is not None:
                set_pipeline_state(state, name, current, fp)
        save_state(state)

    print(f"\nDone -- switched to '{target}'. Restart CSP to see the change.")


# ----------------------------------------------------------------------
# Interactive menu (no-args / double-click launch)
# ----------------------------------------------------------------------
_BANNER = """
=============================================================
  Clip Studio Paint  --  Russian translation switcher
=============================================================
"""


def _maybe_initial_snapshot() -> None:
    """One-time snapshot of the user's CSP originals so 'restore' has
    something to copy back, and so status detection works against a real
    reference. Subsequent runs no-op -- each pipeline's `backup` command
    skips files whose backup already exists, and refuses to overwrite a
    saved original with a patched file."""
    needs_msg = True
    for label, module_loader, target_dir, has_files in [
        ("plug-ins", _plugins_module, lambda mod: mod.PLUGINS_DIR,
         lambda d: d.is_dir() and any(d.glob("*.dll"))),
        ("tool palette", _tools_module, lambda mod: mod.TOOLS_DIR,
         lambda d: d.is_dir() and any(p.is_file() for p in d.rglob("*"))),
        ("materials", _materials_module, lambda mod: mod.MATERIALS_DIR,
         lambda d: d.is_dir() and any(p.is_file() for p in d.rglob("*"))),
    ]:
        try:
            mod = module_loader()
        except SystemExit:
            continue
        if has_files(target_dir(mod)):
            continue
        if needs_msg:
            print("\n  First launch: snapshotting your current CSP files so we")
            print("  can restore them later. This may take a moment for the")
            print("  material catalog (a few thousand small files)...\n")
            needs_msg = False
        try:
            mod.cmd_backup(_pipe_args())
        except SystemExit as e:
            # Don't abort the whole menu over one pipeline failing to snapshot
            # (e.g. live install already patched -- backup detects this and exits).
            print(f"  (could not snapshot {label}: {e})")


def cmd_menu(args) -> None:
    _maybe_initial_snapshot()
    while True:
        print(_BANNER)

        state = load_state()
        pipes = all_pipelines()
        cached_all = state.get("pipelines", {})

        statuses: dict[str, str] = {}
        print("  Current state:")
        width = max(len(_LABELS[n]) for n in pipes)
        for name, pipe in pipes.items():
            current, fp = classify(pipe, args.csp, cached_all.get(name))
            if fp is not None:
                set_pipeline_state(state, name, current, fp)
            statuses[name] = current
            label = _LABELS[name].ljust(width)
            print(f"    {label}   {_MARKERS[current]}   ({current})")
        save_state(state)

        # Summary line
        unique = set(statuses.values())
        if unique == {"russian"}:
            summary = "Everything is in Russian."
        elif unique == {"original"}:
            summary = "Everything is in English (original)."
        else:
            summary = "Subsystems are in a mix of states."
        print(f"\n  {summary}")

        print()
        print("  [1] Switch to Russian")
        print("  [2] Restore the original (English)")
        print("  [0] Exit")
        print()

        try:
            choice = input("  Choose: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if choice == "0" or choice.lower() in ("q", "quit", "exit"):
            return
        if choice in ("1", "2"):
            target = "russian" if choice == "1" else "original"
            args.target = target
            # If cmd_switch needs to re-launch elevated, make the new admin
            # process resume on the chosen target instead of the menu.
            sys.argv = [sys.argv[0], target, "--keep-open"]
            try:
                cmd_switch(args)
            except SystemExit as e:
                print(f"\n{e}")
            _pause()
            # Restore for the next menu iteration.
            sys.argv = [sys.argv[0]]
            continue
        print(f"\n  unknown choice: {choice!r}")
        _pause()


def _pause() -> None:
    try:
        input("\n  press Enter to continue...")
    except EOFError:
        pass


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------
def main(argv: list[str] | None = None) -> None:
    raw = sys.argv[1:] if argv is None else argv
    no_args = len(raw) == 0

    parser = argparse.ArgumentParser(
        prog="lang.py" if not FROZEN else "csp-russian",
        description="Switch CSP between Russian and the original install, "
                    "across all four subsystems, in one command.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="examples:\n"
               "  csp-russian russian      install Russian everywhere\n"
               "  csp-russian original     restore the original install\n"
               "  csp-russian status       show what is installed\n"
               "  csp-russian              interactive menu",
    )
    parser.add_argument("target", nargs="?", default="menu",
                        metavar="TARGET",
                        help="'russian', 'original', 'status', or 'menu' "
                             "(default: menu)")
    parser.add_argument("--csp", metavar="DIR",
                        help="CSP 'resource' folder (auto-detected if omitted)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print what would happen, change nothing")
    parser.add_argument("--force", action="store_true",
                        help="proceed even if CSP appears to be running")
    parser.add_argument("--keep-open", action="store_true",
                        help=argparse.SUPPRESS)

    args = parser.parse_args(raw)

    # `lang.py` without args = menu (the documented double-click UX).
    # Explicit `lang.py status` = old non-interactive behaviour.
    if no_args:
        args.target = "menu"

    _configure_pipelines()

    try:
        if args.target == "menu":
            cmd_menu(args)
        elif args.target == "status":
            cmd_status(args)
        else:
            cmd_switch(args)
    finally:
        # Pause before closing the window when we're an elevated re-launch
        # (single-shot, no menu loop) so the user can read the output. The
        # menu loop pauses internally between actions, so no double-pause.
        if args.keep_open:
            try:
                input("\nPress Enter to close this window...")
            except EOFError:
                pass


if __name__ == "__main__":
    main()

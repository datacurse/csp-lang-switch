#!/usr/bin/env python3
"""
lang.py
=======
Top-level "change the language of my CSP install" switcher.

    python src/lang.py russian      <- show the Russian translation everywhere
    python src/lang.py original     <- restore whatever was there before we ran
    python src/lang.py status       <- per-pipeline current state

This is the user-facing entrypoint. It wraps the four per-subsystem pipelines:

    main UI       src/install.py          (resource bundles in C:\\Program Files)
    plug-ins      src/plugins.py          (filter DLLs in C:\\Program Files)
    tool palette  src/tools.py            (SQLite DBs in C:\\Program Files + %APPDATA%)
    materials     src/materials.py        (SQLite catalog in %APPDATA%)

Two states are exposed to the user:

  * `russian`   -- the patched build for every pipeline
  * `original`  -- whatever was on this machine before we ever ran. For the
                   main UI that is the stock English CSP ships in
                   `resource/english/`; for the other three it is the local
                   backup snapshot the pipelines maintain in `plugins/`,
                   `tools/`, and `materials/`.

The four backup snapshots are taken automatically the first time `lang.py
russian` runs, so the user never has to remember an ordering of `backup` then
`install`. If a snapshot already exists it is left untouched (the per-pipeline
`backup` commands refuse to overwrite an original with a patched file).

State tracking
--------------
A `.lang-state.json` at the repo root caches the last-known current state per
pipeline (`russian`, `original`, or `unknown`) alongside a content fingerprint
of the install. The fingerprint is verified before trusting the cache; if the
files on disk have drifted, the cache entry is treated as `unknown` and
recomputed.

The fingerprint is a sha256 over a sorted manifest of "<relpath>\\t<sha256>" for
every relevant file in the pipeline's install location. It is content-only and
ignores mtime / size metadata, so it survives backup-and-restore round trips.

Admin elevation
---------------
Three of the four pipelines write into `C:\\Program Files` and self-elevate via
UAC. To avoid four separate UAC prompts (and four elevated consoles), this
wrapper self-elevates once at the start of any state-changing command, then
spawns the per-pipeline scripts as subprocesses -- which inherit elevation.

No external dependencies (standard library only).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import install  # for ensure_admin, check_csp_closed, find_csp_resource, etc.


# Lazy loaders for the per-pipeline scripts. Lazy so an environment where one
# of them sys.exits at import-time (e.g. no %APPDATA% layout) doesn't break the
# wrapper itself.
def _tools_module():
    import tools
    return tools


def _materials_module():
    import materials
    return materials

# ----------------------------------------------------------------------
# Paths
# ----------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
STATE_FILE = ROOT / ".lang-state.json"

# Repo locations of patched builds + original snapshots.
RUSSIAN_BUILD     = ROOT / "russian"
RUSSIAN_PLUGINS   = ROOT / "russian-plugins"
RUSSIAN_TOOLS     = ROOT / "russian-tools"
RUSSIAN_MATERIALS = ROOT / "russian-materials"

PLUGINS_BACKUP    = ROOT / "plugins"
TOOLS_BACKUP      = ROOT / "tools"
MATERIALS_BACKUP  = ROOT / "materials"

ENGLISH_STOCK     = ROOT / "resource" / "english"

PIPELINES = ("main-ui", "plugins", "tools", "materials")


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
# Per-pipeline locators (read-only — used by status + fingerprinting)
#
# We deliberately reuse the per-pipeline scripts' own path resolvers, so the
# wrapper can't drift from what they actually read and write.
# ----------------------------------------------------------------------
def main_ui_install_dir(csp: str | None, slot: str) -> Path:
    """The CSP slot we overwrite for the main UI (e.g. resource/english)."""
    return install.find_csp_resource(csp) / slot


def main_ui_resource_files(folder: Path) -> list[Path]:
    """GUID-named resource files in `folder` -- the only files install.py
    copies. Stray Thumbs.db etc. are ignored so they cannot poison hashing."""
    return install.resource_files(folder)


def plugin_install_dir(csp: str | None) -> Path:
    res = install.find_csp_resource(csp)
    # res = <csp>/resource ; plug-ins live at <csp>/PlugIn/PAINT
    return res.parent / "PlugIn" / "PAINT"


def tool_install_files(csp: str | None) -> list[Path]:
    """Every name-bearing tool DB that tools.py would patch, across both the
    install seed and the per-user working copy. Returns [] if either root is
    missing -- status should keep working on a partial setup."""
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
    """The catalog DB + every per-pack catalog.xml / catalogMaterial.cac that
    materials.py would patch. Returns [] if the user data tree is missing."""
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
# Pipeline definitions
# ----------------------------------------------------------------------
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

    def __init__(self, name: str, script: str):
        self.name = name
        self.script = SRC / script

    def install_fingerprint(self, csp: str | None) -> str | None:
        raise NotImplementedError

    def is_state(self, csp: str | None, state: str) -> bool | None:
        raise NotImplementedError

    def switch_to(self, target: str, csp: str | None, dry_run: bool) -> None:
        raise NotImplementedError


class MainUIPipeline(Pipeline):
    """Main UI bundles. `resource/english/` (stock) is `original`;
    `russian/` (the patched build, a 32-file subset of the 39 stock files) is
    `russian`. We compare only the GUID-named files install.py copies --
    Thumbs.db etc. would otherwise poison hashing -- and only on the
    intersection with the reference, since the russian build is a strict
    subset of the english stock."""

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
        _run_pipeline(self.script, target_lang, csp=csp, dry_run=dry_run)


class PluginsPipeline(Pipeline):
    """Filter-menu plug-in DLLs. The backup in `plugins/` is `original`;
    the patched build in `russian-plugins/` is `russian`."""

    def install_fingerprint(self, csp):
        return fingerprint_dir(plugin_install_dir(csp), ("*.dll",))

    def is_state(self, csp, state):
        slot = plugin_install_dir(csp)
        ref = RUSSIAN_PLUGINS if state == "russian" else PLUGINS_BACKUP
        ref_names = {p.name for p in ref.glob("*.dll")} if ref.is_dir() else set()
        return _files_equal(slot, ref, ref_names)

    def switch_to(self, target, csp, dry_run):
        if target == "russian":
            _ensure_backup(self.script, PLUGINS_BACKUP, "*.dll",
                           label="plug-in", dry_run=dry_run)
            _run_pipeline(self.script, "install", csp=csp, dry_run=dry_run)
        else:
            _run_pipeline(self.script, "restore", csp=csp, dry_run=dry_run)


class ToolsPipeline(Pipeline):
    """Tool-palette SQLite DBs across two roots (install seed + per-user data).
    tools.py preserves each file's relpath under the backup tag (`install/`
    vs `userdata/`), so the backup root mirrors the live tree.

    State detection only compares the *install seed* (tag `install`). The
    per-user `userdata` working copy is mutated by CSP at runtime, so it
    diverges from any reference within minutes of running CSP -- byte-
    equality there is unreliable. Patching still covers both roots."""

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
        if target == "russian":
            _ensure_backup(self.script, TOOLS_BACKUP, "*.sqlite",
                           label="tool DB", dry_run=dry_run, recursive=True)
            _run_pipeline(self.script, "install", csp=csp, dry_run=dry_run)
        else:
            _run_pipeline(self.script, "restore", csp=csp, dry_run=dry_run)


class MaterialsPipeline(Pipeline):
    """Material catalog: a single .cmdb plus per-pack catalog.xml / .cac files.
    materials.py mirrors the live tree under `materials/`.

    State detection only compares the per-pack files (`catalog.xml`,
    `catalogMaterial.cac`) -- they are static after install. The top-level
    CatalogMaterial.cmdb is mutated by CSP at runtime (favourites, recent,
    user-added materials) and would make byte-equality fail. Patching still
    covers the .cmdb too."""

    def install_fingerprint(self, csp):
        return fingerprint_files(material_install_files())

    def is_state(self, csp, state):
        try:
            m = _materials_module()
            ref_root = RUSSIAN_MATERIALS if state == "russian" else MATERIALS_BACKUP
            if not ref_root.is_dir():
                return None
            # materials.py stores pack files at <root>/<CATALOG>/<pack-relpath>/<file>,
            # where pack-relpath is relative to common_dir()/Material/.
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
        if target == "russian":
            _ensure_backup(self.script, MATERIALS_BACKUP, "*",
                           label="material DB", dry_run=dry_run, recursive=True)
            _run_pipeline(self.script, "install", csp=csp, dry_run=dry_run)
        else:
            _run_pipeline(self.script, "restore", csp=csp, dry_run=dry_run)


def all_pipelines() -> dict[str, Pipeline]:
    return {
        "main-ui":   MainUIPipeline("main-ui", "install.py"),
        "plugins":   PluginsPipeline("plugins", "plugins.py"),
        "tools":     ToolsPipeline("tools", "tools.py"),
        "materials": MaterialsPipeline("materials", "materials.py"),
    }


# ----------------------------------------------------------------------
# Subprocess plumbing
# ----------------------------------------------------------------------
def _run_pipeline(script: Path, *cmd_args: str, csp: str | None,
                  dry_run: bool) -> None:
    """Invoke `python <script> <cmd_args> --yes [--csp DIR] [--dry-run]`,
    inheriting our stdio so the user sees the pipeline's normal output.

    --yes is passed because the wrapper already confirmed at its own level.
    Children inherit our elevation, so no extra UAC prompts."""
    cmd: list[str] = [sys.executable, str(script), *cmd_args, "--yes"]
    # plugins.py / tools.py / install.py accept --csp; materials.py does not.
    # Pass --csp only to scripts that accept it.
    if csp and script.name in ("install.py", "plugins.py", "tools.py"):
        cmd += ["--csp", csp]
    if dry_run:
        cmd += ["--dry-run"]
    print(f"\n>>> {script.name} {' '.join(cmd_args)}")
    subprocess.run(cmd, check=True)


def _ensure_backup(script: Path, backup_dir: Path, glob: str, *,
                   label: str, dry_run: bool,
                   recursive: bool = False) -> None:
    """If `backup_dir` has no matching files yet, run the script's `backup`
    command to populate it. Idempotent: a second call is a no-op."""
    if backup_dir.is_dir():
        it = backup_dir.rglob(glob) if recursive else backup_dir.glob(glob)
        if any(p.is_file() for p in it):
            return
    print(f"\n(no {label} backup found at {backup_dir} -- snapshotting first)")
    _run_pipeline(script, "backup", csp=None, dry_run=dry_run)


# ----------------------------------------------------------------------
# State classification
# ----------------------------------------------------------------------
def classify(pipe: Pipeline, csp: str | None,
             cached: dict | None) -> tuple[str, str | None]:
    """Return (current_state, fingerprint).

    `current_state` ∈ {`russian`, `original`, `unknown`}. The cache is used as
    a fast path: if the on-disk fingerprint matches what the cache last saw,
    we trust its label. Otherwise we recompute by asking the pipeline whether
    the install matches its `russian` or `original` reference."""
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
def cmd_status(args) -> None:
    state = load_state()
    pipes = all_pipelines()
    cached_all = state.get("pipelines", {})

    print()
    width = max(len(n) for n in pipes)
    for name, pipe in pipes.items():
        current, fp = classify(pipe, args.csp, cached_all.get(name))
        # Refresh the cache so the user sees a consistent picture next run.
        if fp is not None:
            set_pipeline_state(state, name, current, fp)
        marker = {"russian": "RU", "original": "ORIG", "unknown": "??"}[current]
        print(f"  {name.ljust(width)}   {marker:<5}   ({current})")
    save_state(state)

    print()
    print("  switch:  python src/lang.py russian   |   python src/lang.py original")
    print()


def cmd_switch(args) -> None:
    target = args.target
    if target not in ("russian", "original"):
        sys.exit(f"error: unknown target '{target}' (expected 'russian' or 'original')")

    state = load_state()
    pipes = all_pipelines()
    cached_all = state.get("pipelines", {})

    # Plan: which pipelines actually need to move?
    plan: list[tuple[str, Pipeline, str]] = []
    for name, pipe in pipes.items():
        current, _fp = classify(pipe, args.csp, cached_all.get(name))
        if current == target:
            print(f"  {name}: already {target} -- skipping")
        else:
            plan.append((name, pipe, current))

    if not plan:
        print(f"\nall pipelines already on '{target}'. Nothing to do.")
        return

    print(f"\nwill switch {len(plan)} pipeline(s) to '{target}':")
    for name, _pipe, current in plan:
        print(f"  - {name}  ({current} -> {target})")

    if not args.dry_run:
        install.check_csp_closed(args.force)
        install.ensure_admin()  # one prompt, children inherit elevation

    for name, pipe, _current in plan:
        try:
            pipe.switch_to(target, args.csp, args.dry_run)
        except subprocess.CalledProcessError as e:
            sys.exit(f"\nerror: pipeline '{name}' failed (exit {e.returncode})")

    # Re-fingerprint everything afterwards so the cache reflects reality.
    if not args.dry_run:
        for name, pipe in pipes.items():
            current, fp = classify(pipe, args.csp, None)
            if fp is not None:
                set_pipeline_state(state, name, current, fp)
        save_state(state)

    print(f"\ndone -- switched to '{target}'. Restart CSP to see the change.")


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------
def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="lang.py",
        description="Switch CSP between Russian and the original install, "
                    "across all four pipelines, in one command.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="examples:\n"
               "  python src/lang.py russian      install Russian everywhere\n"
               "  python src/lang.py original     restore the original install\n"
               "  python src/lang.py status       show what is installed",
    )
    parser.add_argument("target", nargs="?", default="status",
                        metavar="TARGET",
                        help="'russian', 'original', or 'status' "
                             "(default: status)")
    parser.add_argument("--csp", metavar="DIR",
                        help="CSP 'resource' folder (auto-detected if omitted)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print what would happen, change nothing")
    parser.add_argument("--force", action="store_true",
                        help="proceed even if CSP appears to be running")
    parser.add_argument("--keep-open", action="store_true",
                        help=argparse.SUPPRESS)

    args = parser.parse_args(argv)
    try:
        if args.target == "status":
            cmd_status(args)
        else:
            cmd_switch(args)
    finally:
        if args.keep_open:
            try:
                input("\npress Enter to close this window...")
            except EOFError:
                pass


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
lang.py
=======
Top-level language-pack switcher for a Clip Studio Paint install.

Community translations (Russian today; Ukrainian, Kazakh, etc. later) are
installed into CSP's English slot and into the global plug-in location.
Official CSP languages are not patched; selecting one restores the
community changes and tells the user which CSP language to choose manually.

Examples:
    python src/lang.py russian      install the Russian community pack
    python src/lang.py english      install stock English into the English slot
    python src/lang.py status       show per-pipeline state
    python src/lang.py              open the simple picker
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import install  # for ensure_admin, check_csp_closed, find_csp_resource, etc.
from common import (
    csp_is_running,
    detect_installed_csp_version as _detect_installed_csp_version,
    find_csp_resource_optional,
    is_admin,
    pause_console,
    quiet_stdout,
    read_exe_product_version,
    run_elevated_sync,
    attach_console,
    csp_exe_from_resource,
    set_celsys_base,
)
from version import (
    DEFAULT_VERSION,
    SUPPORTED_VERSIONS,
    GUARD_GUID,
    GUARD_SLOT,
    fingerprint_guard_file,
    guard_profile,
    install_matches_version,
    set_active_version as _set_version_langs_root,
)

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


# ----------------------------------------------------------------------
# Paths -- source mode vs bundled exe
# ----------------------------------------------------------------------
FROZEN = getattr(sys, "frozen", False)
APP_NAME = "csp-lang-switch"
LEGACY_APP_NAMES = ("csp-lang", "csp-russian")
COMMUNITY_SLOT = "english"


def _local_appdata() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local"))


def _legacy_user_data_roots() -> list[Path]:
    return [_local_appdata() / name for name in LEGACY_APP_NAMES]


def _migrate_file_if_missing(dst: Path, *candidates: Path) -> None:
    """Copy the first existing legacy file into *dst* when the new path is empty."""
    if dst.is_file():
        return
    for src in candidates:
        if src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            return


if FROZEN:
    DATA_ROOT = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    USER_DATA = _local_appdata() / APP_NAME
    USER_DATA.mkdir(parents=True, exist_ok=True)
    STATE_FILE = USER_DATA / "state.json"
    SETTINGS_FILE = USER_DATA / "settings.json"
    for legacy_root in _legacy_user_data_roots():
        _migrate_file_if_missing(STATE_FILE, legacy_root / "state.json")
        _migrate_file_if_missing(SETTINGS_FILE, legacy_root / "settings.json")
else:
    DATA_ROOT = Path(__file__).resolve().parent.parent
    USER_DATA = DATA_ROOT
    STATE_FILE = DATA_ROOT / ".lang-state.json"
    SETTINGS_FILE = DATA_ROOT / ".csp-lang-switch-settings.json"
    _migrate_file_if_missing(
        SETTINGS_FILE, DATA_ROOT / ".csp-lang-settings.json")

    _migrate_file_if_missing(
        SETTINGS_FILE, DATA_ROOT / ".csp-lang-settings.json")

_selected_version: str = DEFAULT_VERSION
_pipelines_configured = False


def _frozen_langs_dir(version: str) -> Path:
    """Bundled language trees: langs/<version>/ with legacy flat fallback."""
    nested = DATA_ROOT / "langs" / version
    if nested.is_dir() and (nested / "english").is_dir():
        return nested
    if version == DEFAULT_VERSION:
        legacy = DATA_ROOT / "langs"
        if legacy.is_dir() and (legacy / "english").is_dir():
            return legacy
    return nested


def set_active_version(version: str) -> str:
    """Select the bundled CSP version and refresh pipeline paths."""
    global LANGS_DIR, ENGLISH_STOCK, BUNDLED_ENGLISH, PLUGINS_BACKUP
    global _selected_version, _pipelines_configured
    if version not in SUPPORTED_VERSIONS:
        raise ValueError(f"unsupported CSP version: {version}")
    _set_version_langs_root(version)
    _selected_version = version
    if FROZEN:
        LANGS_DIR = _frozen_langs_dir(version)
    else:
        import version as ver
        LANGS_DIR = ver.langs_root(version)
    ENGLISH_STOCK = LANGS_DIR / "english" / "ui"
    BUNDLED_ENGLISH = LANGS_DIR / "english"
    if not FROZEN:
        PLUGINS_BACKUP = LANGS_DIR / "english" / "plugins"
    _pipelines_configured = False
    _configure_pipelines()
    return version


if FROZEN:
    LANGS_DIR = _frozen_langs_dir(DEFAULT_VERSION)
else:
    import version as ver
    LANGS_DIR = ver.langs_root(DEFAULT_VERSION)
ENGLISH_STOCK = LANGS_DIR / "english" / "ui"
BUNDLED_ENGLISH = LANGS_DIR / "english"

# In bundled mode, prefer the new data folder but keep older backup locations
# usable so existing users are not stranded after product renames.
def _backup_dir(name: str) -> Path:
    current = USER_DATA / name
    if FROZEN and not any(current.rglob("*")):
        for legacy_root in _legacy_user_data_roots():
            legacy = legacy_root / name
            if any(legacy.rglob("*")):
                return legacy
    return current


PLUGINS_BACKUP = _backup_dir("plugins")

if not FROZEN:
    # In source mode, stock snapshots live under the active version tree.
    PLUGINS_BACKUP = LANGS_DIR / "english" / "plugins"


def detect_installed_csp_version(csp: str | None = None) -> str | None:
    """Return a supported version id for the installed CSP, or None."""
    ver, _resource = _detect_installed_csp_version(csp, SUPPORTED_VERSIONS)
    return ver


def detected_csp_product_version(csp: str | None = None) -> str | None:
    """Return the raw ProductVersion from CLIPStudioPaint.exe."""
    resource = find_csp_resource_optional(csp)
    if resource is None:
        return None
    return read_exe_product_version(csp_exe_from_resource(resource))


def resolve_csp_version(
    explicit: str | None,
    detected: str | None,
    saved: str | None,
) -> str:
    """Pick the CSP version to use: explicit flag, detected install, then saved."""
    if explicit and explicit in SUPPORTED_VERSIONS:
        return explicit
    if detected and detected in SUPPORTED_VERSIONS:
        return detected
    if saved and saved in SUPPORTED_VERSIONS:
        return saved
    return DEFAULT_VERSION

PIPELINES = ("main-ui", "plugins")
ORIGINAL = "original"
UNKNOWN = "unknown"
WARNINGS: list[str] = []


# ----------------------------------------------------------------------
# Language metadata / discovery
# ----------------------------------------------------------------------
OFFICIAL_LABELS = {
    "japanese": "Japanese",
    "english": "English",
    "korean": "Korean",
    "chinese_t": "Traditional Chinese",
    "chinese_tc": "Traditional Chinese",
    "french": "French",
    "spanish": "Spanish",
    "german": "German",
    "thai": "Thai",
    "indonesian": "Indonesian",
    "portuguese_b": "Portuguese (Brazil)",
    "portuguese": "Portuguese (Brazil)",
    "chinese_s": "Simplified Chinese",
    "chinese_sc": "Simplified Chinese",
}

OFFICIAL_AUTONYMS = {
    "japanese": "日本語",
    "english": "English",
    "korean": "한국어",
    "chinese_t": "繁體中文",
    "chinese_tc": "繁體中文",
    "french": "Français",
    "spanish": "Español",
    "german": "Deutsch",
    "thai": "ภาษาไทย",
    "indonesian": "Bahasa Indonesia",
    "portuguese_b": "Português (Brasil)",
    "portuguese": "Português (Brasil)",
    "chinese_s": "简体中文",
    "chinese_sc": "简体中文",
}

COMMUNITY_LABELS = {
    "russian": "Russian",
    "ukrainian": "Ukrainian",
    "kazakh": "Kazakh",
}

COMMUNITY_AUTONYMS = {
    "russian": "Русский",
    "ukrainian": "Українська",
    "kazakh": "Қазақша",
}


@dataclass(frozen=True)
class LanguageChoice:
    id: str
    label: str
    autonym: str
    kind: str  # community | official

    @property
    def display(self) -> str:
        return f"{self.autonym} ({self.label})" if self.autonym != self.label else self.label


def choice_display(choice: LanguageChoice, gui_lang: str | None = None) -> str:
    """Language label for the GUI, using localized names when requested."""
    if not gui_lang or gui_lang == "en":
        return choice.display
    import gui_i18n as i18n
    loc = i18n.language_label(gui_lang, choice.id)
    if not loc:
        return choice.display
    if choice.autonym.casefold() == loc.casefold():
        return choice.autonym
    return loc


def _has_files(folder: Path) -> bool:
    return folder.is_dir() and any(p.is_file() for p in folder.rglob("*"))


def community_pack_root(pack: str) -> Path:
    return LANGS_DIR / pack


def community_subdir(pack: str, subdir: str) -> Path:
    return community_pack_root(pack) / subdir


def discover_community_packs() -> dict[str, LanguageChoice]:
    """Community packs present under langs/<id>/.

    Official CSP language snapshots such as langs/japanese/ui are excluded;
    those are developer references, not community packs.
    """
    out: dict[str, LanguageChoice] = {}
    if not LANGS_DIR.is_dir():
        return out
    official_ids = set(OFFICIAL_LABELS) | {"other"}
    for d in sorted(LANGS_DIR.iterdir()):
        if not d.is_dir() or d.name in official_ids:
            continue
        if not any(_has_files(d / sub) for sub in PIPELINES_SUBDIRS.values()):
            continue
        label = COMMUNITY_LABELS.get(d.name, d.name.replace("_", " ").title())
        autonym = COMMUNITY_AUTONYMS.get(d.name, label)
        out[d.name] = LanguageChoice(d.name, label, autonym, "community")
    return out


def discover_official_languages(csp: str | None) -> dict[str, LanguageChoice]:
    """Official language folders present in the live CSP resource directory."""
    try:
        resource = install.find_csp_resource(csp)
    except SystemExit:
        return {}
    out: dict[str, LanguageChoice] = {}
    for d in sorted(resource.iterdir()) if resource.is_dir() else []:
        if d.name == "other" or not d.is_dir() or not install.resource_files(d):
            continue
        label = OFFICIAL_LABELS.get(d.name, d.name.replace("_", " ").title())
        autonym = OFFICIAL_AUTONYMS.get(d.name, label)
        out[d.name] = LanguageChoice(d.name, label, autonym, "official")
    return out


PIPELINES_SUBDIRS = {
    "main-ui": "ui",
    "plugins": "plugins",
}


def known_state_values() -> set[str]:
    return {ORIGINAL, *discover_community_packs().keys()}


def official_state(language: str) -> str:
    return f"official:{language}"


def is_official_state(state: str) -> bool:
    return state.startswith("official:")


def official_id_from_state(state: str) -> str:
    return state.split(":", 1)[1]


def state_label(state: str) -> str:
    if state == ORIGINAL:
        return "original"
    if state == UNKNOWN:
        return UNKNOWN
    if is_official_state(state):
        lang = official_id_from_state(state)
        label = OFFICIAL_LABELS.get(lang, lang.replace("_", " ").title())
        return f"official:{label}"
    return state


def pipeline_display_state(state: str, gui_lang: str | None = None) -> str:
    """Human-readable pipeline state for the GUI."""
    import gui_i18n as i18n

    if state == ORIGINAL:
        if gui_lang and gui_lang != "en":
            return i18n.t(gui_lang, "state_stock")
        return "English (stock)"
    if state == UNKNOWN:
        if gui_lang and gui_lang != "en":
            return i18n.t(gui_lang, "state_unknown")
        return "Unknown"
    if is_official_state(state):
        lang = official_id_from_state(state)
        if gui_lang and gui_lang != "en":
            import gui_i18n as i18n
            label = (i18n.language_label(gui_lang, lang)
                     or OFFICIAL_LABELS.get(lang, lang.replace("_", " ").title()))
            return i18n.t(gui_lang, "state_official", label=label)
        label = OFFICIAL_LABELS.get(lang, lang.replace("_", " ").title())
        return f"{label} (official)"
    choice = discover_community_packs().get(state)
    if choice:
        return choice_display(choice, gui_lang)
    return state.replace("_", " ").title()


def state_marker(state: str) -> str:
    if state == ORIGINAL:
        return "EN"
    if state == UNKNOWN:
        return "??"
    if is_official_state(state):
        return "OF"
    return state[:2].upper()


def choice_by_target(target: str, csp: str | None) -> LanguageChoice | None:
    communities = discover_community_packs()
    officials = discover_official_languages(csp)
    low = target.lower()
    aliases = {"original": "english", "restore": "english"}
    low = aliases.get(low, low)
    if low in communities:
        return communities[low]
    if low in officials:
        return officials[low]
    return None


# ----------------------------------------------------------------------
# Lazy module loaders
# ----------------------------------------------------------------------
def _plugins_module():
    import plugins
    return plugins


# ----------------------------------------------------------------------
# Pipeline path overrides
# ----------------------------------------------------------------------


def _configure_pipelines() -> None:
    """Point helper modules at the data root and writable backups."""
    global _pipelines_configured
    install.ROOT = DATA_ROOT
    install.LANGS_DIR = LANGS_DIR
    if FROZEN:
        p = _plugins_module()
        p.PLUGINS_DIR = PLUGINS_BACKUP
        p.BUILD_DIR = LANGS_DIR / "russian" / "plugins"
        if not _pipelines_configured:
            _seed_bundled_backups()
    _pipelines_configured = True


def _install_matches_version(csp: str | None, version: str | None = None) -> bool:
    ver = version or _selected_version
    resource = install.find_csp_resource(csp)
    guard_path = resource / GUARD_SLOT / GUARD_GUID
    return install_matches_version(guard_path, ver)


def _require_matching_csp_version(csp: str | None, choice: LanguageChoice) -> None:
    if choice.kind != "community":
        return
    if _install_matches_version(csp):
        return
    sys.exit(
        f"error: this build targets Clip Studio Paint {_selected_version}, but the "
        f"installed CSP resource files do not match.\n"
        f"       Update CSP to {_selected_version} or pick the matching version "
        f"in the switcher."
    )


def _repack_stale_community_translations() -> None:
    """When running from source, rebuild langs/ files whose worksheets changed."""
    if FROZEN:
        return
    import batch

    batch.configure_version(_selected_version)
    manifest = batch.load_manifest()
    stale: list[str] = []
    for rec in manifest:
        if rec.get("target") != "yes":
            continue
        if not batch.resource_for(rec).is_file():
            # e.g. companion-mode (6FFACA71) — not shipped in CSP 4.0.0 stock
            continue
        ws = batch.worksheet_for(rec)
        uniq = batch.unique_for(rec)
        out = batch.output_for(rec, "russian")
        if not ws.is_file():
            continue
        sources = [ws]
        if uniq.is_file():
            sources.append(uniq)
        newest = max(p.stat().st_mtime for p in sources)
        if not out.is_file() or newest > out.stat().st_mtime:
            stale.append(rec["short"])
    if not stale:
        return
    print(f"\nRepacking {len(stale)} stale translation file(s) before install...")
    for short in stale:
        rec = batch.resolve(manifest, short)
        print(f"  pack {rec['short']}-{rec['slug']}")
        if not batch._pack_one(rec, "russian"):
            sys.exit(f"error: repack failed for {rec['short']}-{rec['slug']}")


def _seed_bundled_backups() -> None:
    """Copy bundled English stock into LOCALAPPDATA when backup dirs are empty."""
    if not FROZEN or not BUNDLED_ENGLISH.is_dir():
        return
    jobs = (
        ("plugins", PLUGINS_BACKUP, ("*.dll",)),
    )
    for sub, dst, _patterns in jobs:
        src = BUNDLED_ENGLISH / sub
        if not src.is_dir() or not any(src.rglob("*")):
            continue
        if dst.is_dir() and any(dst.rglob("*")):
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst, dirs_exist_ok=True)
        print(f"Seeded {sub} backup from bundled English stock -> {dst}")


def _set_build_dir(pipeline: str, pack: str) -> None:
    """Set a pipeline module's build directory for the selected community pack."""
    root = community_subdir(pack, PIPELINES_SUBDIRS[pipeline])
    modules = {
        "plugins": _plugins_module,
    }
    loader = modules.get(pipeline)
    if loader is None:
        return
    loader().BUILD_DIR = root


def add_warning(message: str) -> None:
    WARNINGS.append(message)
    print(message)


def clear_warnings() -> None:
    WARNINGS.clear()


# ----------------------------------------------------------------------
# State file
# ----------------------------------------------------------------------
def load_state() -> dict:
    if not STATE_FILE.is_file():
        return {"version": 2, "pipelines": {}}
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 2, "pipelines": {}}
    if not isinstance(data, dict) or "pipelines" not in data:
        return {"version": 2, "pipelines": {}}
    data["version"] = 2
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
    if not folder.is_dir():
        return None
    files: set[Path] = set()
    for pat in patterns:
        it = folder.rglob(pat) if recursive else folder.glob(pat)
        files.update(p for p in it if p.is_file())
    if not files:
        return None
    h = hashlib.sha256()
    for p in sorted(files):
        rel = p.relative_to(folder).as_posix()
        h.update(f"{rel}\t{_hash_file(p)}\n".encode("utf-8"))
    return h.hexdigest()


def fingerprint_files(files: list[Path]) -> str | None:
    real = [p for p in files if p.is_file()]
    if not real:
        return None
    h = hashlib.sha256()
    for p in sorted(real):
        h.update(f"{p.name}\t{_hash_file(p)}\n".encode("utf-8"))
    return h.hexdigest()


# ----------------------------------------------------------------------
# Per-pipeline locators
# ----------------------------------------------------------------------
def main_ui_install_dir(csp: str | None, slot: str) -> Path:
    return install.find_csp_resource(csp) / slot


def main_ui_resource_files(folder: Path) -> list[Path]:
    return install.resource_files(folder)


def plugin_install_dir(csp: str | None) -> Path:
    res = install.find_csp_resource(csp)
    return res.parent / "PlugIn" / "PAINT"


# ----------------------------------------------------------------------
# Pipeline plumbing
# ----------------------------------------------------------------------
def _pipe_args(**kwargs) -> argparse.Namespace:
    defaults = dict(
        csp=None, dry_run=False, yes=True, force=False, keep_open=False,
        only_files=None, partial_merges=None,
    )
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def _files_equal(slot_dir: Path, ref_dir: Path,
                 names: set[str]) -> bool | None:
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
    """One swappable subsystem."""

    subdir = ""

    def __init__(self, name: str):
        self.name = name

    def community_ref(self, pack: str) -> Path:
        return community_subdir(pack, self.subdir)

    def has_community_ref(self, pack: str) -> bool:
        return _has_files(self.community_ref(pack))

    def desired_state(self, choice: LanguageChoice) -> str:
        if choice.kind == "community" and self.has_community_ref(choice.id):
            return choice.id
        return ORIGINAL

    def install_fingerprint(self, csp: str | None) -> str | None:
        raise NotImplementedError

    def is_state(self, csp: str | None, state: str) -> bool | None:
        raise NotImplementedError

    def switch_to(self, choice: LanguageChoice, csp: str | None,
                  dry_run: bool) -> None:
        raise NotImplementedError


def _sync_community_tool_dbs(
    csp: str | None, choice: LanguageChoice, *, dry_run: bool
) -> None:
    if choice.kind != "community":
        return
    import tool_db
    if not dry_run and not is_admin():
        install.ensure_admin()
    resource = install.find_csp_resource(csp)
    tool_db.sync_tool_dbs(resource, language=choice.id, dry_run=dry_run)


class MainUIPipeline(Pipeline):
    subdir = "ui"

    def desired_state(self, choice: LanguageChoice) -> str:
        if choice.kind == "community" and self.has_community_ref(choice.id):
            return choice.id
        if choice.kind == "official" and choice.id != COMMUNITY_SLOT:
            return official_state(choice.id)
        return ORIGINAL

    def install_fingerprint(self, csp):
        return fingerprint_files(
            main_ui_resource_files(main_ui_install_dir(csp, COMMUNITY_SLOT)))

    def is_state(self, csp, state):
        slot = main_ui_install_dir(csp, COMMUNITY_SLOT)
        if state == ORIGINAL:
            ref = ENGLISH_STOCK
        elif is_official_state(state):
            ref = install.find_csp_resource(csp) / official_id_from_state(state)
        else:
            ref = self.community_ref(state)
        ref_names = {p.name for p in main_ui_resource_files(ref)}
        return _files_equal(slot, ref, ref_names)

    def switch_to(
        self,
        choice,
        csp,
        dry_run,
        *,
        only_files: set[str] | None = None,
        partial_merges: dict | None = None,
    ):
        if choice.kind == "community" and self.has_community_ref(choice.id):
            install.cmd_install(_pipe_args(
                target=choice.id, slot=COMMUNITY_SLOT, csp=csp,
                dry_run=dry_run, only_files=only_files,
                partial_merges=partial_merges))
            if not dry_run:
                import tool_db
                tool_db.sync_tool_dbs(
                    install.find_csp_resource(csp), language=choice.id)
            return
        if choice.kind == "official" and choice.id != COMMUNITY_SLOT:
            self._copy_official_to_slot(choice, csp, dry_run, only_files=only_files)
            return
        install.cmd_install(_pipe_args(
            target="english", slot=COMMUNITY_SLOT, csp=csp, dry_run=dry_run,
            only_files=only_files, partial_merges=partial_merges))
        if not dry_run:
            import tool_db
            tool_db.sync_tool_dbs(
                install.find_csp_resource(csp), language="english")

    def _copy_official_to_slot(self, choice, csp, dry_run, *, only_files=None):
        resource_dir = install.find_csp_resource(csp)
        src = resource_dir / choice.id
        slot = resource_dir / COMMUNITY_SLOT
        src_files = install.resource_files(src)
        if only_files:
            src_files = [f for f in src_files if f.name in only_files]
        if not src_files:
            sys.exit("error: no UI resource files selected for install")
        print(f"will install {choice.display} ({len(src_files)} files) "
              f"onto the {COMMUNITY_SLOT} slot")
        print(f"  {src}  ->  {slot}")
        install.copy_over(src_files, slot, dry_run=dry_run)
        if dry_run:
            print("[dry-run] nothing was changed")
        else:
            print(f"\ndone -- {choice.display} installed onto the "
                  f"{COMMUNITY_SLOT} slot.")


class PluginsPipeline(Pipeline):
    subdir = "plugins"

    def install_fingerprint(self, csp):
        return fingerprint_dir(plugin_install_dir(csp), ("*.dll",))

    def is_state(self, csp, state):
        slot = plugin_install_dir(csp)
        ref = PLUGINS_BACKUP if state == ORIGINAL else self.community_ref(state)
        ref_names = {p.name for p in ref.glob("*.dll")} if ref.is_dir() else set()
        return _files_equal(slot, ref, ref_names)

    def switch_to(self, choice, csp, dry_run):
        p = _plugins_module()
        if choice.kind == "community" and self.has_community_ref(choice.id):
            self._ensure_backup(dry_run)
            _set_build_dir(self.name, choice.id)
            p.cmd_install(_pipe_args(csp=csp, dry_run=dry_run))
        else:
            self._restore_if_possible(p, csp, dry_run)

    def _ensure_backup(self, dry_run):
        p = _plugins_module()
        if p.PLUGINS_DIR.is_dir() and any(p.PLUGINS_DIR.glob("*.dll")):
            return
        if dry_run:
            print(f"\n[dry-run] would snapshot plug-ins to {p.PLUGINS_DIR}")
            return
        print(f"\n(no plug-in backup at {p.PLUGINS_DIR} -- snapshotting first)")
        p.cmd_backup(_pipe_args(dry_run=dry_run))

    def _restore_if_possible(self, p, csp, dry_run):
        if not (p.PLUGINS_DIR.is_dir() and any(p.PLUGINS_DIR.glob("*.dll"))):
            add_warning("\nWARNING: no plug-in backup found; plug-ins were not restored.")
            return
        p.cmd_restore(_pipe_args(csp=csp, dry_run=dry_run))


def all_pipelines() -> dict[str, Pipeline]:
    return {
        "main-ui": MainUIPipeline("main-ui"),
        "plugins": PluginsPipeline("plugins"),
    }


# ----------------------------------------------------------------------
# State classification
# ----------------------------------------------------------------------
def classify(pipe: Pipeline, csp: str | None,
             cached: dict | None) -> tuple[str, str | None]:
    fp = pipe.install_fingerprint(csp)
    if cached and cached.get("fingerprint") == fp:
        cur = cached.get("current", "")
        if cur in known_state_values() or is_official_state(cur):
            if pipe.is_state(csp, cur) is True:
                return cur, fp
    for pack in discover_community_packs():
        if pipe.is_state(csp, pack) is True:
            return pack, fp
    if isinstance(pipe, MainUIPipeline):
        for lang in discover_official_languages(csp):
            if lang == COMMUNITY_SLOT:
                continue
            state = official_state(lang)
            if pipe.is_state(csp, state) is True:
                return state, fp
    if pipe.is_state(csp, ORIGINAL) is True:
        return ORIGINAL, fp
    return UNKNOWN, fp


def classify_all(args) -> dict[str, str]:
    state = load_state()
    pipes = all_pipelines()
    cached_all = state.get("pipelines", {})
    statuses: dict[str, str] = {}
    for name, pipe in pipes.items():
        current, fp = classify(pipe, args.csp, cached_all.get(name))
        statuses[name] = current
        if fp is not None:
            set_pipeline_state(state, name, current, fp)
    save_state(state)
    return statuses


def summary_for(statuses: dict[str, str]) -> str:
    unique = set(statuses.values())
    if len(unique) == 1:
        only = next(iter(unique))
        if only == ORIGINAL:
            return "English stock files are installed in the CSP English slot."
        if only == UNKNOWN:
            return "Current install does not match a known pack."
        if is_official_state(only):
            lang = official_id_from_state(only)
            label = discover_official_languages(None).get(lang)
            display = label.display if label else state_label(only)
            return f"Official UI active through the English slot: {display}."
        choice = discover_community_packs().get(only)
        label = choice.display if choice else only
        return f"Community pack active: {label}."
    official = [s for s in unique if is_official_state(s)]
    if official and unique <= {ORIGINAL, *official}:
        lang = official_id_from_state(official[0])
        label = discover_official_languages(None).get(lang)
        display = label.display if label else state_label(official[0])
        return f"Official UI active through the English slot: {display}; global data is stock."
    communities = [s for s in unique if s not in (ORIGINAL, UNKNOWN)]
    if communities:
        return "Subsystems are mixed; switch again to make them consistent."
    return "Subsystems are in a mix of original and unknown states."


def summary_for_gui(statuses: dict[str, str], gui_lang: str) -> str:
    import gui_i18n as i18n

    if gui_lang == "en":
        return summary_for(statuses)
    unique = set(statuses.values())
    if len(unique) == 1:
        only = next(iter(unique))
        if only == ORIGINAL:
            return i18n.t(gui_lang, "summary_all_stock")
        if only == UNKNOWN:
            return i18n.t(gui_lang, "summary_all_unknown")
        if is_official_state(only):
            lang = official_id_from_state(only)
            label = discover_official_languages(None).get(lang)
            display = choice_display(label, gui_lang) if label else state_label(only)
            return i18n.t(gui_lang, "summary_official_ui", display=display)
        choice = discover_community_packs().get(only)
        display = choice_display(choice, gui_lang) if choice else only
        return i18n.t(gui_lang, "summary_community", display=display)
    official = [s for s in unique if is_official_state(s)]
    if official and unique <= {ORIGINAL, *official}:
        lang = official_id_from_state(official[0])
        label = discover_official_languages(None).get(lang)
        display = choice_display(label, gui_lang) if label else state_label(official[0])
        return i18n.t(gui_lang, "summary_official_mixed", display=display)
    communities = [s for s in unique if s not in (ORIGINAL, UNKNOWN)]
    if communities:
        return i18n.t(gui_lang, "summary_mixed")
    return i18n.t(gui_lang, "summary_mixed_unknown")


# ----------------------------------------------------------------------
# Commands
# ----------------------------------------------------------------------
_LABELS = {"main-ui": "main UI", "plugins": "plug-ins"}


def _print_status(args) -> dict[str, str]:
    statuses = classify_all(args)
    print()
    print("  Current state:")
    width = max(len(_LABELS[n]) for n in PIPELINES)
    for name in PIPELINES:
        current = statuses.get(name, UNKNOWN)
        label = _LABELS[name].ljust(width)
        print(f"    {label}   {state_marker(current)}   ({state_label(current)})")
    print(f"\n  {summary_for(statuses)}")
    return statuses


def cmd_status(args) -> None:
    _print_status(args)
    communities = discover_community_packs()
    officials = discover_official_languages(args.csp)
    if communities:
        print()
        print("  community packs:")
        for c in communities.values():
            print(f"    {c.id:12} {c.display}")
    if officials:
        print()
        print("  official CSP languages:")
        for c in officials.values():
            print(f"    {c.id:12} {c.display}")
    if not FROZEN:
        print()
        print("  switch:  python src/lang.py <language>")
    print()


def _choice_or_exit(target: str, csp: str | None) -> LanguageChoice:
    choice = choice_by_target(target, csp)
    if choice:
        return choice
    communities = " ".join(discover_community_packs()) or "(none found)"
    officials = " ".join(discover_official_languages(csp)) or "(none found)"
    sys.exit("error: unknown language target "
             f"{target!r}\n       community: {communities}\n"
             f"       official:  {officials}")


def _final_instruction(choice: LanguageChoice) -> str:
    return f"Restart CSP to see {choice.display}."


def build_switch_argv(args) -> list[str]:
    """Build argv for an elevated re-launch (GUI or UAC handoff)."""
    argv = [args.target]
    if getattr(args, "from_gui", False):
        argv.append("--from-gui")
    if getattr(args, "keep_open", False):
        argv.append("--keep-open")
    if args.csp:
        argv.extend(["--csp", args.csp])
    celsys_base = getattr(args, "celsys_base", None)
    if celsys_base:
        argv.extend(["--cel-sys", celsys_base])
    csp_version = getattr(args, "csp_version", None)
    if csp_version:
        argv.extend(["--csp-version", csp_version])
    if args.force:
        argv.append("--force")
    if args.dry_run:
        argv.append("--dry-run")
    enabled = getattr(args, "pipelines", None)
    if enabled is not None and enabled != set(PIPELINES):
        argv.extend(["--pipelines", ",".join(sorted(enabled))])
    return argv


def cmd_switch(args) -> None:
    from_gui = getattr(args, "from_gui", False)
    if getattr(args, "csp_version", None):
        set_active_version(args.csp_version)
    clear_warnings()
    choice = _choice_or_exit(args.target, args.csp)
    _configure_pipelines()
    _require_matching_csp_version(args.csp, choice)
    if choice.kind == "community" and not args.dry_run:
        _repack_stale_community_translations()
    state = load_state()
    pipes = all_pipelines()
    cached_all = state.get("pipelines", {})
    enabled: set[str] | None = getattr(args, "pipelines", None)

    plan: list[tuple[str, Pipeline, str, str]] = []
    for name, pipe in pipes.items():
        if enabled is not None and name not in enabled:
            continue
        current, _fp = classify(pipe, args.csp, cached_all.get(name))
        desired = pipe.desired_state(choice)
        needs_refresh = (
            choice.kind == "community"
            and desired == choice.id
            and pipe.has_community_ref(choice.id)
            and pipe.is_state(args.csp, choice.id) is not True
        )
        if current == desired and not needs_refresh:
            if not from_gui:
                print(f"  {_LABELS[name]}: already {state_label(desired)} -- skipping")
        else:
            plan.append((name, pipe, current, desired))

    if enabled is not None and not enabled:
        sys.exit("error: no subsystems selected")

    if not plan:
        if choice.kind == "community" and not args.dry_run:
            install.check_csp_closed(args.force)
            _sync_community_tool_dbs(args.csp, choice, dry_run=args.dry_run)
        if not from_gui:
            if enabled is not None and len(enabled) < len(PIPELINES):
                print(f"\nSelected subsystems already match '{choice.display}'. "
                      f"Nothing to do.")
            else:
                print(f"\nAll subsystems already match '{choice.display}'. "
                      f"Nothing to do.")
            print(_final_instruction(choice))
        return

    if not args.dry_run:
        install.check_csp_closed(args.force)
        if not is_admin():
            if from_gui:
                rc, err = run_elevated_sync(build_switch_argv(args))
                if rc != 0:
                    sys.exit(err or "error: switch failed")
                return
            install.ensure_admin()

    out = quiet_stdout() if from_gui else nullcontext()
    with out:
        print(f"\nWill switch {len(plan)} subsystem(s) for '{choice.display}':")
        for name, _pipe, current, desired in plan:
            print(f"  - {_LABELS[name]}  ({state_label(current)} -> "
                  f"{state_label(desired)})")

        for name, pipe, _current, _desired in plan:
            try:
                pipe.switch_to(choice, args.csp, args.dry_run)
            except SystemExit as e:
                sys.exit(f"\nerror: subsystem '{_LABELS[name]}' failed: {e}")

        if not args.dry_run:
            for name, pipe in pipes.items():
                current, fp = classify(pipe, args.csp, None)
                if fp is not None:
                    set_pipeline_state(state, name, current, fp)
            save_state(state)

        if WARNINGS:
            print(f"\nFinished with {len(WARNINGS)} warning(s) for '{choice.display}'.")
        else:
            print(f"\nDone -- switched file state for '{choice.display}'.")
        print(_final_instruction(choice))


# ----------------------------------------------------------------------
# Console menu
# ----------------------------------------------------------------------
_BANNER = """
=============================================================
  Clip Studio Paint  --  Language switcher
=============================================================
"""


def cmd_menu(args) -> None:
    while True:
        print(_BANNER)
        _print_status(args)

        choices = list(discover_community_packs().values())
        official = list(discover_official_languages(args.csp).values())
        if official:
            choices.extend(official)
        print()
        for i, choice in enumerate(choices, 1):
            kind = "community" if choice.kind == "community" else "official"
            print(f"  [{i}] {choice.display}  ({kind})")
        print("  [0] Exit")
        print()

        try:
            raw = input("  Choose: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if raw == "0" or raw.lower() in ("q", "quit", "exit"):
            return
        try:
            choice = choices[int(raw) - 1]
        except (ValueError, IndexError):
            print(f"\n  unknown choice: {raw!r}")
            _pause()
            continue

        args.target = choice.id
        sys.argv = [sys.argv[0], choice.id, "--keep-open"]
        try:
            cmd_switch(args)
        except SystemExit as e:
            print(f"\n{e}")
        _pause()
        sys.argv = [sys.argv[0]]


def _pause() -> None:
    try:
        input("\n  press Enter to continue...")
    except EOFError:
        pass


# ----------------------------------------------------------------------
# Simple GUI
# ----------------------------------------------------------------------
def _ensure_lang_module_alias() -> None:
    """Make `python src/lang.py` share one module with `from lang import ...`."""
    import sys

    main_mod = sys.modules.get("__main__")
    if main_mod is None:
        return
    main_file = Path(getattr(main_mod, "__file__", "") or "").name
    if main_file == "lang.py":
        sys.modules["lang"] = main_mod


def _show_gui_error(message: str) -> None:
    print(f"GUI error: {message}", file=sys.stderr)
    try:
        from tkinter import messagebox

        messagebox.showerror("csp-lang-switch", message)
    except Exception:
        pass


def cmd_gui(args) -> None:
    _ensure_lang_module_alias()
    try:
        from gui_picker import run_picker
        run_picker(args, SETTINGS_FILE)
    except KeyboardInterrupt:
        pass
    except ImportError:
        print(
            'GUI unavailable (install customtkinter: pip install customtkinter); '
            'falling back to console menu.')
        cmd_menu(args)
    except Exception as e:  # pragma: no cover
        import traceback

        traceback.print_exc()
        _show_gui_error(str(e))


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------
def main(argv: list[str] | None = None) -> None:
    _ensure_lang_module_alias()
    raw = sys.argv[1:] if argv is None else argv
    no_args = len(raw) == 0

    parser = argparse.ArgumentParser(
        prog="lang.py" if not FROZEN else APP_NAME,
        description="Switch Clip Studio Paint between community packs and "
                    "stock official languages.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="examples:\n"
               "  csp-lang-switch russian      install the Russian community pack\n"
               "  csp-lang-switch english      restore stock files for English\n"
               "  csp-lang-switch japanese     restore stock files for Japanese\n"
               "  csp-lang-switch status       show what is installed\n"
               "  csp-lang-switch              open the language picker",
    )
    parser.add_argument("target", nargs="?", default="gui",
                        metavar="TARGET",
                        help="community pack, official language, 'status', "
                             "'menu', or 'gui' (default: gui)")
    parser.add_argument("--csp", metavar="DIR",
                        help="CSP 'resource' folder (auto-detected if omitted)")
    parser.add_argument(
        "--cel-sys", metavar="DIR",
        help="CELSYS install folder (default: C:\\Program Files\\CELSYS)",
    )
    parser.add_argument(
        "--csp-version", metavar="VER", choices=SUPPORTED_VERSIONS,
        help="CSP version to use (default: auto-detect from install)",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="print what would happen, change nothing")
    parser.add_argument("--force", action="store_true",
                        help="proceed even if CSP appears to be running")
    parser.add_argument("--keep-open", action="store_true",
                        help=argparse.SUPPRESS)
    parser.add_argument("--from-gui", action="store_true",
                        help=argparse.SUPPRESS)
    parser.add_argument("--pipelines", default=None,
                        help=argparse.SUPPRESS)
    parser.add_argument("--gui-error-file", default=None,
                        help=argparse.SUPPRESS)

    args = parser.parse_args(raw)
    if args.pipelines:
        args.pipelines = {p.strip() for p in args.pipelines.split(",") if p.strip()}
    if no_args:
        args.target = "gui"
    if args.keep_open:
        attach_console()

    import gui_i18n as i18n
    celsys_base = args.cel_sys
    if not celsys_base and SETTINGS_FILE:
        celsys_base = i18n.load_celsys_base(SETTINGS_FILE)
    set_celsys_base(celsys_base)
    args.celsys_base = celsys_base

    detected = detect_installed_csp_version(args.csp)
    saved = i18n.load_csp_version(SETTINGS_FILE) if SETTINGS_FILE else None
    version = resolve_csp_version(args.csp_version, detected, saved)
    set_active_version(version)
    args.csp_version = version
    args.detected_csp_version = detected
    args.raw_csp_product_version = detected_csp_product_version(args.csp)

    _configure_pipelines()

    try:
        if args.target == "gui":
            cmd_gui(args)
        elif args.target == "menu":
            cmd_menu(args)
        elif args.target == "status":
            cmd_status(args)
        else:
            cmd_switch(args)
    except SystemExit as e:
        err_file = getattr(args, "gui_error_file", None)
        if err_file and e.args:
            msg = str(e.args[0])
            if msg and msg not in ("0", "None"):
                try:
                    Path(err_file).write_text(msg, encoding="utf-8")
                except OSError:
                    pass
        raise
    finally:
        if args.keep_open:
            pause_console()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
lang.py
=======
Top-level language-pack switcher for a Clip Studio Paint install.

Community translations (Russian today; Ukrainian, Kazakh, etc. later) are
installed into CSP's English slot and into the global plug-in/tool/material
locations. Official CSP languages are not patched; selecting one restores the
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
from common import is_admin, quiet_stdout, run_elevated_sync
from version import (
    LANGS_ROOT,
    ACTIVE_VERSION,
    GUARD_GUID,
    GUARD_SLOT,
    GUARD_SIZE,
    GUARD_SHA256,
    fingerprint_guard_file,
)


for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


# ----------------------------------------------------------------------
# Paths -- source mode vs bundled exe
# ----------------------------------------------------------------------
FROZEN = getattr(sys, "frozen", False)
APP_NAME = "csp-lang"
LEGACY_APP_NAME = "csp-russian"
COMMUNITY_SLOT = "english"

if FROZEN:
    DATA_ROOT = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    _localappdata = os.environ.get("LOCALAPPDATA") or \
        str(Path.home() / "AppData" / "Local")
    USER_DATA = Path(_localappdata) / APP_NAME
    LEGACY_USER_DATA = Path(_localappdata) / LEGACY_APP_NAME
    USER_DATA.mkdir(parents=True, exist_ok=True)
    STATE_FILE = USER_DATA / "state.json"
    SETTINGS_FILE = USER_DATA / "settings.json"
else:
    DATA_ROOT = Path(__file__).resolve().parent.parent
    USER_DATA = DATA_ROOT
    LEGACY_USER_DATA = DATA_ROOT
    STATE_FILE = DATA_ROOT / ".lang-state.json"
    SETTINGS_FILE = DATA_ROOT / ".csp-lang-settings.json"

if FROZEN:
    LANGS_DIR = DATA_ROOT / "langs"
else:
    LANGS_DIR = LANGS_ROOT
ENGLISH_STOCK = LANGS_DIR / "english" / "ui"
BUNDLED_ENGLISH = LANGS_DIR / "english"

# In bundled mode, prefer new backup locations but keep old csp-russian backups
# usable so existing users are not stranded after the product rename.
def _backup_dir(name: str) -> Path:
    current = USER_DATA / name
    legacy = LEGACY_USER_DATA / name
    if FROZEN and not any(current.rglob("*")) and any(legacy.rglob("*")):
        return legacy
    return current


PLUGINS_BACKUP = _backup_dir("plugins")
TOOLS_BACKUP = _backup_dir("tools")
MATERIALS_BACKUP = _backup_dir("materials")
COLORSETS_BACKUP = _backup_dir("colorsets")

if not FROZEN:
    # In source mode, stock snapshots live under the active version tree.
    PLUGINS_BACKUP = LANGS_ROOT / "english" / "plugins"
    TOOLS_BACKUP = LANGS_ROOT / "english" / "tools"
    MATERIALS_BACKUP = LANGS_ROOT / "english" / "materials"
    COLORSETS_BACKUP = LANGS_ROOT / "english" / "colorsets"

PIPELINES = ("main-ui", "plugins", "tools", "materials", "colorsets")
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
    "tools": "tools",
    "materials": "materials",
    "colorsets": "colorsets",
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
        label = OFFICIAL_LABELS.get(lang, lang.replace("_", " ").title())
        if gui_lang and gui_lang != "en":
            return i18n.t(gui_lang, "state_official", label=label)
        return f"{label} (official)"
    choice = discover_community_packs().get(state)
    if choice:
        return choice.display
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
def _tools_module():
    import tools
    return tools


def _materials_module():
    import materials
    return materials


def _plugins_module():
    import plugins
    return plugins


def _colorsets_module():
    import colorsets
    return colorsets


# ----------------------------------------------------------------------
# Pipeline path overrides
# ----------------------------------------------------------------------
_pipelines_configured = False


def _configure_pipelines() -> None:
    """Point helper modules at the data root and writable backups."""
    global _pipelines_configured
    if _pipelines_configured:
        return
    install.ROOT = DATA_ROOT
    install.LANGS_DIR = LANGS_DIR
    if FROZEN:
        p = _plugins_module()
        p.PLUGINS_DIR = PLUGINS_BACKUP
        t = _tools_module()
        t.TOOLS_DIR = TOOLS_BACKUP
        m = _materials_module()
        m.MATERIALS_DIR = MATERIALS_BACKUP
        c = _colorsets_module()
        c.COLORSETS_DIR = COLORSETS_BACKUP
        _seed_bundled_backups()
    _pipelines_configured = True


def _bundled_guard_profile() -> tuple[int, str] | None:
    """Size + sha256 of the bundled English main-UI guard file."""
    path = ENGLISH_STOCK / GUARD_GUID
    if not path.is_file():
        return None
    data = path.read_bytes()
    return len(data), hashlib.sha256(data).hexdigest()


def _install_matches_active_version(csp: str | None) -> bool:
    expected = _bundled_guard_profile()
    if expected is None:
        return True
    if GUARD_SIZE is not None and GUARD_SHA256 is not None:
        expected = (GUARD_SIZE, GUARD_SHA256)
    resource = install.find_csp_resource(csp)
    actual = fingerprint_guard_file(resource / GUARD_SLOT / GUARD_GUID)
    return actual == expected


def _require_matching_csp_version(csp: str | None, choice: LanguageChoice) -> None:
    if choice.kind != "community":
        return
    if _install_matches_active_version(csp):
        return
    sys.exit(
        f"error: this build targets Clip Studio Paint {ACTIVE_VERSION}, but the "
        f"installed CSP resource files do not match.\n"
        f"       Update CSP to {ACTIVE_VERSION} or use a matching csp-lang build."
    )


def _seed_bundled_backups() -> None:
    """Copy bundled English stock into LOCALAPPDATA when backup dirs are empty."""
    if not FROZEN or not BUNDLED_ENGLISH.is_dir():
        return
    jobs = (
        ("plugins", PLUGINS_BACKUP, ("*.dll",)),
        ("tools", TOOLS_BACKUP, ("**/*",)),
        ("materials", MATERIALS_BACKUP, ("**/*",)),
        ("colorsets", COLORSETS_BACKUP, ("**/*",)),
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
    if pipeline == "plugins":
        mod = _plugins_module()
        if hasattr(mod, "configure_language"):
            mod.configure_language(pack)
        else:
            mod.BUILD_DIR = root
    elif pipeline == "tools":
        mod = _tools_module()
        if hasattr(mod, "configure_language"):
            mod.configure_language(pack)
        else:
            mod.BUILD_DIR = root
    elif pipeline == "materials":
        mod = _materials_module()
        if hasattr(mod, "configure_language"):
            mod.configure_language(pack)
        else:
            mod.BUILD_DIR = root
    elif pipeline == "colorsets":
        mod = _colorsets_module()
        if hasattr(mod, "configure_language"):
            mod.configure_language(pack)
        else:
            mod.BUILD_DIR = root


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


def colorset_install_files(csp: str | None) -> list[Path]:
    try:
        c = _colorsets_module()
        out: list[Path] = []
        for tag, root in c.roots(csp).items():
            for abspath, _rel in c.discover(root, tag):
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
    defaults = dict(csp=None, dry_run=False, yes=True, force=False,
                    keep_open=False)
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

    def switch_to(self, choice, csp, dry_run):
        if choice.kind == "community" and self.has_community_ref(choice.id):
            install.cmd_install(_pipe_args(
                target=choice.id, slot=COMMUNITY_SLOT, csp=csp,
                dry_run=dry_run))
            return
        if choice.kind == "official" and choice.id != COMMUNITY_SLOT:
            self._copy_official_to_slot(choice, csp, dry_run)
            return
        install.cmd_install(_pipe_args(
            target="english", slot=COMMUNITY_SLOT, csp=csp, dry_run=dry_run))

    def _copy_official_to_slot(self, choice, csp, dry_run):
        resource_dir = install.find_csp_resource(csp)
        src = resource_dir / choice.id
        slot = resource_dir / COMMUNITY_SLOT
        src_files = install.resource_files(src)
        if not src_files:
            sys.exit(f"error: no resource files in official language folder: {src}")
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


class ToolsPipeline(Pipeline):
    subdir = "tools"

    def install_fingerprint(self, csp):
        return fingerprint_files(tool_install_files(csp))

    def is_state(self, csp, state):
        try:
            t = _tools_module()
            ref_root = TOOLS_BACKUP if state == ORIGINAL else self.community_ref(state)
            if not ref_root.is_dir():
                return None
            saw_any = False
            for tag, root in t.roots(csp).items():
                for abspath, rel in t.discover(root, tag):
                    saw_any = True
                    rf = ref_root / tag / rel
                    if not rf.is_file():
                        return False
                    if abspath.stat().st_size != rf.stat().st_size:
                        return False
                    if _hash_file(abspath) != _hash_file(rf):
                        return False
            return True if saw_any else None
        except SystemExit:
            return None

    def switch_to(self, choice, csp, dry_run):
        t = _tools_module()
        if choice.kind == "community" and self.has_community_ref(choice.id):
            self._ensure_backup(dry_run, csp)
            _set_build_dir(self.name, choice.id)
            t.cmd_install(_pipe_args(csp=csp, dry_run=dry_run))
        else:
            self._restore_if_possible(t, csp, dry_run)

    def _ensure_backup(self, dry_run, csp):
        t = _tools_module()
        if t.TOOLS_DIR.is_dir() and any(p.is_file() for p in t.TOOLS_DIR.rglob("*")):
            return
        if dry_run:
            print(f"\n[dry-run] would snapshot tool DBs to {t.TOOLS_DIR}")
            return
        print(f"\n(no tool-DB backup at {t.TOOLS_DIR} -- snapshotting first)")
        t.cmd_backup(_pipe_args(csp=csp, dry_run=dry_run))

    def _restore_if_possible(self, t, csp, dry_run):
        if not (t.TOOLS_DIR.is_dir() and any(p.is_file() for p in t.TOOLS_DIR.rglob("*"))):
            add_warning("\nWARNING: no tool-DB backup found; tool palette was not restored.")
            return
        t.cmd_restore(_pipe_args(csp=csp, dry_run=dry_run))


class MaterialsPipeline(Pipeline):
    subdir = "materials"

    def install_fingerprint(self, csp):
        return fingerprint_files(material_install_files())

    def is_state(self, csp, state):
        try:
            m = _materials_module()
            ref_root = MATERIALS_BACKUP if state == ORIGINAL else self.community_ref(state)
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

    def switch_to(self, choice, csp, dry_run):
        m = _materials_module()
        if choice.kind == "community" and self.has_community_ref(choice.id):
            self._ensure_backup(dry_run)
            _set_build_dir(self.name, choice.id)
            m.cmd_install(_pipe_args(dry_run=dry_run))
        else:
            self._restore_if_possible(m, dry_run)

    def _ensure_backup(self, dry_run):
        m = _materials_module()
        if m.MATERIALS_DIR.is_dir() and any(
                p.is_file() for p in m.MATERIALS_DIR.rglob("*")):
            return
        if dry_run:
            print(f"\n[dry-run] would snapshot materials to {m.MATERIALS_DIR}")
            return
        print(f"\n(no material backup at {m.MATERIALS_DIR} -- snapshotting first)")
        m.cmd_backup(_pipe_args(dry_run=dry_run))

    def _restore_if_possible(self, m, dry_run):
        if not (m.MATERIALS_DIR.is_dir() and any(
                p.is_file() for p in m.MATERIALS_DIR.rglob("*"))):
            add_warning("\nWARNING: no material backup found; materials were not restored.")
            return
        m.cmd_restore(_pipe_args(dry_run=dry_run))


class ColorSetsPipeline(Pipeline):
    subdir = "colorsets"

    def install_fingerprint(self, csp):
        return fingerprint_files(colorset_install_files(csp))

    def is_state(self, csp, state):
        try:
            c = _colorsets_module()
            ref_root = COLORSETS_BACKUP if state == ORIGINAL else self.community_ref(state)
            if not ref_root.is_dir():
                return None
            saw_any = False
            for tag, root in c.roots(csp).items():
                for abspath, rel in c.discover(root, tag):
                    saw_any = True
                    rf = ref_root / tag / rel
                    if not rf.is_file():
                        return False
                    if abspath.stat().st_size != rf.stat().st_size:
                        return False
                    if _hash_file(abspath) != _hash_file(rf):
                        return False
            return True if saw_any else None
        except SystemExit:
            return None

    def switch_to(self, choice, csp, dry_run):
        c = _colorsets_module()
        if choice.kind == "community" and self.has_community_ref(choice.id):
            self._ensure_backup(dry_run, csp)
            _set_build_dir(self.name, choice.id)
            c.cmd_install(_pipe_args(csp=csp, dry_run=dry_run))
        else:
            self._restore_if_possible(c, csp, dry_run)

    def _ensure_backup(self, dry_run, csp):
        c = _colorsets_module()
        if c.COLORSETS_DIR.is_dir() and any(
                p.is_file() for p in c.COLORSETS_DIR.rglob("*")):
            return
        if dry_run:
            print(f"\n[dry-run] would snapshot color sets to {c.COLORSETS_DIR}")
            return
        print(f"\n(no color-set backup at {c.COLORSETS_DIR} -- snapshotting first)")
        c.cmd_backup(_pipe_args(csp=csp, dry_run=dry_run))

    def _restore_if_possible(self, c, csp, dry_run):
        if not (c.COLORSETS_DIR.is_dir() and any(
                p.is_file() for p in c.COLORSETS_DIR.rglob("*"))):
            add_warning("\nWARNING: no color-set backup found; color sets were not restored.")
            return
        c.cmd_restore(_pipe_args(csp=csp, dry_run=dry_run))


def all_pipelines() -> dict[str, Pipeline]:
    return {
        "main-ui": MainUIPipeline("main-ui"),
        "plugins": PluginsPipeline("plugins"),
        "tools": ToolsPipeline("tools"),
        "materials": MaterialsPipeline("materials"),
        "colorsets": ColorSetsPipeline("colorsets"),
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
            display = label.display if label else state_label(only)
            return i18n.t(gui_lang, "summary_official_ui", display=display)
        choice = discover_community_packs().get(only)
        display = choice.display if choice else only
        return i18n.t(gui_lang, "summary_community", display=display)
    official = [s for s in unique if is_official_state(s)]
    if official and unique <= {ORIGINAL, *official}:
        lang = official_id_from_state(official[0])
        label = discover_official_languages(None).get(lang)
        display = label.display if label else state_label(official[0])
        return i18n.t(gui_lang, "summary_official_mixed", display=display)
    communities = [s for s in unique if s not in (ORIGINAL, UNKNOWN)]
    if communities:
        return i18n.t(gui_lang, "summary_mixed")
    return i18n.t(gui_lang, "summary_mixed_unknown")


# ----------------------------------------------------------------------
# Commands
# ----------------------------------------------------------------------
_LABELS = {"main-ui": "main UI", "plugins": "plug-ins",
           "tools": "tool palette", "materials": "materials",
           "colorsets": "color sets"}

_GUI_LABELS = {"main-ui": "Main UI", "plugins": "Plug-ins",
               "tools": "Tool palette", "materials": "Materials",
               "colorsets": "Color sets"}


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
    if args.csp:
        argv.extend(["--csp", args.csp])
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
    clear_warnings()
    choice = _choice_or_exit(args.target, args.csp)
    _configure_pipelines()
    _require_matching_csp_version(args.csp, choice)
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
        if current == desired:
            if not from_gui:
                print(f"  {_LABELS[name]}: already {state_label(desired)} -- skipping")
        else:
            plan.append((name, pipe, current, desired))

    if enabled is not None and not enabled:
        sys.exit("error: no subsystems selected")

    if not plan:
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
def cmd_gui(args) -> None:
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
        print(f'GUI unavailable ({e}); falling back to console menu.')
        cmd_menu(args)


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------
def main(argv: list[str] | None = None) -> None:
    raw = sys.argv[1:] if argv is None else argv
    no_args = len(raw) == 0

    parser = argparse.ArgumentParser(
        prog="lang.py" if not FROZEN else APP_NAME,
        description="Switch Clip Studio Paint between community packs and "
                    "stock official languages.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="examples:\n"
               "  csp-lang russian      install the Russian community pack\n"
               "  csp-lang english      restore stock files for English\n"
               "  csp-lang japanese     restore stock files for Japanese\n"
               "  csp-lang status       show what is installed\n"
               "  csp-lang              open the language picker",
    )
    parser.add_argument("target", nargs="?", default="gui",
                        metavar="TARGET",
                        help="community pack, official language, 'status', "
                             "'menu', or 'gui' (default: gui)")
    parser.add_argument("--csp", metavar="DIR",
                        help="CSP 'resource' folder (auto-detected if omitted)")
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
            try:
                input("\nPress Enter to close this window...")
            except EOFError:
                pass


if __name__ == "__main__":
    main()

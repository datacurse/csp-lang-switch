#!/usr/bin/env python3
"""
gui_i18n.py
===========
Strings and locale helpers for the csp-lang-switch picker GUI.
"""

from __future__ import annotations

import ctypes
import json
import locale
import sys
from pathlib import Path

SUPPORTED = ("en", "ru")
DEFAULT = "ru"

NATIVE_LABELS = {"en": "English", "ru": "Русский"}

# Localized names for language ids (official + community packs).
LANGUAGE_NAMES: dict[str, dict[str, str]] = {
    "en": {
        "japanese": "Japanese",
        "english": "English",
        "korean": "Korean",
        "chinese_t": "Traditional Chinese",
        "chinese_tc": "Traditional Chinese",
        "chinese_s": "Simplified Chinese",
        "chinese_sc": "Simplified Chinese",
        "french": "French",
        "spanish": "Spanish",
        "german": "German",
        "thai": "Thai",
        "indonesian": "Indonesian",
        "portuguese_b": "Portuguese (Brazil)",
        "portuguese": "Portuguese (Brazil)",
        "russian": "Russian",
        "ukrainian": "Ukrainian",
        "kazakh": "Kazakh",
    },
    "ru": {
        "japanese": "Японский",
        "english": "Английский",
        "korean": "Корейский",
        "chinese_t": "Традиционный китайский",
        "chinese_tc": "Традиционный китайский",
        "chinese_s": "Упрощённый китайский",
        "chinese_sc": "Упрощённый китайский",
        "french": "Французский",
        "spanish": "Испанский",
        "german": "Немецкий",
        "thai": "Тайский",
        "indonesian": "Индонезийский",
        "portuguese_b": "Португальский (Бразилия)",
        "portuguese": "Португальский (Бразилия)",
        "russian": "Русский",
        "ukrainian": "Украинский",
        "kazakh": "Казахский",
    },
}


def language_label(gui_lang: str, lang_id: str) -> str | None:
    """Return the language name in the GUI locale, or None if unknown."""
    lang = normalize_language(gui_lang)
    return LANGUAGE_NAMES.get(lang, LANGUAGE_NAMES[DEFAULT]).get(lang_id)


def detect_system_language() -> str:
    """Pick a supported GUI language from the OS locale."""
    if sys.platform == "win32":
        try:
            lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
            if lang_id == 0x19:  # Russian
                return "ru"
        except Exception:
            pass
    try:
        loc = (locale.getdefaultlocale()[0] or "").lower()
        if loc.startswith("ru"):
            return "ru"
    except Exception:
        pass
    return DEFAULT


def normalize_language(code: str | None) -> str:
    if not code:
        return DEFAULT
    low = code.lower().split("-")[0].split("_")[0]
    return low if low in SUPPORTED else DEFAULT


def load_gui_language(settings_path: Path) -> str:
    """Return saved GUI language, or detect from the system on first run."""
    if settings_path.is_file():
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("gui_language"):
                return normalize_language(data["gui_language"])
        except (OSError, json.JSONDecodeError):
            pass
    return detect_system_language()


def save_gui_language(settings_path: Path, language: str) -> None:
    language = normalize_language(language)
    data: dict = {}
    if settings_path.is_file():
        try:
            raw = json.loads(settings_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data = raw
        except (OSError, json.JSONDecodeError):
            pass
    data["gui_language"] = language
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_csp_version(settings_path: Path) -> str | None:
    if settings_path.is_file():
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("csp_version"):
                return str(data["csp_version"])
        except (OSError, json.JSONDecodeError):
            pass
    return None


def save_csp_version(settings_path: Path, version: str) -> None:
    data: dict = {}
    if settings_path.is_file():
        try:
            raw = json.loads(settings_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data = raw
        except (OSError, json.JSONDecodeError):
            pass
    data["csp_version"] = version
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def default_celsys_base_display() -> str:
    return r"C:\Program Files\CELSYS"


def load_celsys_base(settings_path: Path) -> str | None:
    """Return a saved custom CELSYS root, or None for the default search."""
    if settings_path.is_file():
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("celsys_base"):
                return str(data["celsys_base"])
        except (OSError, json.JSONDecodeError):
            pass
    return None


def save_celsys_base(settings_path: Path, base: str | None) -> None:
    data: dict = {}
    if settings_path.is_file():
        try:
            raw = json.loads(settings_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data = raw
        except (OSError, json.JSONDecodeError):
            pass
    if base and base != default_celsys_base_display():
        data["celsys_base"] = base
    else:
        data.pop("celsys_base", None)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


_STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "window_title": "Clip Studio Paint Language Switcher",
        "gui_language": "Interface language:",
        "choose_language": "Choose a language",
        "choose_celsys_folder": "CELSYS folder",
        "choose_celsys_folder_title": "Select CELSYS install folder",
        "btn_browse": "Browse…",
        "err_celsys_invalid": (
            "The selected folder does not contain a Clip Studio Paint install."
        ),
        "choose_csp_version": "Clip Studio Paint version",
        "csp_version_auto": "detected: {version}",
        "err_csp_version_unsupported": (
            "Installed Clip Studio Paint ({installed}) is not supported. "
            "Supported versions: {supported}."
        ),
        "err_csp_version_mismatch": (
            "Selected version {selected} does not match the installed CSP "
            "({installed}). Pick the detected version to apply Russian."
        ),
        "choose_blurb": (
            "Community packs use CSP's English slot. Official languages "
            "are also copied into that slot, so no CSP reinstall is needed."
        ),
        "community_box": "Community translations",
        "official_box": "Official CSP languages",
        "now_prefix": "now:",
        "now_unknown": "now: ?",
        "now_active": "active now",
        "checking_status": "Checking current state…",
        "switching": "Switching language…",
        "no_community": "No community packs bundled.",
        "no_official": "CSP install not found.",
        "official_not_yet": "not available yet",
        "btn_apply": "Apply",
        "btn_refresh": "Re-check",
        "btn_close": "Close",
        "err_no_language_title": "No language selected",
        "err_no_language": "Choose a language first.",
        "err_nothing_title": "Nothing selected",
        "err_nothing": "Check at least one subsystem to switch.",
        "failed_title": "Switch failed",
        "switch_failed": (
            "Could not complete the switch. Close Clip Studio Paint, "
            "accept the administrator prompt if shown, and try again."
        ),
        "err_csp_not_found": (
            "Clip Studio Paint was not found on this computer. "
            "Install CSP or use Browse to point at your CELSYS folder."
        ),
        "err_csp_running": "Close Clip Studio Paint before switching languages.",
        "err_csp_userdata": (
            "Could not find CSP user data. Launch Clip Studio Paint "
            "at least once, then try again."
        ),
        "err_csp_resource_path": "The selected folder is not a valid CSP resource directory.",
        "err_admin_denied": (
            "Administrator permission was not granted. Accept the "
            "UAC prompt and try again."
        ),
        "err_version_mismatch": (
            "This language pack is for Clip Studio Paint {version}, "
            "but your installed CSP version does not match."
        ),
        "err_unknown_language": "Unknown language selected.",
        "err_permission_denied": (
            "Could not write to Program Files. Run as "
            "administrator or accept the UAC prompt."
        ),
        "err_generic": "Something went wrong. Close CSP, try again, or re-check status.",
        "warnings_title": "Finished with warnings",
        "done_title": "Done",
        "restart_csp": "Restart Clip Studio Paint.",
        "state_stock": "English (stock)",
        "state_unknown": "Unknown",
        "state_official": "{label} (official)",
        "summary_all_stock": "English stock files are installed in the CSP English slot.",
        "summary_all_unknown": "Current install does not match a known pack.",
        "summary_official_ui": "Official UI active through the English slot: {display}.",
        "summary_community": "Community pack active: {display}.",
        "summary_official_mixed": (
            "Official UI active through the English slot: {display}; "
            "global data is stock."
        ),
        "summary_mixed": "Subsystems are mixed; switch again to make them consistent.",
        "summary_mixed_unknown": "Subsystems are in a mix of original and unknown states.",
    },
    "ru": {
        "window_title": "Переключатель языка Clip Studio Paint",
        "gui_language": "Язык интерфейса:",
        "choose_language": "Выберите язык",
        "choose_celsys_folder": "Папка CELSYS",
        "choose_celsys_folder_title": "Выберите папку установки CELSYS",
        "btn_browse": "выбрать",
        "err_celsys_invalid": (
            "В выбранной папке нет установки Clip Studio Paint."
        ),
        "choose_csp_version": "Версия Clip Studio Paint",
        "csp_version_auto": "обнаружена: {version}",
        "err_csp_version_unsupported": (
            "Установленная версия Clip Studio Paint ({installed}) не поддерживается. "
            "Поддерживаются: {supported}."
        ),
        "err_csp_version_mismatch": (
            "Выбрана версия {selected}, но установлена {installed}. "
            "Выберите обнаруженную версию, чтобы применить русский перевод."
        ),
        "choose_blurb": (
            "Сообщественные переводы ставятся в английский слот CSP. "
            "Официальные языки тоже копируются в этот слот. "
            "Переустанавливать CSP не нужно."
        ),
        "community_box": "Сообщественные переводы",
        "official_box": "Официальные языки CSP",
        "now_prefix": "сейчас:",
        "now_unknown": "сейчас: ?",
        "now_active": "сейчас активен",
        "checking_status": "Проверка текущего состояния…",
        "switching": "Переключение языка…",
        "no_community": "Сообщественные пакеты не найдены.",
        "no_official": "Установка CSP не найдена.",
        "official_not_yet": "пока недоступен",
        "btn_apply": "Применить",
        "btn_refresh": "Проверить снова",
        "btn_close": "Закрыть",
        "err_no_language_title": "Язык не выбран",
        "err_no_language": "Сначала выберите язык.",
        "err_nothing_title": "Ничего не выбрано",
        "err_nothing": "Отметьте хотя бы одну подсистему для переключения.",
        "failed_title": "Ошибка переключения",
        "switch_failed": (
            "Не удалось переключить язык. Закройте Clip Studio Paint, "
            "подтвердите запрос администратора и попробуйте снова."
        ),
        "err_csp_not_found": (
            "Clip Studio Paint не найден на этом компьютере. "
            "Установите CSP или укажите папку CELSYS через «выбрать»."
        ),
        "err_csp_running": "Закройте Clip Studio Paint перед переключением языка.",
        "err_csp_userdata": (
            "Не найдены пользовательские данные CSP. Запустите "
            "Clip Studio Paint хотя бы один раз и попробуйте снова."
        ),
        "err_csp_resource_path": "Выбранная папка не является каталогом resource CSP.",
        "err_admin_denied": (
            "Не получены права администратора. Подтвердите запрос UAC "
            "и попробуйте снова."
        ),
        "err_version_mismatch": (
            "Этот пакет перевода рассчитан на Clip Studio Paint "
            "{version}, но установленная версия CSP не совпадает."
        ),
        "err_unknown_language": "Выбран неизвестный язык.",
        "err_permission_denied": (
            "Не удалось записать файлы в Program Files. Запустите "
            "от имени администратора или подтвердите запрос UAC."
        ),
        "err_generic": (
            "Что-то пошло не так. Закройте CSP, попробуйте снова "
            "или нажмите «Проверить снова»."
        ),
        "warnings_title": "Готово с предупреждениями",
        "done_title": "Готово",
        "restart_csp": "Перезапустите Clip Studio Paint.",
        "state_stock": "Английский (оригинал)",
        "state_unknown": "Неизвестно",
        "state_official": "{label} (официальный)",
        "summary_all_stock": "В английском слоте CSP установлены оригинальные английские файлы.",
        "summary_all_unknown": "Текущая установка не соответствует известному пакету.",
        "summary_official_ui": "Официальный интерфейс через английский слот: {display}.",
        "summary_community": "Активен пакет сообщества: {display}.",
        "summary_official_mixed": (
            "Официальный интерфейс через английский слот: {display}. "
            "Глобальные данные: оригинал."
        ),
        "summary_mixed": "Подсистемы в разном состоянии; переключите снова для согласованности.",
        "summary_mixed_unknown": "Подсистемы смешаны: оригинал и неизвестное состояние.",
    },
}


def t(language: str, key: str, **kwargs: str) -> str:
    lang = normalize_language(language)
    text = _STRINGS.get(lang, _STRINGS[DEFAULT]).get(key)
    if text is None:
        text = _STRINGS[DEFAULT].get(key, key)
    if kwargs:
        return text.format(**kwargs)
    return text


def localize_error(gui_lang: str, message: str, *, version: str | None = None) -> str:
    """Turn a technical sys.exit message into a user-facing GUI string."""
    lang = normalize_language(gui_lang)
    text = message.strip().removeprefix("error:").strip()
    if "subsystem '" in text and " failed:" in text:
        text = text.split(" failed:", 1)[-1].strip().removeprefix("error:").strip()
    low = text.lower()

    if not text or text.isdigit() or "switch failed" in low:
        return t(lang, "switch_failed")
    if "could not find a csp install" in low:
        return t(lang, "err_csp_not_found")
    if "csp is running" in low:
        return t(lang, "err_csp_running")
    if "administrator rights" in low or "uac prompt" in low:
        return t(lang, "err_admin_denied")
    if "this build targets clip studio paint" in low:
        ver = version or "?"
        return t(lang, "err_version_mismatch", version=ver)
    if "csp user data not found" in low or "%appdata% is not set" in low:
        return t(lang, "err_csp_userdata")
    if "english' subfolder" in low or "not a csp resource directory" in low:
        return t(lang, "err_csp_resource_path")
    if "unknown language target" in low:
        return t(lang, "err_unknown_language")
    if "no subsystems selected" in low:
        return t(lang, "err_nothing")
    if "permission denied" in low:
        return t(lang, "err_permission_denied")
    return t(lang, "err_generic")

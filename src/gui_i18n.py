#!/usr/bin/env python3
"""
gui_i18n.py
===========
Strings and locale helpers for the csp-lang picker GUI.
"""

from __future__ import annotations

import ctypes
import json
import locale
import sys
from pathlib import Path

SUPPORTED = ("en", "ru")
DEFAULT = "en"

NATIVE_LABELS = {"en": "English", "ru": "Русский"}


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


_STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "window_title": "Clip Studio Paint Language Switcher",
        "gui_language": "Interface language:",
        "choose_language": "Choose a language",
        "choose_blurb": ("Community packs use CSP's English slot. Official languages "
                         "are also copied into that slot, so no CSP reinstall is needed."),
        "community_box": "Community translations",
        "official_box": "Official CSP languages",
        "subsystems_box": "What to switch",
        "pipeline_main-ui": "Main UI",
        "pipeline_plugins": "Plug-ins",
        "pipeline_tools": "Tool palette",
        "pipeline_materials": "Materials",
        "pipeline_colorsets": "Color sets",
        "now_prefix": "now:",
        "now_unknown": "now: ?",
        "checking_status": "Checking current state…",
        "no_community": "No community packs bundled.",
        "no_official": "CSP install not found.",
        "btn_apply": "Apply",
        "btn_refresh": "Re-check",
        "btn_close": "Close",
        "err_no_language_title": "No language selected",
        "err_no_language": "Choose a language first.",
        "err_nothing_title": "Nothing selected",
        "err_nothing": "Check at least one subsystem to switch.",
        "confirm_apply_title": "Apply language",
        "confirm_apply": ("Apply {display} to:\n  {labels}\n\n"
                          "Close Clip Studio Paint first."),
        "elevated_title": "Continuing as administrator",
        "elevated_body": "An elevated window was opened to finish the switch.",
        "failed_title": "Switch failed",
        "warnings_title": "Finished with warnings",
        "done_title": "Done",
        "restart_csp": "Restart CSP to see {display}.",
        "state_stock": "English (stock)",
        "state_unknown": "Unknown",
        "state_official": "{label} (official)",
        "summary_all_stock": "English stock files are installed in the CSP English slot.",
        "summary_all_unknown": "Current install does not match a known pack.",
        "summary_official_ui": "Official UI active through the English slot: {display}.",
        "summary_community": "Community pack active: {display}.",
        "summary_official_mixed": ("Official UI active through the English slot: {display}; "
                                   "global data is stock."),
        "summary_mixed": "Subsystems are mixed; switch again to make them consistent.",
        "summary_mixed_unknown": "Subsystems are in a mix of original and unknown states.",
    },
    "ru": {
        "window_title": "Переключатель языка Clip Studio Paint",
        "gui_language": "Язык интерфейса:",
        "choose_language": "Выберите язык",
        "choose_blurb": ("Сообщественные переводы ставятся в английский слот CSP. "
                         "Официальные языки тоже копируются в этот слот — "
                         "переустанавливать CSP не нужно."),
        "community_box": "Сообщественные переводы",
        "official_box": "Официальные языки CSP",
        "subsystems_box": "Что переключить",
        "pipeline_main-ui": "Основной интерфейс",
        "pipeline_plugins": "Подключаемые модули",
        "pipeline_tools": "Палитра инструментов",
        "pipeline_materials": "Материалы",
        "pipeline_colorsets": "Наборы цветов",
        "now_prefix": "сейчас:",
        "now_unknown": "сейчас: ?",
        "checking_status": "Проверка текущего состояния…",
        "no_community": "Сообщественные пакеты не найдены.",
        "no_official": "Установка CSP не найдена.",
        "btn_apply": "Применить",
        "btn_refresh": "Проверить снова",
        "btn_close": "Закрыть",
        "err_no_language_title": "Язык не выбран",
        "err_no_language": "Сначала выберите язык.",
        "err_nothing_title": "Ничего не выбрано",
        "err_nothing": "Отметьте хотя бы одну подсистему для переключения.",
        "confirm_apply_title": "Применить язык",
        "confirm_apply": ("Применить {display} к:\n  {labels}\n\n"
                          "Сначала закройте Clip Studio Paint."),
        "elevated_title": "Запуск от администратора",
        "elevated_body": "Открыто окно с правами администратора для завершения переключения.",
        "failed_title": "Ошибка переключения",
        "warnings_title": "Готово с предупреждениями",
        "done_title": "Готово",
        "restart_csp": "Перезапустите CSP, чтобы увидеть {display}.",
        "state_stock": "Английский (оригинал)",
        "state_unknown": "Неизвестно",
        "state_official": "{label} (официальный)",
        "summary_all_stock": "В английском слоте CSP установлены оригинальные английские файлы.",
        "summary_all_unknown": "Текущая установка не соответствует известному пакету.",
        "summary_official_ui": "Официальный интерфейс через английский слот: {display}.",
        "summary_community": "Активен сообщественный пакет: {display}.",
        "summary_official_mixed": ("Официальный интерфейс через английский слот: {display}; "
                                   "глобальные данные — оригинал."),
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


def pipeline_label(language: str, pipeline: str) -> str:
    return t(language, f"pipeline_{pipeline}")

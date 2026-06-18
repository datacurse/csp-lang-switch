#!/usr/bin/env python3
"""Append high-priority workspace/import dialog translations."""

from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "translation" / "gap_translations.csv"
FILE = "742DEA58-main-ui"

ROWS: list[tuple[str, str]] = [
    (
        "The following items will be changed by importing workspace. \r\n%sDo you want to proceed?",
        "При импорте рабочего пространства будут изменены следующие элементы.\r\n%sПродолжить?",
    ),
    (
        "Status of current workspace has not registered yet. \r\nDo you want to register it before importing?",
        "Текущее рабочее пространство ещё не зарегистрировано.\r\nЗарегистрировать его перед импортом?",
    ),
    (
        "Registered workspaces \r\nwill be reset to their original defaults.\r\nAny added workspaces will be deleted.",
        "Зарегистрированные рабочие пространства\r\nбудут сброшены к исходным значениям по умолчанию.\r\nВсе добавленные рабочие пространства будут удалены.",
    ),
    (
        'Workspace with name "%s" already exists. \r\nDo you want to overwrite?',
        'Рабочее пространство с именем «%s» уже существует.\r\nПерезаписать?',
    ),
    (
        "The information below will be saved in the workspace.\r\n\u3000-Palette position info-View status\r\n\u3000-Shortcut settings\r\n\u3000-Command palette layout\r\n\u3000-Preferences->Unit settings",
        "Следующие сведения будут сохранены в рабочем пространстве.\r\n\u3000-Сведения о расположении палитр — состояние вида\r\n\u3000-Настройки сочетаний клавиш\r\n\u3000-Раскладка панели команд\r\n\u3000-Настройки->Настройки единиц измерения",
    ),
    (
        "Please save the current workspace \r\n to register it as material.",
        "Сохраните текущее рабочее пространство,\r\nчтобы зарегистрировать его как материал.",
    ),
    (
        "Please save the current workspace \r\n before switching to a different one",
        "Сохраните текущее рабочее пространство\r\nперед переключением на другое",
    ),
    (
        "It is possible to change this dialog settings from\r\nWindows -> Workspace-> Workspace import settings\r\n at any time.",
        "Изменить настройки этого диалога можно в любое время через\r\nОкно -> Рабочая среда -> Настройки импорта рабочего пространства.",
    ),
    (
        "Workspace changed.\r\nSetting saved in Window-> Workspace -> %s. \r\nPlease change workspace from this menu from now on.",
        "Рабочая среда изменена.\r\nНастройка сохранена в Окно -> Рабочая среда -> %s.\r\nВ дальнейшем переключайте рабочую среду через это меню.",
    ),
    (
        "\r\n\r\nTo revert the changes, select the Window menu > Workspace > %s.",
        "\r\n\r\nЧтобы отменить изменения, выберите меню «Окно» > «Рабочая среда» > %s.",
    ),
    (
        "\r\n\r\nThe palette layout has been automatically adjusted based on your display set-up.\r\nTo revert the changes, select Windows > Workspace > %s.",
        "\r\n\r\nРаскладка палитр была автоматически настроена под ваш экран.\r\nЧтобы отменить изменения, выберите Окно > Рабочая среда > %s.",
    ),
    (
        "Your workspace has been changed. \r\nThe palette layout has been automatically adjusted based on your display set-up.",
        "Ваша рабочая среда изменена.\r\nРаскладка палитр была автоматически настроена под ваш экран.",
    ),
    (
        "An auto-action is included in shortcut settings and/or command bar settings.\r\nWhen loading this workspace material in another environment, settings with auto-actions will not be applied.\r\n",
        "В настройки сочетаний клавиш и/или панели команд включено авто-действие.\r\nПри загрузке этого материала рабочего пространства в другой среде настройки с авто-действиями не будут применены.\r\n",
    ),
    (
        "These Command Bar Settings include a user-made tool.\r\nWhen loading this workspace material in another environment, some tool settings may not be applied.\r\n",
        "Эти настройки панели команд включают пользовательский инструмент.\r\nПри загрузке этого материала рабочего пространства в другой среде некоторые настройки инструментов могут не примениться.\r\n",
    ),
    (
        "These command bar settings include tools with default settings.\r\nThis workspace may not work correctly in environments where the tool configurations have been changed.\r\n",
        "Эти настройки панели команд включают инструменты с настройками по умолчанию.\r\nЭта рабочая среда может работать некорректно в средах, где конфигурация инструментов была изменена.\r\n",
    ),
    (
        "Layout of palette\r\n",
        "Раскладка палитр\r\n",
    ),
    (
        "Shortcut settings\r\n",
        "Настройки сочетаний клавиш\r\n",
    ),
    (
        "Command Bar Settings\r\n",
        "Настройки панели команд\r\n",
    ),
    (
        "Unit\r\n",
        "Единицы измерения\r\n",
    ),
    (
        "The following items will be reset to default. \r\n%sDo you want to proceed?",
        "Следующие элементы будут сброшены к значениям по умолчанию.\r\n%sПродолжить?",
    ),
    (
        'Reset "%s" to status when registered. \r\nYou cannot undo this. Do you want to proceed?',
        'Сбросить «%s» к состоянию при регистрации.\r\nЭто действие нельзя отменить. Продолжить?',
    ),
    (
        "Found invalid shortcut settings for current OS. \r\nSome or all of the shortcuts for the following commands will be removed. \r\n%s\r\n%s",
        "Обнаружены недопустимые настройки сочетаний клавиш для текущей ОС.\r\nНекоторые или все сочетания для следующих команд будут удалены.\r\n%s\r\n%s",
    ),
]


def main() -> None:
    existing: list[dict[str, str]] = []
    if OUT.is_file():
        with OUT.open(encoding="utf-8-sig", newline="") as f:
            existing = list(csv.DictReader(f))
    seen = {r["source"] for r in existing}
    for src, tgt in ROWS:
        if src in seen:
            continue
        existing.append({"file": FILE, "source": src, "target": tgt})
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["file", "source", "target"])
        w.writeheader()
        w.writerows(existing)
    print(f"appended workspace translations; total rows: {len(existing)}")


if __name__ == "__main__":
    main()

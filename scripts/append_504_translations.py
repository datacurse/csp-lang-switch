#!/usr/bin/env python3
"""Add 5.0.4-only string translations."""

from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "translation" / "gap_translations_504.csv"

ROWS = [
    (
        "742DEA58-main-ui",
        "The most recently edited canvas has been opened.",
        "Открыт последний редактировавшийся холст.",
    ),
    (
        "742DEA58-main-ui",
        "You can open other past canvases from the File menu > Open.",
        "Другие недавние холсты можно открыть через меню «Файл» > «Открыть».",
    ),
    (
        "742DEA58-main-ui",
        "Restoring canvas. It may take some time for the process to finish. Please do not minimize the app until the process is complete.",
        "Восстановление холста. Процесс может занять некоторое время. Не сворачивайте приложение до завершения процесса.",
    ),
    (
        "742DEA58-main-ui",
        "Not all edits may have been restored.",
        "Не все правки могли быть восстановлены.",
    ),
    (
        "742DEA58-main-ui",
        "We have recovered a canvas with unsaved edits.\r\n\r\nPlease save this canvas to keep the edits.",
        "Мы восстановили холст с несохранёнными правками.\r\n\r\nСохраните этот холст, чтобы не потерять правки.",
    ),
    (
        "7F9F9530-cloud-sync",
        "You cannot delete unnamed folders. Please name the folder and try again.",
        "Нельзя удалить папки без имени. Укажите имя папки и повторите попытку.",
    ),
    (
        "7F9F9530-cloud-sync",
        "You cannot delete materials from unnamed folders. Please name the folder and try again.",
        "Нельзя удалить материалы из папок без имени. Укажите имя папки и повторите попытку.",
    ),
]


def main() -> None:
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["file", "source", "target"])
        w.writeheader()
        for file, src, tgt in ROWS:
            w.writerow({"file": file, "source": src, "target": tgt})
    print(f"wrote {len(ROWS)} rows -> {OUT}")


if __name__ == "__main__":
    main()

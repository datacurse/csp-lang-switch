#!/usr/bin/env python3
"""
patch_material_tree.py  --  one-off worksheet fix
=================================================
Adds the Material-palette folder-tree node names to the 7F9F9530 worksheet.

These live in block 6 of 7F9F9530 as a mix of `text` records (multi-word
category names) and `key` records (single-word names: Pattern, Background,
Nature, ...). The Japanese-oracle export keeps the `text` records but skips the
`key` ones, because CSP's own Japanese build *also* leaves block 6 in English
(verified identical across EN/JA/KO/FR/DE/ZH/ES) -- so the oracle cannot see
they are real UI text. Result: the palette tree shows multi-word folders in
Russian and single-word folders in English.

Every skipped name is translated here from CSP's *own* already-translated
sibling records -- the colon-path `text` rows in the same block (e.g.
'Color pattern:Background:Nature' -> 'Цветной узор:Фон:Природа') pin the Russian
for every segment. So this is not a fresh translation, it is propagation.

Run once from the repo root:  python scripts/patch_material_tree.py
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import csp5
from repack import iter_records

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "resource" / "english" / "7F9F9530-3EF0-4be4-8E6B-1C3BF59C3754"
WS = ROOT / "translation" / "files" / "7F9F9530-cloud-sync" / "strings.csv"

# English material-category term -> Russian. Single-segment terms only; colon
# paths are translated segment-by-segment with this same table. Every term is
# taken from the block-6 text records CSP already ships translated, cross-
# checked against the live MaterialFolderTag.mfta tree. '2D'/'3D' stay literal.
TERMS = {
    "All": "Все", "Template": "Шаблон", "Frame": "Рамка",
    "Character": "Персонаж", "Pose": "Поза", "Background": "Фон",
    "Motion": "Движение", "Camera": "Камера", "2D": "2D", "3D": "3D",
    "Item": "Предмет", "Balloon": "Выноска", "Sign": "Знак",
    "Effect": "Эффект", "Other": "Прочее", "Material": "Материал",
    "Pattern": "Узор", "Nature": "Природа", "Artificial": "Искусственное",
    "Texture": "Текстура", "Basic": "Основное", "Dot": "Точки",
    "Gradient": "Градиент", "Cross-hatching": "Перекрёстная штриховка",
    "Dialog": "Реплика", "Feeling": "Настроение", "Narration": "Повествование",
    "Impact": "Удар", "Sentiment": "Настроение", "Wound": "Рана",
    "Light": "Свет", "Icon": "Значок", "Illustration": "Иллюстрация",
    "Building": "Здание", "Tool": "Инструмент", "Decoration": "Украшение",
    "Picture": "Фотография", "Brush": "Кисть", "Head": "Голова",
    "Primitive": "Примитив", "Panorama": "Панорама", "Hand": "Рука",
    "Commodity": "Предметы быта", "Sport": "Спорт", "Fashion": "Мода",
    "Weapon": "Оружие", "Vehicle": "Транспорт", "Housing": "Жильё",
    "Face": "Лицо", "Body": "Тело", "Hair": "Волосы",
    "Download": "Загрузка", "Tone": "Тон", "Favorite": "Избранное",
}


def translate(src: str) -> str:
    """Translate a name, or a colon-path, segment by segment."""
    parts = src.split(":")
    out = []
    for p in parts:
        if p not in TERMS:
            sys.exit(f"ERROR: no translation for segment {p!r} (in {src!r})")
        out.append(TERMS[p])
    return ":".join(out)


def main() -> None:
    # block-6 records present in the resource file
    block6 = [(k, kind, t) for k, kind, t in iter_records(csp5.parse(RES.read_bytes()))
              if k.startswith("6/1/")]

    # rows already in the worksheet
    with WS.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    have = {r["key"] for r in rows}

    new_rows = []
    for key, _kind, source in block6:
        if key in have:
            continue
        target = translate(source)
        if target == source:        # '2D' / '3D' -- nothing to change
            continue
        new_rows.append({"key": key, "source": source, "target": target})

    if not new_rows:
        print("nothing to add -- worksheet already complete")
        return

    rows.extend(new_rows)
    with WS.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["key", "source", "target"])
        w.writeheader()
        w.writerows(rows)

    print(f"added {len(new_rows)} block-6 material-tree rows to {WS.name}")
    for r in new_rows[:8]:
        print(f"  {r['key']:12} {r['source']!r} -> {r['target']!r}")
    print(f"  ... ({len(new_rows)} total)")


if __name__ == "__main__":
    main()

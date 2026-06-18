#!/usr/bin/env python3
"""Machine-translate remaining UI gaps (fallback for bulk fill)."""

from __future__ import annotations

import csv
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GAPS = ROOT / "translation" / "gap_ui_only.csv"
OUT = ROOT / "translation" / "gap_translations_auto.csv"

KEEP = [
    "CLIP STUDIO PAINT", "CLIP STUDIO", "CLIP STUDIO TABMATE", "CELSYS",
    "ComicStudio", "OpenToonz", "Photoshop", "Kindle", "Windows",
    "Mac", "Android", "iPad", "iPhone", "Galaxy", "Wacom", "Surface",
    "OpenGL", "DirectX", "Vulkan", "GLSL", "EPUB", "PDF", "PSD", "PSB",
    "BMP", "JPEG", "PNG", "TIFF", "WebP", "ZIP", "USB", "OK", "Wi-Fi",
    "Bluetooth", "Instagram", "Twitter", "Facebook", "YouTube", "Pixiv",
    "DeviantArt", "Patreon", "PayPal", "Visa", "Mastercard",
]

PLACEHOLDER_RE = re.compile(r"(%[\d]*(?:\.\d+)?[sdif@]|%s|%d|%02d|\{[^}]+\})")


def lf(s: str) -> str:
    return s.replace("\r\n", "\n").replace("\r", "\n")


def protect(text: str) -> tuple[str, list[str]]:
    tokens: list[str] = []

    def repl(m: re.Match[str]) -> str:
        tokens.append(m.group(0))
        return f"__PH{len(tokens)-1}__"

    protected = PLACEHOLDER_RE.sub(repl, text)
    for i, keep in enumerate(KEEP):
        protected = protected.replace(keep, f"__KEEP{i}__")
    return protected, tokens


def restore(text: str, tokens: list[str]) -> str:
    out = text or ""
    for i, keep in enumerate(KEEP):
        out = out.replace(f"__KEEP{i}__", keep)
    for i, tok in enumerate(tokens):
        out = out.replace(f"__PH{i}__", tok)
        out = out.replace(f"__ph{i}__", tok)
    return out


def already_done() -> set[tuple[str, str]]:
    done: set[tuple[str, str]] = set()
    for name in (
        "gap_translations.csv",
        "gap_translations_part1.csv",
        "gap_translations_part2.csv",
        "gap_translations_part3.csv",
        "gap_translations_auto.csv",
    ):
        path = ROOT / "translation" / name
        if not path.is_file():
            continue
        with path.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                tgt = (row.get("target") or "").strip()
                if tgt and tgt != row.get("source", ""):
                    done.add((row["file"], lf(row["source"])))
    return done


def translate_text(translator, text: str) -> str:
    if not text.strip():
        return text
    if len(text.strip()) <= 2 and text.strip().isascii() and text.strip().isalpha():
        return text

    protected, tokens = protect(text)
    chunks: list[str] = []
    buf = protected
    while len(buf) > 4500:
        split = buf.rfind("\n", 0, 4500)
        if split < 1000:
            split = 4500
        chunks.append(buf[:split])
        buf = buf[split:]
    chunks.append(buf)

    out_parts: list[str] = []
    for chunk in chunks:
        for attempt in range(3):
            try:
                part = translator.translate(chunk)
                if part:
                    out_parts.append(part)
                    break
            except Exception:
                time.sleep(1.5 * (attempt + 1))
        else:
            out_parts.append(chunk)
        time.sleep(0.08)
    return restore("".join(out_parts), tokens)


def write_rows(rows: list[dict[str, str]]) -> None:
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["file", "source", "target"])
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    from deep_translator import GoogleTranslator

    translator = GoogleTranslator(source="en", target="ru")
    done = already_done()
    pending: list[dict[str, str]] = []

    with GAPS.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            key = (row["file"], lf(row["source"]))
            if key in done:
                continue
            pending.append(row)

    print(f"auto-translating {len(pending)} string(s)...")
    rows_out: list[dict[str, str]] = []
    for i, row in enumerate(pending, 1):
        src = row["source"]
        try:
            tgt = translate_text(translator, src)
        except Exception as exc:
            print(f"  fail [{i}/{len(pending)}]: {exc}", file=sys.stderr)
            tgt = src
        rows_out.append({"file": row["file"], "source": src, "target": tgt})
        if i % 25 == 0:
            write_rows(rows_out)
            print(f"  {i}/{len(pending)}")
    write_rows(rows_out)
    print(f"wrote {len(rows_out)} row(s) -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

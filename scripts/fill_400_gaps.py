#!/usr/bin/env python3
"""Fill 4.0.0 gap translations from existing worksheets, then auto-translate."""

from __future__ import annotations

import csv
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GAPS = ROOT / "translation" / "gap_400.csv"
OUT = ROOT / "translation" / "gap_translations_400.csv"

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


def load_known() -> dict[str, str]:
    known: dict[str, str] = {}
    files_dir = ROOT / "translation" / "files"
    for uniq in files_dir.glob("*/unique.csv"):
        with uniq.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                src = row["source"]
                tgt = (row.get("target") or "").strip()
                if tgt and tgt != src:
                    known[lf(src)] = tgt
    return known


def adapt(source: str, target: str) -> str:
    src = lf(source)
    tgt = lf(target)
    if src.endswith("\n") and not tgt.endswith("\n"):
        tgt += "\n"
    if "\r\n" in source:
        return tgt.replace("\n", "\r\n")
    return tgt


def lookup(source: str, known: dict[str, str]) -> str | None:
    key = lf(source)
    if key in known:
        return adapt(source, known[key])
    base = key.rstrip(" \t\n\r")
    if base in known:
        return adapt(source, known[base])
    if base.endswith("\n") and base[:-1] in known:
        return adapt(source, known[base[:-1]])
    return None


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


def main() -> int:
    if not GAPS.is_file():
        sys.exit(f"error: run scripts/export_400_gaps.py first ({GAPS})")

    known = load_known()
    pending: list[dict[str, str]] = []
    rows_out: list[dict[str, str]] = []
    seeded = 0

    with GAPS.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            src = row["source"]
            hit = lookup(src, known)
            if hit:
                rows_out.append({"file": row["file"], "source": src, "target": hit})
                seeded += 1
            else:
                pending.append(row)

    print(f"seeded from existing worksheets: {seeded}")
    print(f"auto-translating {len(pending)} string(s)...")

    if pending:
        from deep_translator import GoogleTranslator

        translator = GoogleTranslator(source="en", target="ru")
        for i, row in enumerate(pending, 1):
            src = row["source"]
            try:
                tgt = translate_text(translator, src)
            except Exception as exc:
                print(f"  fail [{i}/{len(pending)}]: {exc}", file=sys.stderr)
                tgt = src
            rows_out.append({"file": row["file"], "source": src, "target": tgt})
            if i % 25 == 0:
                print(f"  {i}/{len(pending)}")

    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["file", "source", "target"])
        w.writeheader()
        w.writerows(rows_out)
    print(f"wrote {len(rows_out)} row(s) -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

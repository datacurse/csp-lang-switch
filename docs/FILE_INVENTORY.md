# CSP5 Resource File Inventory — the 39 shared GUID files

> Counts regenerated 2026-05-19 from `resource/english/` vs `resource/japanese/`
> via the **Japanese oracle** (see [`VERIFIED_METHOD.md`](VERIFIED_METHOD.md) →
> "Choosing the translatable set"). Companion to `VERIFIED_METHOD.md`.
>
> This file is the **human-readable** inventory. Its machine-readable twin is
> [`translation/manifest.csv`](../translation/manifest.csv) (`short,guid,slug,
> covers,target,text_count`) — the file list `src/batch.py` drives the
> translation pipeline from. Keep the two in sync when the file set changes.

Each GUID-named file is a **separate UI resource bundle** for one part of Clip
Studio Paint — not a single monolithic UI file. `742DEA58-…` is the main app
(menus, tools, palettes); the other 38 cover specific subsystems and dialogs.
The GUIDs below are abbreviated to their first segment.

**To fully translate CSP's UI you must patch all 32 target files**, not just
`742DEA58`. The `export → edit CSV → apply` workflow in `VERIFIED_METHOD.md` is
identical for every file.

## Totals

* **39 shared files** (present in all 12 language folders).
* **18,299 translatable strings** across the **32 target files** (Japanese-oracle
  count) — **11,843** in `742DEA58`, **6,456** in the other 31.
* The older `classify()`-only count (14,611 `text` records) **undercounted by
  ~3,900**: it dropped every one-word ASCII UI label. Do not use it to scope work.
* 6 non-target files + 1 `maybe` (`A9BED959`) carry no translatable UI text.
* +16 more GUIDs exist only in the `other` folder and carry no UI text.

## Per-file inventory

`strings` = translatable strings by the Japanese oracle for the 32 targets; for
the 6 non-targets it is the raw `classify()` `text` count (those files are
excluded by human judgement — see below — regardless of the oracle).

| GUID (short) | Bytes | strings | Covers | Target? |
|---|--:|--:|---|:--:|
| `742DEA58` | 3,467,072 | 11,843 | **Main UI** — menus, tools, palettes, all core dialogs | ✅ |
| `E79C2AC5` | 310,785 | 3,044 | Material catalog / material manager | ✅ |
| `5634F3A9` | 275,911 | 529 | Animation & timeline editor | ✅ |
| `DD705E0D` | 112,147 | 630 | Clip Studio cloud menu, profile, direct messages | ✅ |
| `46B67EA9` | 68,693 | 160 | **GLSL shader source code** — not UI text | ❌ |
| `7F9F9530` | 48,920 | 907 | Cloud sync UI — block 6 also drives the Material-palette folder tree | ✅ |
| `F2AD839B` | 26,967 | 288 | License verification dialogs | ✅ |
| `61F04D2D` | 21,689 | 303 | License verification (has `$$$` placeholders) | ✅ |
| `97CDB75A` | 17,731 | 27 | Kindle / e-book export settings | ✅ |
| `8AF4B718` | 17,621 | 67 | Video export | ✅ |
| `0A24C606` | 17,488 | 74 | 3D background / pose / layout presets | ✅ |
| `BFA867AE` | 12,127 | 29 | Misc dialogs, Quick Access | ✅ |
| `DE958EF5` | 10,511 | 35 | Material item settings | ✅ |
| `6FFACA71` | 10,498 | 162 | License / Companion Mode | ✅ |
| `48B1A2B7` | 9,170 | 36 | **EPUB/XML markup templates** — not UI text | ❌ |
| `3CC82939` | 8,362 | 11 | Doodle mode / trial prompts | ✅ |
| `B7DCE242` | 6,672 | 11 | 3D drawing-figure import | ✅ |
| `2D481AE5` | 5,239 | 14 | OpenToonz scene export | ✅ |
| `FCBD92AE` | 4,499 | 68 | OpenGL graphics-performance checker | ✅ |
| `B4E918F2` | 3,008 | 91 | Transform / mask settings | ✅ |
| `5B080EAF` | 2,218 | 37 | Storage / folder-access (mobile) | ✅ |
| `4CB47456` | 1,473 | 37 | Book Viewer (EPUB preview) | ✅ |
| `0238E722` | 1,307 | 15 | Export-data dialog | ✅ |
| `4ed3a72f` | 1,019 | 11 | Monthly-plan bonus material | ✅ |
| `D6B9C91F` | 610 | 15 | 3D lighting | ✅ |
| `7D4C5370` | 580 | 11 | Audio import | ✅ |
| `3D51C869` | 562 | 15 | Character motion / animation | ✅ |
| `C50ECAA0` | 561 | 12 | Login dialog | ✅ |
| `A9BED959` | 395 | 4 | Production-time stats — **Japanese-only, never localized** | ⚠️ |
| `58F2FDAB` | 324 | 2 | Data-transfer dialog | ✅ |
| `549DCB7C` | 305 | 1 | Free-drawing-time message | ✅ |
| `9D97267F` | 304 | 5 | Close-button glyph (`×`) + related | ✅ |
| `3FE1708D` | 255 | 2 | "Do not show again" | ✅ |
| `F40FE4A2` | 237 | 0 | Empty stub container | ❌ |
| `9D7A23F7` | 229 | 2 | "Try again" | ✅ |
| `B8DA21EC` | 205 | 1 | Page counter (`%d / %d`) | ✅ |
| `05F925FA` | 150 | 0 | Empty stub container | ❌ |
| `3DC534C9` | 150 | 0 | Empty stub container | ❌ |
| `F549CE76` | 150 | 0 | Empty stub container | ❌ |

## `7F9F9530` block 6 — the Material-palette folder tree

`7F9F9530`'s block 6 is a material-category table that drives the Material
palette's folder tree (`Все материалы → Цветной узор → …`), not just cloud
sync. CSP ships block 6 English in **every** language, so the Japanese oracle
could not see its single-word `key` records as translatable — 90 folder names
stayed English while the multi-word ones translated. They were patched in by
hand from CSP's own colon-path translations; see VERIFIED_METHOD.md → "The
oracle's blind spot" and [`src/_patch_material_tree.py`](../src/_patch_material_tree.py).
The `907` oracle count above therefore excludes those 90 rows (worksheet: 997).

## Non-targets — do not translate

The Japanese oracle decides *which strings* in a target file to translate; it
does **not** decide that a whole file is off-limits — that is human judgement:

* **`46B67EA9`** — its `text` records are **GLSL shader source code**, not
  user-facing strings.
* **`48B1A2B7`** — its `text` records are **EPUB/XML markup templates**.
* **`F40FE4A2`, `05F925FA`, `3DC534C9`, `F549CE76`** — empty stub containers
  (0 strings).
* **`A9BED959`** — 4 Japanese-only production-time stat strings (`制作時間：…`)
  that were left untranslated even in the English folder. Translate only if a
  fully localized build is wanted.

## Regenerate the counts

Run from the repo root — this reproduces the `strings` column above (oracle
count) for every target file:

```python
import sys; sys.path.insert(0, "src")
import csp5
from repack import iter_records, block1_shape
from pathlib import Path

for f in sorted(Path("resource/english").iterdir(),
                key=lambda p: -p.stat().st_size):
    en = csp5.parse(f.read_bytes())
    ja = csp5.parse((Path("resource/japanese") / f.name).read_bytes())
    assert block1_shape(en.block1) == block1_shape(ja.block1), f.name
    n = sum(1 for (_k, kind, et), (_jk, _jkind, jt)
            in zip(iter_records(en), iter_records(ja))
            if kind == "text" or et != jt)
    print(f"{f.name}  {f.stat().st_size:>9}  strings={n}")
```

Descriptions are hand-derived from sampled strings; counts are exact.

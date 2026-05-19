# CSP5 Resource File Inventory — the 39 shared GUID files

> Generated 2026-05-19 from `resource/english/` via `csp5.parse` +
> `extract_csp_strings.classify`. Companion to [`VERIFIED_METHOD.md`](VERIFIED_METHOD.md).

Each GUID-named file is a **separate UI resource bundle** for one part of Clip
Studio Paint — not a single monolithic UI file. `742DEA58-…` is the main app
(menus, tools, palettes); the other 38 cover specific subsystems and dialogs.
The GUIDs below are abbreviated to their first segment.

**To fully translate CSP's UI you must patch ~32 of these files**, not just
`742DEA58`. The `export → edit CSV → apply` workflow in `VERIFIED_METHOD.md` is
identical for every file.

## Totals

* **39 shared files** (present in all 12 language folders).
* **14,611** `text` records total — **9,368** in `742DEA58`, **5,243** in the
  rest.
* Excluding non-targets (see below), **~14,400 translatable UI strings**, of
  which **~5,040 live outside `742DEA58`** — roughly a third of the workload.
* +16 more GUIDs exist only in the `other` folder and carry no UI text.

## Per-file inventory

| GUID (short) | Bytes | text | Covers | Target? |
|---|--:|--:|---|:--:|
| `742DEA58` | 3,467,072 | 9,368 | **Main UI** — menus, tools, palettes, all core dialogs | ✅ |
| `E79C2AC5` | 310,785 | 2,316 | Material catalog / material manager | ✅ |
| `5634F3A9` | 275,911 | 368 | Animation & timeline editor | ✅ |
| `DD705E0D` | 112,147 | 533 | Clip Studio cloud menu, profile, direct messages | ✅ |
| `46B67EA9` | 68,693 | 160 | **GLSL shader source code** — not UI text | ❌ |
| `7F9F9530` | 48,920 | 833 | Cloud sync UI | ✅ |
| `F2AD839B` | 26,967 | 228 | License verification dialogs | ✅ |
| `61F04D2D` | 21,689 | 255 | License verification (has `$$$` placeholders) | ✅ |
| `97CDB75A` | 17,731 | 14 | Kindle / e-book export settings | ✅ |
| `8AF4B718` | 17,621 | 53 | Video export | ✅ |
| `0A24C606` | 17,488 | 36 | 3D background / pose / layout presets | ✅ |
| `BFA867AE` | 12,127 | 12 | Misc dialogs, Quick Access | ✅ |
| `DE958EF5` | 10,511 | 28 | Material item settings | ✅ |
| `6FFACA71` | 10,498 | 126 | License / Companion Mode | ✅ |
| `48B1A2B7` | 9,170 | 36 | **EPUB/XML markup templates** — not UI text | ❌ |
| `3CC82939` | 8,362 | 9 | Doodle mode / trial prompts | ✅ |
| `B7DCE242` | 6,672 | 9 | 3D drawing-figure import | ✅ |
| `2D481AE5` | 5,239 | 11 | OpenToonz scene export | ✅ |
| `FCBD92AE` | 4,499 | 49 | OpenGL graphics-performance checker | ✅ |
| `B4E918F2` | 3,008 | 53 | Transform / mask settings | ✅ |
| `5B080EAF` | 2,218 | 25 | Storage / folder-access (mobile) | ✅ |
| `4CB47456` | 1,473 | 22 | Book Viewer (EPUB preview) | ✅ |
| `0238E722` | 1,307 | 11 | Export-data dialog | ✅ |
| `4ed3a72f` | 1,019 | 10 | Monthly-plan bonus material | ✅ |
| `D6B9C91F` | 610 | 11 | 3D lighting | ✅ |
| `7D4C5370` | 580 | 9 | Audio import | ✅ |
| `3D51C869` | 562 | 5 | Character motion / animation | ✅ |
| `C50ECAA0` | 561 | 10 | Login dialog | ✅ |
| `A9BED959` | 395 | 4 | Production-time stats — **Japanese-only, never localized** | ⚠️ |
| `58F2FDAB` | 324 | 2 | Data-transfer dialog | ✅ |
| `549DCB7C` | 305 | 1 | Free-drawing-time message | ✅ |
| `9D97267F` | 304 | 1 | Close-button glyph (`×`) | ✅ |
| `3FE1708D` | 255 | 1 | "Do not show again" | ✅ |
| `F40FE4A2` | 237 | 0 | Empty stub container | ❌ |
| `9D7A23F7` | 229 | 1 | "Try again" | ✅ |
| `B8DA21EC` | 205 | 1 | Page counter (`%d / %d`) | ✅ |
| `05F925FA` | 150 | 0 | Empty stub container | ❌ |
| `3DC534C9` | 150 | 0 | Empty stub container | ❌ |
| `F549CE76` | 150 | 0 | Empty stub container | ❌ |

## Non-targets — do not translate

* **`46B67EA9`** — its 160 `text` records are **GLSL shader source code**, not
  user-facing strings.
* **`48B1A2B7`** — its 36 `text` records are **EPUB/XML markup templates**.
* **`F40FE4A2`, `05F925FA`, `3DC534C9`, `F549CE76`** — empty stub containers
  (0 `text`).
* **`A9BED959`** — 4 Japanese-only production-time stat strings (`制作時間：…`)
  that were left untranslated even in the English folder. Translate only if a
  fully localized build is wanted.

## Regenerate the counts

Run from the repo root:

```python
import sys; sys.path.insert(0, "src")
import csp5
from extract_csp_strings import classify
from pathlib import Path

for f in sorted(Path("resource/english").iterdir(),
                key=lambda p: -p.stat().st_size):
    container = csp5.parse(f.read_bytes())
    text = sum(classify(t) == "text"
               for _, node in csp5.iter_string_nodes(container.block1)
               for t in node.strings)
    print(f"{f.name}  {f.stat().st_size:>9}  text={text}")
```

Descriptions are hand-derived from sampled strings; counts are exact.

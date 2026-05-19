# CSP Tool-Palette Translation — VERIFIED METHOD

> **STATUS: WORKING — verified end-to-end.** Last confirmed **2026-05-19**.
>
> Companion to [`VERIFIED_METHOD.md`](VERIFIED_METHOD.md) (resource bundles) and
> [`PLUGIN_TRANSLATION.md`](PLUGIN_TRANSLATION.md) (filter plug-in DLLs). This
> file covers the **Tool palette** — a third subsystem, with its own file
> format, method and tool.

---

## TL;DR

The names in CSP's left-hand **Tool palette** — the tool groups (`Sketch`,
`Decoration`, `Comic`…), the tools (`Pen`, `Pencil`, `Brush`, `Eraser`…) and
**every sub-tool** (`G-pen`, `Charcoal`, `Watercolor`…) — are **not** in the
resource bundles `batch.py` / `repack.py` translate, nor in the filter plug-in
DLLs `plugins.py` handles. They live in **SQLite databases**; every tool node's
displayed name is the `Node.NodeName` column.

There are **two** sets of those DBs and **both must be patched** — see next
section. The tool is [`src/tools.py`](../src/tools.py).

---

## The trap: seed vs. user data

CSP keeps tool DBs in two places:

* **Install seed** — `<CSP install>/Settings/PAINT/.../english/*` — one set per
  UI language. These are the **factory defaults**.
* **User data** — `%APPDATA%/CELSYSUserData/CELSYS/CLIPStudioPaintVer<v>/.../*`
  — the **live working copy** CSP actually reads and draws the palette from.

> On first run CSP **copies the seed into the user-data folder**, then never
> re-reads the seed. Patching the seed alone leaves an existing profile fully
> English — the symptom that cost the first pass of this work. **`tools.py`
> patches both**: the user data so the current profile turns Russian, and the
> seed so a freshly-created profile does too.

The user-data copy is language-agnostic — a single set, no per-language
subfolders — and is what a customised palette is saved back into.

---

## The files

Four DB filenames carry tool names. In the **seed** they sit under
per-language folders; in **user data** one level down in fixed subfolders:

| Filename | Names | Covers |
|---|--:|---|
| `Tool/…/EditImageTool.todb`   | 254 | The full tool palette (the default workspace) |
| `Tool/…/UXEditImageTool.todb` | 135 | Modern-UI subset — **seed only**, no user-data copy |
| `MixPalette/…/MixPaletteTool.todb` | 3 | Mix-palette tools |
| `BrushPreset/…/BrushPreset.bfps`   | 14 | Brush-size preset bar |

The two `.tomd` files in `Tool/` and `EditImageToolDownloadTool.dtdb` are also
SQLite but carry no `Node` table — `tools.py` skips them automatically.

---

## The file format

A stock **SQLite 3** database — no custom format, no reverse-engineering. The
schema relevant to translation:

* Table **`Node`** — the tool tree (groups → tools → sub-tools), one row per
  node. `_PW_ID` is the row id; **`NodeName`** is the displayed name. Container
  rows have an empty `NodeName`; named rows are the translatable set.
* Tables `Manager`, `Variant`, `sqlite_sequence` hold brush parameters and tool
  state — **never touched**.

Translation is a plain `UPDATE Node SET NodeName=? WHERE _PW_ID=?`. The shipped
Japanese seed DB is just the English schema with `NodeName` translated, so a
patched DB is structurally interchangeable with any slot.

---

## The worksheet is a dictionary

A tool name is a plain label: the **same English name always maps to the same
Russian name**, in every DB and every node. So `translation/tools.csv` is a
**dictionary** — columns `source,japanese,target`, one row per *distinct* tool
name — and `apply` translates each DB by `NodeName` lookup. This deliberately
ignores `_PW_ID`, which is what lets one worksheet patch all of: the seed DBs,
the user-data DB (different row ids, extra rows) and any future CSP version.

`japanese` is a per-string reference: CSP ships a fully localized Japanese seed,
so `extract` pairs each clean English seed DB with the `japanese` slot by
`_PW_ID` to fill it. It disambiguates names (`Soft` is `柔らか` on a spray but
`軟らかめ` on an eraser; `Grass` `草むら` vs `Grass patch` `草`).

---

## The tooling — `src/tools.py`

A 5-command pipeline, the Tool-palette counterpart of `plugins.py`. Run from the
repo root:

```
python src/tools.py backup     copy the seed + user-data tool DBs -> tools/
python src/tools.py extract    distinct tool names                -> translation/tools.csv
# ... translate the `target` column of tools.csv ...
python src/tools.py apply      write patched DBs                  -> russian-tools/
python src/tools.py install    copy patched DBs back into seed + user data
python src/tools.py restore    copy the originals back
```

* **`tools/`** — the original DBs; the repo's only backup of them. Gitignored.
  Laid out `tools/<tag>/<relpath>` where `<tag>` is `install` (the seed) or
  `userdata`, recording where each DB must be copied back to.
* **`russian-tools/`** — the patched build, output of `apply`, same layout.
  Gitignored.
* **`translation/tools.csv`** — the dictionary worksheet (`source,japanese,
  target`). Tracked in git. Edit `target`, re-run `apply`. Re-running `extract`
  **preserves** existing `target` values, matched by `source`.
* `install` / `restore` write the seed into `C:\Program Files` (self-elevate via
  a UAC prompt, reusing `install.py`) and the user-data DBs into `%APPDATA%`;
  both refuse to run while CSP is open (CSP locks the SQLite files).

Safeguards: `apply` round-trip-checks every DB (re-reads each patched node and
asserts `NodeName` equals the target). `backup` never overwrites a saved
original and skips any live DB whose `NodeName`s already hold Cyrillic — a
previously-patched DB is not a clean original. Standard library only (no
`pefile`); Python ships `sqlite3`.

---

## Verified facts & figures

* **7 DBs** patched — 4 install seed + 3 user data; **240 distinct tool names**,
  all but 5 translated EN→RU against [`GLOSSARY.md`](../translation/GLOSSARY.md)
  with the Japanese seed as the per-string oracle.
* `apply` round-trip-checked all 7 DBs; `PRAGMA integrity_check` = `ok` on each.
* **2026-05-19, installed into a live CSP:** the user-data `EditImageTool.todb`
  reads back **254/259 Russian** (the 5 untranslated are downloaded tools, see
  below); the seed reads 254/254.

---

## What is NOT covered

* **Downloaded / custom tools.** A user-installed sub-tool keeps its asset name
  (`Concept`, `Pixel_Line`, …); those appear only in the user-data DB, are not
  CSP's stock UI, and are left untranslated. They show up as blank `target`
  rows in `tools.csv` — fill them in if wanted.
* **Texture / material names** shown in Tool Settings (e.g. `Rough paper`) are
  *materials*, not tool nodes — a separate subsystem, not in these DBs.
* CSP rewrites the user-data DB when a tool is edited but **preserves
  `NodeName`**, so the translation persists; a full "reset all sub tools"
  re-seeds it and would need a re-install.
* A CSP update can replace these DBs; re-run `backup → extract → apply →
  install`. The **worksheet and tooling are the durable assets**, not the
  patched DBs.
* macOS / iPad / Android are untested here.

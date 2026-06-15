# CSP Color-Set Translation — VERIFIED METHOD

> **STATUS: WORKING — verified end-to-end.** Last confirmed **2026-06-13** on
> CSP **5.0.0**.
>
> Companion to [`VERIFIED_METHOD.md`](VERIFIED_METHOD.md) (resource bundles),
> [`PLUGIN_TRANSLATION.md`](PLUGIN_TRANSLATION.md), [`TOOL_TRANSLATION.md`](TOOL_TRANSLATION.md),
> and [`MATERIAL_TRANSLATION.md`](MATERIAL_TRANSLATION.md). This file covers the
> **Color Set palette** — a fifth subsystem, with its own file formats, method
> and tool.

---

## TL;DR

The names in CSP's **Color Set** palette and the **Edit color sets** dialog —
`Default color set`, `Additional color set`, … — are **not** applied from the
main UI resource bundles that `batch.py` / `repack.py` translate. The strings
*do* appear in some UI worksheets (e.g. `742DEA58-main-ui`) but patching those
bundles does **not** change what the palette shows at runtime.

They live in two places and **both must be updated**:

* **Install seed** — `<CSP install>/Settings/PAINT/ColorSet/english/*.cls`
* **User profile** — `%APPDATA%/…/CLIPStudioPaintVer*/ColorSet/default.pcs`

The tool is [`src/colorsets.py`](../src/colorsets.py). It is wired into
[`src/lang.py`](../src/lang.py) as the fifth pipeline (`color sets` in
`status`).

---

## Why this is separate from the resource method

CSP's Color Set panel title (`Color Set` → `Цветовой набор`) **is** a normal UI
string in the resource bundles. The **set names in the dropdown** are not — they
are embedded in `.cls` seed files and in the profile's `default.pcs` SQLite DB.

On first run CSP copies the seed into the profile DB, then keeps using the
profile copy — the same seed-vs-user-data trap documented in
[`TOOL_TRANSLATION.md`](TOOL_TRANSLATION.md).

---

## The files

Stock CSP 5.0.0 ships two color sets:

| File | Role |
|---|---|
| `ColorSet/english/001Start.cls` | Default color set (display name + swatches) |
| `ColorSet/english/002.cls` | Additional color set |
| `ColorSet/default.pcs` (user data) | SQLite catalog of loaded sets; references the `.cls` filenames |

The Japanese seed folder (`ColorSet/japanese/`) holds the same files with
cp932-encoded names (`スタートカラーセット`, `追加カラーセット`) and is used
as the per-string oracle during `extract`.

---

## The file formats

### `.cls` — color-set seed (magic `SLCC`)

A small binary container. The display name is stored as UTF-8 (English seed) or
cp932 (Japanese seed), length-prefixed at several offsets (uint16 and uint32
little-endian, plus a raw UTF-8 copy). `apply` replaces every occurrence of the
old name with the translated UTF-8 name and updates the length prefixes.

### `default.pcs` — profile catalog (SQLite 3)

Relevant schema:

* Table **`colorset`** — one row per set. Column **`colorsetname`** is the name
  shown in the dropdown.
* Table **`loadedcolorset`** — maps row ids to seed filenames (`001Start.cls`,
  `002.cls`).

Names may also appear inside the **`colorsetdata`** BLOB columns. Those are
patched through SQL as well (read blob → patch embedded UTF-8 → write back).

---

## Critical rule: never binary-patch the whole `.pcs` file

An early implementation updated `colorsetname` via SQL, then ran a blind
search-and-replace over **the entire `.pcs` bytes**. That corrupts SQLite page
structure (`PRAGMA integrity_check` fails) and CSP fails to load the profile —
symptom: menus render but **all palettes and the canvas vanish**.

**Correct approach:**

1. `UPDATE colorset SET colorsetname=? …` through SQLite.
2. Patch **`colorsetdata` blobs** via SQL (`UPDATE … SET colorsetdata=?`).
3. **Never** rewrite raw bytes outside those SQL operations.

On **`install`**, the live profile DB is **patched in place** — the file is not
replaced wholesale, so the user's swatch data is preserved.

---

## The worksheet is a dictionary

Only **two** stock names exist in CSP 5.0.0:

| `source` | `target` (Russian) |
|---|---|
| `Default color set` | `Набор цветов по умолчанию` |
| `Additional color set` | `Дополнительный набор цветов` |

Worksheet: [`translation/colorsets.csv`](../translation/colorsets.csv) —
columns `source,japanese,target`.

---

## The tooling — `src/colorsets.py`

A 5-command pipeline. Run from the repo root:

```
python src/colorsets.py backup     copy seed .cls + user default.pcs -> langs/english/colorsets/
python src/colorsets.py extract    distinct set names               -> translation/colorsets.csv
# ... translate the `target` column ...
python src/colorsets.py apply      write patched copies             -> langs/russian/colorsets/
python src/colorsets.py install    deploy .cls into seed + patch live default.pcs
python src/colorsets.py restore    copy English .cls back + restore English names in default.pcs
```

Layout under `langs/<language>/colorsets/`:

* `install/english/*.cls` — seed files (copied to Program Files on install)
* `userdata/default.pcs` — reference build of the patched profile DB (used for
  `is_state` fingerprinting; live profile is patched in place on install)

`install` / `restore`:

* Copy `.cls` files into `<CSP>/Settings/PAINT/ColorSet/english/` (needs admin;
  UAC relaunch via `common.ensure_admin`, with `--keep-open` so the elevated
  console stays visible).
* Patch `%APPDATA%/…/ColorSet/default.pcs` in place via SQLite (no admin).
* Refuse to run while CSP is open.

Or use the top-level switcher:

```
python src/lang.py russian    # includes color sets with the other four pipelines
python src/lang.py status     # shows  color sets   RU   (russian)
```

---

## Verified facts

* **2026-06-13, CSP 5.0.0:** after `colorsets.py install`, the Color Set
  dropdown shows **«Набор цветов по умолчанию»** and **«Дополнительный набор
  цветов»**; full UI (tool palette, layers, canvas) loads normally.
* Patched `default.pcs`: `PRAGMA integrity_check` = `ok`.
* Patched `.cls` seed files read back the Russian names; install seed sizes
  grow slightly (664 → 724 bytes for `001Start.cls`) because UTF-8 Cyrillic is
  longer than ASCII.

---

## What is NOT covered

* Custom / downloaded color sets the user adds later — only the two stock sets
  are in the worksheet. Add rows to `colorsets.csv` if new names appear after
  `extract`.
* macOS / iPad / Android are untested.
* A CSP update may replace seed `.cls` files; re-run `backup → extract → apply →
  install`.

---

## See also

* [`src/colorsets.py`](../src/colorsets.py) — module docstring and implementation
* [`scripts/capture_stock.py`](../scripts/capture_stock.py) — runs `colorsets.py backup`
  when capturing stock from a live install
* [`csp-lang-switch.spec`](../csp-lang-switch.spec) — bundles `langs/english/colorsets/` into the exe

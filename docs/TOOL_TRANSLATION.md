# CSP Tool-Palette Translation

> **STATUS: WORKING** — verified with the language switcher on CSP 5.0.4 (2026).
>
> Companion to [`VERIFIED_METHOD.md`](VERIFIED_METHOD.md) (UI resource bundles) and
> [`PLUGIN_TRANSLATION.md`](PLUGIN_TRANSLATION.md) (filter plug-in DLLs). Tool
> palette names are a **third subsystem**: different files, different code
> ([`src/tool_db.py`](../src/tool_db.py)).

---

## TL;DR

Pen, Eraser, Sketch, G-pen, and the rest of the left-hand **Tool palette** are
**not** in the `742DEA58` UI resource pack that `batch.py` / `install.py`
handle. They live in **SQLite `.todb` databases**. Each displayed name is the
`Node.NodeName` column in a `Node` table.

CSP keeps **two copies** of those databases. **Both matter**, but for different
reasons — see [Seed vs. user data](#seed-vs-user-data).

The language switcher hooks tool sync through [`src/lang.py`](../src/lang.py)
(`tool_db.sync_tool_dbs`) whenever you install or restore the Russian community
pack.

---

## Seed vs. user data

| Copy | Path (Windows) | Role |
|------|----------------|------|
| **Install seed** | `<CSP>/Settings/PAINT/Tool/english/EditImageTool.todb` (and siblings under `MixPalette/`, `BrushPreset/`) | Factory defaults. Used when CSP creates a **new** profile. |
| **User data** | `%APPDATA%/CELSYSUserData/CELSYS/CLIPStudioPaintVer*/Tool/EditImageTool.todb` | **Live working copy.** CSP reads this for the palette after first launch. |

On first run CSP copies the seed into user data, then **never re-reads the seed**
for day-to-day editing. Patching only Program Files leaves an existing profile
English. Patching only user data leaves fresh profiles English.

---

## How the language switcher works today

Implementation: [`src/tool_db.py`](../src/tool_db.py), called from
[`src/lang.py`](../src/lang.py) when switching main UI to/from Russian.

Dictionary: [`translation/tools.csv`](../translation/tools.csv) —
`source,japanese,target` — one row per distinct stock tool name (~235 entries).
The `japanese` column is a disambiguation oracle from CSP's Japanese seed; the
switcher only uses `source` → `target`.

### Switching **to Russian**

1. **Backup** (once per machine): copy any not-yet-backed-up live tool DBs into
   `%LOCALAPPDATA%/csp-lang-switch/tools/<install|userdata>/…` before the first
   patch. User-data files are always eligible; install seed is skipped if it
   already looks Russian.
2. **Install seed**: copy the four bundled Russian seed files from
   `versions/<ver>/langs/russian/tools/install/` into Program Files (needs
   admin). This keeps new CSP profiles Russian.
3. **User data**: **patch in place** — for each `NodeName` that appears as
   `source` in `tools.csv`, run
   `UPDATE Node SET NodeName = <target> WHERE _PW_ID = ?`.
   No rows are added or removed; the tool **tree is untouched**.

### Switching **back to English**

1. **User data**: reverse the dictionary (`target` → `source`) and patch in
   place the same way. Custom/downloaded tools whose names are **not** in
   `tools.csv` (e.g. asset names, Japanese download titles) are left as-is.
2. **Install seed**: same reverse patch. Program Files is read-only without
   elevation — the switcher prints a warning and skips those files if admin was
   denied; user data is what CSP actually shows anyway.

The switcher also runs tool sync when main UI is already Russian but tool DBs
may not have been synced yet (`_sync_community_tool_dbs` in `lang.py`).

---

## Why we patch in place (disappearing brushes)

**Do not replace** the live `%APPDATA%` `EditImageTool.todb` with a stock
pre-built file from `langs/russian/tools/userdata/`.

That file is a **fixed factory tree** (~260 nodes). A real profile has **more**
nodes: downloaded sub-tools, copies of downloads placed in Pen / other groups,
extra groups, etc. Replacing the whole file:

- Wipes brushes you added from **Downloads** into custom tool groups (they may
  still appear under Downloads but vanish from Pen and elsewhere).
- Drops downloaded assets until you use **Add from downloads** again.

The correct model is a **label dictionary**: same English name always maps to the
same Russian name, matched by `NodeName` string, ignoring `_PW_ID`. That updates
stock labels (Pen → Перо, G-pen → Перо G) while preserving tree structure, UUID
links, and custom nodes.

```
  WRONG:  shutil.copy(stock_russian.todb → userdata/EditImageTool.todb)
  RIGHT:  UPDATE Node SET NodeName='Перо' WHERE NodeName='Pen'
          (only for names listed in tools.csv)
```

---

## Files involved

| File | Seed path | User-data path | Patched by switcher |
|------|-----------|----------------|---------------------|
| `EditImageTool.todb` | `Tool/english/` | `Tool/` | Yes — in place (userdata); copy (install seed) |
| `UXEditImageTool.todb` | `Tool/english/` | — (seed only) | Copy on Russian install |
| `MixPaletteTool.todb` | `MixPalette/english/` | `MixPalette/` | Yes |
| `BrushPreset.bfps` | `BrushPreset/english/` | `BrushPreset/` | Yes (install copy; userdata patch if `Node` table present) |

Bundled builds live under `versions/<ver>/langs/russian/tools/` (gitignored
Celsys data in dev trees). Only the **`install/`** subtree is copied wholesale;
**`userdata/`** in that bundle is a reference build — the switcher does **not**
deploy it.

---

## What is not covered

* **Downloaded / custom sub-tools** — names come from the asset (`Concept`,
  `さらもちペン`, …). Not in `tools.csv`; stay untranslated. Blank `target` rows
  can be filled if you want them Russian.
* **Tool palette context menus** — Duplicate tool, Import tool, etc. — are in
  the UI resource pack (`742DEA58`), not the `.todb` files.
* **Material folder names** (e.g. «Новая папка» in the Materials palette) — separate
  subsystem; not handled by `tool_db.py`.
* **Variant blob texture names** inside brush data — were handled by the removed
  `tools.py` + `materials.py` pipeline; not part of current switcher scope.
* **macOS / iPad** — untested.

---

## Editing translations

1. Edit `target` in [`translation/tools.csv`](../translation/tools.csv).
2. Re-run the language switcher (Russian) with CSP closed — userdata is
   re-patched from the updated dictionary.
3. For UI strings (menus, dialogs), use `742DEA58-main-ui/unique.csv` and
   `batch.py pack` as usual — see [`TRANSLATION_WORKFLOW.md`](TRANSLATION_WORKFLOW.md).

To regenerate `tools.csv` from a stock English install you need a full
backup/extract pipeline (removed with `src/tools.py` in v43). For routine work,
edit the worksheet directly.

---

## Related code

| Piece | Role |
|-------|------|
| [`src/tool_db.py`](../src/tool_db.py) | Patch/sync logic |
| [`src/lang.py`](../src/lang.py) | Calls `sync_tool_dbs` on Russian/English switch |
| [`translation/tools.csv`](../translation/tools.csv) | EN ↔ RU tool name dictionary |
| `versions/<ver>/langs/russian/tools/install/` | Russian install seed (copied on Russian switch) |

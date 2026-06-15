# csp-lang-switch

A Windows language switcher and localization toolchain for **Clip Studio Paint 5**.
It installs community packs into a live CSP install and provides the tooling to
build and maintain those packs.

CSP has no slots for community languages such as Russian, Ukrainian, or Kazakh.
Its UI strings live in binary resource bundles (GUID-named files, one per
subsystem) and in a few parallel stores. This project parses those assets,
exports their text to editable CSVs, lets us translate, repacks them into files
CSP loads directly, and switches one community pack at a time through CSP's
English slot. The method is **verified end-to-end** — patched files render
correctly inside a running copy of CSP.

## What ships today

**csp-lang-switch** targets **Clip Studio Paint 5.0.0** only. The bundled exe
(`csp-lang-switch.exe`) includes:

| Subsystem | What it covers |
|---|---|
| **Main UI** | 32 shared resource-bundle files under the English slot |
| **Plug-ins** | Filter-menu strings in ~37 `PlugIn/PAINT` DLLs |
| **Tool palette** | Tool / sub-tool names in SQLite DBs (+ brush texture names) |
| **Materials** | Built-in material names in the per-user catalog |
| **Color sets** | Color Set palette dropdown names (`.cls` + `default.pcs`) |

The **Russian** community pack is bundled for all five subsystems. **English
stock** is bundled for restore. Pick Russian or English in the switcher, then
choose **English** as the UI language inside CSP.

Per-machine backups and state live at `%LOCALAPPDATA%\csp-lang-switch\`.
Upgrades from older `%LOCALAPPDATA%\csp-lang\` and `%LOCALAPPDATA%\csp-russian\`
folders are migrated automatically.

## Status

- **Method:** proven and load-tested. See [`docs/VERIFIED_METHOD.md`](docs/VERIFIED_METHOD.md).
- **Shipped switcher:** `csp-lang-switch` (`src/lang.py`) discovers community
  packs under `versions/5.0.0/langs/<language>/` and official CSP languages from
  the live install. It tracks **five pipelines** independently (main UI,
  plug-ins, tools, materials, color sets) and refuses to run when the installed
  CSP build does not match **5.0.0**.
- **Russian pack — main UI:** all **32 content-bearing resource files** are
  packed into `versions/5.0.0/langs/russian/ui/`. Untranslated strings fall
  back to readable English in the English slot. Run `python src/batch.py status`
  for worksheet progress.
- **Russian pack — plug-ins:** all **37 filter DLLs** translated and
  load-tested — see [`docs/PLUGIN_TRANSLATION.md`](docs/PLUGIN_TRANSLATION.md).
- **Russian pack — tool palette:** **240** tool / sub-tool names plus **1,342**
  brush texture names — see [`docs/TOOL_TRANSLATION.md`](docs/TOOL_TRANSLATION.md).
- **Russian pack — materials:** **1,419** distinct built-in material names —
  see [`docs/MATERIAL_TRANSLATION.md`](docs/MATERIAL_TRANSLATION.md).
- **Russian pack — color sets:** both stock Color Set entries translated and
  load-tested on 5.0.0 —
  see [`docs/COLORSET_TRANSLATION.md`](docs/COLORSET_TRANSLATION.md).
- **Workflow:** the end-to-end translation process is a reproducible playbook —
  [`docs/TRANSLATION_WORKFLOW.md`](docs/TRANSLATION_WORKFLOW.md).
- **Out of scope: the CLIP STUDIO launcher** (the separate hub window that
  opens before PAINT). Its visible home screen — Continue Drawing, project
  cards, announcements, notices — is **cloud-served** by Celsys with no
  community-language feed, so most of it is unreachable from local patching. The local
  parts (sidebar / About / Maintenance menus) live in a separate resource
  tree, but a v18 partial-translation attempt crashed the launcher. The
  project intentionally ships PAINT-only.

## Install it / switch languages

### For end users — the bundled exe

Download `csp-lang-switch.exe` and double-click it. A **CustomTkinter** picker
opens (English or Russian interface, auto-detected from Windows). Pick a
community pack or stock English, choose which **subsystems** to switch, and
click **Apply**. UAC fires once when you commit (it needs to write into
`C:\Program Files`). **Close CSP first.**

In CSP itself, set the UI language to **English** — community packs install
into CSP's English resource slot.

The exe also accepts CLI args:

```
csp-lang-switch.exe                  # open the GUI picker (default)
csp-lang-switch.exe russian          # install the Russian community pack (all subsystems)
csp-lang-switch.exe english          # restore stock English everywhere
csp-lang-switch.exe japanese         # copy official Japanese main UI into the English slot;
                                     # plug-ins / tools / materials / color sets stay stock
csp-lang-switch.exe status           # show per-subsystem state
```

In the GUI, only **English** is selectable among official CSP languages today;
other installed languages are listed but marked *not available yet*. The CLI
still accepts any official language folder present in your CSP install (main UI
only — global subsystems restore to stock unless you pick a community pack).

### For developers — the source-tree scripts

The same functionality, run directly from the repo:

```
python src/lang.py                   # GUI picker (needs customtkinter)
python src/lang.py russian           # install the Russian community pack
python src/lang.py english           # restore stock English
python src/lang.py status            # show per-subsystem state
python src/lang.py menu              # console menu (no customtkinter needed)
```

Installing a community pack snapshots the original DLLs / SQLite DBs the first
time it runs, so official-language restore has somewhere to copy back from.
State is cached in `.lang-state.json` and verified against on-disk content
hashes on every run — if anything drifts, the next `status` will show it as
`unknown` rather than lie. GUI language preference is stored in
`.csp-lang-switch-settings.json`.

The per-pipeline scripts ([`install.py`](src/install.py),
[`plugins.py`](src/plugins.py), [`tools.py`](src/tools.py),
[`materials.py`](src/materials.py), [`colorsets.py`](src/colorsets.py)) remain
available for maintenance and for testing each pipeline in isolation — see
[Workflow](#workflow) below.

### Building the exe

```
pip install -r requirements.txt
pyinstaller csp-lang-switch.spec
```

The resulting `dist/csp-lang-switch.exe` bundles the active version tree
(`versions/5.0.0/langs/`: Russian community pack + full English stock for
restore). End users need nothing else installed (no Python, no extra files).

GitHub release notes live in [`release-notes/`](release-notes/). Each file is
bilingual: English first, then `---`, then the same text in Russian. Copy
[`release-notes/TEMPLATE.md`](release-notes/TEMPLATE.md) when cutting a new tag.

### Capturing stock from a CSP install (maintainers)

```
python scripts/capture_stock.py
```

Copies English + Japanese oracle UI, plug-in DLLs, tool DBs, materials,
and color-set files into `versions/5.0.0/langs/`. Requires CSP closed; launch CSP once beforehand
so materials user data exists.

## Layout

| Path | Contents |
|---|---|
| [`docs/`](docs/) | How it works — methods, file inventory, format spec |
| [`src/`](src/) | Python tooling: `lang.py` (top-level switcher); `gui_picker.py` / `gui_i18n.py` (GUI); `batch.py` (orchestrator), `csp5.py`, `repack.py`, `audit.py`, `roundtrip.py`; `install.py`, `plugins.py`, `tools.py`, `materials.py`, `colorsets.py` (per-pipeline deploy); `common.py`, `version.py` |
| [`translation/`](translation/) | Shared Russian worksheets: `manifest.csv`, `GLOSSARY.md`, `plugins.csv`, `tools.csv`, `materials.csv`, `colorsets.csv`, and `files/<short>-<slug>/` |
| `versions/<csp-version>/langs/` | Per-build language trees (gitignored). Active target: **5.0.0**. Archive: **5.0.4** |
| [`csp-lang-switch.spec`](csp-lang-switch.spec) | PyInstaller spec for the end-user exe |
| [`TODO.md`](TODO.md) | Current task |

## Key files

- [`docs/VERIFIED_METHOD.md`](docs/VERIFIED_METHOD.md) — **authoritative** record of what works and how (the binary parse/repack method).
- [`docs/PLUGIN_TRANSLATION.md`](docs/PLUGIN_TRANSLATION.md) — the parallel method for the Filter-menu plug-in DLLs (`plugins.py`).
- [`docs/TOOL_TRANSLATION.md`](docs/TOOL_TRANSLATION.md) — the parallel method for the Tool-palette SQLite DBs (`tools.py`).
- [`docs/MATERIAL_TRANSLATION.md`](docs/MATERIAL_TRANSLATION.md) — the parallel method for the material-catalog SQLite DB (`materials.py`).
- [`docs/COLORSET_TRANSLATION.md`](docs/COLORSET_TRANSLATION.md) — the parallel method for the Color Set palette names (`.cls` + `default.pcs`, `colorsets.py`).
- [`docs/TRANSLATION_WORKFLOW.md`](docs/TRANSLATION_WORKFLOW.md) — reproducible playbook for translating a file, CSP version, or language.
- [`docs/FILE_INVENTORY.md`](docs/FILE_INVENTORY.md) — the 39 shared resource files and what each covers.
- [`docs/CSP5_format_spec.md`](docs/CSP5_format_spec.md) — pre-implementation brief; **stale** where it disagrees with `VERIFIED_METHOD.md`.
- [`translation/manifest.csv`](translation/manifest.csv) — the machine-readable file list `batch.py` drives the pipeline from.
- [`translation/files/742DEA58-main-ui/strings.csv`](translation/files/742DEA58-main-ui/strings.csv) — the main-UI worksheet (`key, source, target`); translate the `target` column only.
- [`translation/GLOSSARY.md`](translation/GLOSSARY.md) — canonical Russian terms for the most frequent words, shared across all Russian worksheets.

## Workflow

Run tooling from the repo root. `src/batch.py` orchestrates the whole pipeline
per file, addressed by short GUID or slug (`742DEA58` or `main-ui`):

```
python src/batch.py status              # progress over every file
python src/batch.py export   <id>       # extract a worksheet (export-all for all)
python src/batch.py dedupe   <id>       # build the unique-strings list
# ... translate the target column of unique.csv ...
python src/batch.py join     <id>       # merge translations back
python src/batch.py pack     <id>       # repack -> langs/russian/ui/, with round-trip check
python src/batch.py pack     <id> --language ukrainian
python src/batch.py audit    <id>       # consistency audit
```

The full translation playbook is [`docs/TRANSLATION_WORKFLOW.md`](docs/TRANSLATION_WORKFLOW.md);
the binary method, install steps and slot strategy are in
[`docs/VERIFIED_METHOD.md`](docs/VERIFIED_METHOD.md).

For a live install, prefer `src/lang.py` — it switches all five subsystems and
tracks state. The lower-level `src/install.py` handles main UI only:

```
python src/install.py russian           # install the Russian UI build onto the English slot
python src/install.py english           # restore the original English
python src/install.py                   # show what is currently installed
```

### Plug-in filters

The Filter menu's plug-in entries live in DLLs, not the resource bundles, and
are handled by a parallel tool — [`src/plugins.py`](src/plugins.py):

```
python src/plugins.py backup            # save the original PlugIn/PAINT DLLs
python src/plugins.py extract           # -> translation/plugins.csv
# ... translate the target column ...
python src/plugins.py apply             # -> langs/russian/plugins/
python src/plugins.py apply --language ukrainian
python src/plugins.py install           # deploy into the live CSP install
```

The method and format are documented in
[`docs/PLUGIN_TRANSLATION.md`](docs/PLUGIN_TRANSLATION.md).

### Tool palette

The left-hand tool / sub-tool names live in SQLite databases in the CSP
install, not the resource bundles, and are handled by another parallel tool —
[`src/tools.py`](src/tools.py):

```
python src/tools.py backup              # save the original tool DBs
python src/tools.py extract             # -> translation/tools.csv
# ... translate the target column ...
python src/tools.py apply               # -> langs/russian/tools/
python src/tools.py apply --language ukrainian
python src/tools.py install             # deploy into the live CSP install
```

The method and format are documented in
[`docs/TOOL_TRANSLATION.md`](docs/TOOL_TRANSLATION.md).

### Material catalog

The built-in material names (paper textures, tones, patterns, 3D, balloons,
frame templates) live in a per-user SQLite catalog — handled by another
parallel tool — [`src/materials.py`](src/materials.py):

```
python src/materials.py backup          # save the original catalog DB
python src/materials.py extract         # -> translation/materials.csv
# ... translate the target column ...
python src/materials.py apply           # -> langs/russian/materials/
python src/materials.py apply --language ukrainian
python src/materials.py install         # deploy into the live CSP user data
```

The method and format are documented in
[`docs/MATERIAL_TRANSLATION.md`](docs/MATERIAL_TRANSLATION.md).

### Color sets

The Color Set palette dropdown names live in `.cls` seed files and the
profile's `default.pcs` SQLite DB — handled by another parallel tool —
[`src/colorsets.py`](src/colorsets.py):

```
python src/colorsets.py backup          # save the original .cls + default.pcs
python src/colorsets.py extract         # -> translation/colorsets.csv
# ... translate the target column ...
python src/colorsets.py apply           # -> langs/russian/colorsets/
python src/colorsets.py apply --language ukrainian
python src/colorsets.py install         # deploy .cls + patch live default.pcs
```

The method and format are documented in
[`docs/COLORSET_TRANSLATION.md`](docs/COLORSET_TRANSLATION.md).

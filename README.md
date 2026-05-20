# csp-translation

Translating the **Clip Studio Paint 5** user interface into **Russian** by
patching its binary resource files.

CSP has no Russian localization. Its UI strings live in binary resource bundles
(GUID-named files, one per subsystem). This project parses those bundles,
exports their text to editable CSVs, lets us translate, and repacks them into
files CSP loads directly. The method is **verified end-to-end** — a patched file
has rendered correctly inside a running copy of CSP.

## Status

- **Method:** proven and load-tested. See [`docs/VERIFIED_METHOD.md`](docs/VERIFIED_METHOD.md).
- **Translation:** all **32 content-bearing files** translated to Russian,
  packed into `russian/`, and round-trip-verified (32/32 byte-for-byte). The
  consistency audit is clean apart from known false positives (brand names, CC
  license names, shader code, internal config keys). Run
  `python src/batch.py status` for live progress.
- **Plug-in filters:** the new Filter menu (categories, filter names, dialog
  parameters) lives in ~37 plug-in DLLs, not the bundles. All 37 are translated
  and load-tested — see [`docs/PLUGIN_TRANSLATION.md`](docs/PLUGIN_TRANSLATION.md).
- **Tool palette:** the left-hand tool / sub-tool names live in SQLite
  databases — both an install seed and a per-user working copy — not the
  bundles. 240 distinct names are translated and installed into both; the
  texture / pattern names baked into each brush's `Variant` blobs (1,342) are
  patched too — see [`docs/TOOL_TRANSLATION.md`](docs/TOOL_TRANSLATION.md).
- **Material catalog:** the built-in materials (paper textures, tones,
  patterns, 3D, balloons, frame templates) live in a per-user SQLite catalog.
  1,419 distinct names translated and installed —
  see [`docs/MATERIAL_TRANSLATION.md`](docs/MATERIAL_TRANSLATION.md).
- **Workflow:** the end-to-end translation process is a reproducible playbook —
  [`docs/TRANSLATION_WORKFLOW.md`](docs/TRANSLATION_WORKFLOW.md).
- **Out of scope: the CLIP STUDIO launcher** (the separate hub window that
  opens before PAINT). Its visible home screen — Continue Drawing, project
  cards, announcements, notices — is **cloud-served** by Celsys with no
  Russian feed, so most of it is unreachable from local patching. The local
  parts (sidebar / About / Maintenance menus) live in a separate resource
  tree, but a v18 partial-translation attempt crashed the launcher. The
  project intentionally ships PAINT-only.

## Install it / undo it

One command switches every subsystem (main UI, plug-in filters, tool palette,
material catalog) between Russian and the original install:

```
python src/lang.py russian        # show Russian everywhere
python src/lang.py original       # restore the original install
python src/lang.py status         # show what is installed right now
```

`russian` snapshots the original DLLs / SQLite DBs the first time it runs, so
`original` always has somewhere to copy back from. State is cached in
`.lang-state.json` and verified against on-disk content hashes on every run, so
if anything drifts the next `status` will show it as `unknown` rather than lie.

Three of the four pipelines write into `C:\Program Files` and need
Administrator rights; `lang.py` self-elevates once via UAC at the start of a
state-changing command. Close CSP before switching.

The per-pipeline scripts ([`install.py`](src/install.py),
[`plugins.py`](src/plugins.py), [`tools.py`](src/tools.py),
[`materials.py`](src/materials.py)) remain available for maintenance and for
testing each pipeline in isolation — see [Workflow](#workflow) below.

## Layout

| Path | Contents |
|---|---|
| [`docs/`](docs/) | How it works — methods, file inventory, format spec |
| [`src/`](src/) | Python tooling: `lang.py` (top-level language switcher); `batch.py` (orchestrator), `csp5.py`, `repack.py`, `audit.py`, `roundtrip.py`; `install.py` (deploy a build into CSP), `plugins.py` (filter-DLL pipeline), `tools.py` (tool-palette pipeline), `materials.py` (material-catalog pipeline) |
| [`translation/`](translation/) | `manifest.csv` (file list), `GLOSSARY.md`, `plugins.csv` (filter-DLL worksheet), `tools.csv` (tool-palette worksheet), `materials.csv` (material-catalog worksheet), and `files/<short>-<slug>/` — one worksheet folder per resource file |
| `resource/` | Original CSP resource binaries, 12 languages — gitignored (copyrighted, large) |
| `russian/` | Output of `batch.py pack` — the Russian resource build — gitignored (regenerable) |
| `plugins/`, `russian-plugins/` | Original / patched filter-DLLs, managed by `plugins.py` — gitignored |
| `tools/`, `russian-tools/` | Original / patched tool-palette SQLite DBs, managed by `tools.py` — gitignored |
| `materials/`, `russian-materials/` | Original / patched material-catalog SQLite DB, managed by `materials.py` — gitignored |
| [`TODO.md`](TODO.md) | Current task |

## Key files

- [`docs/VERIFIED_METHOD.md`](docs/VERIFIED_METHOD.md) — **authoritative** record of what works and how (the binary parse/repack method).
- [`docs/PLUGIN_TRANSLATION.md`](docs/PLUGIN_TRANSLATION.md) — the parallel method for the Filter-menu plug-in DLLs (`plugins.py`).
- [`docs/TOOL_TRANSLATION.md`](docs/TOOL_TRANSLATION.md) — the parallel method for the Tool-palette SQLite DBs (`tools.py`).
- [`docs/MATERIAL_TRANSLATION.md`](docs/MATERIAL_TRANSLATION.md) — the parallel method for the material-catalog SQLite DB (`materials.py`).
- [`docs/TRANSLATION_WORKFLOW.md`](docs/TRANSLATION_WORKFLOW.md) — reproducible playbook for translating a file, CSP version, or language.
- [`docs/FILE_INVENTORY.md`](docs/FILE_INVENTORY.md) — the 39 shared resource files and what each covers.
- [`docs/CSP5_format_spec.md`](docs/CSP5_format_spec.md) — pre-implementation brief; **stale** where it disagrees with `VERIFIED_METHOD.md`.
- [`translation/manifest.csv`](translation/manifest.csv) — the machine-readable file list `batch.py` drives the pipeline from.
- [`translation/files/742DEA58-main-ui/strings.csv`](translation/files/742DEA58-main-ui/strings.csv) — the main-UI worksheet (`key, source, target`); translate the `target` column only.
- [`translation/GLOSSARY.md`](translation/GLOSSARY.md) — canonical Russian terms for the most frequent words, shared across all files.

## Workflow

Run tooling from the repo root. `src/batch.py` orchestrates the whole pipeline
per file, addressed by short GUID or slug (`742DEA58` or `main-ui`):

```
python src/batch.py status              # progress over every file
python src/batch.py export   <id>       # extract a worksheet (export-all for all)
python src/batch.py dedupe   <id>       # build the unique-strings list
# ... translate the target column of unique.csv ...
python src/batch.py join     <id>       # merge translations back
python src/batch.py pack     <id>       # repack -> russian/, with round-trip check
python src/batch.py audit    <id>       # consistency audit
```

The full translation playbook is [`docs/TRANSLATION_WORKFLOW.md`](docs/TRANSLATION_WORKFLOW.md);
the binary method, install steps and slot strategy are in
[`docs/VERIFIED_METHOD.md`](docs/VERIFIED_METHOD.md).

Deploy a build into a live CSP install — and switch languages back — without
reinstalling the app, with `src/install.py`:

```
python src/install.py russian           # install the Russian build onto CSP
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
python src/plugins.py apply             # -> russian-plugins/
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
python src/tools.py apply               # -> russian-tools/
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
python src/materials.py apply           # -> russian-materials/
python src/materials.py install         # deploy into the live CSP user data
```

The method and format are documented in
[`docs/MATERIAL_TRANSLATION.md`](docs/MATERIAL_TRANSLATION.md).

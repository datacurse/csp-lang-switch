# CSP 4.2.0 — stock and Russian build data

This folder holds the **4.2.0** language snapshots and Russian community build.

**Status:** active and **verified** (2026-06). Russian UI, material-folder tree,
filter plug-ins, and tool-palette names work on a clean 4.2.0 install. Bundled
in `csp-lang-switch.exe` alongside the 5.x versions.

Layout:

```
langs/
  english/    stock English UI + plugins
  japanese/   translation oracle (ui/)
  russian/    patched Russian community build (ui + plugins + tools/install)
```

Capture from a live 4.2.0 install (CSP closed, UI language English):

```
python scripts/capture_stock.py --version 4.2.0
python src/batch.py --version 4.2.0 pack-all
python src/plugins.py --version 4.0.0 harvest   # if plugins.csv targets empty
python src/plugins.py --version 4.2.0 apply --yes
```

Then build the tool-palette install seed from the live 4.2.0 `Settings/PAINT`
tree (copy `Tool/english/*.todb`, `MixPalette/english/*.todb`,
`BrushPreset/english/*.bfps` into `langs/russian/tools/install/`, patch with
`translation/tools.csv` via `tool_db.patch_node_names`). See
[`docs/TOOL_TRANSLATION.md`](../../docs/TOOL_TRANSLATION.md).

`pack-all` re-exports keys from the captured stock and maps translations by
English `source` text, so worksheets built for another CSP version (e.g. 5.0.4)
still pack correctly for 4.2.0. Key-specific rows in `strings.csv` apply only
when their `source` column matches this version's stock — otherwise CSP can
crash on launch (same rule as 5.0.2).

### Window / Filter menu strings (Tool, Material, Effect)

On 4.2.0 these menu labels use **different resource keys** than on 5.x:

| Label    | 4.2.0 key       | 5.0.x key       |
|----------|-----------------|-----------------|
| Tool     | `13/1/1196#0`   | `13/1/1197#0`   |
| Material | `13/1/1253#0`   | `13/1/1254#0`   |
| Effect   | `13/1/1394#0`   | `13/1/1396#0`   |

The material-palette guard (`_material_folder_sources()` in `src/batch.py`)
blocks translating English category names such as `Tool`, `Material`, and
`Effect` in the main UI, because those strings also label nodes in `7F9F9530`
block 6. On 5.x, explicit key whitelists (`MATERIAL_NAME_UI_KEYS`) were enough.
On 4.x the keys drift, so `batch.py` also exempts exact `Tool` / `Material` /
`Effect` sources in the main UI file (`742DEA58`) and maps them from
`unique.csv` (`Инструмент`, `Материал`, `Эффект`). See
[`docs/VERIFIED_METHOD.md`](../../docs/VERIFIED_METHOD.md) → material-folder guard.

Copyrighted Celsys data — gitignored, not redistributed.

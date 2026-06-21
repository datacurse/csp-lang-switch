# CSP 5.0.2 — stock and Russian build data

This folder holds the **5.0.2** language snapshots and Russian community build.

**Status:** active and **verified** (2026-06). Russian UI, material-folder tree,
filter plug-ins, and tool-palette names work on a clean 5.0.2 install. Bundled
in `csp-lang-switch.exe` alongside `5.0.0` and `5.0.4`.

Layout:

```
langs/
  english/    stock English UI + plugins
  japanese/   translation oracle (ui/)
  russian/    patched Russian community build (ui + plugins)
```

Capture from a live 5.0.2 install (CSP closed, UI language English):

```
python scripts/capture_stock.py --version 5.0.2
python src/batch.py --version 5.0.2 pack-all
python src/plugins.py --version 5.0.0 harvest   # if plugins.csv targets empty
python src/plugins.py --version 5.0.2 apply --yes
```

Then build the tool-palette install seed from the live 5.0.2 `Settings/PAINT`
tree (copy `Tool/english/*.todb`, `MixPalette/english/*.todb`,
`BrushPreset/english/*.bfps` into `langs/russian/tools/install/`, patch with
`translation/tools.csv` via `tool_db.patch_node_names`). See
[`docs/TOOL_TRANSLATION.md`](../../docs/TOOL_TRANSLATION.md).

`pack-all` re-exports keys from the captured stock and maps translations by
English `source` text, so worksheets built for another CSP version (e.g. 5.0.4)
still pack correctly for 5.0.2. Key-specific rows in `strings.csv` are applied
only when their `source` column matches this version's stock — otherwise CSP can
crash on launch (5.0.2 license/about text differs from 5.0.4 in ~102 rows; those
stay English until re-exported from 5.0.2 stock).

Copyrighted Celsys data — gitignored, not redistributed.

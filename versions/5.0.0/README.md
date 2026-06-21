# CSP 5.0.0 — stock and Russian build data

Language snapshots and community builds for **Clip Studio Paint Ver. 5.0.0**.

**Status:** active and **verified** (2026-06). Russian UI, material-folder tree,
filter plug-ins, and tool-palette names work on a clean 5.0.0 install. Bundled
in `csp-lang-switch.exe` alongside `5.0.2` and `5.0.4`.

```
langs/
  english/    stock English (ui, plugins)
  japanese/   translation oracle (ui/)
  russian/    patched Russian community build (ui + plugins + tools/install)
```

Capture from a live 5.0.0 install (CSP closed, UI language English):

```
python scripts/capture_stock.py --version 5.0.0
python src/batch.py --version 5.0.0 pack-all
python src/plugins.py --version 5.0.0 harvest   # if plugins.csv targets empty
python src/plugins.py --version 5.0.0 apply --yes
```

Then build the tool-palette install seed from the live 5.0.0 `Settings/PAINT`
tree (copy `Tool/english/*.todb`, `MixPalette/english/*.todb`,
`BrushPreset/english/*.bfps` into `langs/russian/tools/install/`, patch with
`translation/tools.csv` via `tool_db.patch_node_names`). See
[`docs/TOOL_TRANSLATION.md`](../../docs/TOOL_TRANSLATION.md).

`pack-all` re-exports keys from the captured stock and maps translations by
English `source` text. Key-specific rows in `strings.csv` apply only when their
`source` matches this version's stock (same rule as 5.0.2 — ~102 license/about
strings may stay English until re-exported from 5.0.0 stock).

Gitignored — copyrighted Celsys data.

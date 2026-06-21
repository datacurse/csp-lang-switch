# CSP 4.0.0 — stock and Russian build data

This folder holds the **4.0.0** language snapshots and Russian community build.

**Status:** active and **verified** (2026-06). Russian UI, material-folder tree,
and filter plug-ins work on a clean 4.0.0 install. Bundled in
`csp-lang-switch.exe` alongside 4.2.0 and the 5.x versions.

Layout:

```
langs/
  english/    stock English UI + plugins
  japanese/   translation oracle (ui/)
  russian/    patched Russian community build (ui + plugins + tools/install)
```

Capture from a live 4.0.0 install (CSP closed, UI language English):

```
python scripts/capture_stock.py --version 4.0.0
python scripts/export_400_gaps.py
python scripts/fill_400_gaps.py
python scripts/apply_400_gaps.py
python src/batch.py join-all
python src/batch.py --version 4.0.0 pack-all
python src/plugins.py --version 4.0.0 backup --yes
python src/plugins.py --version 4.0.0 apply --yes
```

Then build the tool-palette install seed from the live 4.0.0 `Settings/PAINT`
tree (copy `Tool/english/*.todb`, `MixPalette/english/*.todb`,
`BrushPreset/english/*.bfps` into `langs/russian/tools/install/`, patch with
`translation/tools.csv` via `tool_db.patch_node_names`). See
[`docs/TOOL_TRANSLATION.md`](../../docs/TOOL_TRANSLATION.md).

`pack-all` re-exports keys from the captured stock and maps translations by
English `source` text, so worksheets built for another CSP version (e.g. 5.0.4)
still pack correctly for 4.0.0. The `export_400_gaps` / `fill_400_gaps` /
`apply_400_gaps` steps add strings that exist only in 4.0.0.

### Resources not in 4.0.0 stock

The shared manifest lists **32** UI targets, but CSP 4.0.0 ships fewer resource
files than 4.2.0 / 5.x. Notably **`6FFACA71` (companion-mode)** has a
worksheet but **no English stock file** under `versions/4.0.0/langs/english/ui/`.
That is expected — the feature arrived in a later CSP build.

When running the switcher **from source**, `lang.py` repacks stale worksheets
before install. It now **skips** manifest entries whose English stock is missing
for the selected version, so a stale `6FFACA71` worksheet cannot abort the
whole switch with `repack failed for 6FFACA71-companion-mode`. Install already
ignored that file (`N file(s) not in this build keep their current contents`).

### Window / Filter menu strings (Tool, Material, Effect)

On 4.0.0 these use different keys than on 5.x (same pattern as 4.2.0):

| Label    | 4.0.0 key       | 5.0.x key       |
|----------|-----------------|-----------------|
| Tool     | `13/1/1198#0`   | `13/1/1197#0`   |
| Material | `13/1/1255#0`   | `13/1/1254#0`   |
| Effect   | `13/1/1395#0`   | `13/1/1396#0`   |

See [`docs/VERIFIED_METHOD.md`](../../docs/VERIFIED_METHOD.md) → `MATERIAL_UI_SOURCES`.

Copyrighted Celsys data — gitignored, not redistributed.

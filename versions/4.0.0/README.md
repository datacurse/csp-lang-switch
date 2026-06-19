# CSP 4.0.0 — stock and Russian build data

This folder holds the **4.0.0** language snapshots and Russian community build.

**Status:** active. Bundled in `csp-lang-switch.exe` alongside the other supported versions.

Layout:

```
langs/
  english/    stock English UI + plugins
  japanese/   translation oracle (ui/)
  russian/    patched Russian community build (ui + plugins)
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

`pack-all` re-exports keys from the captured stock and maps translations by
English `source` text, so worksheets built for another CSP version (e.g. 5.0.0)
still pack correctly for 4.0.0. The `export_400_gaps` / `fill_400_gaps` /
`apply_400_gaps` steps add strings that exist only in 4.0.0.

Copyrighted Celsys data — gitignored, not redistributed.

# CSP 5.0.4 — stock and Russian build data

This folder holds the **5.0.4** language snapshots and Russian community build.

**Status:** active. Bundled in `csp-lang-switch.exe` alongside `5.0.0`.

Layout:

```
langs/
  english/    stock English UI + plugins
  japanese/   translation oracle (ui/)
  russian/    patched Russian community build (ui + plugins)
```

Capture from a live 5.0.4 install (CSP closed, UI language English):

```
python scripts/capture_stock.py --version 5.0.4
python src/batch.py --version 5.0.4 pack-all
python src/plugins.py --version 5.0.0 harvest   # if plugins.csv targets empty
python src/plugins.py --version 5.0.4 apply --yes
```

`pack-all` re-exports keys from the captured stock and maps translations by
English `source` text, so worksheets built for another CSP version (e.g. 5.0.0)
still pack correctly for 5.0.4.

Copyrighted Celsys data — gitignored, not redistributed.

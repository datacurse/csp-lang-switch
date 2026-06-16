# CSP 4.2.0 — stock and build data (skeleton)

Language snapshots and the Russian community build for **Clip Studio Paint
Ver. 4.2.0** (forum source:
[4.2.0 thread](https://vk.com/wall-200668271_44094)).

**Status:** infrastructure skeleton only — no data captured yet. The active
build target is still `versions/5.0.0/` (`ACTIVE_VERSION` in `src/version.py`
and both `.spec` files). Flip those to `4.2.0` once this tree is populated and
verified.

Populate with `scripts/capture_stock.py` from a local English CSP 4.2.0 install:

```
langs/
  english/    stock English (ui, plugins)
  japanese/   translation oracle (ui/)
  russian/    patched Russian community build (after pack)
```

The translation worksheets stay shared at `translation/` — source text is
stable across builds, so `batch.py dedupe` carries every existing translation
over by `source`; only genuinely new/changed strings re-export with an empty
`target`. See [`docs/TRANSLATION_WORKFLOW.md`](../../docs/TRANSLATION_WORKFLOW.md)
→ "Another CSP version".

Gitignored — copyrighted Celsys data (`versions/*/langs/`).

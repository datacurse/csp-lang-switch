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
- **Translation:** `742DEA58` (main UI, 9,368 strings) fully translated to
  Russian and consistency-audited. The other ~31 content-bearing files are not
  done yet.
- **Workflow:** the end-to-end translation process is a reproducible playbook —
  [`docs/TRANSLATION_WORKFLOW.md`](docs/TRANSLATION_WORKFLOW.md).

## Layout

| Path | Contents |
|---|---|
| [`docs/`](docs/) | How it works — method, file inventory, format spec |
| [`src/`](src/) | Python tooling (`csp5.py`, `repack.py`, …); `src/legacy/` = reference-only |
| [`translation/`](translation/) | The translation worksheet, glossary, word-frequency data |
| `resource/` | Original CSP resource binaries, 12 languages — gitignored (copyrighted, large) |
| `russian/` | Output of `repack.py apply` — the Russian build — gitignored (regenerable) |
| [`TODO.md`](TODO.md) | Current task |

## Key files

- [`docs/VERIFIED_METHOD.md`](docs/VERIFIED_METHOD.md) — **authoritative** record of what works and how (the binary parse/repack method).
- [`docs/TRANSLATION_WORKFLOW.md`](docs/TRANSLATION_WORKFLOW.md) — reproducible playbook for translating a file, CSP version, or language.
- [`docs/FILE_INVENTORY.md`](docs/FILE_INVENTORY.md) — the 39 shared resource files and what each covers.
- [`docs/CSP5_format_spec.md`](docs/CSP5_format_spec.md) — pre-implementation brief; **stale** where it disagrees with `VERIFIED_METHOD.md`.
- [`translation/english_742DEA58_strings.csv`](translation/english_742DEA58_strings.csv) — main-UI worksheet (`key, source, target`); translate the `target` column only.
- [`translation/GLOSSARY.md`](translation/GLOSSARY.md) — canonical Russian terms for the most frequent words.

## Workflow

Run tooling from the repo root.

```
python src/repack.py export <resource_file> strings.csv --kind text   # extract
# ... edit the target column of strings.csv (UTF-8) ...
python src/repack.py apply  <resource_file> strings.csv <patched_file> # repack
```

Full procedure, install steps, and the slot strategy are in
[`docs/VERIFIED_METHOD.md`](docs/VERIFIED_METHOD.md).

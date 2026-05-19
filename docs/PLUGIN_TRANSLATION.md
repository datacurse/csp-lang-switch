# CSP Filter Plug-in Translation — VERIFIED METHOD

> **STATUS: WORKING — verified end-to-end.** Last confirmed **2026-05-19**.
>
> Companion to [`VERIFIED_METHOD.md`](VERIFIED_METHOD.md). That file covers the
> **resource bundles**; this one covers the **filter plug-in DLLs** — a separate
> subsystem, with a separate file format, method, and tool.

---

## TL;DR

CSP's new **Filter menu** — the categories (Blur, Correction, Distort, Effect,
Render, Sharpen), every filter name, and the filter dialog parameters — is **not
in the resource bundles** that `batch.py` / `repack.py` translate. It lives
inside the **~37 filter plug-in DLLs** in `<CSP install>/PlugIn/PAINT/`.

Each DLL stores its UI text as a **standard Windows `RT_STRING` resource**, with
one entry per language and **no Russian**. They are translated by overwriting
the **English** entry with Russian via the Windows `UpdateResource` API. The
tool is [`src/plugins.py`](../src/plugins.py); the method is **verified
end-to-end** — the patched DLLs render the whole Russian Filter menu in a
running copy of CSP.

---

## Why this is separate from the resource method

CSP's `Filter` menu mixes **two** filter systems:

* **Legacy filters** — ordinary strings inside the `742DEA58` resource bundle.
  Handled by the normal resource pipeline ([`TRANSLATION_WORKFLOW.md`](TRANSLATION_WORKFLOW.md)).
* **Plug-in filters** — the `Blur` / `Correction` / `Distort` / `Effect` /
  `Render` / `Sharpen` categories. Each filter is its own DLL in `PlugIn/PAINT/`
  (`GaussBlur.dll`, `MotionBlur.dll`, …) carrying its **own** UI strings.

CELSYS localized the plug-ins into German, Spanish, French, Chinese, Japanese,
Korean, Portuguese, Thai and Indonesian — but **not Russian**. So the plug-in
filter menu stays English in the Russian build until the DLLs are patched.

`CLIPStudioPaint.exe` is **not** involved — the category words do not appear in
the exe at all. Every plug-in-menu string comes from a plug-in DLL.

---

## The file format

Each plug-in DLL has a standard Windows **`RT_STRING`** resource in its `.rsrc`
section — no custom format, no reverse-engineering.

* Resource tree: `RT_STRING` → block id → **`LANG` id**. One `LANG` entry per
  language CSP ships, and **no `1049` (Russian)**:

  | LANG | Language | LANG | Language |
  |--:|---|--:|---|
  | 7 | German | 1041 | Japanese |
  | 9 | **English** | 1042 | Korean |
  | 10 | Spanish | 1046 | Portuguese |
  | 12 | French | 1054 | Thai |
  | 1028 | Chinese (Traditional) | 1057 | Indonesian |
  | 2052 | Chinese (Simplified) | | |

* A block is **16 consecutive strings**, each `[uint16 length][UTF-16LE text]`,
  the length in UTF-16 code units. Empty slots are a length of 0.

* Slot order inside a filter plug-in's block: **`[category name]`,
  `[filter name]`, `[parameter labels…]`**. A plug-in uses one or two blocks.

---

## The method

Overwrite the **English (`LANG 9`)** entry with Russian — the same
"english slot = our translation" convention the resource method uses
([`VERIFIED_METHOD.md`](VERIFIED_METHOD.md) → "Slot strategy"). CSP set to
English then serves the now-Russian strings.

Writing is done with the Windows **`UpdateResource`** API (`kernel32`, via
`ctypes`): it rebuilds the `.rsrc` section and absorbs the size growth (Cyrillic
UTF-16 text is longer than English). The PE stays valid.

### The category-consistency rule

The 6 category headers come from the plug-ins too — each plug-in's slot #1 is
its category name, and CSP groups filters by it. A header is only translated
when **every plug-in in that category** gets the **identical** Russian name.
The fixed map:

| English | Russian | English | Russian |
|---|---|---|---|
| Blur | Размытие | Effect | Эффект |
| Correction | Коррекция | Render | Рендеринг |
| Distort | Искажение | Sharpen | Резкость |

Patch only some of a category's plug-ins and CSP shows that category twice.

---

## The tooling — `src/plugins.py`

A 5-command pipeline, the plug-in counterpart of `batch.py`. Run from the repo
root:

```
python src/plugins.py backup     copy PlugIn/PAINT/*.dll  -> plugins/
python src/plugins.py extract    English strings          -> translation/plugins.csv
# ... translate the `target` column of plugins.csv ...
python src/plugins.py apply      write patched DLLs        -> russian-plugins/
python src/plugins.py install    copy patched DLLs into the live CSP install
python src/plugins.py restore    copy the originals back into the live install
```

* **`plugins/`** — the original DLLs; the repo's only backup of the plug-in
  originals. Gitignored.
* **`russian-plugins/`** — the patched build, output of `apply`. Gitignored.
* **`translation/plugins.csv`** — the worksheet (`key,source,target`); `key` is
  `<dll>:<block>:<slot>`. Tracked in git. Edit `target`, re-run `apply`.
* `install` / `restore` write into `C:\Program Files`, self-elevate via a UAC
  prompt (reusing `install.py`), and refuse to run while CSP is open.

Safeguards: `apply` round-trip-checks every DLL (re-reads it and asserts the
English entry equals what it wrote). `backup` never overwrites a saved original
and skips any live DLL whose English entry already holds Cyrillic — a
previously-patched DLL is not a clean original.

`extract` / `apply` need **`pefile`** (`pip install pefile`); `install` /
`restore` are standard-library only.

---

## Verified facts & figures

* **37 plug-in DLLs** in `PlugIn/PAINT/`; **284 translatable strings**, **183
  unique**. 73 strings were reused verbatim from the `742DEA58` main-UI
  worksheet; the rest were translated against
  [`GLOSSARY.md`](../translation/GLOSSARY.md).
* The extract also covers the **PSD / PSB / PDF import-export dialogs**
  (`ExportPSD.dll`, `ImportPDFX.dll`, …), not only filters.
* A handful of records are non-translatable identifiers, kept verbatim (`pdf`,
  `psb|psb`, `psd|psd`, the `clipstudio.module.…` plug-in id).
* **2026-05-19, load-tested in CSP:** the full 37-DLL patched build was
  installed and CSP rendered the entire Filter menu — categories, filter names,
  and dialog parameters — correctly in Russian.

---

## What is NOT covered

* The **legacy** filter entries are resource-bundle strings — translated by the
  resource pipeline, not this one.
* A CSP update can replace the plug-in DLLs and reset them to English; re-run
  `backup → extract → apply → install` after an update. The **worksheet and
  tooling are the durable assets**, not the patched DLLs.
* macOS / iPad / Android plug-ins are untested here.

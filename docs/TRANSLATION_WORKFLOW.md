# CSP Translation Workflow — reproducible playbook

> How a full, consistent translation of a CSP resource file was produced.
> Companion to [`VERIFIED_METHOD.md`](VERIFIED_METHOD.md): that doc covers the
> **binary** side (parse / edit CSV / repack); **this** doc covers the
> **translation production** side — turning an English worksheet into a good,
> consistent translation at scale.
>
> First executed 2026-05-19: `742DEA58-…` (main UI), English → Russian,
> 9,368 string records. Follow this to translate another file, another CSP
> version, or another language **without reinventing the process.**

---

## The pipeline at a glance

```
export ─► dedupe ─► glossary ─► translate (parallel chunks) ─► join
       ─► special cases ─► repack + round-trip ─► consistency audit ─► fix ─► install
```

The durable assets are the **tooling** (`src/`), the **glossary**, and this
doc. The patched binary itself is disposable — regenerable and version-specific.

---

## Step 0 — Pick the target file(s)

`742DEA58-…` is the main UI (~9,368 strings). A full UI translation means
repeating this for the ~32 content-bearing shared files — see
[`FILE_INVENTORY.md`](FILE_INVENTORY.md). The workflow below is identical for
every file; do them one at a time.

## Step 1 — Export the worksheet

```
python src/repack.py export <resource_file> translation/<name>_strings.csv --kind text
```

Produces a `key,source,target` CSV. **`key` is version-specific — never edit
it.** The CSV is **UTF-8 with BOM**.

## Step 2 — Dedupe

The worksheet has duplicate source strings (9,368 rows → 7,212 unique). Build a
unique-strings list so each string is translated **once** — less work, and
exact duplicates are guaranteed identical for free.

```python
import csv
seen = {}
for r in csv.DictReader(open('translation/<name>_strings.csv', encoding='utf-8-sig')):
    seen.setdefault(r['source'], '')
with open('translation/unique_strings.csv', 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f); w.writerow(['source', 'target'])
    for s in seen: w.writerow([s, ''])
```

## Step 3 — Build the glossary

Tokenize the source column, count word frequencies (`word_frequency.csv`), and
write a [`GLOSSARY.md`](../translation/GLOSSARY.md) for the target language.

**The glossary is small on purpose.** Do *not* pre-translate hundreds of
obvious words — `layer→слой` is not a decision. Lock only:

* **contested terms** — where two renderings compete (`preset`, `tone`, …);
* **ambiguous terms** — one English word, two meanings (`frame` = animation
  кадр vs comic-panel рамка; `select` = choose vs make-a-selection);
* **brand / do-not-translate** terms.

The glossary is an **output refined during the work**, not a giant input.

## Step 4 — Translate the unique strings in parallel chunks

Fan the 7,212 unique strings out to **N parallel translators** (12 chunks of
576 worked well). Each translator gets the **same brief**: the glossary, a
**locked-terminology table**, and the **formatting rules**. Each returns a JSON
array of translations, one per source line, in order.

Mandatory formatting rules for every translator:

* Preserve every format placeholder verbatim and in order — `%s %d %1$s %@ %%`.
* Preserve newlines and leading/trailing spaces inside strings.
* File-dialog filters are `desc|*.ext|desc|*.ext` — translate the descriptions
  (even-index segments) only; keep every `*.ext` pattern.
* Keep verbatim: product/brand names, Creative Commons license names, file
  extensions, URLs, version numbers, module IDs.
* Empty source → empty target.

## Step 5 — Join back into the worksheet

Apply the chunk translations into `unique_strings.csv`, then map them into the
full worksheet by **source text** (fills all duplicate rows consistently):

```python
import csv
trans = {r['source']: r['target']
         for r in csv.DictReader(open('translation/unique_strings.csv', encoding='utf-8-sig'))}
rows = list(csv.DictReader(open('translation/<name>_strings.csv', encoding='utf-8-sig')))
for r in rows:
    r['target'] = trans.get(r['source'], r['target'])
with open('translation/<name>_strings.csv', 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['key', 'source', 'target'])
    w.writeheader(); w.writerows(rows)
```

## Step 6 — Special cases

* **Non-English source.** CSP's own "English" files contain stray Japanese/CJK
  strings. Find them (alphabetic chars outside Latin/Cyrillic) and translate
  from meaning.
* **Language-picker autonyms** (`日本語`, `한국어`, …). Decide once: localize
  them (consistent with a fully-localized UI) or keep each in its own script
  (so a native speaker can find their language).
* **Third-party license blocks.** Translate only the vendor-authored intro /
  `* About <library>` headers; keep the MIT/BSD/etc. license bodies in English
  — they are legally binding verbatim and several require it.

## Step 7 — Repackage and verify

```
python src/repack.py apply <resource_file> translation/<name>_strings.csv russian/<GUID>
python src/roundtrip.py russian/<GUID>
```

`apply` re-parses its own output; `roundtrip.py` confirms a byte-for-byte
round-trip. Both must pass.

## Step 8 — Consistency audit

```
python src/audit.py translation/<name>_strings.csv
```

Flags English UI terms translated in some rows but left English in others —
the main cross-chunk drift class. Fix the genuine drift, rebuild (Step 7),
re-run until only false positives remain (Air Action effect names, brand
names, module IDs, URLs, XML templates, CC license names — all correctly
English). Dedup (Step 2) already eliminates exact-duplicate drift; the audit
catches term-level drift. Its blind spot: pure synonym drift (one English term
→ two valid target-language words) — rare with a shared glossary.

## Step 9 — Install / load-test

Drop the patched file into a CSP language slot and launch. Slot strategy and
install steps: [`VERIFIED_METHOD.md`](VERIFIED_METHOD.md).

---

## Gotchas (learned the hard way)

* **The CSV is UTF-8 *with BOM*.** Always read and write it with
  `encoding='utf-8-sig'`. Reading with plain `utf-8` makes the first column
  `﻿key`.
* **Opening a file with `'w'` truncates it immediately.** Read the whole CSV
  into memory *before* opening it for writing — a crash mid-write otherwise
  destroys the worksheet. (It can be regenerated with Step 1, but don't.)
* **Translate from `source`, key results by `source`, not by `key`.** `key` is
  version-specific; `source` is stable and is what makes duplicates consistent.
* The patched binary is **per-version and disposable**. Tooling + glossary +
  this doc are the assets to keep.

---

## Adapting the workflow

**Another language.** Write a new `GLOSSARY.md`, redo Step 3's frequency pass
and locked terms, and re-decide the autonym question (Step 6). Everything else
is identical.

**Another CSP version.** Re-export (Step 1) — string IDs, `key`s and counts may
all have changed. **Seed the new translation for free** by joining the old
`unique_strings.csv` onto the new worksheet by `source`: every unchanged
English string carries its translation over, and only genuinely new/changed
strings need translating. Then run Steps 4–8 on the remainder.

**Another resource file.** Same pipeline, one file at a time;
[`FILE_INVENTORY.md`](FILE_INVENTORY.md) lists the ~32 that carry UI text.

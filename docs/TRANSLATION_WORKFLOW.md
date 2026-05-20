# CSP Translation Workflow — reproducible playbook

> How a full, consistent translation of a CSP resource file was produced.
> Companion to [`VERIFIED_METHOD.md`](VERIFIED_METHOD.md): that doc covers the
> **binary** side (parse / edit CSV / repack); **this** doc covers the
> **translation production** side — turning an English worksheet into a good,
> consistent translation at scale.
>
> First run 2026-05-19 on `742DEA58-…` (main UI), English → Russian. A second
> pass the same day fixed the translatable-set bug (Step 1) and re-did all 32
> target files via the Japanese oracle — `742DEA58` went 9,368 → 11,843
> strings. Follow this to translate another file, CSP version, or language
> **without reinventing the process.**

---

## The pipeline at a glance

```
export (Japanese oracle) ─► dedupe ─► glossary ─► translate (parallel chunks)
       ─► join ─► special cases ─► repack + round-trip ─► consistency audit ─► fix ─► install
```

The durable assets are the **tooling** (`src/`), the **manifest**, the
**glossary**, the **worksheets** (`translation/files/`), and this doc. The
patched binary itself is disposable — regenerable and version-specific.

---

## Step 0 — Pick the target file(s)

`742DEA58-…` is the main UI (~11,843 translatable strings). A full UI
translation means repeating this for all 32 content-bearing target files. The file set is the
[`manifest.csv`](../translation/manifest.csv) (`short,guid,slug,covers,target,
text_count`); [`FILE_INVENTORY.md`](FILE_INVENTORY.md) is its prose companion.
`python src/batch.py status` prints progress over every file. The workflow
below is identical for every file; do them one at a time.

Each file gets its own folder `translation/files/<short>-<slug>/` holding
`strings.csv`, `unique.csv` and `word_frequency.csv`. The orchestrator
`src/batch.py` drives the whole pipeline by file `<id>` (a short GUID or slug,
e.g. `742DEA58` or `main-ui`).

## Step 1 — Export the worksheet

```
python src/batch.py export <id>      # one file
python src/batch.py export-all       # every not-yet-exported target file
```

Writes `translation/files/<short>-<slug>/strings.csv`, a `key,source,target`
CSV (`export` skips a file that already has one — use `--force` to overwrite).
**`key` is version-specific — never edit it.** The CSV is **UTF-8 with BOM**.

**What counts as translatable — the Japanese oracle.** `batch.py` exports with
`repack.py export --reference <resource/japanese/GUID>`: a record lands in the
worksheet when it is EITHER prose text OR differs from the finished, fully
localized Japanese resource. Never fall back to the old `--kind text` filter —
it silently drops ~3,900 one-word UI labels. The full rationale, the bug it
fixes, and the exact rule are in [`VERIFIED_METHOD.md`](VERIFIED_METHOD.md) →
"Choosing the translatable set".

## Step 2 — Dedupe

The worksheet has duplicate source strings (`742DEA58`: 11,843 rows → 8,046
unique). Build a unique-strings list so each string is translated **once** —
less work, and exact duplicates are guaranteed identical for free.

```
python src/batch.py dedupe <id>
```

Writes `unique.csv` (one row per distinct `source`) and `word_frequency.csv`
into the file's folder. Re-running it is safe: any translations already done —
in `unique.csv` or in the worksheet — are carried over by `source` text.

## Step 3 — Build the glossary

`dedupe` already wrote the file's `word_frequency.csv`. Use it to write a
[`GLOSSARY.md`](../translation/GLOSSARY.md) for the target language — **one
shared glossary across all files**, extended as new files surface new terms.

**The glossary is small on purpose.** Do *not* pre-translate hundreds of
obvious words — `layer→слой` is not a decision. Lock only:

* **contested terms** — where two renderings compete (`preset`, `tone`, …);
* **ambiguous terms** — one English word, two meanings (`frame` = animation
  кадр vs comic-panel рамка; `select` = choose vs make-a-selection);
* **brand / do-not-translate** terms.

The glossary is an **output refined during the work**, not a giant input.

## Step 4 — Translate the unique strings in parallel chunks

Translate the empty `target` cells of the file's `unique.csv`. Fan the unique
strings out to **N parallel translators** (the oracle re-pass used 8 chunks of
~236). Each translator gets the **same brief**: the glossary, a
**locked-terminology table**, and the **formatting rules**. Each returns a JSON
object mapping `source → target` (an object, not an array — it survives an
agent miscounting, and exact-duplicate keys collapse harmlessly).

**Attach the Japanese rendering as a hint.** Build each chunk as
`[{"source": …, "ja": …}, …]` — the `ja` value comes free from the oracle
(English vs Japanese record diff). It resolves the ambiguous glossary terms
(`frame` = кадр/рамка, `select` = выбрать/выделить, `number` = число/номер) far
better than guessing from a bare one-word English label, and confirms menu
names (CSP's "Story" menu is `ページ管理` — page management).

Mandatory formatting rules for every translator:

* Preserve every format placeholder verbatim and in order — `%s %d %1$s %@ %%`.
* Preserve newlines and leading/trailing spaces inside strings.
* File-dialog filters are `desc|*.ext|desc|*.ext` — translate the descriptions
  (even-index segments) only; keep every `*.ext` pattern.
* Keep verbatim: product/brand names, Creative Commons license names, file
  extensions, URLs, version numbers, module IDs.
* Empty source → empty target.

## Step 5 — Join back into the worksheet

Apply the chunk translations into the file's `unique.csv`, then:

```
python src/batch.py join <id>
```

This maps `unique.csv` into the worksheet by **source text** — filling all
duplicate rows consistently — and writes `strings.csv` back. It reads the whole
worksheet into memory before writing, so a crash mid-write can't destroy it.

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
python src/batch.py pack <id>        # one file, or `pack-all` for every file
```

`pack` runs `repack.py apply` (writes the patched file to `russian/<GUID>`)
**and** the `roundtrip.py` byte-for-byte check on the output, in one step.
Both must pass.

## Step 8 — Consistency audit

```
python src/batch.py audit <id>       # omit <id> to audit every worksheet
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

`batch.py` already handles the first two — they bite only if you write your
own CSV scripts:

* **The CSV is UTF-8 *with BOM*.** Always read and write it with
  `encoding='utf-8-sig'`. Reading with plain `utf-8` makes the first column
  `﻿key`.
* **Opening a file with `'w'` truncates it immediately.** Read the whole CSV
  into memory *before* opening it for writing — a crash mid-write otherwise
  destroys the worksheet.
* **Translate from `source`, key results by `source`, not by `key`.** `key` is
  version-specific; `source` is stable and is what makes duplicates consistent.
  Translate in `unique.csv` (keyed by `source`); `join` maps it back.
* **Never gate the translatable set on `classify()`.** Its `key` bucket —
  "ASCII, no space, ≤40 chars" — swallows every one-word UI label (`Layer`,
  `Edit`, `Save`, `File`). `batch.py export` uses the Japanese oracle
  (`--reference`) instead; see Step 1. Symptom of getting this wrong: a UI
  where multi-word commands translate but single-word menus and palette names
  stay English. This bug cost one whole translation pass.
* **The oracle has one blind spot: blocks CSP left English in *every*
  language.** There `en == ja`, so a non-prose record gets no signal and is
  dropped — even though it is live UI text. Found so far: `7F9F9530` block 6
  (the Material-palette folder tree), fixed by
  [`src/_patch_material_tree.py`](../src/_patch_material_tree.py). No heuristic
  catches these; find them by eyeballing the running UI. Full account:
  VERIFIED_METHOD.md → "The oracle's blind spot".
* The patched binary is **per-version and disposable**. Tooling + manifest +
  glossary + this doc are the assets to keep.

---

## Adapting the workflow

**Another language.** Write a new `GLOSSARY.md`, redo Step 3's frequency pass
and locked terms, and re-decide the autonym question (Step 6). Everything else
is identical.

**Another CSP version.** Re-export with `batch.py export <id> --force` — string
IDs, `key`s and counts may all have changed. (Export needs `resource/japanese/`
present: it is the oracle.) The translation is **seeded for free**:
`batch.py dedupe` carries every existing translation over by `source` text, so
only genuinely new/changed strings land with an empty `target`. Then run Steps
4–8 on the remainder.

**Another resource file.** Same pipeline, one file at a time. `manifest.csv`
lists every file and `batch.py status` tracks which are done.

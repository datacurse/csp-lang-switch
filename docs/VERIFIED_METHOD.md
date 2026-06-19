# CSP5 Resource Translation — VERIFIED METHOD

> **STATUS: WORKING — verified end-to-end.** Last confirmed **2026-05-19**.
>
> This file is the **authoritative** record of what works. Where it disagrees
> with [`CSP5_format_spec.md`](CSP5_format_spec.md) (a *pre-implementation*
> brief that openly speculates), **this file wins.**
>
> Scope: this file covers the **resource bundles**. The Filter menu's
> **plug-in DLLs** are a separate subsystem with their own method and tool —
> see [`PLUGIN_TRANSLATION.md`](PLUGIN_TRANSLATION.md).

---

## TL;DR for a future session

Translating Clip Studio Paint 5 by editing its binary resource files **works and
has been load-tested in CSP itself.** The structural model is solved, the
tooling is built and verified, and a patched file has been confirmed to render
correctly inside a running copy of CSP. Do **not** re-litigate the file format
or rebuild the parser — build on what is here.

The workflow is: **`repack.py export` → edit a CSV → `repack.py apply` → drop the
patched file into a CSP language folder.**

Decide *what* to translate with the **Japanese oracle**, not a heuristic:
`export --reference langs/japanese/ui/<GUID>` includes a record iff it is prose
text or differs from the finished Japanese resource. See "Choosing the
translatable set" below — this is the single most important lesson learned.

---

## What is proven (and how)

### 1. The parser/serializer model is correct — 485/485 round-trip

`serialize(parse(f)) == f`, byte-for-byte, holds for **every** resource file:
**485/485 files** across all 12 stock language folders CSP shipped plus the
working English copy. Because [`csp5.py`](../src/csp5.py) stores **no absolute offsets**
and `serialize()` recomputes every offset and length from child sizes, a passing
round-trip is a proof that the structural model is complete and correct.

Re-verify any time with:

```
python src/roundtrip.py resource
```

### 2. The index and footer are language-independent — confirmed across all 12 languages

Block 2 (index, 143,422 bytes) and block 3 (footer, 48 bytes) of every shared
resource file are **byte-identical across all 12 language folders** (the original
spec only checked English vs Japanese). The repacker therefore copies them
**verbatim** and never rebuilds them. Confirmed for all 39 shared GUID files.

### 3. Repackaging works — CSP load test PASSED

On **2026-05-19** a patched `742DEA58-…` file was produced by `repack.py apply`
(English base + several Russian `target` strings), placed in CSP's **`french`**
resource folder, and CSP was set to French. **CSP launched and rendered the
patched UI correctly**, showing the Russian strings. This is the real-world
confirmation that round-trip success translates into a file CSP actually accepts.

> Scope of that test: one file (`742DEA58-…`), a partial translation — a smoke
> test, not a full-UI patch. It proves the *method*, not a finished product.

---

## The file format, as actually implemented (authoritative)

All integers are **unsigned 32-bit big-endian**.

* **Top-level container** — a 40-byte header: `uint32 block_count (=3)` then
  `3 × (uint32 id, uint32 offset, uint32 length)`. **Offsets are absolute file
  offsets.** Blocks are contiguous right after the header.
  * block id=1 — string data (a recursively nested container)
  * block id=2 — index table (language-independent → copied verbatim)
  * block id=3 — footer (language-independent → copied verbatim)

* **Block 1** is built from one repeating primitive, a **directory**:
  `uint32 count` then `count × (uint32 id, uint32 offset, uint32 length)`, and
  the child data follows **immediately, with no gap or padding**. Entry offsets
  are absolute file offsets and chain perfectly:
  `entry[0].offset == node_start + 4 + 12*count`,
  `entry[n+1].offset == entry[n].offset + entry[n].length`, and the last entry
  ends exactly at the node's end.

* A directory's first `uint32` **is exactly its entry count** — always.

* **Strings** are stored as `[uint32 byte_length][UTF-8 bytes]`, no terminator.
  `byte_length` is a UTF-8 **byte** count, not a character count.

* Block 1 is a tree of three node kinds: **directory**, **string-stream leaf**
  (a run of length-prefixed strings), and **blob leaf** (PNG assets / opaque
  sub-containers). The parser classifies each byte range by structural
  validation in this order: directory → string stream → blob.

There is **no fixed byte budget** per string — `serialize()` recomputes every
length and offset — so a translation may be any length (Cyrillic UTF-8 is ~2
bytes/char; that is fine).

---

## Choosing the translatable set — the Japanese oracle

This is the lesson that cost a whole translation pass; do not relearn it.

**The trap.** [`extract_csp_strings.py`](../src/extract_csp_strings.py) has a
`classify()` heuristic that buckets each string as `text` / `key` / `url`. Its
rule for `key` is "ASCII, no space, ≤40 chars" — meant to catch identifiers like
`PWView`. But that description **also fits almost every one-word UI label**:
`Layer`, `Cancel`, `Save`, `Edit`, `File`, `View`, `Window`, `Color`. The first
translation pass exported with `--kind text`, so all of these were **silently
dropped** — ~3,900 strings, ~21% of the UI, including the entire menu bar. The
symptom in CSP: a half-translated UI where multi-word commands ("Color Wheel")
were translated but every single-word menu and palette name stayed English.

**Why a heuristic can't fix this.** No lexical rule separates the label `Layer`
from the identifier `PWView` — both are short ASCII CamelCase-ish tokens. You
need an external source of truth.

**The oracle.** CSP ships a *fully localized* Japanese resource for every file.
A record's English text and its Japanese text differ **iff Cygames considered
it translatable UI text**. So:

> A record is translatable **iff** it is prose (`classify() == "text"`)
> **OR** its English text differs from the Japanese resource.

`repack.py export --reference langs/japanese/ui/<GUID>` implements exactly this.
The two halves of the rule are a deliberate **union** — it is always a *superset*
of the old `text`-only worksheet, so re-exporting can never *lose* an existing
translation:

* the `classify() == "text"` half keeps all prose, including stray Japanese
  that CSP's English file ships (which equals the Japanese resource yet still
  needs translating);
* the `en != ja` half rescues the one-word labels the heuristic mislabels.

Only records that are **both** non-prose **and** identical in English and
Japanese are excluded — genuine identifiers (`OK`, `CELSYS`, `5.0.0`, `Ver.%s`,
registry paths). Measured on `742DEA58`: the translatable set went 9,368 →
**11,843**; across all 32 target files, **3,888** real strings were recovered.

`classify()` is still fine for the `stats` breakdown — just never let it gate
what gets translated.

### Never translate the material folder tree — block 6 of `7F9F9530`

Block 6 of `7F9F9530` is the **Material-palette folder tree** (`All materials →
Color pattern → … → Texture`). These are **not** ordinary display labels:
CSP matches stock and downloaded materials to their built-in folder **by name**,
comparing the (localized) tree node against the folder tag stored in the local
material database (`CatalogMaterial.cmdb` / `MaterialFolderTag.mfta`) — there is
no stable id behind the name. So if the folder name is translated, the match
fails and **the folder opens empty**. (The 3D folders are the exception: they
bind to language-neutral `SystemTag` codes such as `3DPrimitive` /
`3DDessindollHead`, which is why 3D kept working when every other category broke.)

**Policy: these strings stay English in every resource file, every CSP version.**
Enforced in `src/batch.py`:

* **`_material_folder_sources()`** — the ~214 English strings from block 6 of
  `7F9F9530` (folder names and colon-paths like `Monochromatic pattern:Texture`).
* **`export` / `pack` / `join`** skip any row whose key *or source* is in that set.
  This matters because `pack` maps translations by **source text**: the same
  `"All materials"` in `742DEA58` main UI would otherwise pick up Russian from
  `unique.csv` even when block 6 keys in `7F9F9530` were already protected.

The cost is cosmetic — the palette tree shows English category names inside an
otherwise-Russian UI — and it is strictly better than folders that resolve to
zero materials.

> Historical note: an earlier approach went the other way — a
> `scripts/patch_material_tree.py` helper *added* Russian folder names (block 6
> ships English in all 12 languages, so the Japanese oracle could not see them as
> translatable). That script has been removed: translating these names is exactly
> what breaks material selection.

---

## The reproducible procedure

This section is the **binary-level** primitive: `repack.py` on a single file.
For translating the whole UI (~32 files) drive it through the orchestrator
`src/batch.py` instead — see [`TRANSLATION_WORKFLOW.md`](TRANSLATION_WORKFLOW.md).
`batch.py` calls exactly the `repack.py` commands below, one file at a time.

### 1. Export a translation worksheet

```
python src/repack.py export <resource_file> strings.csv --reference <japanese_file>
```

Produces a CSV with columns `key, source, target`. `key` addresses the string
inside the file (an entry-ID tree path, e.g. `1/1/3#0`) — **never edit it**.

**Use `--reference`, not `--kind`.** `--reference` points at the matching file
in `langs/japanese/ui/`; a record is exported when it is prose text **or**
differs from that finished Japanese resource. The old `--kind text` filter
relied on the `classify()` heuristic, which labels every space-free ASCII string
≤40 chars a non-translatable "identifier" — so it silently dropped ~3,900 real
one-word UI labels (`Layer`, `Cancel`, `Edit`, `File`, and the whole menu bar).
The Japanese resource is fully localized, so "differs from Japanese" is the
ground truth for "translatable UI text".

### 2. Translate

Edit only the `target` column. **Save as UTF-8** — for Cyrillic this is
critical (Excel: "CSV UTF-8"; LibreOffice: character set = Unicode UTF-8). The
CSV is just an overlay; it carries no structural data.

### 3. Repackage

```
python src/repack.py apply <resource_file> strings.csv <patched_file>
```

`apply` re-parses the original binary, substitutes text by `key`, recomputes all
offsets/lengths via `serialize()`, and re-parses its own output as a sanity
check. Index and footer ride along verbatim.

### 4. Install into CSP

1. **Close CSP.**
2. **Back up** the target file: `resource\<language>\<GUID>`.
3. Copy the patched file over it — the filename must stay the **exact GUID**, no
   extension, no suffix.
4. Launch CSP, set the UI language to that language, restart if prompted.

For the whole build, [`src/install.py`](../src/install.py) automates steps 1–3:
`python src/install.py russian` overwrites the `english` slot with
`langs/russian/ui/` (the repo's `langs/english/ui/` holds the stock English,
so `install.py english` is the undo). It refuses to run while CSP is open and
self-elevates via UAC.

---

## Slot strategy

CSP picks a resource folder by the selected UI language and has no `russian`
slot. Two viable approaches:

* **Overwrite `english`** (the current switcher strategy) — the app copies the
  selected community or official language into CSP's English slot; untranslated
  community strings fall back to readable English.
* **Use a different language slot** (the 2026-05-19 verified approach used
  `french`) — keeps a real English option intact and turns an unused language
  into the translation slot.

Both are sound. A patched file is a **complete English-derived resource**;
dropping it into another language's folder just makes CSP load it. The block-1
**tree shape and record count are identical across all 12 languages** (verified:
`742DEA58-…` has 12,910 records and the same nesting in every folder), so the
file is structurally interchangeable between slots.

The entry-ID *labels* are a subtler matter: identical for most language pairs
but **not all** — `742DEA58-…` differs from English in 8 id-paths in the
Japanese file and 10 in the Traditional-Chinese file (0 in the other nine).
A worksheet `key` is therefore only guaranteed valid against the **same file it
was exported from**. This is harmless in practice: `repack.py apply` always runs
against the English source the worksheet came from. It matters only for the
Japanese **oracle** (`export --reference`), which aligns records by **tree
position**, not by key — `repack.block1_shape()` asserts the shapes match first.

---

## Verified facts & figures (`742DEA58-…`, the main UI file)

* 3,467,072 bytes; block 1 = tree of 1,293 directories, max depth 3.
* 12,910 structured string records. The `classify()` buckets are 9,368 `text`,
  3,433 `key`, 109 `url` — but 2,449 of those `key` records and 26 of the `url`
  records are **real UI text** (they differ in the Japanese resource). The true
  translatable count is **11,843** — see "Choosing the translatable set".
* 495 blob leaves (2.67 MB) — PNG assets + opaque sub-containers, not translated.
* 55 distinct GUID files exist: **39 shared** across all 12 language folders +
  16 present only in `other`. Only the 39 carry translatable UI text.

A per-file breakdown of all 39 shared files — what each one covers, its
translatable-string count, and which six are non-targets (shader code, XML
templates, empty stubs) — is in [`FILE_INVENTORY.md`](FILE_INVENTORY.md).
Totals (oracle count): **18,299 translatable strings** across the 32 target
files — **11,843 in `742DEA58`** and **6,456 in the other 31**. A full UI
translation means patching all 32 of these files, not just `742DEA58`.

---

## Corrections to `CSP5_format_spec.md`

`CSP5_format_spec.md` is the **pre-implementation handoff brief**. Its §6
("PARTIALLY UNDERSTOOD") and §12 "open questions" are now **resolved**, and a
few of its guesses were **wrong**:

| Spec said (speculative) | Actually (verified) |
|---|---|
| Offsets are "block-1-relative" (§5/§6) | Offsets are **file-absolute** |
| A "~40-byte secondary structure" sits between some directories and their data (§6-C) | **No such structure** — child data follows the entry array immediately |
| A node "header field" sometimes ≠ entry count (§6-A/B) | A directory's first `uint32` **is** its entry count, always; the apparent mismatches were old-heuristic misparses |
| ~29,642 string records, ~8,647 translatable, 6,535 unique (greedy scan, §5/§10) | Tree-parse actuals: 12,910 records, 9,368 text, 7,212 unique |
| "39 GUID-named files" (§1) | 55 distinct GUIDs total — 39 shared + 16 `other`-only |

What the spec got **right** and should still be trusted on: the 3-block
big-endian container, the 40-byte header, length-prefixed UTF-8 strings, block 1
as a relocatable nested tree with stable directory IDs, and index/footer being
language-independent.

---

## Tooling

All Python lives in [`src/`](../src/); run it from the repo root
(`python src/<tool>.py …`).

* [`csp5.py`](../src/csp5.py) — parser + serializer. The round-trip-verified core.
* [`repack.py`](../src/repack.py) — `export` / `apply` / `stats`; the
  single-file CSV primitive.
* [`batch.py`](../src/batch.py) — **the orchestrator for translation work.**
  Drives `export` / `dedupe` / `join` / `pack` / `audit` / `status` across all
  files in `translation/manifest.csv`. Run this; it calls the tools below.
* [`extract_csp_strings.py`](../src/extract_csp_strings.py) — text/key/url
  classifier; imported by `repack.py`.
* [`roundtrip.py`](../src/roundtrip.py) — verification harness
  (`serialize(parse(f))==f`).
* [`audit.py`](../src/audit.py) — translation-consistency audit; see
  [`TRANSLATION_WORKFLOW.md`](TRANSLATION_WORKFLOW.md).

---

## What is NOT done yet / open

* All **32 content-bearing shared files** are translated to Russian and packed
  into `langs/russian/ui/` (all 32 round-trip byte-for-byte). Re-confirm a full live
  load-test in CSP after any re-pack.
* CSP updates can change string IDs or add strings; re-export and re-apply
  against each new build. The **tooling** is the durable asset, not any one
  patched file.
* macOS resource files live in the app bundle and are expected to use the same
  format (untested here). iPad/Android are sandboxed and not patchable this way.

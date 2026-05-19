# CSP5 Resource Translation — VERIFIED METHOD

> **STATUS: WORKING — verified end-to-end.** Last confirmed **2026-05-19**.
>
> This file is the **authoritative** record of what works. Where it disagrees
> with [`CSP5_format_spec.md`](CSP5_format_spec.md) (a *pre-implementation*
> brief that openly speculates), **this file wins.**

---

## TL;DR for a future session

Translating Clip Studio Paint 5 by editing its binary resource files **works and
has been load-tested in CSP itself.** The structural model is solved, the
tooling is built and verified, and a patched file has been confirmed to render
correctly inside a running copy of CSP. Do **not** re-litigate the file format
or rebuild the parser — build on what is here.

The workflow is: **`repack.py export` → edit a CSV → `repack.py apply` → drop the
patched file into a CSP language folder.**

---

## What is proven (and how)

### 1. The parser/serializer model is correct — 485/485 round-trip

`serialize(parse(f)) == f`, byte-for-byte, holds for **every** resource file:
**485/485 files** across all 12 language folders (`resource/`) plus the
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

## The reproducible procedure

This section is the **binary-level** primitive: `repack.py` on a single file.
For translating the whole UI (~32 files) drive it through the orchestrator
`src/batch.py` instead — see [`TRANSLATION_WORKFLOW.md`](TRANSLATION_WORKFLOW.md).
`batch.py` calls exactly the `repack.py` commands below, one file at a time.

### 1. Export a translation worksheet

```
python src/repack.py export <resource_file> strings.csv --kind text
```

Produces a CSV with columns `key, source, target`. `key` addresses the string
inside the file (an entry-ID tree path, e.g. `1/1/3#0`) — **never edit it**.

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

---

## Slot strategy

CSP picks a resource folder by the selected UI language and has no `russian`
slot. Two viable approaches:

* **Overwrite `english`** (the original spec's recommendation) — users set CSP
  to English and see the translation; untranslated strings fall back to readable
  English.
* **Use a different language slot** (the 2026-05-19 verified approach used
  `french`) — keeps a real English option intact and turns an unused language
  into the translation slot.

Both are sound: the block-1 tree shape and key set are **identical across all
languages** (verified: English vs French `742DEA58-…` have the same 12,910
keys). A patch built against the English file drops cleanly into any language
folder.

---

## Verified facts & figures (`742DEA58-…`, the main UI file)

* 3,467,072 bytes; block 1 = tree of 1,293 directories, max depth 3.
* 12,910 structured string records: **9,368 `text`** (7,212 unique), 3,433
  `key`, 109 `url`.
* 495 blob leaves (2.67 MB) — PNG assets + opaque sub-containers, not translated.
* 55 distinct GUID files exist: **39 shared** across all 12 language folders +
  16 present only in `other`. Only the 39 carry translatable UI text.

A per-file breakdown of all 39 shared files — what each one covers, its `text`
count, and which six are non-targets (shader code, XML templates, empty stubs) —
is in [`FILE_INVENTORY.md`](FILE_INVENTORY.md). Totals: **14,611 `text` records**,
**9,368 in `742DEA58`** and **5,243 in the other 38**; a full UI translation
means patching ~32 of these files, not just `742DEA58`.

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

* Only `742DEA58-…` has been patched and load-tested. A full UI translation
  means repeating the procedure for the **~32 content-bearing shared files**
  (39 total minus 6 non-targets — see [`FILE_INVENTORY.md`](FILE_INVENTORY.md)).
* No Russian translation content exists yet — only the method is proven.
* CSP updates can change string IDs or add strings; re-export and re-apply
  against each new build. The **tooling** is the durable asset, not any one
  patched file.
* macOS resource files live in the app bundle and are expected to use the same
  format (untested here). iPad/Android are sandboxed and not patchable this way.

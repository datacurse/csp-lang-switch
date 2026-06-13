# Clip Studio Paint 5 — Resource File Format & Russian Translation Patch
## Technical specification and implementation brief

> **⚠️ STATUS (2026-05-19): IMPLEMENTED & VERIFIED.** This is the original
> *pre-implementation* brief. The work it describes is done: the parser
> round-trips 485/485 files and a patched file has been load-tested in CSP.
> **§6 ("PARTIALLY UNDERSTOOD") and §12's "open questions" are RESOLVED**, and
> a few guesses here turned out wrong (offsets are file-absolute, not
> block-1-relative; there is no "secondary structure"). Where this brief
> speculates, **[`VERIFIED_METHOD.md`](VERIFIED_METHOD.md) is authoritative** —
> read that first. This file is kept as the historical record of the analysis.

**Purpose of this document.** This is a complete handoff brief for implementing a
Russian translation patch for Clip Studio Paint 5 (CSP 5, current build Ver. 5.0.4).
It records everything reverse-engineered so far about the resource file format and
defines the work needed to build a *parser* (reads strings out) and a *repacker*
(writes a translated file back). It is written to be handed to Claude Code, which
will do the implementation with the real files present and CSP available for
load-testing.

The target file used for reverse-engineering is
`742DEA58-ED6B-4402-BC11-20DFC6D08040` — the largest resource file and the one
holding the main application UI. It lives in
`...\CELSYS\CLIP STUDIO 1.5\CLIP STUDIO PAINT\resource\<language>\`.

Two real samples were analysed: the **English** copy (3,467,072 bytes) and the
**Japanese** copy (3,582,739 bytes). Diffing them is what unlocked most of the
findings below.

---

## 1. Project context

- CSP 5 has 11 official UI languages, each with its own folder under `resource\`:
  `japanese, english, french, german, spanish, portuguese, korean, chinese_sc,
  chinese_tc, indonesian, thai`. Russian is **not** among them and never has been.
- Each language folder contains the **same 39 GUID-named files**. There is also an
  `other` folder containing those same 39 files (byte-identical to the `english`
  copies) plus 16 extra language-neutral binary assets that exist nowhere else.
- The patch only needs to translate the **39 string files**. The 16 extra files in
  `other` must be left untouched.
- `742DEA58-...` is by far the largest of the 39 and holds the main UI. The other
  38 use the **same format** and the same tooling will apply to them.

**Slot strategy.** CSP picks a resource folder by the selected UI language; it will
not look for a `russian` folder that does not exist in its internal list.
Recommended approach: **translate the files and overwrite the `english` folder**,
then ship as a resource-folder overlay. The switcher copies the selected language
into that English slot. Advantage: any string left untranslated falls back to
readable English rather than Japanese. (A stretch goal — finding and editing the internal
language→folder map to add a real "Russian" entry — is out of scope for v1.)

**Legal note.** This modifies copyrighted software resources. Distribute a
resource-folder overlay only, never bundled with cracked binaries, and develop and
test against a legitimately licensed CSP install.

---

## 2. CONFIRMED — top-level container format

All integers are **unsigned 32-bit big-endian**. The file begins with a 40-byte
header directory:

```
offset 0   uint32  block_count = 3
offset 4   uint32  block[0].id      = 1
offset 8   uint32  block[0].offset
offset 12  uint32  block[0].length
offset 16  uint32  block[1].id      = 2
offset 20  uint32  block[1].offset
offset 24  uint32  block[1].length
offset 28  uint32  block[2].id      = 3
offset 32  uint32  block[2].offset
offset 36  uint32  block[2].length
```

The three blocks are laid out contiguously right after the header; each block's
offset equals the previous block's offset + length, and block[2] ends exactly at
end-of-file. Verified on both samples:

| block | role          | English (off, len)   | Japanese (off, len)  |
|-------|---------------|----------------------|----------------------|
| id=1  | string data   | 40, 3,323,562        | 40, 3,439,229        |
| id=2  | index table   | 3,323,602, 143,422   | 3,439,269, 143,422   |
| id=3  | footer        | 3,467,024, 48        | 3,582,691, 48        |

---

## 3. CONFIRMED — the index and footer are language-independent

**This is the most important finding for the repacker.** Block id=2 (143,422 bytes)
and block id=3 (48 bytes) are **byte-for-byte identical between the English and
Japanese files**. Not similar — identical, every byte.

If the index encoded byte offsets into the string data, it would *have* to differ
between languages because the strings have different lengths. It does not differ at
all. Therefore the index references strings by **stable IDs**, not by position, and
those IDs do not move when text changes. The footer is the same.

**Consequence:** the repacker copies block id=2 and block id=3 **verbatim**. It
never parses or rebuilds them. The entire repacking problem reduces to rebuilding
block id=1 (the string data) and then rewriting the 40-byte top-level header with
the new block lengths/offsets.

(Footer content, for reference — identical in both files, as twelve uint32s:
`48, 16, 20, 44, 0, 2, 0xFFFFFFFF, 0xFFFFFFFF, 0, 0, 262151, 851969`.)

---

## 4. CONFIRMED — string encoding

Strings are stored as **length-prefixed UTF-8**:

```
uint32  byte_length      (big-endian; this is BYTES, not characters)
byte[]  utf8_data         (byte_length bytes of UTF-8)
```

No null terminator. The length is the UTF-8 byte count. Confirmed by decoding
thousands of real strings cleanly from both files, e.g. English `Show command bar`
(16 bytes), `Adapt view to editing target` (28 bytes); Japanese `コマンドバーの表示`,
`カラーセットの読み込み`.

**Implication for Russian.** UTF-8 Cyrillic is 2 bytes per character. Russian
strings will be roughly 1.3–1.6× the byte length of the English source. Because the
format is relocatable (Section 5), this is fine — there is **no fixed byte budget**
per string, unlike the older CSP 1.x format. The repacker just recomputes offsets.

---

## 5. CONFIRMED — block id=1 is a relocatable nested container

Block id=1 is not a flat blob. It is a **recursively nested container** built from
one repeating primitive: a *directory* of `(id, offset, length)` entries. The actual
strings sit at the leaves.

What is firmly established:

- **It is a relocatable tree.** The English and Japanese files have the **same
  directory IDs at every level**; only the `offset` and `length` fields differ, and
  they differ by exactly the cumulative byte-delta of the translated text. Example —
  the root's first five section entries `(id, offset, length)`:

  | id | English            | Japanese           |
  |----|--------------------|--------------------|
  | 1  | (1, 6080, 14458)   | (1, 6080, 14505)   |
  | 2  | (2, 20538, 6163)   | (2, 20585, 6273)   |
  | 3  | (3, 26701, 6027)   | (3, 26858, 6430)   |
  | 4  | (4, 32728, 5752)   | (4, 33288, 6777)   |
  | 5  | (5, 38480, 2863)   | (5, 40065, 2884)   |

  Same IDs, offsets chain (`offset[n+1] = offset[n] + length[n]`), lengths track the
  text. This is the signature of a clean relocatable container: change the text,
  recompute the offsets, done.

- **Offsets are absolute within block id=1** (block-1-relative — i.e. measured from
  the first byte of block id=1's data, which is file offset 40). Verified: nested
  directory entries reference positions such as 6520 and 20674 that are correct only
  under the block-1-relative interpretation.

- **The root directory** is `uint32 count = 503` followed by 503 entries of
  `(uint32 id, uint32 offset, uint32 length)`. The 503 entries chain perfectly. The
  503 top-level "sections" then contain the strings, nested further.

- A greedy scan of block id=1 recovers **~29,642 string records** total, of which
  roughly **8,647 are translatable UI text** (`6,535 unique`); the remainder are
  internal identifiers (`PWView`, `PWPushButton`), printf-style format keys (`%s`),
  and URLs, which must NOT be translated.

---

## 6. PARTIALLY UNDERSTOOD — the internal node layout

This is the part that still needs work, and it is the first job for Claude Code. The
high-level model is solid; the byte-exact node layout is not yet pinned down.

**Working model of a directory node:**

```
uint32   header_field        (see open question A)
entry[]  N x (uint32 id, uint32 offset, uint32 length)
?        possibly a ~40-byte secondary structure (a count=3 mini-directory)
bytes    data region: either child nodes, or a string stream
```

- The data region of a node is either **more directory nodes** or a **string
  stream** (a run of `[uint32 len][utf8]` records).
- A recursive walk reaches a depth of about 4 levels: roughly 160 directory nodes
  over ~2,600 leaf regions.
- The string stream's records **cross leaf/slice boundaries** — a single string can
  start in one directory-entry slice and finish in the next. So the directory
  entries paginate the byte stream; they are not one-string-per-entry.

**Known-good worked examples (use these as parser test fixtures):**

- *Root node*, English block-1 offset 0: `header_field = 503`, and there really are
  503 chaining entries. Here `header_field == entry_count`.

- *Section node id=2*, English block-1 offset 20538, region length 6163:
  `header_field = 20`, but only **6** valid `(id, offset, length)` entries chain
  (ids 4, 14, 15, 16, 6, 10), after which string data begins. So here
  `header_field (20) != entry_count (6)`. Right after the 6th entry, at block-1
  offset 20614, the string stream begins: `[uint32 16]["Import file (%s)"]`,
  `[uint32 42]["Range of frames to import as pose sequence"]`, then
  `"Some motion files may have terms of use.\r\nPlease check these before using the
  file."`, `"OK"`, `"Cancel"`, `"Start frame"`, `"End frame"`.

- *Section node id=1*, English block-1 offset 6080: `header_field = 33`; its string
  stream begins at block-1 offset 6480 (= 6080 + 4 + 33×12, i.e. immediately after
  the directory).

- A node whose `header_field` is a large number like 2474 (English section id=6,
  block-1 offset 41343) is probably a **binary/blob leaf**, not a directory and not
  a text stream — the parser must tolerate a third node kind.

**Open questions to resolve (each is answerable empirically with the two files):**

- **A. The node header field.** Sometimes it equals the entry count (root: 503),
  sometimes it does not (section id=2: 20 vs 6 entries). Determine what it is. It may
  be a string-count, a type tag, a flags word, or a size. Note that the values
  `16` and `20` recur in the index/footer headers too — possibly a shared record
  header shape `[length][16][20][...][0][count][-1][-1]`.

- **B. Where the real entry count comes from**, if not the header field. Likely
  inferable as "entries that chain until the first one fails validation," but
  confirm against a deterministic field.

- **C. The ~40-byte secondary blocks** between some directories and their data
  (observed as `count=3` mini-directories). Determine when they are present and how
  to rebuild them.

- **D. Node-kind discrimination** — directory vs string-stream-leaf vs binary blob.
  A robust rule is needed so the parser never misclassifies (an earlier heuristic
  parser misclassified ~20% of the block).

- **E. Confirm the index truly needs no update.** Evidence is strong (identical
  EN/JA), but Claude Code should confirm block id=2 contains no block-1 byte offsets
  before relying on copy-verbatim.

---

## 7. The verification methodology — round-trip test

Do **not** attempt to write the repacker until the parser passes this test.

> **Round-trip test:** `serialize(parse(file)) == file`, byte-for-byte, for **both**
> the English and the Japanese sample.

A parser that can re-emit the original file unchanged has, by definition, a correct
and complete structural model. Iterate the parser (resolving Section 6's open
questions) until round-trip passes on both files. Only then is repacking safe — at
that point repacking is just "parse, substitute strings, recompute, serialize."

Suggested parser internal representation: a tree of nodes, where each node stores
its kind (directory / string-stream / blob), its children or its decoded string
records, and the *original* header/id values — but **not** absolute offsets, since
those must be recomputed on serialize. If serialize recomputes every offset/length
from child sizes and still reproduces the original bytes, the layout model is proven.

---

## 8. The repacker algorithm

Once the parser round-trips:

1. **Parse** the target file into header + block id=1 tree + raw block id=2 + raw
   block id=3.
2. **Walk the block-1 tree** to the leaf string streams; decode every
   `[uint32 len][utf8]` record into a list keyed by a stable path
   (e.g. `section_id / ... / record_index`).
3. **Substitute** each record's text with its Russian translation (UTF-8).
   Untranslated records keep their original text.
4. **Re-serialize block id=1 bottom-up:** rebuild each string stream, then each
   directory's entry `length` and `offset` fields, then each section, then the block.
   Every offset is absolute within block 1 and is computed from the running layout.
   Rebuild any secondary structures (open question C).
5. **Reassemble the file:** new block id=1, then block id=2 **verbatim**, then block
   id=3 **verbatim**. Recompute the 40-byte top-level header (block id=1's new
   length; block id=2 and id=3's new offsets — their lengths are unchanged).
6. **Write** the output file.

**Fallback approach** if the full tree model proves stubborn — an *offset-fixup*
repacker: locate every string record by scanning; replace text and record each
position's byte-delta; then fix up every absolute offset field (shift by the
cumulative delta of all changes before it) and every directory `length` field
(adjust by the delta of changes inside its range). This needs only a reliable
partition of block 1 into "structure bytes" vs "string-record bytes," not a full
semantic tree. It is less elegant but robust. The round-trip test still applies.

**Validation after repacking:** patch only a handful of strings first, load the file
in a legitimate CSP 5 install, and confirm the UI renders and no palettes/menus
break. A wrong length or offset typically makes CSP silently fail to load the file
or show empty panels. Expand only once a small patch loads cleanly.

---

## 9. Translation workflow

1. **Extract** English strings with the provided `extract_csp_strings.py` (Section
   10). Work from English — it is the practical source language for a Russian
   translation.
2. **Build a glossary first.** Settle the core recurring terms before bulk
   translation so the result stays consistent: layer, brush, canvas, selection,
   tone, ruler, frame, vector, raster, clipping, opacity, blending mode, etc.
3. **Translate** the ~6,500 unique `text`-kind strings. Skip `key` and `url` kinds
   entirely. Watch for printf placeholders (`%s`, `%d`) — keep them and their order.
   Watch for menu accelerators and trailing punctuation.
4. **Repack** with the tool from Section 8, targeting the `english` folder's copy of
   each of the 39 files (start with `742DEA58-...`).
5. **Test** in CSP, iterate.
6. Repeat extraction/translation/repack for the other 38 files. They are smaller and
   use the same format.

Rough scope: ~6,500 unique strings in the main file. A meaningful but bounded
project for a single full application UI.

---

## 10. Tools already built

Two standalone Python scripts (standard library only) already exist and work:

- **`csp_resource_inspect.py`** — inventories the whole `resource\` directory:
  per-folder file counts and sizes, a cross-folder size matrix, byte-identity groups,
  and header hex dumps. Useful for confirming structure across all 39 files and all
  language folders.

- **`extract_csp_strings.py`** — parses the 3-block header of any resource file,
  greedy-scans block id=1 for `[uint32 len][utf8]` records, classifies them as
  `text` / `key` / `url`, and writes `<prefix>.json` and `<prefix>.tsv`. This is the
  string extractor for the translation workflow. It is heuristic (greedy scan, not a
  full tree parse) — good for translation scoping and review, but the *repacker*
  needs the proper round-trip-verified parser from Section 7.

The repacker, and a tree-accurate parser to replace the greedy extractor, are the
code to be written in Claude Code.

---

## 11. Cross-version and maintenance caveats

- All findings are from CSP **Ver. 5.0.x** on Windows. The macOS resource files live
  inside the app bundle (`...app/Contents/Resources/<language>/`) and are expected to
  be identical in format. iPad/Android are sandboxed and not patchable this way.
- Celsys ships a major CSP version yearly plus frequent minor updates. Each update
  can change string IDs, add strings, or in principle alter the format. The patch
  must be re-generated against each update; the tooling (parser + repacker) is what
  has lasting value, not any single patched file.
- Keep the parser tolerant: validate the 3-block header, validate that block id=2 and
  id=3 are present and copy them blind, and fail loudly rather than silently if a
  node does not match the model — a malformed output file is worse than a clear error.

---

## 12. Quick reference — what is settled vs open

**Settled (build on these directly):**
- 3-block big-endian container; 40-byte top header.
- Block id=2 (index) and id=3 (footer) are language-independent → copy verbatim.
- Strings are `[uint32 big-endian byte-length][UTF-8]`.
- Block id=1 is a relocatable nested tree; offsets are absolute within block 1;
  directory IDs are stable across languages.
- Root of block 1 is `[uint32 503][503 × (id, offset, length)]`.
- ~6,500 unique translatable strings in `742DEA58-...`; 39 files total.

**Open (resolve via round-trip testing in Claude Code):**
- Exact node header layout and the meaning of its first field.
- How the true entry count is determined.
- The ~40-byte secondary structures.
- Directory / string-leaf / binary-blob discrimination.
- Final confirmation that the index needs no rewriting.

**Definition of done for Phase 1:** a parser for which
`serialize(parse(f)) == f` byte-for-byte, for both the English and Japanese
`742DEA58-...` samples.

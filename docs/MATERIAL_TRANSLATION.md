# CSP Material-Catalog Translation — VERIFIED METHOD

> **STATUS: WORKING — verified end-to-end.** Last confirmed **2026-05-19**.
>
> Fourth subsystem, alongside [`VERIFIED_METHOD.md`](VERIFIED_METHOD.md)
> (resource bundles), [`PLUGIN_TRANSLATION.md`](PLUGIN_TRANSLATION.md) (filter
> DLLs) and [`TOOL_TRANSLATION.md`](TOOL_TRANSLATION.md) (tool palette).

---

## TL;DR

The names of CSP's built-in **materials** — paper textures, manga tones and
patterns, speech-balloon shapes, comic frame templates, 3D poses, 3D objects,
plants, buildings — shown in the Material palette and the "select material"
dialogs are **not** in the resource bundles, plug-in DLLs, or tool DBs. They
live in CSP's per-user material data, and translating them takes patching **two
layers** — the lesson that cost a pass of this work. The tool is
[`src/materials.py`](../src/materials.py).

All materials are **built-in** — the catalog reports `Downloaded = 0` for every
one of its ~1,573 materials; nothing came from CLIP STUDIO ASSETS.

---

## The trap: the catalog DB is *not* where the displayed name is

Everything lives under
`%APPDATA%/CELSYSUserData/CELSYS/CLIPStudioCommon/`:

* **`MaterialDB/CatalogMaterial.cmdb`** — a SQLite catalog index. Its
  `Tag.Title` column **is** the picker's tag-filter chips → patch it. But its
  `MaterialModifier.MaterialName` column is **only a search / user-rename
  field** — patching it changes *nothing* on screen. (`NatMaterialName` is a
  normalized search key; `SystemTag.Title` is internal identifiers — both left
  alone.)

* **`Material/Install/` and `Material/Install2/`** — every material is one pack
  folder (1,573 packs total), each holding a **`catalog.xml`** (XML manifest)
  and a **`catalogMaterial.cac`** (binary "catalog cache"). The **displayed
  material name** is the `<name>` here — in *both* files.

> Patching only the `.cmdb` translated the tags but left every material name
> English. The name shown in the picker comes from the per-pack catalog files,
> so **both** `catalog.xml` and `catalogMaterial.cac` must be patched.

---

## The `.cac` format

`catalogMaterial.cac` is a **sequential binary stream** — a serialized
catalog→groups→items→files tree — with **no offset table**. Strings (including
each `<name>`) are stored as `[uint16-LE byte-length][UTF-8 bytes]`; fixed-width
fields sit between them.

Because nothing stores an absolute offset or a total size, a name is patched by
an **exact byte substitution**: find `[len(old)][old-UTF-8]` and replace with
`[len(new)][new-UTF-8]`. The file simply grows (Cyrillic UTF-8 is longer) and
CSP, parsing sequentially, accepts it. The 2-byte length prefix is matched too,
so a short name can never match inside a longer one (`[5]"Blood"` ≠ the middle
of `[9]"Blood 003"`). Verified: every one of 526 catalog names across all 394
`Install` packs is byte-findable this way.

`catalog.xml` is plain XML — the `<name>EN</name>` text is replaced directly.

> The live `.cac` files carry the Windows **hidden** attribute, and
> `open('wb')` fails on an existing hidden file — `install` clears the
> attribute before copying and restores it after.

---

## The worksheet is a dictionary

A material name is a plain label, so — as in `tools.py` — the worksheet
`translation/materials.csv` is a **dictionary** (`source,target`, one row per
distinct name) and `apply` translates by name lookup. **1,876 distinct names**
(material names from every `catalog.xml`, plus the `Tag.Title` tags).

There is **no Japanese oracle** for materials (no localized Japanese catalog on
disk to diff against). Names were translated directly against
[`GLOSSARY.md`](../translation/GLOSSARY.md) plus a material-specific term list.
A name with no translation (an auto-generated `Layer 16`, a pixiv-id import,
`001`) keeps the English — it is left blank-equivalent in the worksheet and
`apply` skips it, so user-created / imported materials stay untouched.

---

## The tooling — `src/materials.py`

```
python src/materials.py backup     copy the catalog DB + every pack's catalog files -> materials/
python src/materials.py extract    distinct material + tag names -> translation/materials.csv
# ... translate the `target` column of materials.csv ...
python src/materials.py apply      write patched copies -> russian-materials/
python src/materials.py install    copy the patched files into the live CSP user data
python src/materials.py restore    copy the originals back
```

* **`materials/`** — the originals: `CatalogMaterial.cmdb` + `catalog/<rel>/…`
  (every pack's `catalog.xml` + `catalogMaterial.cac`). Gitignored.
* **`russian-materials/`** — the patched build, same layout. Gitignored.
* **`translation/materials.csv`** — the dictionary worksheet (`source,target`).
  Tracked in git. Edit `target`, re-run `apply`. `extract` preserves existing
  targets, matched by `source`.
* `install` / `restore` write into `%APPDATA%` — **no elevation needed** — and
  refuse to run while CSP is open (CSP locks the files).

Safeguards: `apply` round-trip-checks every patched `.cac` (the English record
gone, the Russian record present) and the `.cmdb` tags; `backup` refuses a
catalog DB that already holds Cyrillic.

---

## Verified facts & figures

* **1,876 distinct names** translated EN→RU; **1,573 material packs** across
  `Install` + `Install2`.
* `apply` patched the `.cmdb` (127 tags) and 1,573 packs (4,625 material-name
  occurrences in `catalog.xml` + `.cac`); per-`.cac` round-trip checks passed.
* **2026-05-19, installed into a live CSP:** the live `catalog.xml` files read
  back **4,625 Russian** `<name>` values (396 left English — auto-generated /
  imported material names that have no translation, by design).

---

## What is NOT covered

* **Fresh CSP profiles** — the install seed is `clipstudio_assets/*.fto` (an
  unparsed archive); a new profile re-derives English names from it. This method
  patches the existing per-user catalog only.
* **`catalog.zip`** — each pack also has a zipped copy of `catalog.xml`, used
  for cloud sync / re-export, not for display; left English. A cloud "repair"
  of the catalog could in principle regenerate a pack from it.
* **Downloaded materials** — none exist here (`Downloaded = 0` everywhere); a
  user who installs material from CLIP STUDIO ASSETS would get English names for
  it and could re-run `extract → apply → install`.
* macOS / iPad / Android are untested here.

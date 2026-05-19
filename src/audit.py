#!/usr/bin/env python3
"""
audit.py
========
Translation-consistency audit for a `repack.py export` worksheet
(`key,source,target`). It catches the main cross-chunk drift class:

  an English UI term that recurs across many source strings, but is
  translated in some targets and left in English in others.

How it works: for every English word / 2-3-word phrase that occurs in >=5
distinct source rows, count how many of those rows still contain the phrase
verbatim in the target. 0 = consistently translated; all = consistently kept
in English (brand/format/abbr); a mix = INCONSISTENT -> reported.

Usage:  python src/audit.py [worksheet.csv]
        (default: translation/english_742DEA58_strings.csv)
"""
import csv
import re
import sys
import collections

STOP = set(
    "the a an of to in for on at and or is be it as by with from this that "
    "are was not no all any can do if you your when what which while into "
    "out off up down so we our us has have had will".split()
)
WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9']*")


def load(path):
    """Load worksheet rows, skipping intentionally-English-heavy blocks
    (license texts etc.) — a target over 2000 chars is not UI label text."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    kept = [r for r in rows if len(r["target"]) <= 2000]
    if len(kept) != len(rows):
        print(f"(skipped {len(rows) - len(kept)} oversized row(s) — "
              f"license/legal blocks)")
    return kept


def ngrams(words, n):
    return [tuple(words[i:i + n]) for i in range(len(words) - n + 1)]


def main(path):
    # Windows consoles default to a legacy codepage (cp1252) that cannot encode
    # Cyrillic; force UTF-8 so printing translated target text never crashes.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    rows = load(path)
    occ = collections.defaultdict(set)          # term -> set of row indices
    for i, r in enumerate(rows):
        words = WORD.findall(r["source"])
        for n in (1, 2, 3):
            for g in set(ngrams(words, n)):
                occ[g].add(i)

    flagged = []
    for term, idxs in occ.items():
        if len(idxs) < 5:
            continue
        if all(w.lower() in STOP for w in term):
            continue
        if len(term) == 1 and (len(term[0]) < 4 or term[0].lower() in STOP):
            continue
        phrase = " ".join(term)
        pat = re.compile(r"(?<![A-Za-z])" + re.escape(phrase) + r"(?![A-Za-z])", re.I)
        eng = [i for i in idxs if pat.search(rows[i]["target"])]
        if 0 < len(eng) < len(idxs):
            flagged.append((phrase, len(eng), len(idxs), eng))

    # longest phrases first, then by how lopsided (rarer side = likely the bug)
    flagged.sort(key=lambda t: (-len(t[0].split()), min(t[1], t[2] - t[1])))

    print(f"worksheet: {path}  ({len(rows)} rows)")
    print(f"inconsistent terms (translated in some rows, English in others): "
          f"{len(flagged)}\n")
    for phrase, eng, total, eng_idx in flagged:
        minority_is_english = eng <= total - eng
        print(f"=== {phrase!r}  -- English in {eng}/{total} rows")
        show = eng_idx if minority_is_english else \
            [i for i in occ[tuple(phrase.split())] if i not in set(eng_idx)]
        label = "still English:" if minority_is_english else "translated:"
        for i in show[:4]:
            t = rows[i]["target"].replace("\n", " / ")
            print(f"    {label:15} [{rows[i]['key']}] {t[:88]}")
        print()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1
         else "translation/english_742DEA58_strings.csv")

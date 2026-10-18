"""Phrase dictionary matching with nesting (PLAN.md §4.4).

For every dictionary entry and text, we report:
  total       every occurrence (overlapping variants of the SAME entry at the same place count once)
  standalone  occurrences not inside a longer occurrence of a DIFFERENT entry  <- headline number
  nested_in   {parent_phrase_id: count} for the rest (attributed to the longest container)

Matching uses the same normalized token stream as word counting, so punctuation, hyphens,
curly quotes and diacritics never matter. 'match_case' entries additionally require each
capitalized word in the pattern to be capitalized in the text.

Short forms (e.g. 'Elder Cook') are NOT matched here; see cbtn/mentions.py.
"""
from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .tokenize import tokens

TRUE = {"true", "1", "yes", "y"}


@dataclass
class Pattern:
    entry_id: str
    keys: tuple[str, ...]          # folded lower-case token keys
    forms: tuple[str, ...]         # original-case pattern tokens (for match_case)
    match_case: bool


@dataclass
class Entry:
    phrase_id: str
    canonical: str
    variants: list[str]
    short_forms: list[str]
    category: str
    match_case: bool
    ambiguous: bool
    verify: bool
    notes: str
    surname_guard: bool = False      # single first-name entries: skip when a surname follows (Abraham Lincoln)


@dataclass
class Occurrence:
    entry_id: str
    start: int
    end: int          # exclusive, token index


@dataclass
class PhraseCounts:
    total: Counter = field(default_factory=Counter)
    standalone: Counter = field(default_factory=Counter)
    nested_in: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))

    def merge(self, other: "PhraseCounts") -> None:
        self.total.update(other.total)
        self.standalone.update(other.standalone)
        for k, c in other.nested_in.items():
            self.nested_in[k].update(c)


def _split(v: str) -> list[str]:
    return [x.strip() for x in (v or "").split("|") if x.strip()]


def load_dictionary(path: str | Path) -> list[Entry]:
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return [Entry(
        phrase_id=str(r["phrase_id"]), canonical=r["canonical"].strip(),
        variants=_split(r.get("variants", "")), short_forms=_split(r.get("short_forms", "")),
        category=r.get("category", ""), match_case=r.get("match_case", "").lower() in TRUE,
        ambiguous=r.get("ambiguous", "").lower() in TRUE, verify=r.get("verify", "").lower() in TRUE,
        notes=r.get("notes", ""), surname_guard=r.get("surname_guard", "").lower() in TRUE,
    ) for r in rows if r.get("canonical", "").strip()]


class PhraseMatcher:
    def __init__(self, entries: list[Entry]):
        self.entries = {e.phrase_id: e for e in entries}
        self.by_first: dict[str, list[Pattern]] = defaultdict(list)
        for e in entries:
            for text in [e.canonical, *e.variants]:
                toks = tokens(text)
                if not toks:
                    continue
                p = Pattern(e.phrase_id, tuple(k for k, _ in toks), tuple(f for _, f in toks), e.match_case)
                self.by_first[p.keys[0]].append(p)
        for lst in self.by_first.values():
            lst.sort(key=lambda p: -len(p.keys))
        # Adam (CP-2.4): 'Abraham Lincoln', 'Jacob Hamblin', 'Elder Alma Sonne' are not the prophets. Checked on the
        # original text (punctuation still visible): name + whitespace + capitalized word -> blank the name.
        guarded = [e.canonical for e in entries if e.surname_guard]
        self.surname_guard_re = (re.compile(r"\b(?:" + "|".join(map(re.escape, guarded)) +
                                            r")\b(?=[ \t ]+[A-ZÀ-Þ][a-zß-ÿ])")
                                 if guarded else None)

    @classmethod
    def from_csv(cls, path: str | Path) -> "PhraseMatcher":
        return cls(load_dictionary(path))

    def find(self, toks: list[tuple[str, str]]) -> list[Occurrence]:
        keys = [k for k, _ in toks]
        forms = [f for _, f in toks]
        raw: list[Occurrence] = []
        for i, k in enumerate(keys):
            for p in self.by_first.get(k, ()):
                n = len(p.keys)
                if tuple(keys[i:i + n]) != p.keys:
                    continue
                if p.match_case and not all(
                        ((not pf[:1].isupper()) or tf[:1].isupper())
                        and (not (len(pf) > 1 and pf.isupper()) or tf.isupper())     # 'AI' needs all caps, not 'Ai'
                        for pf, tf in zip(p.forms, forms[i:i + n])):
                    continue
                raw.append(Occurrence(p.entry_id, i, i + n))
        # one occurrence per entry per overlapping region: keep longest, left to right
        by_entry: dict[str, list[Occurrence]] = defaultdict(list)
        for o in raw:
            by_entry[o.entry_id].append(o)
        kept: list[Occurrence] = []
        for occs in by_entry.values():
            occs.sort(key=lambda o: (o.start, -(o.end - o.start)))
            last_end = -1
            for o in occs:
                if o.start >= last_end:
                    kept.append(o)
                    last_end = o.end
                elif o.end > last_end and kept and kept[-1].entry_id == o.entry_id:
                    pass  # overlapping variant of same entry: already counted
        return kept

    def count(self, text: str, **tok_kwargs) -> PhraseCounts:
        if self.surname_guard_re is not None:
            text = self.surname_guard_re.sub(lambda m: "_" * len(m.group(0)), text)   # '_' tokens are dropped
        toks = tokens(text, **tok_kwargs)
        occs = self.find(toks)
        pc = PhraseCounts()
        for o in occs:
            pc.total[o.entry_id] += 1
            containers = [c for c in occs if c.entry_id != o.entry_id and c.start <= o.start
                          and c.end >= o.end and (c.end - c.start) > (o.end - o.start)]
            if containers:
                parent = max(containers, key=lambda c: c.end - c.start)
                pc.nested_in[o.entry_id][parent.entry_id] += 1
            else:
                pc.standalone[o.entry_id] += 1
        return pc


def validate_dictionary(entries: list[Entry]) -> list[str]:
    """Rules from Adam's review (PLAN.md §4.4). Returns human-readable problems."""
    problems = []
    seen: dict[tuple, str] = {}
    for e in entries:
        canon = tuple(k for k, _ in tokens(e.canonical))
        for text in [e.canonical, *e.variants]:
            key = tuple(k for k, _ in tokens(text))
            if key in seen and seen[key] != e.phrase_id:
                problems.append(f"#{e.phrase_id} '{text}' duplicates a pattern in #{seen[key]}")
            seen[key] = e.phrase_id
        for v in e.variants:
            vk = tuple(k for k, _ in tokens(v))
            n = len(canon)
            if len(vk) > n and any(vk[i:i + n] == canon for i in range(len(vk) - n + 1)):
                problems.append(f"#{e.phrase_id} variant '{v}' is just a longer version of '{e.canonical}'")
        for field_val in [e.canonical, *e.variants, *e.short_forms, e.category, e.notes]:
            if not field_val.isascii():
                problems.append(f"#{e.phrase_id} has non-ASCII text: {field_val!r}")
    return problems

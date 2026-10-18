"""Resolve short-form mentions such as 'Elder Cook' or 'President Smith' (PLAN.md §5.5).

Steps, tried in order (the step that decided is recorded):
  1 antecedent  the same talk used exactly one matching person's full name earlier
  2 footnote    a note referenced from the same paragraph names exactly one matching person
  3 title_date  exactly one person held that title+surname at the talk date (lower confidence);
                if nobody held it at that date, exactly one person who held it earlier
  4 ambiguous   otherwise -> counted under 'ambiguous: <short form>' and written for review
Overrides: config/mention_overrides.csv (talk_id, paragraph, short_form, person) always win.
"""
from __future__ import annotations

import csv
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .leaders import surname
from .textnorm import for_counting

TITLES = ("Elder", "President", "Bishop", "Sister", "Brother")
# 'President Stephen L Richards': a bare initial without a period also starts a full name
_FULL_NAME_FOLLOWS = re.compile(r"\s+(?:[A-Z]\.|[A-Z]\b(?=\s+[A-Z])|[A-Z\u00C0-\u00DE][^\W\d_]+\b(?!\s*[,.;:!?]?\s*$))")
_NOT_A_SURNAME = {"Brother", "Sister", "Elder", "President", "Bishop"}     # 'our Elder Brother' (the Savior)
# surname may contain O'Brien-style apostrophes or hyphens, but a possessive 's is not part of it ("President Hinckley's")
_SHORT = re.compile(r"\b(Elder|President|Bishop|Sister|Brother)\s+"
                    r"([A-Z\u00C0-\u00DE][^\W\d_]+(?:-[^\W\d_]+|['\u2019](?!s\b)[^\W\d_]+)*)")


@dataclass
class Person:
    name: str
    periods: dict[str, list[tuple[str, str]]] = field(default_factory=lambda: defaultdict(list))  # title -> [(start,end)]

    @property
    def surname_key(self) -> str:
        return for_counting(surname(self.name)).lower()


@dataclass
class Mention:
    short_form: str
    paragraph: int
    offset: int
    person: str | None
    step: str
    confidence: str
    candidates: list[str]


def _norm_date(s: str, end: bool = False) -> str:
    s = (s or "").strip()
    if not s:
        return "9999-12-31" if end else "0000-01-01"
    if re.fullmatch(r"\d{4}", s):
        return f"{s}-12-31" if end else f"{s}-01-01"
    if re.fullmatch(r"\d{4}-\d{2}", s):
        return f"{s}-28" if end else f"{s}-01"
    return s


def build_titles_csv(root: str | Path, out: str | Path) -> Path:
    """Title history for the resolver (PLAN §5.5): reference/leaders/leader_titles.csv (checked against bylines),
    reference/leaders/presidents_pre1945.csv, plus every speaker's byline titles (archive/speaker_titles.csv)."""
    root, out = Path(root), Path(out)
    rows = []
    for src in ("leader_titles.csv", "presidents_pre1945.csv"):
        p = root / "reference/leaders" / src
        if p.exists():
            with open(p, encoding="utf-8-sig", newline="") as f:
                rows += [{"name": r["name"], "title": r["title"], "start": r["start"], "end": r["end"]}
                         for r in csv.DictReader(f)]
    spk, st = root / "archive/speakers.csv", root / "archive/speaker_titles.csv"
    if spk.exists() and st.exists():
        with open(spk, encoding="utf-8-sig", newline="") as f:
            names = {r["speaker_id"]: r["name"] for r in csv.DictReader(f)}
        with open(st, encoding="utf-8-sig", newline="") as f:
            rows += [{"name": names.get(r["speaker_id"], r["speaker_id"]), "title": r["title"],
                      "start": r["from"], "end": r["to"]} for r in csv.DictReader(f) if r["title"] in TITLES]
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["name", "title", "start", "end"])
        w.writeheader()
        w.writerows(rows)
    return out


class Resolver:
    def __init__(self, people: dict[str, Person], overrides: dict[tuple, str] | None = None):
        self.people = people
        self.overrides = overrides or {}
        self.by_surname: dict[str, list[Person]] = defaultdict(list)
        for p in people.values():
            self.by_surname[p.surname_key].append(p)
        # full-name regexes (diacritic-folded, case-insensitive, flexible whitespace/periods)
        self.full_name_re = {
            p.name: re.compile(r"\b" + r"\.?\s+".join(re.escape(part.rstrip("."))
                                                      for part in for_counting(p.name).split()) + r"\b", re.I)
            for p in people.values()}

    @classmethod
    def from_titles_csv(cls, path: str | Path, overrides_path: str | Path | None = None) -> "Resolver":
        people: dict[str, Person] = {}
        with open(path, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                p = people.setdefault(r["name"], Person(r["name"]))
                p.periods[r["title"]].append((_norm_date(r["start"]), _norm_date(r["end"], end=True)))
        overrides = {}
        if overrides_path and Path(overrides_path).exists():
            with open(overrides_path, newline="", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    overrides[(r["talk_id"], int(r["paragraph"]), r["short_form"])] = r["person"]
        return cls(people, overrides)

    def _named_in(self, text: str, cands: list[Person]) -> list[str]:
        t = for_counting(text)
        return [p.name for p in cands if self.full_name_re[p.name].search(t)]

    def resolve_talk(self, talk_id: str, talk_date: str, paragraphs: list[str],
                     para_notes: list[list[str]] | None = None) -> list[Mention]:
        """paragraphs: spoken text; para_notes[i]: texts of notes referenced from paragraph i."""
        para_notes = para_notes or [[] for _ in paragraphs]
        out: list[Mention] = []
        for i, para in enumerate(paragraphs):
            for m in _SHORT.finditer(para):
                title, sur = m.group(1), m.group(2)
                if sur in _NOT_A_SURNAME:
                    continue
                if _FULL_NAME_FOLLOWS.match(para, m.end()):
                    continue          # 'President Dallin H. Oaks' is a full-name mention, not a short form
                form = f"{title} {sur}"
                cands = [p for p in self.by_surname.get(for_counting(sur).lower(), []) if title in p.periods]
                key = (talk_id, i, form)
                if key in self.overrides:
                    out.append(Mention(form, i, m.start(), self.overrides[key], "override", "high", [c.name for c in cands]))
                    continue
                if not cands:
                    out.append(Mention(form, i, m.start(), None, "no_candidate", "none", []))
                    continue
                # 1 antecedent (full name earlier in this talk, including earlier in this paragraph)
                earlier = "\n".join(paragraphs[:i]) + "\n" + para[:m.start()]
                hit = self._named_in(earlier, cands)
                if len(hit) == 1:
                    out.append(Mention(form, i, m.start(), hit[0], "antecedent", "high", [c.name for c in cands]))
                    continue
                # 2 footnote
                hit = self._named_in("\n".join(para_notes[i]), cands)
                if len(hit) == 1:
                    out.append(Mention(form, i, m.start(), hit[0], "footnote", "high", [c.name for c in cands]))
                    continue
                # 3 title + date
                d = _norm_date(talk_date)
                active = [c for c in cands if any(s <= d <= e for s, e in c.periods[title])]
                if len(active) == 1:
                    out.append(Mention(form, i, m.start(), active[0].name, "title_date", "medium", [c.name for c in cands]))
                    continue
                if not active:
                    past = [c for c in cands if any(s <= d for s, _ in c.periods[title])]
                    if len(past) == 1:
                        out.append(Mention(form, i, m.start(), past[0].name, "title_date_historical", "low",
                                           [c.name for c in cands]))
                        continue
                    if not past:   # nobody had this title yet: probably someone not in the tables
                        out.append(Mention(form, i, m.start(), None, "no_candidate_at_date", "none",
                                           [c.name for c in cands]))
                        continue
                # 4 ambiguous
                out.append(Mention(form, i, m.start(), None, "ambiguous", "none", [c.name for c in cands]))
        return out

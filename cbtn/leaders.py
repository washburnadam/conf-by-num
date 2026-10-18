"""Leader roles, dated titles and short-form generation (PLAN.md §5.5).

Inputs (reference/leaders/*_raw.csv, compiled from Wikipedia 2026-10-08, all marked verify):
  apostles_raw.csv, first_presidency_raw.csv, q12_presidents_raw.csv,
  presiding_bishopric_raw.csv, auxiliary_presidents_raw.csv

Output: leader_titles.csv with one row per (person, role, title, start, end).
Talk bylines (Step 1) add more rows with source=byline and override these when they disagree.

Title rules (verify against bylines):
  apostle in the Twelve ............ Elder
  First Presidency member .......... President
  President/Acting Pres. of Twelve . President
  Presiding Bishopric .............. Bishop
  RS / YW / Primary general pres. .. Sister   (President only where bylines show it)
  Sunday School / YM general pres. . Brother, Elder (if a General Authority)
"""
from __future__ import annotations

import csv
import re
from collections import defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path

SUFFIXES = {"jr", "jr.", "sr", "sr.", "ii", "iii"}


def slug(name: str) -> str:
    from .textnorm import fold_diacritics
    return re.sub(r"[^a-z0-9]+", "-", fold_diacritics(name).lower()).strip("-")


def surname(name: str) -> str:
    parts = [p for p in name.replace(",", " ").split() if p.lower() not in SUFFIXES]
    return parts[-1] if parts else name


def _date(s: str) -> str:
    return (s or "").strip()


@dataclass
class TitleRow:
    person_id: str
    name: str
    role: str
    organization: str
    title: str
    start: str
    end: str
    source: str
    verify: str = "true"


def build_titles(ref_dir: str | Path) -> list[TitleRow]:
    ref = Path(ref_dir)
    rows: list[TitleRow] = []

    def read(name):
        with open(ref / name, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    for r in read("apostles_raw.csv"):
        rows.append(TitleRow(slug(r["name"]), r["name"], "Apostle", "Quorum of the Twelve", "Elder",
                             _date(r["ordained"]), _date(r["left"]), "apostles_raw"))
    for r in read("first_presidency_raw.csv"):
        rows.append(TitleRow(slug(r["name"]), r["name"], r["position"], "First Presidency", "President",
                             _date(r["start"]), _date(r["end"]), "first_presidency_raw"))
    for r in read("q12_presidents_raw.csv"):
        rows.append(TitleRow(slug(r["name"]), r["name"], r["role"] + " of the Quorum of the Twelve",
                             "Quorum of the Twelve", "President", _date(r["start"]), _date(r["end"]),
                             "q12_presidents_raw"))
    for r in read("presiding_bishopric_raw.csv"):
        rows.append(TitleRow(slug(r["name"]), r["name"], r["position"], "Presiding Bishopric", "Bishop",
                             _date(r["start"]), _date(r["end"]), "presiding_bishopric_raw"))
    for r in read("auxiliary_presidents_raw.csv"):
        org = r["organization"]
        # 'President <surname>' for auxiliary presidents is recent usage; it is NOT assumed here.
        # Talk bylines (source=byline) add it where the Church actually used it.
        titles = ["Sister"] if org in {"Relief Society", "Young Women", "Primary"} else ["Brother", "Elder"]
        for t in titles:
            rows.append(TitleRow(slug(r["name"]), r["name"], f"{org} General President", org, t,
                                 _date(r["start"]), _date(r["end"]), "auxiliary_presidents_raw"))
    return rows


def write_titles(rows: list[TitleRow], path: str | Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(rows[0]).keys()))
        w.writeheader()
        for r in sorted(rows, key=lambda r: (r.person_id, r.start, r.title)):
            w.writerow(asdict(r))


def short_forms_by_person(rows: list[TitleRow]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        out[r.name].add(f"{r.title} {surname(r.name)}")
    return out


def _year(s: str, default: int) -> int:
    m = re.match(r"(\d{4})", s or "")
    return int(m.group(1)) if m else default


def collisions(rows: list[TitleRow], since: int = 1971) -> list[dict]:
    """Short forms shared by 2+ people whose title periods touch the conference era."""
    by_form: dict[str, dict[str, tuple[int, int]]] = defaultdict(dict)
    for r in rows:
        form = f"{r.title} {surname(r.name)}"
        a, b = _year(r.start, 1800), _year(r.end, 2100)
        lo, hi = by_form[form].get(r.name, (a, b))
        by_form[form][r.name] = (min(lo, a), max(hi, b))
    out = []
    for form, people in sorted(by_form.items()):
        if len(people) > 1:
            out.append({"short_form": form,
                        "people": "; ".join(f"{n} ({a}-{'' if b == 2100 else b})" for n, (a, b) in sorted(people.items())),
                        "overlap_with_conference_era": any(b >= since for _, b in people.values())})
    return out

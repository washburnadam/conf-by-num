"""Conference discovery: index page -> ordered list of talk URLs with sessions (PLAN.md step 1.1).

Session detection: on the conference index the session pages appear as links whose slug
contains 'session'; talks listed after a session link belong to that session. This is an
assumption to VERIFY in step 1.1 (the JSON API may expose sessions directly).
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from bs4 import BeautifulSoup


@dataclass
class Item:
    url: str
    slug: str
    session: str
    order_in_session: int
    order_in_conference: int
    link_text: str


def conference_keys(first: str = "1971-04", last: str = "2026-10") -> list[str]:
    y0, m0 = map(int, first.split("-"))
    y1, m1 = map(int, last.split("-"))
    out = []
    for y in range(y0, y1 + 1):
        for m in (4, 10):
            if (y, m) >= (y0, m0) and (y, m) <= (y1, m1):
                out.append(f"{y:04d}-{m:02d}")
    return out


def parse_index(html: str, year: int, month: int, base_url: str, talk_url_regex: str) -> list[Item]:
    soup = BeautifulSoup(html, "lxml")
    rx = re.compile(talk_url_regex)
    items: list[Item] = []
    seen = set()
    session, in_sess, order = "", 0, 0
    for a in soup.find_all("a", href=True):
        m = rx.search(a["href"])
        if not m or int(m.group(1)) != year or int(m.group(2)) != month:
            continue
        slug = m.group(3)
        if slug in seen:
            continue
        seen.add(slug)
        text = " ".join(a.get_text(" ").split())
        if "session" in slug.lower():
            session, in_sess = text.split("  ")[0][:80] or slug, 0
            continue
        in_sess += 1
        order += 1
        url = base_url.rstrip("/") + f"/study/general-conference/{year:04d}/{month:02d}/{slug}?lang=eng"
        items.append(Item(url, slug, session, in_sess, order, text[:160]))
    return items


def classify(link_text: str, rules: dict[str, str]) -> str:
    """item_type from the index link text (title + speaker), using selectors.yaml item_type_rules.
    Provisional: the parser re-classifies from the page title."""
    for kind, rx in rules.items():
        if re.search(rx, link_text, re.I):
            return kind
    return "talk"


def manifest(conf_key: str, items: list[Item], source: str, rules: dict[str, str] | None = None) -> dict:
    rows = []
    for i in items:
        d = asdict(i)
        d["item_type"] = classify(i.link_text, rules or {})
        rows.append(d)
    by_type: dict[str, int] = {}
    for d in rows:
        by_type[d["item_type"]] = by_type.get(d["item_type"], 0) + 1
    return {"conference": conf_key, "source": source, "items": rows,
            "counts": {"items": len(rows), **by_type}}

"""HTML -> Talk record (PLAN.md §3.1, §3.2 step 1.3).

Selectors come from config/selectors.yaml and are UNVERIFIED until step 1.3.
Key behaviors (verified with a synthetic fixture in tests/, not yet with real pages):
  * footnote markers are removed at the DOM level BEFORE text extraction, recording
    each marker's character offset -> no more 'heart5'
  * notes are parsed separately with their links (scripture tool needs them)
  * paragraphs are tagged body/blockquote/list_item/heading/caption
  * parentheticals are flagged; only high-confidence citations leave spoken_text
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from bs4 import BeautifulSoup, NavigableString, Tag

from .archive import PARSER_VERSION, Paragraph, Speaker, Talk
from .citations import strip_citations
from .leaders import slug as person_slug

_WS = re.compile(r"\s+")

# Adam's "same person" decisions (CP-1.5 speaker review): alias speaker_id -> canonical speaker_id
_ALIAS_FILE = Path(__file__).resolve().parents[1] / "config" / "speaker_aliases.csv"
SPEAKER_ALIASES: dict[str, str] = {}
if _ALIAS_FILE.exists():
    import csv as _csv
    with open(_ALIAS_FILE, encoding="utf-8-sig", newline="") as _f:
        SPEAKER_ALIASES = {r["alias_id"]: r["canonical_id"] for r in _csv.DictReader(_f) if r.get("alias_id")}


def load_selectors(path: str | Path) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def _first(soup, selectors):
    for sel in selectors:
        el = soup.select_one(sel)
        if el is not None:
            return el, sel
    return None, None


def _clean(s: str) -> str:
    return _WS.sub(" ", (s or "").replace(" ", " ")).strip()


def _maybe_json_body(html: str) -> tuple[str, dict, list[dict] | None]:
    """If the input is the JSON API payload, return (body_html, meta, notes); notes come from content.footnotes
    (the JSON body has no notes section). For HTML input notes is None (parsed from the page)."""
    s = html.lstrip()
    if s.startswith("{"):
        d = json.loads(s)
        content = d.get("content", d)
        body = content.get("body") or content.get("html") or ""
        notes = []
        for key, fn in (content.get("footnotes") or {}).items():
            raw_marker = str(fn.get("marker") or "").strip().rstrip(".")
            marker = re.sub(r"\D", "", raw_marker) or raw_marker or re.sub(r"\D", "", key)   # e.g. "1." -> "1", "*" stays
            frag = BeautifulSoup(fn.get("text") or "", "lxml")
            text = re.sub(r"\s+([.,;:!?”’)\]])", r"\1", _clean(frag.get_text(" ")))
            text = re.sub(r"([“‘(\[])\s+", r"\1", text)
            notes.append({"marker": marker, "text": text, "links": [a.get("href") for a in frag.select("a[href]")]})
        notes.sort(key=lambda n: int(n["marker"]) if n["marker"].isdigit() else 0)
        meta = d.get("meta") or {}
        return body, {"input": "json", "canonical_url": meta.get("canonicalUrl")}, notes
    return html, {"input": "html"}, None


def text_with_markers(el: Tag, marker_selectors: list[str]) -> tuple[str, list[dict]]:
    """Extract text, skipping footnote marker elements and recording their offsets."""
    marker_nodes = set()
    for sel in marker_selectors:
        for m in el.select(sel):
            marker_nodes.add(id(m))
    parts: list[str] = []
    refs: list[dict] = []
    length = 0

    def walk(node):
        nonlocal length
        for child in node.children:
            if isinstance(child, NavigableString):
                s = str(child)
                parts.append(s)
                length += len(s)
            elif isinstance(child, Tag):
                if id(child) in marker_nodes:
                    val = child.get("data-value") or child.get("data-marker") or _clean(child.get_text())
                    parent_a = child if child.name == "a" else child.find_parent("a")
                    href = parent_a.get("href") if parent_a is not None else None
                    if not val and href:
                        val = re.sub(r"\D", "", str(href))
                    refs.append({"marker": str(val), "char_offset": length})
                    continue
                if child.name == "br":
                    parts.append(" ")
                    length += 1
                    continue
                walk(child)

    walk(el)
    raw = "".join(parts)
    # normalize whitespace while keeping offsets approximately right (offsets refer to cleaned text)
    cleaned, mapping = [], []
    prev_space = True
    for i, ch in enumerate(raw.replace(" ", " ")):
        if ch.isspace():
            if not prev_space:
                cleaned.append(" ")
                mapping.append(i)
            prev_space = True
        else:
            cleaned.append(ch)
            mapping.append(i)
            prev_space = False
    text = "".join(cleaned).strip()
    lead = len("".join(cleaned)) - len("".join(cleaned).lstrip())

    def remap(off):
        for j, orig in enumerate(mapping):
            if orig >= off:
                return max(0, j - lead)
        return len(text)

    for r in refs:
        r["char_offset"] = remap(r["char_offset"])
    return text, refs


def classify_item(title: str, rules: dict) -> str:
    for kind, rx in (rules or {}).items():
        if re.search(rx, title or "", re.I):
            return kind
    return "talk"


def split_author(name_text: str, titles: list[str]) -> tuple[str, str, str]:
    """'By Elder Gerald Causse' -> ('Elder Gerald Causse', 'Elder', 'Gerald Causse')."""
    s = re.sub(r"^\s*(?:presented\s+)?by\s+", "", _clean(name_text), flags=re.I)   # "Presented by President …"
    for t in titles:
        if s.startswith(t + " "):
            return s, t, s[len(t) + 1:].strip()
    return s, "", s


@dataclass
class ParseContext:
    year: int
    month: int
    url: str
    session: str = ""
    order_in_session: int = 0
    order_in_conference: int = 0


def parse_talk(html: str, ctx: ParseContext, sel: dict) -> Talk:
    body_html, extra, json_notes = _maybe_json_body(html)
    soup = BeautifulSoup(body_html, "lxml")
    used = {}
    flags: list[str] = []

    title_el, used["title"] = _first(soup, sel["title"])
    title = _clean(title_el.get_text()) if title_el else ""
    a_el, used["author_name"] = _first(soup, sel["author_name"])
    r_el, used["author_role"] = _first(soup, sel["author_role"])
    k_el, used["kicker"] = _first(soup, sel["kicker"])
    display, honorific, name = split_author(a_el.get_text() if a_el else "", sel["author_titles"])
    if not name:
        flags.append("no_author")

    # notes first (then remove them from the body so they can't leak into paragraphs)
    notes = json_notes or []
    n_root, used["notes"] = _first(soup, sel["notes"])
    if json_notes is not None:
        used["notes"] = "json:content.footnotes"
    if n_root is not None and json_notes is None:
        items = []
        for s_ in sel["note_item"]:
            items = n_root.select(s_)
            if items:
                break
        for i, li in enumerate(items, 1):
            marker = li.get("data-marker") or li.get("id", "").replace("note", "") or str(i)
            marker = re.sub(r"\D", "", str(marker)) or str(i)
            links = [a.get("href") for a in li.select("a[href]")]
            note_text = re.sub(r"\s+([.,;:!?])", r"\1", _clean(li.get_text(" ")))
            notes.append({"marker": marker, "text": note_text, "links": links})
        n_root.decompose()

    b_root, used["body"] = _first(soup, sel["body"])
    for el in [title_el, a_el, r_el, k_el]:
        if el is not None and b_root is not None and el in b_root.descendants:
            el.extract()
    skip = set(sel.get("skip_classes", []))
    kinds = sel["paragraph_kinds"]
    paragraphs: list[Paragraph] = []
    seen = set()
    if b_root is not None:
        for el in b_root.find_all(["p", "h2", "h3", "h4", "h5", "h6", "li", "figcaption", "blockquote"]):
            if id(el) in seen or skip.intersection(el.get("class", [])):
                continue
            if any(skip.intersection(p.get("class", [])) for p in el.parents if isinstance(p, Tag)):
                continue
            if el.name == "blockquote" and el.find("p"):
                continue                      # its <p> children are handled individually
            if el.find(["p", "li"]) and el.name in ("li",):
                continue
            kind = "body"
            if el.name in ("h2", "h3", "h4", "h5", "h6"):
                kind = "heading"
            elif el.name == "figcaption" or el.find_parent("figcaption") or el.find_parent("figure"):
                kind = "caption"
            elif el.name == "blockquote" or el.find_parent("blockquote"):
                kind = "blockquote"
            elif el.name == "li" or el.find_parent("li"):
                kind = "list_item"
            text, refs = text_with_markers(el, sel["footnote_marker"])
            seen.add(id(el))
            if not text:
                continue
            spoken, found = strip_citations(text) if kind in ("body", "blockquote", "list_item") else (text, [])
            paragraphs.append(Paragraph(
                index=len(paragraphs) + 1, raw_text=text, spoken_text=spoken, kind=kind,
                footnote_refs=refs,
                parentheticals=[{"text": f.text, "char_offset": f.char_offset, "class": f.cls,
                                 "score": f.score, "rule": f.rule} for f in found]))
    else:
        flags.append("no_body")

    note_marks = {n["marker"] for n in notes}
    ref_marks = {r["marker"] for p in paragraphs for r in p.footnote_refs}
    if ref_marks - note_marks:
        flags.append(f"markers_without_note:{','.join(sorted(ref_marks - note_marks, key=lambda x: int(x) if x.isdigit() else 0))}")
    if note_marks - ref_marks:
        flags.append(f"notes_without_marker:{','.join(sorted(note_marks - ref_marks, key=lambda x: int(x) if x.isdigit() else 0))}")
    if not notes:
        flags.append("no_notes_section")

    slug = re.search(r"/(\d{4})/(\d{2})/([^/?#]+)", ctx.url)
    talk_id = f"{ctx.year:04d}-{ctx.month:02d}-{slug.group(3) if slug else person_slug(title)}"
    topics = []
    for s_ in sel.get("site_topics", []):
        for t in soup.select(s_):
            v = t.get("content") or t.get_text()
            topics += [x.strip() for x in str(v).split(",") if x.strip()]
    return Talk(
        talk_id=talk_id, conference={"year": ctx.year, "month": ctx.month}, session=ctx.session,
        order_in_session=ctx.order_in_session, order_in_conference=ctx.order_in_conference, url=ctx.url,
        title=title,
        speaker=Speaker(name_display=display, name=name,
                        speaker_id=SPEAKER_ALIASES.get(person_slug(name), person_slug(name)) if name else "unknown",
                        title=honorific, calling=_clean(r_el.get_text()) if r_el else None),
        item_type=classify_item(title, sel.get("item_type_rules")),
        summary=_clean(k_el.get_text()) if k_el else "",
        site_topics=topics, paragraphs=paragraphs, notes=notes,
        source={"parser_version": PARSER_VERSION, "selectors": used, **extra},
        qa_flags=flags,
    )


def dom_outline(html: str, max_lines: int = 200, text_chars: int = 40) -> str:
    """Compact outline of a page for agents (PLAN.md §0.2): tag, id, classes, a little text."""
    body_html, _ = _maybe_json_body(html)
    soup = BeautifulSoup(body_html, "lxml")
    lines: list[str] = []

    def walk(node, depth):
        if len(lines) >= max_lines:
            return
        for ch in node.children:
            if isinstance(ch, Tag):
                if ch.name in ("script", "style", "svg", "noscript"):
                    continue
                own = _clean("".join(s for s in ch.strings))[:text_chars]
                cls = ".".join(ch.get("class", []))
                attrs = "".join(f"[{k}]" for k in ch.attrs if k.startswith("data-"))
                lines.append(f"{'  ' * depth}<{ch.name}{'#' + ch['id'] if ch.get('id') else ''}"
                             f"{'.' + cls if cls else ''}{attrs}> {own!r}")
                walk(ch, depth + 1)

    walk(soup.body or soup, 0)
    return "\n".join(lines[:max_lines])

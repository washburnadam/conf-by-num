"""Parenthetical flagging (PLAN.md §3.2 step 1.3, decision #1).

Every '( ... )' in a paragraph is recorded and classified:
  citation   high confidence reference -> removed from spoken_text
  uncertain  some reference features    -> kept in spoken_text, listed for review
  spoken     no reference features      -> kept

Rules are deliberately simple and transparent; refine them in docs/citation_rules.md and
re-run `cbtn citations review`. Minor errors are acceptable (small share of text).
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

BOOKS = [
    # Old Testament
    "Genesis", "Gen", "Exodus", "Ex", "Exod", "Leviticus", "Lev", "Numbers", "Num", "Deuteronomy", "Deut",
    "Joshua", "Josh", "Judges", "Judg", "Ruth", "1 Samuel", "2 Samuel", "1 Sam", "2 Sam", "1 Kings", "2 Kings",
    "1 Chronicles", "2 Chronicles", "1 Chr", "2 Chr", "Ezra", "Nehemiah", "Neh", "Esther", "Job", "Psalms",
    "Psalm", "Ps", "Proverbs", "Prov", "Ecclesiastes", "Eccl", "Song of Solomon", "Isaiah", "Isa", "Jeremiah",
    "Jer", "Lamentations", "Lam", "Ezekiel", "Ezek", "Daniel", "Dan", "Hosea", "Joel", "Amos", "Obadiah",
    "Jonah", "Micah", "Nahum", "Habakkuk", "Zephaniah", "Haggai", "Zechariah", "Zech", "Malachi", "Mal",
    # New Testament
    "Matthew", "Matt", "Mark", "Luke", "John", "Acts", "Romans", "Rom", "1 Corinthians", "2 Corinthians",
    "1 Cor", "2 Cor", "Galatians", "Gal", "Ephesians", "Eph", "Philippians", "Philip", "Colossians", "Col",
    "1 Thessalonians", "2 Thessalonians", "1 Thes", "2 Thes", "1 Timothy", "2 Timothy", "1 Tim", "2 Tim",
    "Titus", "Philemon", "Hebrews", "Heb", "James", "1 Peter", "2 Peter", "1 Pet", "2 Pet", "1 John", "2 John",
    "3 John", "Jude", "Revelation", "Rev",
    # Book of Mormon
    "1 Nephi", "2 Nephi", "3 Nephi", "4 Nephi", "1 Ne", "2 Ne", "3 Ne", "4 Ne", "Jacob", "Enos", "Jarom",
    "Omni", "Words of Mormon", "W of M", "Mosiah", "Alma", "Helaman", "Hel", "Mormon", "Morm", "Ether",
    "Moroni", "Moro",
    # D&C / Pearl of Great Price
    "D&C", "D & C", "Doctrine and Covenants", "Official Declaration", "Moses", "Abraham", "Abr",
    "Joseph Smith—Matthew", "Joseph Smith-Matthew", "JS-M", "Joseph Smith—History", "Joseph Smith-History",
    "JS-H", "JS—H", "Articles of Faith", "A of F", "JST",
    # abbreviations seen in CP-1.3 review
    "JS—M", "JS–M", "1 Jn", "2 Jn", "3 Jn", "Jn", "Esth", "1 Kgs", "2 Kgs", "1 Chron", "2 Chron", "Hab", "Hag",
    "Zeph", "Obad", "Mic", "Nah", "Philem", "Jas", "1 Thess", "2 Thess", "1 Jn",
]
_BOOK_RE = "|".join(sorted((re.escape(b) for b in BOOKS), key=len, reverse=True))
SCRIPTURE_REF = re.compile(rf"\b(?:{_BOOK_RE})\.?\s+\d+(?::\d+(?:[-–,]\s?\d+)*)?", re.I)
DC_SECTION = re.compile(r"\b(?:D\s?&\s?C|Doctrine and Covenants|Doc\.?\s?(?:&|and)\s?Cov\.?)\s+\d+", re.I)
SOURCE_WORDS = re.compile(
    r"Conference Report|Ensign|Liahona|New Era|Friend|Improvement Era|Church News|Journal of Discourses|"
    r"History of the Church|Teachings of|Gospel Doctrine|Discourses of|Times and Seasons|Millennial Star|"
    r"Deseret News|Gospel Library|General Handbook|BYU|Brigham Young University|speeches\.byu|devotional|fireside|Handbook|"
    r"Hymns?,? no\.|Children's Songbook|Preach My Gospel|Bible Dictionary|Guide to the Scriptures|Topical Guide|"
    r"see also|^\s*see\b|^\s*cf\.",
    re.I)
PAGE_VOL = re.compile(r"\b(?:p|pp|vol|ed|no|chap|ch)\.\s?\d+", re.I)
YEAR_ONLY = re.compile(r"^\s*(?:1[89]\d\d|20\d\d)\s*$")
YEAR_ANY = re.compile(r"\b(?:1[89]\d\d|20\d\d)\b")
ANNOTATION = re.compile(r"^\s*(?:ibid\.?|italics added\.?|emphasis added\.?|emphasis in original\.?|"
                        r"paragraphing altered|capitalization standardized|spelling standardized|"
                        r"punctuation standardized)[\s.;,]*$", re.I)
ANNOTATION_ANY = re.compile(r"italics added|emphasis added|emphasis in original|\bibid\b|"
                            r"(?:spelling|punctuation|capitalization) (?:and \w+ )?standardized", re.I)
MONTHS = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sept?(?:ember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?"
DATE = re.compile(rf"\b{MONTHS}\s+(?:\d{{1,2}},?\s+)?(?:1[6-9]\d\d|20\d\d)\b")
BRACKET_YEAR = re.compile(r"\[(?:1[6-9]\d\d|20\d\d)\]")      # book citation style: Title [1983], 7-10
QUOTED_TITLE_LOCATOR = re.compile(r"[\"\u201c][^\"\u201d]{2,150}[,.]?[\"\u201d]\s*,?.*\d")
TITLE_PAGE = re.compile(r"^[A-Z][\w'\u2019 .&:-]{2,120}[A-Za-z.],\s+\d+(?:[-\u2013]\d+)?\.?\s*$")
PUBLISHER = re.compile(r"\b[A-Z][a-z]+(?: [A-Z][a-z]+)*:\s.+\b(?:1[89]\d\d|20\d\d)\b")
URL = re.compile(r"\b[\w-]+\.(?:com|org|net|edu|gov)\b|https?://", re.I)
PAREN = re.compile(r"\(([^()]{1,300})\)")
# any "Abbr. 3:11" style reference whose book isn't in BOOKS (CP-1.3: the list will never be complete)
SCRIPTURE_GENERIC = re.compile(r"^\s*(?:[1-4]\s)?[A-Z][A-Za-z—–-]{0,12}\.?\s+\d+:\d+")
PLAY_REF = re.compile(r"\bact\s+(?:\d+|[IVX]+)\b|\bsc\.\s*\d|,\s*[IVX]+,\s*[ivx]+\b")    # (Hamlet, act 1, sc. 3.)
# Adam (CP-1.3): spoken parentheticals are inserted phrases or clauses, never names, labels, single words or refs.
_LOWER_WORD = re.compile(r"\b[a-z][a-z’']*\b")

OVERRIDES_FILE = Path(__file__).resolve().parents[1] / "config" / "parenthetical_overrides.csv"


def _load_overrides() -> dict[str, str]:
    """Exact-text decisions by Adam that no rule captures (config/parenthetical_overrides.csv)."""
    if not OVERRIDES_FILE.exists():
        return {}
    with open(OVERRIDES_FILE, encoding="utf-8", newline="") as f:
        return {r["text"].strip(): r["class"].strip() for r in csv.DictReader(f) if r.get("text")}


OVERRIDES = _load_overrides()


def is_inserted_phrase(s: str) -> bool:
    """Spoken parenthetical: a phrase/clause starting lowercase (2+ words), or a full sentence
    (3+ words, ends . ! ?, at least 3 lowercase words; CP-1.5 spot check: "(I am still learning!)")."""
    words = s.split()
    if len(words) >= 2 and s[:1].islower():
        return True
    return len(words) >= 3 and s.rstrip()[-1:] in ".!?" and len(_LOWER_WORD.findall(s)) >= 3


@dataclass
class Parenthetical:
    text: str            # including the parentheses
    char_offset: int
    cls: str             # citation | uncertain | spoken
    score: float
    rule: str


def classify(inner: str) -> tuple[str, float, str]:
    s = inner.strip()
    if s in OVERRIDES:
        return OVERRIDES[s], 1.0, "override"
    if ANNOTATION.match(s):
        return "citation", 0.9, "annotation"
    if SCRIPTURE_REF.search(s) or DC_SECTION.search(s):
        return "citation", 0.95, "scripture_ref"
    if SCRIPTURE_GENERIC.match(s):
        return "citation", 0.85, "scripture_ref_generic"
    if PLAY_REF.search(s):
        return "citation", 0.85, "play_ref"
    if re.match(r"\s*(?:see|cf\.)\s", s, re.I) and (re.search(r"\d", s) or re.search(r"\b[A-Z][a-z]+", s[4:])):
        return "citation", 0.8, "see_reference"
    if SOURCE_WORDS.search(s) and (re.search(r"\d", s) or ":" in s):
        return "citation", 0.9, "source_with_locator"
    if PAGE_VOL.search(s):
        return "citation", 0.8, "page_or_volume"
    if QUOTED_TITLE_LOCATOR.search(s):
        return "citation", 0.85, "quoted_title_with_locator"
    if DATE.search(s):
        return "citation", 0.75, "dated_source"
    if BRACKET_YEAR.search(s):
        return "citation", 0.8, "bracket_year"
    if PUBLISHER.search(s):
        return "citation", 0.75, "publisher_place_year"
    if URL.search(s):
        return "citation", 0.8, "url"
    if TITLE_PAGE.match(s):
        return "citation", 0.7, "title_page"
    if ANNOTATION_ANY.search(s):
        return "citation", 0.7, "annotation_in_text"
    if re.fullmatch(r"\d{1,2}|[a-z]|[ivx]{1,4}", s):
        return "citation", 0.5, "enumerator"                    # list numbering like (1), (a), (iv): not spoken
    if YEAR_ONLY.match(s):
        return "citation", 0.6, "year_only"                    # Adam (CP-1.3): year-only refs are not spoken
    if is_inserted_phrase(s):
        return ("uncertain", 0.5, "source_word_in_phrase") if SOURCE_WORDS.search(s) else \
               ("spoken", 0.1, "inserted_phrase")
    if SOURCE_WORDS.search(s):
        return "citation", 0.6, "source_word"
    return "citation", 0.5, "name_label_or_word"             # names, labels, single words, numbers


BRACKET = re.compile(r"\[([^\[\]]{1,300})\]")
# Square brackets are usually editor's insertions, which Adam counts as spoken (CP-1.5). Only these high-confidence
# rules turn a bracket into a citation ("[Gospel Doctrine, p. 304.]", "[Isa. 5:20]") (CP-2.4).
BRACKET_CITATION_RULES = {"scripture_ref", "scripture_ref_generic", "page_or_volume", "source_with_locator",
                          "quoted_title_with_locator", "play_ref", "see_reference", "annotation",
                          "annotation_in_text", "title_page", "url", "publisher_place_year", "bracket_year"}


def find_parentheticals(text: str) -> list[Parenthetical]:
    out = []
    for m in PAREN.finditer(text):
        cls, score, rule = classify(m.group(1))
        out.append(Parenthetical(m.group(0), m.start(), cls, score, rule))
    for m in BRACKET.finditer(text):
        cls, score, rule = classify(m.group(1))
        if cls == "citation" and rule in BRACKET_CITATION_RULES:
            out.append(Parenthetical(m.group(0), m.start(), "citation", score, "bracket_" + rule))
    out.sort(key=lambda p: p.char_offset)
    # a bracket inside a removed parenthetical (or vice versa) must not be cut twice
    kept, end = [], -1
    for p in out:
        if p.cls == "citation" and p.char_offset < end:
            continue
        kept.append(p)
        if p.cls == "citation":
            end = p.char_offset + len(p.text)
    return kept


def strip_citations(text: str) -> tuple[str, list[Parenthetical]]:
    """Return text with 'citation' parentheticals removed (others kept) plus all findings."""
    found = find_parentheticals(text)
    out, last = [], 0
    for p in found:
        if p.cls == "citation":
            out.append(text[last:p.char_offset])
            last = p.char_offset + len(p.text)
    out.append(text[last:])
    cleaned = re.sub(r"\s+([,.;:!?])", r"\1", re.sub(r"[ \t]{2,}", " ", "".join(out))).strip()
    return cleaned, found

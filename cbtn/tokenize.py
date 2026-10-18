"""Word tokenizer and histogram counting (PLAN.md §4.1).

Rules
- Apostrophes are part of words; every other non-letter/non-digit character is a boundary
  (hyphens included: "Latter-day" -> "latter", "day").
- Case-insensitive counting; the display form is the most common original spelling.
- Diacritics folded for counting.
- A token must contain a letter.
- Digit-bearing tokens: ordinals (5th, 21st, 2nd, 3d) and decades (1830s, '80s, 80s) are kept;
  everything else with a digit (A1, MP3, 13a, 23ff) is dropped. Decisions can be overridden
  per token in config/digit_tokens.csv (columns: token, decision[keep|drop]).
- Footnote backstop: 'heart5' where 5 is a footnote marker in the paragraph -> 'heart' (logged).
- Web addresses (TempleSquare.org, www.x.com, https://...) are not counted (Adam, CP-5.3, 2026-10-11; logged).
"""
from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .textnorm import fold_diacritics, normalize_chars

# A raw token: letters/digits with internal apostrophes.
_RAW = re.compile(r"[^\W_]+(?:'[^\W_]+)*'?", re.UNICODE)
_ORDINAL = re.compile(r"^\d+(st|nd|rd|th|d)$", re.I)
_DECADE = re.compile(r"^'?\d{2}(\d{2})?s$", re.I)
_URL = re.compile(r"(?:https?://|www\.)\S+|\b[\w-]+(?:\.[\w-]+)*\.(?:org|com|net|edu|gov|io|info|tv|app)\b(?:/\S*)?",
                  re.I | re.UNICODE)
_GLUED_MARKER = re.compile(r"^([^\W\d_]+(?:'[^\W\d_]+)*)(\d{1,3})$", re.UNICODE)


@dataclass
class DigitPolicy:
    overrides: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path | None) -> "DigitPolicy":
        if not path or not Path(path).exists():
            return cls()
        with open(path, newline="", encoding="utf-8") as f:
            return cls({r["token"].lower(): r["decision"].strip().lower() for r in csv.DictReader(f)})

    def keep(self, tok_lower: str) -> bool:
        if tok_lower in self.overrides:
            return self.overrides[tok_lower] == "keep"
        return bool(_ORDINAL.match(tok_lower) or _DECADE.match(tok_lower))


@dataclass
class TokenizeLog:
    marker_splits: list[tuple[str, str]] = field(default_factory=list)   # (original, kept_word)
    digit_dropped: Counter = field(default_factory=Counter)
    digit_kept: Counter = field(default_factory=Counter)
    url_dropped: Counter = field(default_factory=Counter)


def raw_tokens(text: str) -> list[str]:
    """Tokens in original case (after char normalization, before folding)."""
    t = normalize_chars(text)
    out = []
    for m in _RAW.finditer(t):
        tok = m.group(0).strip("'")
        # keep a leading apostrophe only for decades like '80s
        if m.group(0).startswith("'") and _DECADE.match(m.group(0)):
            tok = m.group(0)
        if tok:
            out.append(tok)
    return out


def tokens(text: str, *, markers: Iterable[str] = (), policy: DigitPolicy | None = None,
           log: TokenizeLog | None = None) -> list[tuple[str, str]]:
    """Return (count_key, display_form) pairs for countable tokens."""
    policy = policy or DigitPolicy()
    markers = {str(m) for m in markers}
    out: list[tuple[str, str]] = []
    if "." in text or "//" in text:
        for m in _URL.finditer(text):
            if log is not None:
                log.url_dropped[m.group(0).rstrip(".,;:)!?”\"'")] += 1
        text = _URL.sub(" ", text)
    for tok in raw_tokens(text):
        if any(ch.isdigit() for ch in tok):
            g = _GLUED_MARKER.match(tok)
            if g and markers and g.group(2) in markers:
                if log is not None:
                    log.marker_splits.append((tok, g.group(1)))
                tok = g.group(1)
            else:
                low = tok.lower()
                if not any(ch.isalpha() for ch in tok):
                    continue                      # pure number
                if policy.keep(low):
                    if log is not None:
                        log.digit_kept[low] += 1
                else:
                    if log is not None:
                        log.digit_dropped[low] += 1
                    continue
        key = fold_diacritics(tok).lower()
        out.append((key, tok))
    return out


@dataclass
class Histogram:
    counts: Counter = field(default_factory=Counter)
    forms: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))
    talks: dict[str, set] = field(default_factory=lambda: defaultdict(set))
    speakers: dict[str, set] = field(default_factory=lambda: defaultdict(set))

    def add(self, text: str, *, talk_id: str = "", speaker_id: str = "", markers=(),
            policy: DigitPolicy | None = None, log: TokenizeLog | None = None) -> None:
        for key, form in tokens(text, markers=markers, policy=policy, log=log):
            self.counts[key] += 1
            self.forms[key][form] += 1
            if talk_id:
                self.talks[key].add(talk_id)
            if speaker_id:
                self.speakers[key].add(speaker_id)

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    def display(self, key: str) -> str:
        """Most common original spelling, lower-cased unless it is mostly capitalized mid-text.
        Legacy histograms were all lower case; we keep lower case for comparability and expose
        the most common form separately."""
        return self.forms[key].most_common(1)[0][0] if self.forms.get(key) else key

    def rows(self):
        total = self.total or 1
        for rank, (key, n) in enumerate(sorted(self.counts.items(), key=lambda kv: (-kv[1], kv[0])), 1):
            yield {
                "rank": rank, "word": key, "display": self.display(key), "count": n,
                "rate_per_10k": round(n / total * 10000, 4),
                "talks_using": len(self.talks.get(key, ())),
                "speakers_using": len(self.speakers.get(key, ())),
            }

    def write_csv(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = list(self.rows())
        with open(path, "w", newline="", encoding="utf-8-sig") as f:      # BOM: Excel shows accents correctly
            w = csv.DictWriter(f, fieldnames=["rank", "word", "display", "count", "rate_per_10k",
                                              "talks_using", "speakers_using"])
            w.writeheader()
            w.writerows(rows)

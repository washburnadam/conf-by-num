"""Character normalization shared by every counting step.

Two layers:
  normalize_chars(text)  -> fixes ligatures, quotes, dashes, invisible characters.
                            Keeps letters (including diacritics) so the archive text
                            stays faithful. Safe for display.
  fold_diacritics(text)  -> strips accents for COUNTING only (Causse == Causse with accent).

Rules come from PLAN.md §4.1 and the legacy pipeline notes (ligatures, UTF-8, curly quotes).
NFKC is deliberately NOT used: it turns superscript digits into ordinary digits, which would
re-create the "heart5" footnote problem.
"""
from __future__ import annotations

import re
import unicodedata

# Typographic ligatures -> letters (required fix; the April 2026 legacy histogram had "beneﬁt").
LIGATURES = {
    "ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi",
    "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st",
    "Ĳ": "IJ", "ĳ": "ij", "Œ": "OE", "œ": "oe",
    "Æ": "AE", "æ": "ae",
}

# Apostrophe-like characters -> straight apostrophe (kept as part of words).
APOSTROPHES = {"’": "'", "‘": "'", "ʼ": "'", "′": "'", "＇": "'", "`": "'"}

# Characters that become a plain space (word boundaries / invisible junk).
TO_SPACE = {
    " ", " ", " ", " ", " ", " ", " ", " ",
    " ", " ", " ", " ", "　",            # spaces
    "—", "–", "‒", "―", "−", "‐", "‑",  # dashes/hyphens
    "…",                                                     # ellipsis
    "“", "”", "„", "«", "»",             # double quotes
}
# Zero-width / formatting characters are deleted (they sit inside words).
DELETE = {"﻿", "​", "‌", "‍", "⁠", "­"}

# Superscript / subscript digits: footnote markers that survived extraction become spaces,
# never digits, so they cannot glue onto words.
SUPERSCRIPTS = {ch: " " for ch in "¹²³⁰⁴⁵⁶⁷⁸⁹"
                "₀₁₂₃₄₅₆₇₈₉"}

_TABLE = {ord(k): v for k, v in LIGATURES.items()}
_TABLE.update({ord(k): v for k, v in APOSTROPHES.items()})
_TABLE.update({ord(k): " " for k in TO_SPACE})
_TABLE.update({ord(k): None for k in DELETE})
_TABLE.update({ord(k): v for k, v in SUPERSCRIPTS.items()})


def normalize_chars(text: str) -> str:
    """Display-safe normalization (keeps diacritics)."""
    if not text:
        return ""
    # editorial letters inside a word: "[s]he" -> "she", "[a]nd" -> "and", "Savior[s]" -> "Saviors" (CP-2.4)
    text = _BRACKET_IN_WORD.sub(lambda m: m.group(1) or m.group(2), text)
    return text.translate(_TABLE)


_BRACKET_IN_WORD = re.compile(r"(?<=[^\W\d_])\[([^\W\d_]{1,3})\]|\[([^\W\d_]{1,3})\](?=[^\W\d_])")


def fold_diacritics(text: str) -> str:
    """Remove accents: 'Caussé' -> 'Causse'. Used only for counting/matching."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def for_counting(text: str) -> str:
    return fold_diacritics(normalize_chars(text))

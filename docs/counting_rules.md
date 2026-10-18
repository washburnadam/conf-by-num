# Counting rules (implemented in cbtn/textnorm.py, cbtn/tokenize.py, cbtn/phrases.py)

## What is counted
- `spoken_text` of paragraphs with kind `body`, `blockquote`, `list_item`, in items with `item_type = talk`.
- Never: titles, teasers/summaries, speaker names, callings, notes, headings, captions, sustainings,
  reports, session videos, high-confidence parenthetical citations.

## Characters (normalize_chars)
- Ligatures → letters: ﬀ ff, ﬁ fi, ﬂ fl, ﬃ ffi, ﬄ ffl, ﬅ/ﬆ st (also Æ/æ, Œ/œ, Ĳ/ĳ).
- Curly/typographic apostrophes → `'` (kept inside words).
- Dashes, ellipses, double quotes, non-breaking and other spaces → space.
- Zero-width characters, soft hyphens, BOM → deleted.
- Superscript digits → space (never glue onto words). NFKC is deliberately not used.

## Tokens
- Token = letters/digits with internal apostrophes; leading/trailing apostrophes stripped.
- Hyphens split words (`Latter-day` → `latter`, `day`) — same as legacy.
- Counting key = lower case + diacritics folded (`Caussé` = `Causse`). Display form = most common spelling.
- Must contain a letter. Digit-bearing tokens: ordinals (`5th`, `21st`, `3d`) and decades (`1830s`, `80s`)
  kept; others (`A1`, `MP3`, `13a`, `23ff`) dropped. Overrides: config/digit_tokens.csv (token,decision).
- Footnote backstop: `word14` whose number is a footnote marker in the same paragraph → `word` (logged).
- Web addresses (`TempleSquare.org`, `www.lds.org`, `https://…`) are not counted (Adam, CP-5.3, 2026-10-12);
  every one is logged to `reports/url_dropped.csv` by `cbtn histogram`.

## Verified 2026-10-08 against Adam's April 2026 files
Run on ConferenceCapture_Apr2026.xlsx rows 5+: total 42,341 words — identical to WordHistogram_Apr2026.xlsx.
All 50 differing entries are ligature fixes (beneﬁt, ﬁnancial) and diacritic folding (23 names, e.g. Caussé).
Unique words 4,580 → 4,576. (`python tools/regress_apr2026.py`)

## Phrases
- Same token stream; variants roll up to the canonical entry; one count per span per entry.
- total / standalone (not inside a longer *different* entry) / nested_in. Standalone is the headline.
- `match_case` entries require capitalized pattern words to be capitalized in the text.
- Short forms ("Elder Cook") are not counted here — see cbtn/mentions.py and PLAN §5.5.

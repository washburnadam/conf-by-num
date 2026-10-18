# Conference by the Numbers

A word-by-word look at the General Conferences of The Church of Jesus Christ of Latter-day Saints,
from 1971 to today. Each conference is compared with every conference before it, to show which words
and phrases the speakers emphasized.

- **Interactive site:** https://washburnadam.github.io/conf-by-num/
- **Articles:** [Conference by the Numbers on Medium](https://adamlwashburn.medium.com/) ·
  earlier editions (2014–2020) at [visualscriptures.blogspot.com](https://visualscriptures.blogspot.com/)

## What's in this repository
| Folder | Contents |
|---|---|
| `cbtn/` | Python code to download, clean, count and analyze talks, and to draw the charts |
| `tools/` | The infographic builder (`conference_poster.py`: PNG, editable PowerPoint and interactive HTML) and the Medium header images |
| `config/` | Phrase dictionary, analysis settings, word lists, topic groups for the bubble chart |
| `docs/` | Method, counting rules, citation rules and chart style |
| `data/` | Derived numbers per conference: word and phrase counts, emphasized words, unique words, talk list, and word trends since 1971. **No talk text.** |
| `reference/` | Church leaders and their titles over time (used to identify speakers and mentions) |
| `site/` | The interactive web pages (published with GitHub Pages) |
| `tests/` | Automated checks |

## Method in brief
1. **Spoken words only.** The code counts what speakers said. It excludes titles, summaries, footnotes,
   inline references like "(D&C 121:45)", headings, captions and web addresses.
2. **Careful counting.** Footnote markers are removed before counting, so they don't stick to words.
   Typographic ligatures (ﬁ → fi) and accents (Caussé = Causse) are normalized. Apostrophes stay with their
   words (Savior's), and hyphenated words are split.
3. **Compare with the past.** A word's rate per 10,000 words in a conference is compared with its average
   rate across all earlier conferences. Among the 300 most-used words of a conference, a word used at least
   twice as often as usual (+100%) counts as *emphasized*. The list is reviewed by hand to remove noise
   (names, everyday words, near-duplicates).
4. **Phrases too.** About 380 phrases are tracked, such as "covenant path" and "Book of Mormon", along with
   leaders' names. A phrase found inside a longer one ("Jesus Christ" inside "Church of Jesus Christ of
   Latter-day Saints") is counted separately from standalone uses. Phrases used at least twice as often as
   usual and at least 10 times appear with the emphasized words.

Details are in [`docs/`](docs/).

## Reproduce the analysis
This repository does not include talk text. The code downloads it for you from the Church's website,
politely (one request every 1–2 seconds, with a cache so each page is downloaded once).

    pip install -r requirements.txt
    python -m cbtn.cli discover --all
    python -m cbtn.cli fetch --all
    python -m cbtn.cli parse --all
    python -m cbtn.cli histogram --all
    python -m cbtn.cli db rebuild
    python -m cbtn.cli analyze 2026-10
    python tools/conference_poster.py 2026-10
    python -m pytest -q

You're responsible for using the Church's website in line with its terms of use.

## Licenses
- **Code:** MIT (see LICENSE).
- **Derived data and charts** (`data/`, `site/`, images): CC BY 4.0 (see LICENSE-DATA).
  Please credit "Conference by the Numbers, Adam Washburn".
- **Leader reference tables** (`reference/leaders/`): compiled from Wikipedia, CC BY-SA 4.0
  (sources in `reference/leaders/SOURCES.md`).

## Disclaimer
This is an independent personal project. It is not affiliated with or endorsed by The Church of Jesus
Christ of Latter-day Saints. General Conference talks are © Intellectual Reserve, Inc. and are not
redistributed here. Talk titles and speaker names link to the official talk pages.

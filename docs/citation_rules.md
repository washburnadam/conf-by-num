# Parenthetical citation rules (cbtn/citations.py) — version 0.2 (2026-10-08)

Every `( … )` is recorded with class, score and rule. Only `citation` is removed from spoken_text.

| Rule | Class | Example |
|---|---|---|
| annotation | citation | (emphasis added) (Ibid.) |
| scripture_ref | citation | (D&C 121:45) (see 2 Ne. 31:18) (Matt. 22:36–37) |
| see_reference | citation | (see verse 17) (see Harper, Making Sense…, 75) |
| source_with_locator | citation | (Ensign, Nov. 1988, p. 4) (Teachings of Gordon B. Hinckley, 94) |
| page_or_volume | citation | (p. 469) (CR, April 1954, pp. 11–12) |
| quoted_title_with_locator | citation | (“Temples and Work Therein,” Ensign, Nov. 1990, 61) |
| dated_source | citation | (address given at …, June 25, 2021); years 1600–2099 (CP-1.3: 1789 was missed) |
| bracket_year | citation | (As a Man Thinketh [1983], 7–10) (added CP-1.3) |
| scripture_ref_generic | citation | (Esth. 4:8) — any "Abbr. 3:11" form not in the book list (CP-1.3) |
| play_ref | citation | (Hamlet, act 1, sc. 3.), (King Lear, I, iv, 312) (CP-1.3) |
| year_only | citation | (1948) — Adam, CP-1.3: not spoken |
| inserted_phrase | spoken | (and heaven help us not to fail), (Mount Vernon, of course, was …) |
| name_label_or_word | citation | (Jenkins Lloyd Jones.), (Membership), (Allah), (1) |
| override | as listed | config/parenthetical_overrides.csv, e.g. (Adam’s) → spoken |

**Adam's rule (CP-1.3):** a parenthetical is spoken only when it is an inserted phrase or clause: it starts lowercase
(2+ words), or it is a full sentence (3+ words, ends . ! ?, 3+ lowercase words; lowered from 5 after the CP-1.5
spot check found "(I am still learning!)"). Bare list numbers "(1)", "(a)" are labeled `enumerator` (not spoken). Names, shortened sources, labels,
single words, numbers and references are not spoken. Exceptions go in the override file.
| publisher_place_year | citation | (Salt Lake City: Bookcraft, 1966) |
| url | citation | (see latin-english.com) |
| title_page | citation | (Church History in the Fulness of Times, 257) |
| annotation_in_text | citation | (Lectures on Faith, 6:8; italics added) |
| source_word_only | uncertain | (see it) — kept, listed for review |
| year_only | uncertain | (1966) — kept (pure numbers are never counted anyway) |
| no_reference_features | spoken | (perhaps a little cynically) (and I remember it well) |

## Trial on the legacy text (1971–April 2026, 4,202 talks; legacy source, so approximate)
- 26,596 citations, 2,648 spoken, 1,266 uncertain.
- Inline citations by decade: 1970s 6,596 · 1980s 7,376 · 1990s 6,136 · 2000s 3,811 · 2010s 2,144 · 2020s 533
  (footnotes gradually replaced inline references).
- Effect on the old corpus: "see" −6,200, "c"/"d" (from D&C) −6,000 each, "ne" −2,200, "matt" −1,700,
  "ensign" −1,100 … (reports/preview_corpus_diff.csv).

## To refine (CP-1.3)
Run `python -m cbtn.cli citations review --all` on the fresh import; scan reports/citations_review.csv
(spoken + uncertain); add or adjust rules here and in citations.py; re-run.

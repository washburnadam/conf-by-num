# Analysis method — learned from Adam's workbooks (CP-4.1, 2026-10-11; for Adam to confirm)

Sources: `inputs/prior_analyses/{Apr2021,Apr2025,Oct2025,Apr2026} Conference vs All Conference.xlsx`, profiled by
`tools/profile_analyses.py` (sheet layouts, formulas, small sheets → `reports/analysis_profile/*.txt`) and
`tools/infer_removals.py` (what was removed by hand). Apr2026's Final Data/Graph are a copy of Oct2025 (save-as),
so Apr2025 and Apr2021 are the reference cases. Earlier notes from the published articles are kept at the end.

## 1. What the workbooks do (sheet by sheet)
| Sheet | What it holds | Key formula |
|---|---|---|
| Original Data | A–C: target conference histogram (#, word, freq; Apr2025: 52,414 words, 5,540 unique). H–K: Wiktionary general lexicon (freq per billion). O–T: all-conference corpus with a "Corrected" column: the corpus count minus a 37-word **title-word list** (V–W: Acting, Apostles, Assistant, Auditing, Bishop, …). | `S = Q − lookup(title list)`, `T = S/total` |
| Processed Data | Target words with share `D = freq/total` and **"Top 100 General?"** (is the word among the 100 most common English words?). Third block = the words that are **not** in the top 100 (Christ, Jesus, god, love, lord …). | `E = MATCH(word, top-100) → Y/N` |
| Processed2 / Final Data | For every non-top-100 word: `D` share in target, `F` = share in the all-conference corpus ("Ave. %"), `G = D − F` ("Subtracted %"), **`H = D/F − 1` ("Ratio", % above baseline)**. | `H = (D/F − 1)` |
| Graph (2025) / Sheet1 (2021) | **Emphasized words**: ~31 words sorted by Ratio, high → low. | — |
| UniqueWords (2025) / Sheet2 (2021) | **New words**: used for the first time (e.g. 2021: coronavirus, incivility, constitutionalism …). | — |
| Sheet1 (2025) | Three word lists: top non-lexicon words by frequency (Christ, Jesus, god, love …); a curated topic list with phrases (Jesus Christ, God, Love, Church … Book of Mormon, Grace); and a third list (covenant, again, heart, power, disciples …). | — |

## 2. The rule as practiced
- **Lexicon** = the 100 most common general English words (Wiktionary) — removed before the ratio test.
- **Rate** = share of all words (length-normalized); the baseline is the **pooled** all-conference share, not the
  mean of per-conference shares (matches the draft's check against the Apr 2025 deck within 1–4%).
- **Ratio** shown as "% above baseline" = target share / baseline share − 1.
- **Emphasized** = among the **top ~290 words by frequency** in the conference (freq ≥ 24 in Apr2025, ≥ 26 in Apr2021)
  **and** ratio ≥ ~1.0 (= **2× the baseline**; Apr2021 let one word in at 1.95×), sorted by ratio; ~31 words.
- **Removed by hand** (recovered by `tools/infer_removals.py`):
  - Apr2025 (36 candidates → 31): `m`, `invite`, `Russell`, `while`, `father's`
  - Apr2021 (35 → 31): `Nelson`, `Russell`, `m`, `God's`
  - i.e. name parts, single letters (from initials), possessives of words already counted, function words, and one
    near-duplicate (`invite` next to `invitation`).
- **Baseline in the old workbooks** = all conferences **through and including** the target conference
  (Apr2025 corpus 7,454,326 = Oct2025 corpus minus Oct2025), minus the 37 title words.

## 3. Proposed implementation (cbtn/analyze.py; config/analysis_defaults.yaml) — please confirm
| Item | Old workbook | Proposed | Why |
|---|---|---|---|
| Baseline | all conferences incl. target, minus title words | **all other conferences up to the target, target excluded** (plan decision #8); no title-word correction | Non-talk items and bylines are no longer counted, so the 37-word correction is unnecessary; including the target dampens its own spikes |
| Lexicon | Wiktionary top 100 | same (`GeneralLexicon_Wiktionary_Top1000.csv`, first 100) | as practiced |
| Frequency gate | top ~290 by count (≈ freq ≥ 25) | **rank ≤ 300 in the conference** (shown with the equivalent count) | Talks keep getting shorter (2026 ≈ 41–44k words vs 52–55k); a rank gate keeps the list size stable where a fixed 25 would not |
| Ratio gate | ≥ ~1.0 above (2×) | **≥ 2.0× baseline** (`min_ratio: 2.0`), report also at 1.5× and 3× | as practiced |
| Noise | by hand | **pre-flagged** in `analysis/curation.csv`: leader name parts, single letters, possessives whose base word is present, function words (Wiktionary top 1,000), near-duplicates (invite/invitation), single-talk spikes (≥ 60% from one talk) — **you decide keep/drop**; recurring ones go to `config/exclude_words.txt` | the four removal kinds seen above |
| New words | separate list | words with **no use in any earlier conference** (strict), listed separately | as practiced |
| Phrases | (not in workbooks) | same test on standalone phrase counts | plan §6.2 |

## 4. Questions for CP-4.1
1. **Baseline:** exclude the target conference (proposed) or keep including it as before?
2. **Frequency gate:** rank ≤ 300 (proposed) or a fixed count (25)?
3. **Sheet1 (2025) lists:** what are the curated topic list (col F) and the third list (col I) for — the infographic
   word cloud? Should the tool produce them (e.g. top non-lexicon words by frequency, top by "subtracted %")?
4. Anything you also do that isn't visible in the formulas (e.g. merging singular/plural, checking talks)?

---
## Earlier notes (from the articles and the Apr 2025 deck; kept for reference)
- Articles: lexicon words are "the, and, it, of…" words; emphasized words "used more than the typical conference of the
  past, and occurred at least 25 times"; unique words listed for some conferences; usage-over-time charts for chosen
  words/phrases; top-cited scripture chapters counted once per talk (future scripture tool).
- Apr 2025 deck: y = % increase over the average past conference, minimum ~24 mentions and ≥ 100% increase;
  length-normalized rates reproduce Adam's values within ~1–4% (Easter 12.96 vs 13.46, worship 7.51 vs 7.67).

## Findings from the legacy data (kept for the record)
Re-counting the old spreadsheets' source text showed three problems that the current pipeline fixes:
- The old baseline contained the website footer about **3,400** times, inflating *church, jesus, christ, latter,
  day* and *saints*.
- About **26,600** inline citations (e.g. "(D&C 121:45)") had been counted as spoken words.
- About **45,900** footnote numbers were glued to words (e.g. "heart5").

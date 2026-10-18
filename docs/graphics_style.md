# Graphics style (from Adam's decks: Apr 2016, Oct 2020, Oct 2022 image, Apr 2025, Additional Graphs)

Source files: inputs/prior_graphics/ (PowerPoint originals + Oct 2022 image). Templates: cbtn/graphics.py.
Command: `python -m cbtn.cli graphics YYYY-MM --theme thought_provoking|goldfish|oct2020|emo_kid|sugar|all
--trends "Easter,resurrected,..." --speaker-phrases "Book of Mormon,covenant path"`
Output: outputs/graphics/YYYY-MM/ (PNG 1400 px wide at 200 dpi + SVG + emphasized_words_plotted.csv).

## The classic poster (built in PowerPoint on a tall portrait slide: 7 × 22–25 in)
Top to bottom:
1. **Banner** — "CONFERENCE… / …BY THE NUMBERS", heavy rounded sans (Aharoni), white on the darkest palette color.
2. **Subtitle band** — "<Month Year> General Conference (of) The Church of Jesus Christ of Latter-day Saints".
3. **Explainer** — a big UP arrow ("The further up, the more a word was used compared to past conferences.
   (100% increase means a word was used twice as much as the average past conference.)") and a RIGHT arrow
   ("The further right, the more times a word was used in <conference>"), plus "What words were emphasized by
   the speakers?" in black.
4. **Emphasized Conference Words** — rounded panel; scatter of x = # of mentions, y = % increase over the
   average # of mentions, **log base-2 y axis** labelled 100%, 200%, 400%, 800%, 1600% … ; each point labelled
   with a leader line. When a few very frequent words (Jesus, Christ, Savior) squash the x axis, an **inset**
   shows all words (Apr 2025) or an **expanded view** zooms into the crowded cluster (Oct 2020).
5. **Word and Phrase Trends** — header band, then small multiples (2 × 2) of count per conference since 1971
   (x = year, April = .33, October = .83), dots (± thin line), current conference at the right end.
6. Optional sections that vary by year: **Unique words** never used before (word cloud, Oct 2020),
   **Top 3 speakers** using a phrase since 1971 (Oct 2022), "first time in conference" callouts (Apr 2016),
   annotated story arrow across the scatter (Oct 2020 extra slide), scripture chapters (2019).

## Method encoded in the charts (verified against the Apr 2025 deck data)
- Points plotted: words with ≥ ~24 mentions and ≥ 100% increase (Apr 2025: 31 words, 24–404 mentions).
- y = (rate this conference ÷ average rate of all past conferences) − 1. Recomputing Adam's Apr 2025 values
  from the legacy text with **length-normalized rates** reproduces them within ~1–4% (e.g. Easter 12.96 vs 13.46,
  worship 7.51 vs 7.67, Savior 2.68 vs 2.68). Raw per-conference averages do not (Easter 10.6).
  The larger gap for Jesus/Christ (2.09 → 2.43) comes from the website footer that inflated the old baseline.
- Adam keeps some names (e.g. "Nelson" in Apr 2025); the automatic pick leaves names out, his curation decides.

## Seen in the Oct 2025 poster (ConfByNumbersOct2025.jpg, read 2026-10-11)
- Same order as above: banner (white text) · subtitle band · up/right explainer arrows · "Emphasized Conference Words"
  rounded panel (log-2 y from 100% to 1600%, magenta points, black labels with leader lines) · **"Unique Words from
  <Conference>" (Not used in past conferences)** — ~14 words scattered in staggered rows in blue / near-black / grey.
- New section: **fact cards** — big numbers in colored rounded boxes, staggered in two columns (e.g. "18 — Number of
  Presidents of the Church since 1830", "19 — days of apostolic interregnum"). These are Adam's own facts and
  wording; the tool can supply numbers from the database on request but does not write the cards' text.
- No trends section and no top-speaker cards in Oct 2025 (they appear in other years).

## Palettes (Adam: "open to different color designs"; each year looks a little different)
| Theme | Hex | Used in |
|---|---|---|
| **oct2025** (default) | banner C8501E · band 0E82A3 · up F36C0F · right 12B4E3 · panel 20B29B · points D23B6B · header C92A5C | Oct 2025 |
| thought_provoking | ECD078 · D95B43 · C02942 · 542437 · 53777A | Oct 2022 |
| goldfish | 69D2E7 · A7DBD8 · E0E4CC · F38630 · FA6900 | Apr 2025 |
| oct2020 | EF5030 · F08E2B · F7AC2A · 58B6C2 · 519331 · 6D7371 | Oct 2020 |
| emo_kid | 556270 · 4ECDC4 · C7F464 · FF6B6B · C44D58 | sample (not yet used) |
| sugar | FE4365 · FC9D9A · F9CDAD · C8C8A9 · 83AF9B | sample (not yet used) |
| Apr 2016 | olive/army greens with red, blue and green point groups (Candara) | Apr 2016 |
Roles per theme (banner, band, up arrow, right arrow, panel, points, trend line, section header, cards) are in
`THEMES` in cbtn/graphics.py; text color on each fill is chosen automatically for contrast.

## Fonts
Decks use **Aharoni** (headings/body), FangSong and Candara/Calibri in places. Templates try Aharoni → Inter →
Segoe UI → Arial. On Adam's Windows PC Aharoni should be found automatically.

## Presentation approach (Adam, 2026-10-08)
Every conference: the **classic** poster plus **2–3 new presentation ideas**, each with a one-line rationale;
Adam picks what to publish. Current new templates:
- **A · Rising words** — ranked lollipop of % increase (log) with a 50-year sparkline per word. Rationale: reads
  in seconds on a phone, and the sparklines show at a glance whether a spike is new or a long-term trend.
- **B · Conference fingerprint** — heat strip of each emphasized word's rate at every conference since 1971
  (single hue, darkest = that word's peak, current conference outlined). Rationale: shows whether this
  conference set an all-time high for each word.
- **C · Phrase spotlight** — phrases most above their past average (standalone uses; lighter bar = uses nested in
  a longer phrase) plus the top speakers for the leading phrase. Rationale: phrases carry more meaning than
  single words ("A singular word does not convey a message" — Apr 2025 article).
Further ideas to try: annotated story arrow (Oct 2020 extra slide), theme map grouping words into topics,
interactive web page (Step 6).

## Word selection (CP-4.1 / Step 5)
The plotted words start from `archive/conferences/<conf>/analysis/curation.csv` (top 300 words, ≥ 2× baseline). Until Adam
marks `decision = keep` rows, the poster uses a provisional pick: the starting set minus flagged names, possessives,
function words and near-duplicates (one-talk words stay). Once any row is marked `keep`, only kept words are plotted.

## Not yet automated
Fact cards (Oct 2025; Adam's text), leader lines for every scatter label (Oct 2025 has them on all words; the
template uses them only where labels must move), Aharoni font (not installed on this PC; Segoe UI is used),
expanded-cluster zoom panel (Oct 2020 style), story-arrow annotation, first-time-word callouts with speaker
names, scripture-chapter section, editable PowerPoint export (charts are PNG/SVG; data CSV is exported for
rebuilding in PowerPoint if preferred).

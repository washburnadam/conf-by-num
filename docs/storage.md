# Storage (PLAN §5)

- **archive/** — source of truth, human readable, committed to git.
  `conferences/YYYY-MM/{conference.json, talks/*.json, talks/*.md, histogram_words.csv,
  histogram_phrases.csv, keywords.csv, qa_report.md, analysis/}`
- **data/cbtn.sqlite** — derived; `python -m cbtn.cli db rebuild` then `db check`. Never edit by hand.
- **data/legacy_archive/** + **data/legacy.sqlite** — provisional copy of Adam's legacy workbooks
  (1971–Apr 2025 + Apr 2026) for testing; not the source of truth.
- **outputs/** — disposable Excel/charts.

## SQLite tables (cbtn/db.py)
conferences · talks (tid int key) · speakers · speaker_aliases · speaker_titles (dated titles; byline + reference)
· paragraphs (pid int key, raw_text only when different) · paragraphs_fts (FTS5, external content, diacritics removed)
· footnote_refs · notes · note_links · parentheticals · words + word_counts_raw (int ids, WITHOUT ROWID)
· views word_counts, conference_word_counts, conference_phrase_counts · phrases · phrase_counts · phrase_nesting
· mentions (short-form resolution with step + confidence) · keywords · talk_keywords · keyword_runs
· scripture_refs (empty until the scripture tool) · view sessions (per conference session: first order, items, talks).

Notes (CP-3, 2026-10-11):
- `speaker_aliases` holds both byline display forms and Adam's same-person decisions (`source = adam_decision`,
  from config/speaker_aliases.csv); speaker ids in talks are already canonical.
- `speaker_titles` = reference/leaders/leader_titles.csv + presidents_pre1945.csv + every byline title.
- `mentions` are resolved per talk (a full name anywhere earlier in the talk can decide a later short form); the
  resolver's title history is written to data/resolver_titles.csv on each rebuild.
- Not built (yet): per-conference `qa_report.md` (the CP reports and reports/*.csv cover it).

## Measured on the legacy copy (4,202 talks, 157,682 paragraphs, 7.45 M counted words)
- Histograms + phrases for all 110 conferences: ~65 s. DB rebuild incl. phrases and mention resolution: ~70 s.
- DB size 152 MB (first draft was 527 MB before integer ids / external-content FTS / VACUUM).
- Archive JSON + Markdown for the legacy copy: 172 MB.

## Useful queries
```sql
-- rate of a word per conference
SELECT c.conf_key, IFNULL(w.count,0)*10000.0/c.words FROM conferences c
LEFT JOIN conference_word_counts w ON w.conf_key=c.conf_key AND w.word='covenant';
-- exact phrase search
SELECT p.talk_id, p.spoken_text FROM paragraphs_fts f JOIN paragraphs p ON p.pid=f.rowid
WHERE paragraphs_fts MATCH '"covenant path"' LIMIT 20;
```

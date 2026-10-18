"""SQLite index (PLAN.md §5.3). Derived from archive/ — never edit by hand.

    cbtn db rebuild   -> drops and rebuilds data/cbtn.sqlite from the archive
    cbtn db check     -> compares DB counts with the archive files
"""
from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

from .archive import iter_talks, list_conferences
from .phrases import PhraseMatcher
from .tokenize import DigitPolicy, Histogram

SCHEMA = """
PRAGMA journal_mode = WAL;
CREATE TABLE conferences (conf_key TEXT PRIMARY KEY, year INT, month INT, talks INT, words INT);
CREATE TABLE speakers (speaker_id TEXT PRIMARY KEY, name TEXT);
CREATE TABLE speaker_aliases (speaker_id TEXT, alias TEXT, source TEXT);
CREATE TABLE speaker_titles (speaker_id TEXT, name TEXT, title TEXT, role TEXT, organization TEXT,
                             start TEXT, end TEXT, source TEXT, verify INT);
CREATE TABLE talks (tid INTEGER PRIMARY KEY, talk_id TEXT UNIQUE, conf_key TEXT, session TEXT, order_in_session INT,
                    order_in_conference INT, url TEXT, title TEXT, speaker_id TEXT, speaker_display TEXT,
                    speaker_title TEXT, calling TEXT, item_type TEXT, summary TEXT, words INT,
                    parser_version TEXT, qa_flags TEXT);
-- raw_text is stored only when it differs from spoken_text (saves space)
CREATE TABLE paragraphs (pid INTEGER PRIMARY KEY, paragraph_id TEXT UNIQUE, talk_id TEXT, idx INT, kind TEXT,
                         raw_text TEXT, spoken_text TEXT);
CREATE VIRTUAL TABLE paragraphs_fts USING fts5(spoken_text, content='paragraphs', content_rowid='pid',
                                               tokenize = 'unicode61 remove_diacritics 2');
CREATE TABLE footnote_refs (paragraph_id TEXT, marker TEXT, char_offset INT);
CREATE TABLE notes (talk_id TEXT, marker TEXT, text TEXT);
CREATE TABLE note_links (talk_id TEXT, marker TEXT, href TEXT);
CREATE TABLE parentheticals (paragraph_id TEXT, text TEXT, char_offset INT, class TEXT, score REAL, rule TEXT);
CREATE TABLE words (word_id INTEGER PRIMARY KEY, word TEXT UNIQUE);
CREATE TABLE word_counts_raw (word_id INT, tid INT, count INT, PRIMARY KEY (word_id, tid)) WITHOUT ROWID;
CREATE VIEW word_counts AS
  SELECT t.talk_id, w.word, c.count FROM word_counts_raw c JOIN words w USING (word_id) JOIN talks t USING (tid);
CREATE TABLE phrase_counts (talk_id TEXT, phrase_id TEXT, total INT, standalone INT);
CREATE TABLE phrase_nesting (talk_id TEXT, phrase_id TEXT, parent_phrase_id TEXT, count INT);
CREATE TABLE phrases (phrase_id TEXT PRIMARY KEY, canonical TEXT, category TEXT, variants TEXT,
                      short_forms TEXT, ambiguous INT, verify INT);
CREATE TABLE keywords (keyword_id INTEGER PRIMARY KEY, term TEXT, normalized TEXT, kind TEXT,
                       UNIQUE(normalized, kind));
CREATE TABLE keyword_runs (run_id TEXT PRIMARY KEY, source TEXT, model TEXT, prompt_version TEXT,
                           date TEXT, notes TEXT);
CREATE TABLE talk_keywords (talk_id TEXT, keyword_id INT, source TEXT, weight REAL, run_id TEXT, reviewed INT);
CREATE TABLE mentions (talk_id TEXT, paragraph_id TEXT, short_form TEXT, person TEXT, step TEXT,
                       confidence TEXT, candidates TEXT);
CREATE TABLE scripture_refs (talk_id TEXT, paragraph_id TEXT, ref TEXT, book TEXT, chapter INT,
                             verse_start INT, verse_end INT, mode TEXT);   -- filled by the future scripture tool
CREATE VIEW sessions AS
  SELECT conf_key, session, MIN(order_in_conference) AS first_order, COUNT(*) AS items,
         SUM(item_type = 'talk') AS talks
  FROM talks GROUP BY conf_key, session;
CREATE INDEX ix_pc_phrase ON phrase_counts(phrase_id);
CREATE INDEX ix_mentions_person ON mentions(person);
CREATE INDEX ix_talk_conf ON talks(conf_key);
CREATE VIEW conference_word_counts AS
  SELECT t.conf_key, w.word, SUM(c.count) AS count, COUNT(*) AS talks_using
  FROM word_counts_raw c JOIN words w USING (word_id) JOIN talks t USING (tid)
  WHERE t.item_type = 'talk' GROUP BY t.conf_key, w.word;
CREATE VIEW conference_phrase_counts AS
  SELECT t.conf_key, p.phrase_id, SUM(p.total) AS total, SUM(p.standalone) AS standalone,
         COUNT(DISTINCT p.talk_id) AS talks_using
  FROM phrase_counts p JOIN talks t USING (talk_id) WHERE t.item_type = 'talk' GROUP BY t.conf_key, p.phrase_id;
"""


def connect(path: str | Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    return con


def rebuild(archive_root: str | Path, db_path: str | Path, phrases_csv: str | Path | None = None,
            titles_csv: str | Path | None = None, digit_csv: str | Path | None = None,
            resolver=None, progress=None) -> dict:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = db_path.with_suffix(".building")
    if tmp.exists():
        tmp.unlink()
    con = connect(tmp)
    con.executescript(SCHEMA)
    policy = DigitPolicy.load(digit_csv)
    matcher = PhraseMatcher.from_csv(phrases_csv) if phrases_csv and Path(phrases_csv).exists() else None
    if matcher:
        con.executemany("INSERT INTO phrases VALUES (?,?,?,?,?,?,?)", [
            (e.phrase_id, e.canonical, e.category, "|".join(e.variants), "|".join(e.short_forms),
             int(e.ambiguous), int(e.verify)) for e in matcher.entries.values()])
    for tc in ([titles_csv, Path(titles_csv).with_name("presidents_pre1945.csv")] if titles_csv else []):
        if Path(tc).exists():
            with open(tc, newline="", encoding="utf-8-sig") as f:
                con.executemany("INSERT INTO speaker_titles VALUES (?,?,?,?,?,?,?,?,?)", [
                    (r["person_id"], r["name"], r["title"], r["role"], r["organization"], r["start"], r["end"],
                     r["source"], int(r.get("verify", "true") == "true")) for r in csv.DictReader(f)])
    aliases = Path(archive_root).parent / "config" / "speaker_aliases.csv"      # Adam's same-person decisions
    if aliases.exists():
        with open(aliases, newline="", encoding="utf-8-sig") as f:
            con.executemany("INSERT INTO speaker_aliases VALUES (?,?,?)",
                            [(r["canonical_id"], r["alias_id"], "adam_decision") for r in csv.DictReader(f)])

    stats = {"conferences": 0, "talks": 0, "paragraphs": 0, "words": 0}
    word_ids: dict[str, int] = {}
    confs = list_conferences(archive_root)
    for ci, ck in enumerate(confs):
        c_talks = c_words = 0
        for t in iter_talks(archive_root, ck):
            sp = t.speaker
            con.execute("INSERT OR IGNORE INTO speakers VALUES (?,?)", (sp.speaker_id, sp.name))
            con.execute("INSERT INTO speaker_aliases VALUES (?,?,?)", (sp.speaker_id, sp.name_display, "byline"))
            if sp.title:
                con.execute("INSERT INTO speaker_titles VALUES (?,?,?,?,?,?,?,?,?)",
                            (sp.speaker_id, sp.name, sp.title, sp.calling or "", "", ck, ck, "byline", 0))
            talk_hist = Histogram()
            for p in t.paragraphs:
                pid = f"{t.talk_id}#p{p.index}"
                cur = con.execute("INSERT INTO paragraphs (paragraph_id, talk_id, idx, kind, raw_text, spoken_text) "
                                  "VALUES (?,?,?,?,?,?)",
                                  (pid, t.talk_id, p.index, p.kind,
                                   None if p.raw_text == p.spoken_text else p.raw_text, p.spoken_text))
                if p.is_spoken:
                    con.execute("INSERT INTO paragraphs_fts (rowid, spoken_text) VALUES (?,?)",
                                (cur.lastrowid, p.spoken_text))
                con.executemany("INSERT INTO footnote_refs VALUES (?,?,?)",
                                [(pid, r["marker"], r.get("char_offset")) for r in p.footnote_refs])
                con.executemany("INSERT INTO parentheticals VALUES (?,?,?,?,?,?)",
                                [(pid, x["text"], x["char_offset"], x["class"], x["score"], x["rule"])
                                 for x in p.parentheticals])
                if p.is_spoken and t.counts_toward_histograms:
                    kw = dict(markers=t.markers_for(p), policy=policy)
                    talk_hist.add(p.spoken_text, **kw)
                    if matcher:
                        pc = matcher.count(p.spoken_text, **kw)
                        con.executemany("INSERT INTO phrase_counts VALUES (?,?,?,?)",
                                        [(t.talk_id, k, v, pc.standalone[k]) for k, v in pc.total.items()])
                        con.executemany("INSERT INTO phrase_nesting VALUES (?,?,?,?)",
                                        [(t.talk_id, k, par, n) for k, c in pc.nested_in.items() for par, n in c.items()])
                stats["paragraphs"] += 1
            if resolver is not None and t.counts_toward_histograms:
                # whole talk at once, so 'antecedent' can use a full name from any earlier paragraph
                sp_paras = [p for p in t.paragraphs if p.is_spoken]
                for m in resolver.resolve_talk(t.talk_id, ck + "-01", [p.spoken_text for p in sp_paras],
                                               [t.notes_for(p) for p in sp_paras]):
                    con.execute("INSERT INTO mentions VALUES (?,?,?,?,?,?,?)",
                                (t.talk_id, f"{t.talk_id}#p{sp_paras[m.paragraph].index}", m.short_form,
                                 m.person, m.step, m.confidence, "; ".join(m.candidates)))
            for n in t.notes:
                con.execute("INSERT INTO notes VALUES (?,?,?)", (t.talk_id, str(n["marker"]), n["text"]))
                con.executemany("INSERT INTO note_links VALUES (?,?,?)",
                                [(t.talk_id, str(n["marker"]), h) for h in n.get("links", [])])
            cur = con.execute("INSERT INTO talks (talk_id, conf_key, session, order_in_session, order_in_conference, "
                              "url, title, speaker_id, speaker_display, speaker_title, calling, item_type, summary, "
                              "words, parser_version, qa_flags) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                t.talk_id, ck, t.session, t.order_in_session, t.order_in_conference, t.url, t.title,
                sp.speaker_id, sp.name_display, sp.title, sp.calling, t.item_type, t.summary,
                talk_hist.total, t.source.get("parser_version", ""), json.dumps(t.qa_flags)))
            tid = cur.lastrowid
            for w, c in talk_hist.counts.items():
                wid = word_ids.get(w)
                if wid is None:
                    wid = word_ids[w] = len(word_ids) + 1
                    con.execute("INSERT INTO words VALUES (?,?)", (wid, w))
                con.execute("INSERT INTO word_counts_raw VALUES (?,?,?)", (wid, tid, c))
            if t.counts_toward_histograms:
                c_talks += 1
                c_words += talk_hist.total
        y, m = ck.split("-")
        con.execute("INSERT INTO conferences VALUES (?,?,?,?,?)", (ck, int(y), int(m), c_talks, c_words))
        stats["conferences"] += 1
        stats["talks"] += c_talks
        stats["words"] += c_words
        con.commit()
        if progress:
            progress(ci + 1, len(confs), ck)
    _load_keywords(con, archive_root)
    con.commit()
    con.execute("INSERT INTO paragraphs_fts(paragraphs_fts) VALUES ('optimize')")
    con.commit()
    con.execute("VACUUM")
    con.close()
    if db_path.exists():
        db_path.unlink()
    tmp.rename(db_path)
    return stats


def _load_keywords(con: sqlite3.Connection, archive_root: str | Path) -> None:
    runs: dict[str, str] = {}
    for f in Path(archive_root).glob("conferences/*/keywords.csv"):
        with open(f, newline="", encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                if r.get("run_id"):
                    runs.setdefault(r["run_id"], r["source"])
    for run_id, source in runs.items():      # every keyword traceable to how it was produced (PLAN §5.4)
        con.execute("INSERT OR IGNORE INTO keyword_runs VALUES (?,?,?,?,?,?)",
                    (run_id, source, "", "", "-".join(run_id.split("-")[-3:]),          # 'tfidf-2026-10-11' -> date
                     "TF-IDF top 15 per talk vs the whole archive" if source == "tfidf" else ""))
    for f in Path(archive_root).glob("conferences/*/keywords.csv"):
        with open(f, newline="", encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                con.execute("INSERT OR IGNORE INTO keywords (term, normalized, kind) VALUES (?,?,?)",
                            (r["term"], r["term"].lower(), r.get("kind", "keyword")))
                kid = con.execute("SELECT keyword_id FROM keywords WHERE normalized=? AND kind=?",
                                  (r["term"].lower(), r.get("kind", "keyword"))).fetchone()[0]
                con.execute("INSERT INTO talk_keywords VALUES (?,?,?,?,?,?)",
                            (r["talk_id"], kid, r["source"], float(r.get("weight") or 0), r.get("run_id", ""),
                             int(r.get("reviewed", "0") or 0)))


def check(archive_root: str | Path, db_path: str | Path) -> list[str]:
    """Return a list of mismatches between DB and archive (empty list == OK)."""
    con = connect(db_path)
    problems = []
    for ck in list_conferences(archive_root):
        n_files = sum(1 for t in iter_talks(archive_root, ck) if t.counts_toward_histograms)
        row = con.execute("SELECT talks FROM conferences WHERE conf_key=?", (ck,)).fetchone()
        if not row:
            problems.append(f"{ck}: missing from DB")
        elif row["talks"] != n_files:
            problems.append(f"{ck}: DB talks {row['talks']} != archive {n_files}")
        hist = Path(archive_root) / "conferences" / ck / "histogram_words.csv"
        if hist.exists():
            with open(hist, newline="", encoding="utf-8-sig") as f:
                total = sum(int(r["count"]) for r in csv.DictReader(f))
            dbw = con.execute("SELECT words FROM conferences WHERE conf_key=?", (ck,)).fetchone()
            if dbw and dbw["words"] != total:
                problems.append(f"{ck}: DB words {dbw['words']} != histogram {total}")
    db_confs = {r[0] for r in con.execute("SELECT conf_key FROM conferences")}
    for extra in sorted(db_confs - set(list_conferences(archive_root))):
        problems.append(f"{extra}: in DB but not in archive")
    con.close()
    return problems

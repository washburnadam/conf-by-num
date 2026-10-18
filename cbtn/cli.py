"""cbtn command line.  Run as:  python -m cbtn.cli <command> ...

Every command prints a short summary (<= ~50 lines) and writes details to files (PLAN.md §0.2).
--archive selects the archive root: archive/ (default, source of truth) or data/legacy_archive
(provisional copy of the legacy workbooks, for testing).
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config"
REF = ROOT / "reference" / "leaders"


def _p(*a):
    print(*a, flush=True)


def _write_csv(path: Path, rows: list[dict]) -> None:
    import csv
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def _confs(args, archive_root):
    from .archive import list_conferences
    if getattr(args, "all", False):
        return list_conferences(archive_root)
    return [args.conference]


def _db_path(archive_root: Path) -> Path:
    return ROOT / "data" / ("legacy.sqlite" if "legacy" in str(archive_root) else "cbtn.sqlite")


# ---------------------------------------------------------------------------------------------
def cmd_dom_outline(a):
    from .parse import dom_outline
    src = Path(a.file)
    html = src.read_text(encoding="utf-8") if not src.suffix == ".gz" else __import__("gzip").decompress(
        src.read_bytes()).decode("utf-8")
    _p(dom_outline(html, max_lines=a.lines))


def cmd_discover(a):
    import yaml
    from .archive import write_conference_manifest
    from .discover import conference_keys, manifest, parse_index
    from .fetch import Fetcher
    sel = yaml.safe_load((CFG / "selectors.yaml").read_text(encoding="utf-8"))
    f = Fetcher(ROOT / "data/cache/html", ROOT / "data/fetch_log.csv", delay=a.delay)
    keys = conference_keys(a.first, a.last) if a.all else [a.conference]
    rows = []
    for ck in keys:
        y, m = map(int, ck.split("-"))
        url = sel["base_url"] + sel["conference_index"].format(year=y, month=m)
        html = f.get(url)
        if html is None:
            rows.append({"conference": ck, "items": 0, "talks": 0, "note": "index not available"})
            continue
        items = parse_index(html, y, m, sel["base_url"], sel["talk_url_regex"])
        man = manifest(ck, items, url, sel.get("item_type_rules"))
        write_conference_manifest(a.archive, ck, man)
        rows.append({"conference": ck, "items": len(items), "talks": man["counts"].get("talk", 0),
                     "non_talk": len(items) - man["counts"].get("talk", 0),
                     "sessions": len({i.session for i in items}), "note": "" if items else "no items"})
    if len(rows) <= 10:
        for r in rows:
            _p(f"{r['conference']}: {r['items']} items, {r['talks']} talks {r['note']}".rstrip())
        return
    out = ROOT / "reports" / "discovery_counts.csv"
    _write_csv(out, rows)
    bad = [r for r in rows if r["note"]]
    _p(f"{len(rows)} conferences: {sum(r['items'] for r in rows)} items, {sum(r['talks'] for r in rows)} talks; "
       f"{len(bad)} problems -> {out.relative_to(ROOT)}")
    for r in bad[:20]:
        _p(f"  {r['conference']}: {r['note']}")


def _source_url(url: str, source: str) -> str:
    """Talk page URL -> the URL actually fetched/cached (the JSON content API, or the page itself)."""
    if source == "html":
        return url
    import yaml
    sel = yaml.safe_load((CFG / "selectors.yaml").read_text(encoding="utf-8"))
    m = re.search(r"/general-conference/(\d{4})/(\d{2})/([^/?#]+)", url)
    return sel["base_url"] + sel["json_api"].format(year=int(m.group(1)), month=int(m.group(2)), slug=m.group(3))


def cmd_fetch(a):
    from .archive import conference_dir
    from .fetch import Fetcher
    f = Fetcher(ROOT / "data/cache/html", ROOT / "data/fetch_log.csv", delay=a.delay)
    for ck in _confs(a, a.archive):
        man = json.loads((conference_dir(a.archive, ck) / "conference.json").read_text(encoding="utf-8"))
        ok = sum(1 for it in man["items"] if f.get(_source_url(it["url"], a.source)) is not None)
        _p(f"{ck}: fetched/cached {ok}/{len(man['items'])} ({a.source})")


def cmd_parse(a):
    from .archive import conference_dir, write_talk
    from .fetch import Fetcher
    from .parse import ParseContext, load_selectors, parse_talk
    sel = load_selectors(CFG / "selectors.yaml")
    f = Fetcher(ROOT / "data/cache/html", ROOT / "data/fetch_log.csv")
    fails = []
    for ck in _confs(a, a.archive):
        y, m = map(int, ck.split("-"))
        man = json.loads((conference_dir(a.archive, ck) / "conference.json").read_text(encoding="utf-8"))
        kinds, flags = Counter(), Counter()
        for it in man["items"]:
            cp = f.cache_path(_source_url(it["url"], a.source))
            if not cp.exists():
                fails.append((ck, it["url"], "not cached"))
                continue
            try:
                html = __import__("gzip").decompress(cp.read_bytes()).decode("utf-8")
                t = parse_talk(html, ParseContext(y, m, it["url"], it["session"], it["order_in_session"],
                                                  it["order_in_conference"]), sel)
                write_talk(a.archive, t)
                kinds[t.item_type] += 1
                for q in t.qa_flags:
                    flags[q.split(":")[0]] += 1
            except Exception as e:  # noqa: BLE001
                fails.append((ck, it["url"], repr(e)[:200]))
        _p(f"{ck}: {dict(kinds)} flags={dict(flags)}")
    if fails:
        out = ROOT / "reports/parse_failures.csv"
        out.parent.mkdir(exist_ok=True)
        with open(out, "a", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerows(fails)
        _p(f"{len(fails)} failures -> {out}")


def cmd_show_talk(a):
    from .archive import iter_talks
    ck = a.talk_id[:7]
    for t in iter_talks(a.archive, ck):
        if t.talk_id != a.talk_id:
            continue
        sp = t.speaker
        _p(f"{t.talk_id} | {t.title} | {sp.name_display} | {sp.calling} | {t.item_type} | flags={t.qa_flags}")
        if t.summary:
            _p(f"SUMMARY (not counted): {t.summary[:300]}")
        paras = list(t.paragraphs)
        if a.full:
            show = paras
        elif a.paragraphs:
            lo, hi = map(int, a.paragraphs.split("-"))
            show = [p for p in paras if lo <= p.index <= hi]
        else:   # audit view
            spoken = [p for p in paras if p.is_spoken]
            flagged = [p for p in paras if p.parentheticals or p.footnote_refs or not p.is_spoken]
            pick = {id(x) for x in spoken[:1] + spoken[-1:] + flagged}
            show = [p for p in paras if id(p) in pick]
        last = max((p.index for p in paras if p.is_spoken), default=None)
        for p in show:
            txt = p.spoken_text
            if p.index == last and len(txt) > a.chars:      # show how the talk ends, not just how the paragraph starts
                txt = txt[:a.chars // 2] + " … " + txt[-a.chars // 2:]
            else:
                txt = txt[:a.chars]
            _p(f"[{p.index} {p.kind}] {txt}")
            for x in p.parentheticals:
                _p(f"    ( {x['class']}/{x['rule']} ) {x['text'][:120]}")
            if p.footnote_refs:
                _p(f"    markers: {[r['marker'] for r in p.footnote_refs]}")
        _p(f"notes: {len(t.notes)}" + (f" | first: {t.notes[0]['text'][:150]}" if t.notes else ""))
        return
    _p("talk not found")


def cmd_histogram(a):
    from .phrases import PhraseMatcher
    from .pipeline import count_conference
    from .tokenize import DigitPolicy
    m = PhraseMatcher.from_csv(CFG / "phrases.csv") if not a.words_only else None
    pol = DigitPolicy.load(CFG / "digit_tokens.csv")
    rows, urls = [], []
    for ck in _confs(a, a.archive):
        r = count_conference(a.archive, ck, m, pol)
        urls += [(ck, u, n) for u, n in r["log"].url_dropped.items()]
        rows.append({k: r[k] for k in ("conference", "talks", "words", "unique", "marker_splits",
                                       "digit_kept", "digit_dropped")})
    if urls:   # web addresses are not counted (CP-5.3); log every one
        _write_csv(ROOT / "reports" / "url_dropped.csv", [{"conference": c, "url": u, "count": n} for c, u, n in urls])
        _p(f"web addresses not counted: {sum(n for _, _, n in urls)} -> reports/url_dropped.csv")
    if len(rows) <= 10:
        for r in rows:
            _p(f"{r['conference']}: talks={r['talks']} words={r['words']} unique={r['unique']} "
               f"marker_splits={r['marker_splits']} digit kept/dropped={r['digit_kept']}/{r['digit_dropped']}")
        return
    out = ROOT / "reports" / "histogram_summary.csv"
    _write_csv(out, rows)
    _p(f"{len(rows)} conferences: {sum(r['talks'] for r in rows)} talks, {sum(r['words'] for r in rows):,} words; "
       f"unique per conference {min(r['unique'] for r in rows)}–{max(r['unique'] for r in rows)}; "
       f"marker splits {sum(r['marker_splits'] for r in rows)}; digit tokens kept/dropped "
       f"{sum(r['digit_kept'] for r in rows)}/{sum(r['digit_dropped'] for r in rows)} -> {out.relative_to(ROOT)}")


def cmd_corpus(a):
    from .corpus import build_corpus, write_corpus
    rows, meta = build_corpus(a.archive, through=a.through, exclude=set(a.exclude or []), first=a.first)
    out = Path(a.out) if a.out else Path(a.archive) / "corpus_words.csv"
    write_corpus(rows, meta, out)
    _p(f"corpus {meta['first']}..{meta['last']} ({meta['conferences']} conferences, excluded {meta['excluded']}): "
       f"{meta['words']:,} words, {meta['unique']:,} unique -> {out}")


def cmd_phrases(a):
    from .phrases import load_dictionary, validate_dictionary
    ents = load_dictionary(CFG / "phrases.csv")
    probs = validate_dictionary(ents)
    _p(f"{len(ents)} entries, {len(probs)} problems")
    for x in probs[:40]:
        _p("  " + x)
    if a.action == "recount":
        a.all, a.words_only = True, False
        cmd_histogram(a)


def cmd_citations(a):
    from .archive import iter_talks
    out = ROOT / "reports" / "citations_review.csv"
    out.parent.mkdir(exist_ok=True)
    c = Counter()
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["talk_id", "paragraph", "class", "rule", "score", "text"])
        for ck in _confs(a, a.archive):
            for t in iter_talks(a.archive, ck):
                for p in t.paragraphs:
                    for x in p.parentheticals:
                        c[(x["class"], x["rule"])] += 1
                        if x["class"] != "citation" or a.include_citations:
                            w.writerow([t.talk_id, p.index, x["class"], x["rule"], x["score"], x["text"]])
    for k, n in c.most_common():
        _p(f"{k[0]:10s} {k[1]:28s} {n}")
    _p(f"review list -> {out}")


def cmd_digits(a):
    from .archive import iter_talks
    from .tokenize import DigitPolicy, TokenizeLog, tokens
    pol, log = DigitPolicy.load(CFG / "digit_tokens.csv"), TokenizeLog()
    for ck in _confs(a, a.archive):
        for t in iter_talks(a.archive, ck):
            for p in t.spoken_paragraphs():
                tokens(p.spoken_text, markers=t.markers_for(p), policy=pol, log=log)
    out = ROOT / "reports" / "digit_tokens_review.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["token", "count", "current_decision", "decision"])
        for tok, n in (log.digit_kept + log.digit_dropped).most_common():
            w.writerow([tok, n, "keep" if tok in log.digit_kept else "drop", ""])
    _p(f"kept {len(log.digit_kept)} distinct / dropped {len(log.digit_dropped)} distinct -> {out}")
    _p("Fill 'decision' (keep/drop) and save rows you change into config/digit_tokens.csv (token,decision).")


def cmd_legacy_import(a):
    from .legacy_import import import_workbook
    s = import_workbook(a.workbook, a.out, sheet=a.sheet, first_body_row=a.first_body_row,
                        summary_row=a.summary_row or None, source_label=Path(a.workbook).name)
    _p(dict(s))


def cmd_db(a):
    from .db import check, rebuild
    from .mentions import Resolver
    dbp = Path(a.db) if a.db else _db_path(Path(a.archive))
    if a.action == "rebuild":
        from .mentions import build_titles_csv
        R = Resolver.from_titles_csv(build_titles_csv(ROOT, ROOT / "data" / "resolver_titles.csv"),
                                     CFG / "mention_overrides.csv")
        s = rebuild(a.archive, dbp, CFG / "phrases.csv", REF / "leader_titles.csv", CFG / "digit_tokens.csv",
                    resolver=R, progress=lambda i, n, ck: _p(f"  {i}/{n} {ck}") if i % 10 == 0 or i == n else None)
        _p(f"{dbp}: {s}  size={dbp.stat().st_size / 1e6:.0f} MB")
    probs = check(a.archive, dbp)
    _p("db check: OK" if not probs else "db check problems:\n  " + "\n  ".join(probs[:30]))


def cmd_query(a):
    from .db import connect
    con = connect(Path(a.db) if a.db else _db_path(Path(a.archive)))
    if a.kind == "word":
        rows = con.execute("SELECT c.conf_key, IFNULL(w.count,0) AS count, c.words, "
                           "ROUND(IFNULL(w.count,0)*10000.0/c.words,3) AS per10k FROM conferences c "
                           "LEFT JOIN conference_word_counts w ON w.conf_key=c.conf_key AND w.word=? "
                           "ORDER BY c.conf_key", (a.text.lower(),)).fetchall()
    elif a.kind == "phrase":
        rows = con.execute("SELECT c.conf_key, IFNULL(p.standalone,0) standalone, IFNULL(p.total,0) total, "
                           "ROUND(IFNULL(p.standalone,0)*10000.0/c.words,3) per10k FROM conferences c "
                           "LEFT JOIN conference_phrase_counts p ON p.conf_key=c.conf_key AND p.phrase_id="
                           "(SELECT phrase_id FROM phrases WHERE lower(canonical)=lower(?)) ORDER BY c.conf_key",
                           (a.text,)).fetchall()
    else:  # search
        rows = con.execute("SELECT p.talk_id, substr(p.spoken_text,1,160) FROM paragraphs_fts f "
                           "JOIN paragraphs p ON p.pid=f.rowid WHERE paragraphs_fts MATCH ? LIMIT ?",
                           (f'"{a.text}"', a.limit)).fetchall()
    for r in rows[: a.limit if a.kind == "search" else 1000]:
        _p("\t".join(str(x) for x in tuple(r)))


def cmd_analyze(a):
    from .analyze import (compare, finalize, leader_name_words, load_settings, load_word_list, threshold_grid,
                          write_curation, write_rows)
    from .archive import conference_dir
    from .db import connect
    adir = conference_dir(a.archive, a.conference) / "analysis"
    if a.finalize:
        s = finalize(adir / "curation.csv", adir / "emphasized_final.csv")
        _p(f"kept {s['kept']}, dropped {s['dropped']}, undecided {len(s['undecided'])} -> {adir / 'emphasized_final.csv'}")
        return
    con = connect(Path(a.db) if a.db else _db_path(Path(a.archive)))
    tgt = Counter({r["word"]: r["count"] for r in con.execute(
        "SELECT word, count FROM conference_word_counts WHERE conf_key=?", (a.conference,))})
    tu = {r["word"]: r["talks_using"] for r in con.execute(
        "SELECT word, talks_using FROM conference_word_counts WHERE conf_key=?", (a.conference,))}
    base = Counter({r["word"]: r["n"] for r in con.execute(
        "SELECT word, SUM(count) n FROM conference_word_counts WHERE conf_key < ? GROUP BY word", (a.conference,))})
    share = {}
    for r in con.execute("SELECT w.word, MAX(c.count)*1.0/SUM(c.count) s FROM word_counts_raw c "
                         "JOIN words w USING(word_id) JOIN talks t USING(tid) WHERE t.conf_key=? GROUP BY w.word",
                         (a.conference,)):
        share[r["word"]] = r["s"]
    st = load_settings(CFG / "analysis_defaults.yaml", a.conference)
    from .analyze import load_lexicon, write_new_words
    rows = compare(tgt, base, talks_using=tu, top_talk_share=share, settings=st,
                   exclude=load_word_list(CFG / "exclude_words.txt"),
                   name_words=leader_name_words(REF / "leader_titles.csv"),
                   lexicon=load_lexicon(st["lexicon_top"]), function_words=load_lexicon(st["function_word_top"]),
                   common_words=load_lexicon(1000))
    write_rows(rows, adir / "all_words.csv")
    n = write_curation(rows, adir / "curation.csv")
    nn = write_new_words(rows, adir / "new_words.csv")
    first = con.execute("SELECT MIN(conf_key) FROM conferences").fetchone()[0]
    _p(f"{a.conference}: target {sum(tgt.values()):,} words vs baseline {sum(base.values()):,} "
       f"({first} .. the conference before)")
    for g in threshold_grid(rows, st):
        _p(f"  top {g['top_n']:>3} words & ratio >= {g['min_ratio']}: {g['words_passing']}")
    flagged = sum(1 for r in rows if r.candidate and r.flags)
    _p(f"{n} candidates ({flagged} flagged as possible noise) -> {adir / 'curation.csv'}; {nn} new words -> new_words.csv")
    # phrases: same test on standalone counts (PLAN §6.2); no rank gate, a small count floor instead
    pt = Counter({r["phrase_id"]: r["standalone"] for r in con.execute(
        "SELECT phrase_id, standalone FROM conference_phrase_counts WHERE conf_key=?", (a.conference,))})
    pb = Counter({r["phrase_id"]: r["n"] for r in con.execute(
        "SELECT phrase_id, SUM(standalone) n FROM conference_phrase_counts WHERE conf_key < ? GROUP BY phrase_id",
        (a.conference,))})
    names = {r["phrase_id"]: r["canonical"] for r in con.execute("SELECT phrase_id, canonical FROM phrases")}
    # phrase rates use the conference / baseline WORD totals, so they are comparable with word rates
    t_words = con.execute("SELECT words FROM conferences WHERE conf_key=?", (a.conference,)).fetchone()[0]
    b_words = con.execute("SELECT SUM(words) FROM conferences WHERE conf_key < ?", (a.conference,)).fetchone()[0]
    prow = []
    for pid, n_ in pt.items():
        bc = pb.get(pid, 0)
        rate, brate = n_ / t_words * 10000, bc / b_words * 10000
        ratio = rate / brate if bc else None
        prow.append({"phrase": names.get(pid, pid), "count": n_, "baseline_count": bc,
                     "rate": round(rate, 3), "baseline_rate": round(brate, 4),
                     "ratio": "" if ratio is None else round(ratio, 3),
                     "candidate": bool(ratio and ratio >= st["min_ratio"] and n_ >= st.get("phrase_min_count", 5)),
                     "new": bc == 0})
    prow.sort(key=lambda r: (not r["candidate"], -(r["ratio"] or 0) if r["ratio"] != "" else 0, -r["count"]))
    _write_csv(adir / "phrases.csv", prow)
    _p(f"phrases: {sum(r['candidate'] for r in prow)} candidates (standalone >= {st.get('phrase_min_count', 5)}, "
       f"ratio >= {st['min_ratio']}), {sum(r['new'] for r in prow)} first-time -> phrases.csv")


def cmd_keywords(a):
    from .analyze import leader_name_words
    from .keywords import build_tfidf
    s = build_tfidf(a.archive, exclude=leader_name_words(REF / "leader_titles.csv"),
                    conferences=None if (a.all or not a.conference) else [a.conference])   # no conference = all
    _p(s)


def cmd_export(a):
    from .archive import conference_dir
    from .export_excel import capture_xlsx, histogram_xlsx
    out = ROOT / "outputs" / "excel"
    if a.what == "histogram":
        p = histogram_xlsx(conference_dir(a.archive, a.conference) / "histogram_words.csv",
                           out / f"WordHistogram_{a.conference}.xlsx")
    else:
        p = capture_xlsx(a.archive, a.conference, out / f"ConferenceCapture_{a.conference}.xlsx")
    _p(f"wrote {p}")


def cmd_graphics(a):
    from .analyze import load_settings, load_word_list
    from .archive import conference_dir
    from .graphics import THEMES, build_all
    themes = list(THEMES) if a.theme == "all" else [a.theme]
    out = ROOT / "outputs" / "graphics" / a.conference
    for th in themes:
        r = build_all(Path(a.db) if a.db else _db_path(Path(a.archive)), a.conference, out, theme=th,
                      archive_root=a.archive,
                      curation_csv=conference_dir(a.archive, a.conference) / "analysis" / "curation.csv",
                      settings=load_settings(CFG / "analysis_defaults.yaml", a.conference),
                      exclude=load_word_list(CFG / "exclude_words.txt"), titles_csv=REF / "leader_titles.csv",
                      trend_terms=a.trends.split(",") if a.trends else None,
                      speaker_phrases=a.speaker_phrases.split(",") if a.speaker_phrases else None,
                      min_count=a.min_count)
        _p(f"{th}: {r['status']}; {r['emphasized']} emphasized words, {r['unique_words']} unique words")
    _p(f"-> {out}  (classic_* = established style; new_A/B/C = new presentation ideas)")


def cmd_leaders(a):
    import runpy
    sys.argv = ["build_leaders.py"] + (["--no-phrases"] if a.no_phrases else [])
    runpy.run_path(str(ROOT / "tools/build_leaders.py"), run_name="__main__")


def cmd_add_conference(a):
    """Twice-yearly workflow (PLAN §3.2 step 1.6): discover -> fetch (JSON) -> parse -> validate -> report -> notify.
    Histograms, keywords and the database update are added here once Steps 2-3 are approved."""
    from .archive import iter_talks
    ck = a.conference
    ns = argparse.Namespace(**{**vars(a), "all": False, "source": "json"})
    for step in (cmd_discover, cmd_fetch, cmd_parse):
        step(ns)
    items = list(iter_talks(a.archive, ck))
    talks = [t for t in items if t.item_type == "talk"]
    from .tokenize import tokens
    words = sum(len(tokens(p.spoken_text)) for t in talks for p in t.paragraphs if p.is_spoken)
    par = Counter(x["class"] for t in talks for p in t.paragraphs for x in p.parentheticals)
    flags = Counter(q.split(":")[0] for t in talks for q in t.qa_flags)
    spoken_par = [(t.talk_id, x["text"]) for t in talks for p in t.paragraphs for x in p.parentheticals
                  if x["class"] != "citation"]
    failures = []
    fp = ROOT / "reports/parse_failures.csv"
    if fp.exists():
        failures = [ln for ln in fp.read_text(encoding="utf-8").splitlines() if ln.startswith(ck)]
    no_author = [t.talk_id for t in talks if not t.speaker.name]
    report = ROOT / "reports" / f"CP-add-{ck}.md"
    lines = [
        f"# Add conference {ck}", "",
        f"- Items {len(items)} · talks {len(talks)} · non-talk {len(items) - len(talks)} "
        f"({dict(Counter(t.item_type for t in items if t.item_type != 'talk'))})",
        f"- Spoken words {words:,} · parse failures {len(failures)} · talks without speaker {len(no_author)}",
        f"- Parentheticals: {dict(par)} · QA flags: {dict(flags)}",
        f"- Talks without notes: {sum(1 for t in talks if not t.notes)}", "",
        "## Spoken/uncertain parentheticals (check these)", "",
        *[f"- `{tid}` {txt}" for tid, txt in spoken_par[:40]], "",
        "## Talks", "",
        *[f"- {t.order_in_conference}. {t.title} — {t.speaker.name} ({len(t.paragraphs)} paragraphs)" for t in
          sorted(talks, key=lambda t: t.order_in_conference)],
        "", "Next: histograms/keywords/database once Steps 2–3 are in place; then `cbtn analyze`.",
    ]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    msg = ROOT / "reports" / "notify_message.txt"
    msg.write_text(f"Conference {ck} added: {len(talks)} talks, {words:,} words, {len(failures)} failures. "
                   f"Report {report.name}\n", encoding="utf-8")
    _p(f"{ck}: {len(talks)} talks, {words:,} spoken words, {len(failures)} failures, flags {dict(flags)}")
    _p(f"report -> {report.relative_to(ROOT)}; then run tools/notify.py (no arguments) to push it")


def main(argv=None):
    try:   # Windows consoles default to cp1252 and print curly quotes/dashes as '?'
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(prog="cbtn")
    ap.add_argument("--archive", default=str(ROOT / "archive"))
    sub = ap.add_subparsers(dest="cmd", required=True)

    def conf_args(p, allow_all=True):
        p.add_argument("conference", nargs="?", help="YYYY-MM")
        if allow_all:
            p.add_argument("--all", action="store_true")

    p = sub.add_parser("dom-outline"); p.add_argument("file"); p.add_argument("--lines", type=int, default=150)
    p.set_defaults(fn=cmd_dom_outline)
    p = sub.add_parser("discover"); conf_args(p); p.add_argument("--first", default="1971-04")
    p.add_argument("--last", default="2026-10"); p.add_argument("--delay", type=float, default=1.5)
    p.set_defaults(fn=cmd_discover)
    p = sub.add_parser("fetch"); conf_args(p); p.add_argument("--delay", type=float, default=1.5)
    p.add_argument("--source", choices=["json", "html"], default="json"); p.set_defaults(fn=cmd_fetch)
    p = sub.add_parser("parse"); conf_args(p)
    p.add_argument("--source", choices=["json", "html"], default="json"); p.set_defaults(fn=cmd_parse)
    p = sub.add_parser("corpus"); p.add_argument("--through"); p.add_argument("--first")
    p.add_argument("--exclude", nargs="*", help="YYYY-MM conferences to leave out"); p.add_argument("--out")
    p.set_defaults(fn=cmd_corpus)
    p = sub.add_parser("show-talk"); p.add_argument("talk_id"); p.add_argument("--full", action="store_true")
    p.add_argument("--audit", action="store_true"); p.add_argument("--paragraphs"); p.add_argument("--chars", type=int, default=400)
    p.set_defaults(fn=cmd_show_talk)
    p = sub.add_parser("histogram"); conf_args(p); p.add_argument("--words-only", action="store_true")
    p.set_defaults(fn=cmd_histogram)
    p = sub.add_parser("phrases"); p.add_argument("action", choices=["validate", "recount"]); p.set_defaults(fn=cmd_phrases)
    p = sub.add_parser("citations"); p.add_argument("action", choices=["review"]); conf_args(p)
    p.add_argument("--include-citations", action="store_true"); p.set_defaults(fn=cmd_citations)
    p = sub.add_parser("digits"); p.add_argument("action", choices=["review"]); conf_args(p); p.set_defaults(fn=cmd_digits)
    p = sub.add_parser("legacy-import"); p.add_argument("workbook"); p.add_argument("--sheet")
    p.add_argument("--first-body-row", type=int, default=5); p.add_argument("--summary-row", type=int, default=4)
    p.add_argument("--out", default=str(ROOT / "data/legacy_archive")); p.set_defaults(fn=cmd_legacy_import)
    p = sub.add_parser("db"); p.add_argument("action", choices=["rebuild", "check"]); p.add_argument("--db")
    p.set_defaults(fn=cmd_db)
    p = sub.add_parser("query"); p.add_argument("kind", choices=["word", "phrase", "search"]); p.add_argument("text")
    p.add_argument("--limit", type=int, default=20); p.add_argument("--db"); p.set_defaults(fn=cmd_query)
    p = sub.add_parser("analyze"); p.add_argument("conference"); p.add_argument("--finalize", action="store_true")
    p.add_argument("--db"); p.set_defaults(fn=cmd_analyze)
    p = sub.add_parser("keywords"); conf_args(p); p.set_defaults(fn=cmd_keywords)
    p = sub.add_parser("export"); p.add_argument("what", choices=["histogram", "capture"]); p.add_argument("conference")
    p.set_defaults(fn=cmd_export)
    p = sub.add_parser("graphics"); p.add_argument("conference"); p.add_argument("--db")
    p.add_argument("--theme", default="oct2025", help="oct2025|thought_provoking|goldfish|oct2020|emo_kid|sugar|all")
    p.add_argument("--trends", help="comma list of words/phrases for the 2x2 trend panel")
    p.add_argument("--speaker-phrases", help="comma list of phrases for the top-speaker cards")
    p.add_argument("--min-count", type=int, default=0,
                   help="extra fixed-count floor for the plotted words (the top-300 rank gate already applies)")
    p.set_defaults(fn=cmd_graphics)
    p = sub.add_parser("leaders"); p.add_argument("--no-phrases", action="store_true"); p.set_defaults(fn=cmd_leaders)
    p = sub.add_parser("add-conference"); p.add_argument("conference"); p.add_argument("--delay", type=float, default=1.5)
    p.set_defaults(fn=cmd_add_conference)
    a = ap.parse_args(argv)
    a.archive = Path(a.archive)
    a.fn(a)


if __name__ == "__main__":
    main()

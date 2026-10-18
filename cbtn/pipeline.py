"""Per-conference counting: word + phrase histograms written into the archive (PLAN.md §4)."""
from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

from .archive import conference_dir, iter_talks
from .phrases import PhraseCounts, PhraseMatcher
from .tokenize import DigitPolicy, Histogram, TokenizeLog


def count_conference(root: str | Path, conf_key: str, matcher: PhraseMatcher | None,
                     policy: DigitPolicy | None = None) -> dict:
    h, log = Histogram(), TokenizeLog()
    phr = PhraseCounts()
    phr_talks: dict[str, set] = defaultdict(set)
    per_talk_words: dict[str, Counter] = {}
    per_talk_phr: dict[str, PhraseCounts] = {}
    n_talks = 0
    for t in iter_talks(root, conf_key):
        if not t.counts_toward_histograms:
            continue
        n_talks += 1
        tw = Histogram()
        tp = PhraseCounts()
        for p in t.spoken_paragraphs():
            kw = dict(markers=t.markers_for(p), policy=policy)
            h.add(p.spoken_text, talk_id=t.talk_id, speaker_id=t.speaker.speaker_id, log=log, **kw)
            tw.add(p.spoken_text, **kw)
            if matcher:
                tp.merge(matcher.count(p.spoken_text, **kw))
        per_talk_words[t.talk_id] = tw.counts
        if matcher:
            per_talk_phr[t.talk_id] = tp
            phr.merge(tp)
            for pid in tp.total:
                phr_talks[pid].add(t.talk_id)

    cdir = conference_dir(root, conf_key)
    h.write_csv(cdir / "histogram_words.csv")
    if matcher:
        total_words = h.total or 1
        with open(cdir / "histogram_phrases.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["phrase_id", "canonical", "category", "total", "standalone", "nested_in",
                        "standalone_rate_per_10k", "talks_using"])
            for pid, tot in sorted(phr.total.items(), key=lambda kv: -phr.standalone[kv[0]]):
                e = matcher.entries[pid]
                nest = "; ".join(f"{matcher.entries[k].canonical}: {v}" for k, v in phr.nested_in.get(pid, {}).items())
                w.writerow([pid, e.canonical, e.category, tot, phr.standalone[pid], nest,
                            round(phr.standalone[pid] / total_words * 10000, 4), len(phr_talks[pid])])
    return {"conference": conf_key, "talks": n_talks, "words": h.total, "unique": len(h.counts),
            "marker_splits": len(log.marker_splits), "digit_kept": sum(log.digit_kept.values()),
            "digit_dropped": sum(log.digit_dropped.values()), "url_dropped": sum(log.url_dropped.values()),
            "per_talk_words": per_talk_words, "per_talk_phrases": per_talk_phr, "log": log}

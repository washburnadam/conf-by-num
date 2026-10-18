"""Free keywords at import time (PLAN.md §5.4): TF-IDF top terms per talk vs. the whole corpus.
LLM keywords (Step 7) are a later, separate job; this file only writes source='tfidf'.

Output per conference: archive/conferences/YYYY-MM/keywords.csv
  talk_id, term, kind, source, weight, run_id, reviewed
"""
from __future__ import annotations

import csv
import math
from collections import Counter
from datetime import date
from pathlib import Path

from .archive import conference_dir, iter_talks, list_conferences
from .tokenize import tokens

MIN_LEN = 3


def talk_counts(talk) -> Counter:
    c = Counter()
    for p in talk.spoken_paragraphs():
        for k, _ in tokens(p.spoken_text, markers=talk.markers_for(p)):
            if len(k) >= MIN_LEN and not k.isdigit():
                c[k] += 1
    return c


def build_tfidf(archive_root: str | Path, top_n: int = 15, exclude: set[str] | None = None,
                conferences: list[str] | None = None) -> dict:
    exclude = exclude or set()
    all_confs = list_conferences(archive_root)
    df: Counter = Counter()
    per_talk: dict[str, tuple[str, Counter]] = {}
    n_docs = 0
    for ck in all_confs:                        # document frequency always over the whole archive
        for t in iter_talks(archive_root, ck):
            if not t.counts_toward_histograms:
                continue
            c = talk_counts(t)
            df.update(c.keys())
            n_docs += 1
            if conferences is None or ck in conferences:
                per_talk[t.talk_id] = (ck, c)
    run_id = f"tfidf-{date.today().isoformat()}"
    by_conf: dict[str, list[dict]] = {}
    for tid, (ck, c) in per_talk.items():
        total = sum(c.values()) or 1
        scored = []
        for term, n in c.items():
            if term in exclude or n < 2:
                continue
            idf = math.log((1 + n_docs) / (1 + df[term]))   # common words -> ~0
            scored.append((n / total * idf, term))
        for w, term in sorted(scored, reverse=True)[:top_n]:
            by_conf.setdefault(ck, []).append({"talk_id": tid, "term": term, "kind": "keyword", "source": "tfidf",
                                               "weight": round(w, 6), "run_id": run_id, "reviewed": 0})
    for ck, rows in by_conf.items():
        path = conference_dir(archive_root, ck) / "keywords.csv"
        keep = []
        if path.exists():                       # keep other sources (site/llm/human)
            with open(path, newline="", encoding="utf-8-sig") as f:
                keep = [r for r in csv.DictReader(f) if r["source"] != "tfidf"]
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=["talk_id", "term", "kind", "source", "weight", "run_id", "reviewed"])
            w.writeheader()
            w.writerows(keep + rows)
    return {"talks": len(per_talk), "conferences": len(by_conf), "documents": n_docs, "run_id": run_id}

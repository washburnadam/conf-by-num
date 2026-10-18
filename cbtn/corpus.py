"""All-conference corpus (PLAN §4.2 step 2.5): sum of the per-conference word histograms.

Any conference can be left out (e.g. the conference being analyzed, so it is compared against all the others).
Reads archive/conferences/<conf>/histogram_words.csv; talks_using/speakers_using are recomputed from the talks.
"""
from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

from .archive import conference_dir, iter_talks, list_conferences
from .tokenize import tokens


def build_corpus(root: str | Path, through: str | None = None, exclude: set[str] | None = None,
                 first: str | None = None) -> tuple[list[dict], dict]:
    exclude = exclude or set()
    confs = [c for c in list_conferences(root)
             if c not in exclude and (through is None or c <= through) and (first is None or c >= first)]
    count, display = Counter(), defaultdict(Counter)
    talks_using, speakers_using = defaultdict(set), defaultdict(set)
    for ck in confs:
        path = conference_dir(root, ck) / "histogram_words.csv"
        with open(path, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                n = int(r["count"])
                count[r["word"]] += n
                display[r["word"]][r["display"]] += n
        for t in iter_talks(root, ck):
            if not t.counts_toward_histograms:
                continue
            seen = {k for p in t.spoken_paragraphs() for k, _ in tokens(p.spoken_text)}
            for w in seen:
                talks_using[w].add(t.talk_id)
                speakers_using[w].add(t.speaker.speaker_id)
    total = sum(count.values()) or 1
    rows = [{"rank": i, "word": w, "display": display[w].most_common(1)[0][0], "count": n,
             "rate_per_10k": round(n / total * 10000, 4), "talks_using": len(talks_using[w]),
             "speakers_using": len(speakers_using[w])}
            for i, (w, n) in enumerate(sorted(count.items(), key=lambda kv: (-kv[1], kv[0])), 1)]
    meta = {"conferences": len(confs), "first": confs[0] if confs else "", "last": confs[-1] if confs else "",
            "excluded": sorted(exclude), "words": sum(count.values()), "unique": len(count)}
    return rows, meta


def write_corpus(rows: list[dict], meta: dict, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["rank", "word", "display", "count", "rate_per_10k", "talks_using",
                                          "speakers_using"])
        w.writeheader()
        w.writerows(rows)
    path.with_suffix(".meta.txt").write_text("\n".join(f"{k}: {v}" for k, v in meta.items()) + "\n", encoding="utf-8")

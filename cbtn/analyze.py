"""Standard frequency analysis (PLAN.md §6) — Adam's method as confirmed at CP-4.1 (docs/analysis_method.md).

  rate       = count / total_words * 10,000           (target and baseline)
  baseline   = all EARLIER conferences (target never included)
  ratio      = target_rate / baseline_rate            (2.0 = twice the baseline; workbook 'Ratio' = ratio - 1)
  excess     = count - baseline_rate * target_total / 10,000
  candidate  = among the top `top_n` (300) words of the conference by count, not a general-lexicon word
               (Wiktionary top 100), not a new word, ratio >= min_ratio (2.0) [and count >= min_count if set]
  new words  = no use in any earlier conference (listed separately, no ratio)
Nothing is removed automatically: noise is FLAGGED (name part / single letter, possessive of a counted word,
function word, near-duplicate, single-talk spike) for Adam's choice at the graphics step (Step 5).
"""
from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULTS = {"top_n": 300, "min_count": 0, "min_ratio": 2.0, "new_word_max_baseline": 1,
            "single_talk_share_flag": 0.6, "lexicon_top": 100, "function_word_top": 1000,
            "threshold_grid": {"top_n": [200, 300, 400], "min_ratio": [1.5, 2.0, 3.0]}}

ROOT = Path(__file__).resolve().parents[1]
CONTRACTION_BASES = {"it", "that", "he", "she", "there", "here", "what", "who", "where", "let", "how", "when", "why",
                     "everyone", "everything", "nobody", "somebody", "someone", "one"}
LEXICON_CSV = ROOT / "inputs" / "legacy" / "GeneralLexicon_Wiktionary_Top1000.csv"


def load_settings(path: str | Path | None, conf_key: str | None = None) -> dict:
    s = {k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULTS.items()}
    if path and Path(path).exists():
        y = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        s.update({k: v for k, v in y.items() if k != "per_conference"})
        if conf_key and conf_key in (y.get("per_conference") or {}):
            s.update(y["per_conference"][conf_key])
    return s


def load_lexicon(top: int, path: str | Path = LEXICON_CSV) -> set[str]:
    """The `top` most common general English words (Adam's 'Top 100 General?' column)."""
    from .tokenize import tokens
    if not Path(path).exists():
        return set()
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = sorted(csv.DictReader(f), key=lambda r: int(r["Rank"]))[:top]
    return {k for r in rows for k, _ in tokens(r["Word"])}


def leader_name_words(titles_csv: str | Path) -> set[str]:
    """Lower-case name parts of known leaders (flags 'dallin', 'oaks', 'russell', initials)."""
    from .textnorm import for_counting
    out: set[str] = set()
    if titles_csv and Path(titles_csv).exists():
        with open(titles_csv, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                for part in for_counting(r["name"]).replace(".", " ").split():
                    out.add(part.lower())
    return out


def load_word_list(path: str | Path | None) -> set[str]:
    if not path or not Path(path).exists():
        return set()
    return {ln.strip().lower() for ln in Path(path).read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")}


@dataclass
class Row:
    word: str
    count: int
    rank: int
    rate: float
    baseline_count: int
    baseline_rate: float
    ratio: float | None
    excess: float
    talks_using: int
    top_talk_share: float
    new_word: bool
    lexicon: bool
    excluded: bool
    candidate: bool
    name_flag: bool = False
    possessive_flag: bool = False
    function_flag: bool = False
    single_talk_flag: bool = False
    near_duplicate_of: str = ""

    @property
    def flags(self) -> list[str]:
        return [n for n, v in (("name", self.name_flag), ("possessive", self.possessive_flag),
                               ("function_word", self.function_flag), ("single_talk", self.single_talk_flag),
                               ("near_duplicate", bool(self.near_duplicate_of))) if v]


def compare(target: Counter, base: Counter, *, talks_using: dict[str, int] | None = None,
            top_talk_share: dict[str, float] | None = None, settings: dict | None = None,
            exclude: set[str] | None = None, name_words: set[str] | None = None,
            lexicon: set[str] | None = None, function_words: set[str] | None = None,
            common_words: set[str] | None = None) -> list[Row]:
    s = settings or DEFAULTS
    exclude, lexicon, function_words = exclude or set(), lexicon or set(), function_words or set()
    common_words = common_words or set()
    t_total = sum(target.values()) or 1
    b_total = sum(base.values()) or 1
    ranked = sorted(target.items(), key=lambda kv: (-kv[1], kv[0]))
    rank = {w: i for i, (w, _) in enumerate(ranked, 1)}
    top_n = s.get("top_n") or len(ranked)
    rows = []
    for w, n in ranked:
        bc = base.get(w, 0)
        rate = n / t_total * 10000
        brate = bc / b_total * 10000
        new = bc < s["new_word_max_baseline"]
        ratio = None if new or brate == 0 else rate / brate
        share = (top_talk_share or {}).get(w, 0.0)
        cand = (not new and w not in lexicon and w not in exclude and rank[w] <= top_n
                and n >= (s.get("min_count") or 0) and ratio is not None and ratio >= s["min_ratio"])
        # "father's" is a possessive of a counted word; "it's", "that's", "let's" are contractions, not possessives
        base_word = w[:-2] if w.endswith("'s") and w[:-2] not in CONTRACTION_BASES else ""
        rows.append(Row(w, n, rank[w], round(rate, 3), bc, round(brate, 4),
                        None if ratio is None else round(ratio, 3), round(n - brate * t_total / 10000, 2),
                        (talks_using or {}).get(w, 0), round(share, 3), new, w in lexicon, w in exclude, cand,
                        # a leader's name part that is also a common English word ('joy', 'grant') is not flagged
                        name_flag=(w in (name_words or set()) and w not in common_words) or len(w) == 1,
                        possessive_flag=bool(base_word) and base_word in target,
                        function_flag=w in function_words,
                        single_talk_flag=share >= s["single_talk_share_flag"]))
    # near-duplicates among candidates: same first 5 letters, e.g. invite / invitation (the more frequent one leads)
    cands = sorted((r for r in rows if r.candidate), key=lambda r: -r.count)
    for i, r in enumerate(cands):
        for other in cands[:i]:
            plural = {r.word, other.word} in ({other.word, other.word + "s"}, {r.word, r.word + "s"})
            if (len(r.word) >= 5 and len(other.word) >= 5 and r.word[:5] == other.word[:5] and not plural
                    and not r.possessive_flag):
                r.near_duplicate_of = other.word
                break
    rows.sort(key=lambda r: (not r.candidate, -(r.ratio or 0) if r.candidate else r.rank))
    return rows


def threshold_grid(rows: list[Row], settings: dict) -> list[dict]:
    out = []
    for tn in settings["threshold_grid"]["top_n"]:
        for mr in settings["threshold_grid"]["min_ratio"]:
            n = sum(1 for r in rows if not r.new_word and not r.lexicon and not r.excluded and r.rank <= tn
                    and r.ratio is not None and r.ratio >= mr)
            out.append({"top_n": tn, "min_ratio": mr, "words_passing": n})
    return out


CURATION_FIELDS = ["word", "count", "rank", "rate", "baseline_rate", "ratio", "percent_above_baseline", "excess",
                   "talks_using", "top_talk_share", "flags", "near_duplicate_of", "decision", "reason"]


def write_curation(rows: list[Row], path: str | Path, keep_previous: bool = True) -> int:
    """The consistent starting set for Adam: all candidates, flagged, nothing removed. Decisions survive re-runs."""
    path = Path(path)
    prev = {}
    if keep_previous and path.exists():
        with open(path, newline="", encoding="utf-8-sig") as f:
            prev = {r["word"]: r for r in csv.DictReader(f)}
    path.parent.mkdir(parents=True, exist_ok=True)
    cands = [r for r in rows if r.candidate]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=CURATION_FIELDS)
        w.writeheader()
        for r in cands:
            p = prev.get(r.word, {})
            w.writerow({"word": r.word, "count": r.count, "rank": r.rank, "rate": r.rate,
                        "baseline_rate": r.baseline_rate, "ratio": r.ratio,
                        "percent_above_baseline": round((r.ratio - 1) * 100, 1), "excess": r.excess,
                        "talks_using": r.talks_using, "top_talk_share": r.top_talk_share,
                        "flags": " ".join(r.flags), "near_duplicate_of": r.near_duplicate_of,
                        "decision": p.get("decision", ""), "reason": p.get("reason", "")})
    return len(cands)


def write_new_words(rows: list[Row], path: str | Path) -> int:
    news = sorted((r for r in rows if r.new_word), key=lambda r: (-r.count, r.word))
    path = Path(path)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["word", "count", "talks_using", "flags"])
        w.writeheader()
        for r in news:
            w.writerow({"word": r.word, "count": r.count, "talks_using": r.talks_using, "flags": " ".join(r.flags)})
    return len(news)


def write_rows(rows: list[Row], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(Row.__dataclass_fields__))
        w.writeheader()
        for r in rows:
            w.writerow(r.__dict__)


def finalize(curation_csv: str | Path, out_csv: str | Path) -> dict:
    """Keep rows whose decision is 'keep' (blank counts as undecided and is reported)."""
    with open(curation_csv, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    keep = [r for r in rows if r["decision"].strip().lower() == "keep"]
    undecided = [r["word"] for r in rows if not r["decision"].strip()]
    with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["word", "count", "ratio", "percent_above_baseline", "talks_using"])
        w.writeheader()
        for r in keep:
            ratio = float(r["ratio"])
            w.writerow({"word": r["word"], "count": r["count"], "ratio": ratio,
                        "percent_above_baseline": round((ratio - 1) * 100, 1), "talks_using": r["talks_using"]})
    return {"kept": len(keep), "dropped": sum(1 for r in rows if r["decision"].strip().lower() == "drop"),
            "undecided": undecided}

"""Core unit tests (run: python -m pytest -q)."""
import json
import os
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cbtn.analyze import DEFAULTS, compare  # noqa: E402
from cbtn.citations import classify, strip_citations  # noqa: E402
from cbtn.mentions import Person, Resolver  # noqa: E402
from cbtn.parse import ParseContext, load_selectors, parse_talk  # noqa: E402
from cbtn.phrases import Entry, PhraseMatcher  # noqa: E402
from cbtn.textnorm import for_counting, normalize_chars  # noqa: E402
from cbtn.tokenize import Histogram, TokenizeLog, tokens  # noqa: E402


def keys(text, **kw):
    return [k for k, _ in tokens(text, **kw)]


# ---- tokenizer ---------------------------------------------------------------------------------
def test_ligatures_fixed():
    assert keys("ﬁnancial beneﬁt") == ["financial", "benefit"]


def test_apostrophes_kept_and_curly_normalized():
    assert keys("Savior’s don't ‘quoted’") == ["savior's", "don't", "quoted"]


def test_hyphens_and_dashes_split():
    assert keys("Latter-day Saints—all") == ["latter", "day", "saints", "all"]


def test_diacritics_folded():
    assert keys("Caussé Causse") == ["causse", "causse"]


def test_digit_policy():
    assert keys("the 5th and 21st in the 1830s and '80s") == ["the", "5th", "and", "21st", "in", "the", "1830s", "and", "80s"]
    assert keys("A1 MP3 13a 2024 H2O 23ff") == []


def test_case_insensitive_counting():
    assert keys("Faith FAITH faith") == ["faith", "faith", "faith"]


def test_footnote_backstop_splits_only_known_markers():
    log = TokenizeLog()
    assert keys("heart5 B12", markers={"5"}, log=log) == ["heart"]
    assert log.marker_splits == [("heart5", "heart")]


def test_superscripts_never_glue():
    assert normalize_chars("heart⁵") == "heart "


def test_histogram_display_and_spread():
    h = Histogram()
    h.add("Faith faith FAITH", talk_id="a", speaker_id="x")
    h.add("faith", talk_id="b", speaker_id="y")
    row = next(h.rows())
    assert row["count"] == 4 and row["talks_using"] == 2 and row["speakers_using"] == 2


# ---- phrases -----------------------------------------------------------------------------------
def E(pid, canon, variants=(), match_case=False):
    return Entry(pid, canon, list(variants), [], "", match_case, False, False, "")


def test_nesting_standalone():
    m = PhraseMatcher([E("1", "Jesus Christ"), E("2", "Church of Jesus Christ of Latter-day Saints"),
                       E("3", "Latter-day Saints")])
    pc = m.count("The Church of Jesus Christ of Latter-day Saints testifies of Jesus Christ.")
    assert pc.total["1"] == 2 and pc.standalone["1"] == 1 and pc.nested_in["1"]["2"] == 1
    assert pc.standalone["3"] == 0 and pc.standalone["2"] == 1


def test_overlapping_variants_count_once():
    m = PhraseMatcher([E("21", "Atonement of Jesus Christ", ["the Atonement"])])
    assert m.count("the Atonement of Jesus Christ").total["21"] == 1


def test_match_case():
    m = PhraseMatcher([E("72", "Young Women", match_case=True)])
    assert m.count("the Young Women program").total["72"] == 1
    assert m.count("many young women attended").total.get("72", 0) == 0


# ---- citations ---------------------------------------------------------------------------------
@pytest.mark.parametrize("inner,cls", [
    ("D&C 121:45", "citation"), ("see Alma 32", "citation"), ("Ensign, Nov. 1988, p. 4.", "citation"),
    ("Salt Lake City: Bookcraft, 1966", "citation"), ("emphasis added", "citation"),
    ("Teachings of Gordon B. Hinckley, 94", "citation"),
    ("perhaps a little cynically", "spoken"), ("and I remember it well", "spoken"),
    ("1966", "citation")])   # Adam, CP-1.3: year-only references are not spoken
def test_citation_classes(inner, cls):
    assert classify(inner)[0] == cls


def test_strip_keeps_spoken():
    text, found = strip_citations("He said (and I agree) that we should pray (Alma 34:17).")
    assert text == "He said (and I agree) that we should pray." and len(found) == 2


# ---- parser (synthetic fixture) ----------------------------------------------------------------
def test_parser_synthetic():
    sel = load_selectors(ROOT / "config/selectors.yaml")
    html = (ROOT / "tests/fixtures/synthetic_talk.html").read_text(encoding="utf-8")
    t = parse_talk(html, ParseContext(2026, 4, "https://x/study/general-conference/2026/04/15causse?lang=eng"), sel)
    assert t.speaker.name == "Gérald Caussé" and t.speaker.title == "Elder" and t.speaker.speaker_id == "gerald-causse"
    assert t.summary.startswith("As we abide")
    kinds = [p.kind for p in t.paragraphs]
    assert kinds == ["body", "heading", "body", "blockquote", "caption", "list_item", "list_item", "body"]
    p1 = t.paragraphs[0]
    assert "branches.” Abiding" in p1.spoken_text and p1.footnote_refs[0]["marker"] == "1"
    assert "(see John 15:4–5)" not in t.paragraphs[2].spoken_text
    assert "(and I remember it well)" in t.paragraphs[2].spoken_text
    assert len(t.notes) == 3 and t.notes[0]["links"]
    assert not any("5" in k for p in t.paragraphs for k in keys(p.spoken_text, markers=t.markers_for(p)))


# ---- mentions ----------------------------------------------------------------------------------
def _resolver():
    def P(name, title, s, e):
        p = Person(name)
        p.periods[title].append((s, e))
        return p
    people = {
        "M. Russell Ballard": P("M. Russell Ballard", "Elder", "1985-10-10", "2023-11-12"),
        "Melvin J. Ballard": P("Melvin J. Ballard", "Elder", "1919-01-07", "1939-07-30"),
        "Gerald Causse": P("Gerald Causse", "Bishop", "2012-03-31", "2025-11-14"),
    }
    return Resolver(people)


def test_mentions_steps():
    r = _resolver()
    m = r.resolve_talk("t", "2010-04-03", ["Elder Ballard taught us."])[0]
    assert m.person == "M. Russell Ballard" and m.step == "title_date"
    m = r.resolve_talk("t", "2010-04-03", ["Elder Ballard taught us."], [["Melvin J. Ballard, Sermons, 1949, 2."]])[0]
    assert m.person == "Melvin J. Ballard" and m.step == "footnote"
    m = r.resolve_talk("t", "2018-04-01", ["Bishop Caussé spoke."])[0]
    assert m.person == "Gerald Causse"
    assert r.resolve_talk("t", "2010-04-03", ["Elder M. Russell Ballard said"]) == []


# ---- analysis ----------------------------------------------------------------------------------
def test_compare_basic():
    tgt = Counter({"faith": 30, "vine": 12, "the": 500})
    base = Counter({"faith": 1000, "vine": 10, "the": 60000})
    rows = {r.word: r for r in compare(tgt, base, settings=DEFAULTS)}
    assert rows["vine"].candidate and not rows["the"].candidate


def test_compare_cp41_rules():
    tgt = Counter({"the": 500, "invitation": 30, "invite": 20, "god's": 25, "god": 40, "russell": 25, "m": 25,
                   "zzz": 3, "covid": 9})
    base = Counter({"the": 60000, "invitation": 100, "invite": 80, "god's": 90, "god": 4000, "russell": 50,
                    "m": 50, "zzz": 900})
    rows = {r.word: r for r in compare(tgt, base, settings=dict(DEFAULTS, top_n=7),
                                       lexicon={"the"}, name_words={"russell"})}
    assert not rows["the"].candidate                                   # general lexicon
    assert rows["covid"].new_word and not rows["covid"].candidate      # never used before -> new words list
    assert not rows["zzz"].candidate                                   # below the baseline
    assert rows["invite"].near_duplicate_of == "invitation"
    assert rows["god's"].possessive_flag and rows["russell"].name_flag and rows["m"].name_flag
    assert rows["god's"].candidate                                     # flagged, never removed automatically


# ---- usage harness -----------------------------------------------------------------------------
@pytest.mark.skipif(not (ROOT / ".claude" / "usage_common.py").exists(),
                    reason="usage harness is private (not in the public export)")
def test_harness_soft_hard(tmp_path):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(tmp_path))
    (tmp_path / ".claude").mkdir()
    for f in ["usage_common.py", "statusline.py"]:
        (tmp_path / ".claude" / f).write_text((ROOT / ".claude" / f).read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / ".claude/hooks").mkdir()
    for f in ["budget_guard.py"]:
        (tmp_path / ".claude/hooks" / f).write_text((ROOT / ".claude/hooks" / f).read_text(encoding="utf-8"),
                                                    encoding="utf-8")

    def status(fh, sd, reset_in):
        data = {"rate_limits": {"five_hour": {"used_percentage": fh, "resets_at": time.time() + reset_in},
                                "seven_day": {"used_percentage": sd, "resets_at": time.time() + 3 * 86400}}}
        subprocess.run([sys.executable, str(tmp_path / ".claude/statusline.py")], input=json.dumps(data),
                       text=True, capture_output=True, env=env, check=True)

    def decision(tool, ti):
        out = subprocess.run([sys.executable, str(tmp_path / ".claude/hooks/budget_guard.py")],
                             input=json.dumps({"tool_name": tool, "tool_input": ti}), text=True,
                             capture_output=True, env=env).stdout
        return json.loads(out)["hookSpecificOutput"]["permissionDecision"] if out.strip() else "allow"

    status(50, 10, 3600)
    assert decision("Bash", {"command": "ls"}) == "allow"
    status(81, 10, 3600)
    assert decision("Bash", {"command": "ls"}) == "deny"
    assert decision("Write", {"file_path": "reports/HANDOFF.md"}) == "allow"
    status(85, 10, 600)          # late window -> 95% hard
    assert decision("Bash", {"command": "ls"}) == "allow"
    status(40, 82, 3600)         # weekly stop
    assert decision("Bash", {"command": "python tools/schedule_resume.py"}) == "deny"


# ---- regression against Adam's April 2026 files (skips if missing) ----------------------------
LEG = ROOT / "inputs/legacy"


@pytest.mark.skipif(not (LEG / "WordHistogram_Apr2026.xlsx").exists(), reason="legacy files not present")
def test_apr2026_total_matches_legacy():
    from cbtn.legacy import read_capture, read_histogram
    h = Histogram()
    for t in read_capture(LEG / "ConferenceCapture_Apr2026.xlsx"):
        for p in t.paragraphs:
            h.add(p)
    legacy = read_histogram(LEG / "WordHistogram_Apr2026.xlsx")
    # 42,341 in legacy; one intended difference since CP-2.4: Elder Gong's "talk[s]" is one word ("talks"), the
    # old Excel tool split it into "talk" + "s"
    assert h.total == sum(legacy.values()) - 1
    folded = Counter()
    for w, n in legacy.items():
        folded[for_counting(w).lower()] += n
    folded["talk"] -= 1
    folded["s"] -= 1
    folded["talks"] += 1
    assert dict(folded) == dict(h.counts)          # every other difference = ligature or diacritic folding

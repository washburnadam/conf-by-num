"""Medium.com header images (Adam, 2026-10-17) → outputs/final/<conf>/medium_<A|B|C>_<conf>.png (+ .pptx)

16:9 landscape, 1600 x 900 px (8 x 4.5 in at 200 dpi): Medium's recommended header width with a ratio that crops
cleanly to its thumbnails. Drawn with the poster's Canvas, so each also exists as an editable PowerPoint slide.

  A  Banner + top words: classic orange title panel on the left, the most-emphasized words as a lollipop list
  B  Bubble cloud: every emphasized word/phrase as a packed circle (area = uses, topic colours), title overlaid
  C  Number cards: four big facts for the conference (talk length, emphasized words, unique words, top word)

Usage: python tools/medium_headers.py 2026-04 2026-10
"""
from __future__ import annotations

import csv
import math
import sqlite3
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import conference_poster as cp  # noqa: E402
from conference_poster import BODY, HEAD, INK, MUTED, T, TOPIC_COLORS, Canvas, conf_label, text_w  # noqa: E402

WH, HH = 8.0, 4.5


def topic_colors(items):
    import yaml
    topics = yaml.safe_load((ROOT / "config/word_topics.yaml").read_text(encoding="utf-8"))
    where = {w: t for t, ws in topics.items() for w in ws}
    used = []
    for i in sorted(items, key=lambda i: -i["n"]):
        t = where.get(i["key"], "Other")
        if t not in used:
            used.append(t)
    return {i["key"]: TOPIC_COLORS[used.index(where.get(i["key"], "Other")) % len(TOPIC_COLORS)] for i in items}


def title_block(c, x, y, size=30, color="#FFFFFF", conf=None, ha="left", width=None):
    if width:                                          # shrink to fit the panel
        while size > 12 and text_w("…BY THE NUMBERS", size) > width:
            size -= 0.5
    c.text(x, y, "CONFERENCE…", size, color, ha=ha)
    c.text(x, y + size / 72 * 1.15, "…BY THE NUMBERS", size, color, ha=ha)
    if conf:
        c.text(x, y + size / 72 * 2.15, f"{conf_label(conf)} General Conference", size * 0.42, color, BODY, ha=ha,
               bold=False)


# ---------------------------------------------------------------- A
def header_a(conf, items):
    c = Canvas(h=HH)
    c.rect(0, 0, 3.3, HH, T["banner"])
    c.rect(3.3, 0, 0.12, HH, T["band"])
    title_block(c, 0.35, 1.45, 26, conf=conf, width=3.3 - 0.6)
    c.text(0.35, 3.85, "What did the speakers emphasize?", 11, "#FFFFFF", BODY, ha="left", bold=False)
    top = sorted(items, key=lambda i: -i["x"])[:9]
    x0, x1 = 5.35, 7.55
    lo, hi = 1.0, math.log2(max(i["x"] for i in top)) + 0.15
    c.text(3.75, 0.42, "Most emphasized words and phrases", 13, INK, ha="left")
    c.text(3.75, 0.68, "times as often as in past conferences", 9, MUTED, BODY, ha="left", bold=False)
    for k, it in enumerate(top):
        y = 1.05 + k * 0.37
        X = x0 + (math.log2(it["x"]) - lo) / (hi - lo) * (x1 - x0)
        c.text(5.2, y, it["label"], 11, T["band"] if it["phrase"] else INK, HEAD if not it["phrase"] else BODY,
               ha="right", bold=None if not it["phrase"] else True)
        c.line(x0, y, X, y, "#D9D3C9", 2.5)
        c.circle(X, y, 0.15, T["point"])
        c.text(X + 0.14, y, f"{it['x']:.0f}×" if it["x"] >= 10 else f"{it['x']:.1f}×", 9, MUTED, BODY, ha="left",
               bold=False)
    return c


# ---------------------------------------------------------------- B
def pack_cloud(items, cx0, cy0, scale, box):
    """Greedy spiral packing, biggest first, inside box (x0, y0, x1, y1)."""
    placed = []
    for it in sorted(items, key=lambda i: -i["n"]):
        r = scale * math.sqrt(it["n"]) / 2
        t = 0.0
        while t < 400:
            x = cx0 + 0.035 * t * math.cos(t) * 1.6
            y = cy0 + 0.035 * t * math.sin(t) * 0.9
            ok = box[0] + r <= x <= box[2] - r and box[1] + r <= y <= box[3] - r
            if ok and all(math.hypot(x - px, y - py) >= r + pr + 0.03 for px, py, pr, _ in placed):
                placed.append((x, y, r, it))
                break
            t += 0.08
    return placed


def header_b(conf, items):
    c = Canvas(h=HH, bg="#FBF8F3")
    cols = topic_colors(items)
    maxn = max(i["n"] for i in items)
    scale = 1.25 / math.sqrt(maxn)
    placed = pack_cloud(items, 5.3, 2.25, scale, (2.8, 0.15, WH - 0.12, HH - 0.15))
    for x, y, r, it in placed:
        col = cols[it["key"]]
        if it["phrase"]:
            c.circle(x, y, 2 * r - 1.2 / 72, "#FFFFFF", col, 1.2)
        else:
            c.circle(x, y, 2 * r, col)
        for size in (18, 14, 11, 9, 7.5):
            if text_w(it["label"], size, HEAD) <= 2 * r * 0.86 and size / 72 * 1.1 <= 2 * r * 0.8:
                c.text(x, y, it["label"], size, col if it["phrase"] else "#FFFFFF")
                break
    c.rect(0, 0, 2.6, HH, T["banner"])
    title_block(c, 0.28, 1.5, 21, conf=conf, width=2.6 - 0.5)
    cp_y = 3.6
    for ln in cp.wrap("Words and phrases spoken at least twice as often as usual · circle size = times used", 9,
                      2.6 - 0.5):
        c.text(0.28, cp_y, ln, 9, "#FFFFFF", BODY, ha="left", bold=False)
        cp_y += 0.17
    return c


# ---------------------------------------------------------------- C
def facts(con, conf, items):
    tot = con.execute("SELECT talks, words FROM conferences WHERE conf_key=?", (conf,)).fetchone()
    mins = {}
    tl = ROOT / "outputs/family_review/talk_length.csv"
    if tl.exists():
        mins = {r["conf"]: r["median_minutes"] for r in csv.DictReader(open(tl, encoding="utf-8-sig"))}
    import yaml
    uniq = len(yaml.safe_load((ROOT / "config/unique_words_keep.yaml").read_text(encoding="utf-8")).get(conf, []))
    new_words = sum(1 for _ in csv.DictReader(open(ROOT / f"archive/conferences/{conf}/analysis/new_words.csv",
                                                   encoding="utf-8-sig")))
    top = max((i for i in items if not i["phrase"]), key=lambda i: i["x"])   # a single word, not a name or phrase
    past = [float(v) for k, v in mins.items() if v and "1971" <= k < "2000"]
    return [
        (f"{mins.get(conf, '?')}", "minutes: the typical talk",
         f"was {statistics.median(past):.0f} min in 1971–1999" if past else ""),
        (f"{len(items)}", "words and phrases", "used at least twice as often as usual"),
        (f"{new_words}", "brand-new words", "never spoken in conference since 1971"),
        (f"{top['x']:.0f}×", f"“{top['label']}”", "the most emphasized word"),
    ]


def header_c(con, conf, items):
    c = Canvas(h=HH)
    c.rect(0, 0, WH, 1.3, T["banner"])
    c.text(WH / 2, 0.45, "CONFERENCE… …BY THE NUMBERS", 28, "#FFFFFF")
    c.text(WH / 2, 0.95, f"{conf_label(conf)} General Conference", 13, "#FFFFFF", BODY, bold=False)
    fills = [T["band"], T["point"], T["panel"], T["up"]]
    cw, gap = 1.75, 0.12
    x = (WH - (4 * cw + 3 * gap)) / 2
    for k, (big, mid, small) in enumerate(facts(con, conf, items)):
        c.rect(x, 1.6, cw, 2.55, fills[k], r=0.12)
        size = 40 if text_w(big, 40) <= cw - 0.2 else 30
        c.text(x + cw / 2, 2.3, big, size, "#FFFFFF")
        msz = 12 if text_w(mid, 12) <= cw - 0.16 else 10
        c.text(x + cw / 2, 3.05, mid, msz, "#FFFFFF")
        for j, ln in enumerate(cp.wrap(small, 9, cw - 0.24)):
            c.text(x + cw / 2, 3.38 + j * 0.17, ln, 9, "#FFFFFF", BODY, bold=False)
        x += cw + gap
    return c


def main(confs):
    con = sqlite3.connect(ROOT / "data/cbtn.sqlite")
    cp.W = WH                              # the poster backends size the figure/slide from cp.W
    for conf in confs:
        items, *_ = cp.emphasized_items(con, conf)
        out = ROOT / "outputs/final" / conf
        for name, c in (("A", header_a(conf, items)), ("B", header_b(conf, items)), ("C", header_c(con, conf, items))):
            cp.render_png(c, out / f"medium_{name}_{conf}.png")
            cp.render_pptx([c], out / f"medium_{name}_{conf}.pptx")
        print(f"{conf}: medium_A/B/C written (1600 x 900 px) -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main(sys.argv[1:])

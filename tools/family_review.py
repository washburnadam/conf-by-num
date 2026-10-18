"""Family review pack (Step 5, Adam's request 2026-10-11) for each conference → outputs/family_review/<conf>/

  words.md            all candidate words: word, uses, % above past average, plain-language note
  unique_words.md     words never used in an earlier conference (with uses)
  classic_scatter.png the classic "Emphasized Conference Words" chart, standalone, leader lines, inset for frequent words
  rising_words.png    lollipop + 50-year sparklines, ONLY words with a continual long-term increase
  rising_phrases.png  same format for phrases
  topics_vs_past.png  E-style: bubbles by % above past (x), one row per topic, size + number = uses
  F_small_multiples.png  mockup: 50-year small multiples with each word's earlier peak annotated (talk + speaker)

Usage: python tools/family_review.py 2026-04 2026-10
"""
from __future__ import annotations

import csv
import math
import sqlite3
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import yaml  # noqa: E402
from adjustText import adjust_text  # noqa: E402
from matplotlib.ticker import FuncFormatter, NullLocator  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cbtn.graphics import THEMES, _font, conf_label  # noqa: E402

T = THEMES["oct2025"]
F = [_font(), "Segoe UI", "DejaVu Sans"]     # Aharoni lacks some glyphs (→ ×): fall back per glyph
plt.rcParams["font.family"] = F
import logging  # noqa: E402
logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)   # "Aharoni has only bold" notices
NOTES = {"name": "part of a name", "possessive": "possessive form", "function_word": "common everyday word",
         "single_talk": "mostly from one talk"}


# ---------------------------------------------------------------- data
def load(conf):
    a = ROOT / f"archive/conferences/{conf}/analysis"
    cur = list(csv.DictReader(open(a / "curation.csv", encoding="utf-8-sig")))
    allw = {r["word"]: r for r in csv.DictReader(open(a / "all_words.csv", encoding="utf-8-sig"))}
    new = list(csv.DictReader(open(a / "new_words.csv", encoding="utf-8-sig")))
    disp = {r["word"]: r["display"] for r in csv.DictReader(
        open(ROOT / f"archive/conferences/{conf}/histogram_words.csv", encoding="utf-8-sig"))}
    phr = list(csv.DictReader(open(a / "phrases.csv", encoding="utf-8-sig")))
    # Adam's note #3: the prophet's name counts as ONE item (the full-name phrase), not dallin / h / oaks
    for p in phr:
        if p["phrase"] in MERGED_NAMES and p["ratio"] and float(p["ratio"]) >= 2:
            cur.append({"word": p["phrase"], "count": p["count"], "rank": "", "ratio": p["ratio"], "flags": "",
                        "near_duplicate_of": "", "decision": "", "reason": "", "phrase": True})
            disp[p["phrase"]] = p["phrase"]
    cur.sort(key=lambda r: -float(r["ratio"]))
    return cur, allw, new, disp, phr


MERGED_NAMES = ("Dallin H. Oaks",)


def removed(r):
    return r.get("decision", "").strip().lower() in ("drop", "merge")


def plain(r):
    """The provisional pick: starting set minus names, possessives, everyday words, near-duplicates, Adam's drops."""
    return (not any(f in r["flags"] for f in ("name", "possessive", "function_word")) and not r["near_duplicate_of"]
            and not removed(r))


def pct(ratio):
    return f"+{(float(ratio) - 1) * 100:,.0f}%"


def series(con, conf, word=None, pid=None):
    confs = [r[0] for r in con.execute("SELECT conf_key FROM conferences WHERE conf_key<=? ORDER BY conf_key", (conf,))]
    tot = dict(con.execute("SELECT conf_key, words FROM conferences"))
    if word:
        d = dict(con.execute("SELECT conf_key, count FROM conference_word_counts WHERE word=?", (word,)))
    else:
        d = dict(con.execute("SELECT conf_key, standalone FROM conference_phrase_counts WHERE phrase_id=?", (pid,)))
    return confs, [d.get(c, 0) / tot[c] * 1e4 for c in confs], [d.get(c, 0) for c in confs]


def continual_increase(rates_hist):
    """Five eras 1971 → the conference before: each era's mean >= 0.9 x the previous, last >= 2 x first."""
    n = len(rates_hist)
    if n < 20:
        return False
    k = n // 5
    eras = [sum(rates_hist[i * k:(i + 1) * k if i < 4 else n]) / len(rates_hist[i * k:(i + 1) * k if i < 4 else n])
            for i in range(5)]
    if eras[0] == 0:
        return eras[-1] > 0 and all(eras[i + 1] >= 0.9 * eras[i] for i in range(4))
    # 2x (was 1.5x) plus a steady trend: Oct 2026 check showed era means alone let in flat, tiny histories ('lift')
    return (all(eras[i + 1] >= 0.9 * eras[i] for i in range(4)) and eras[-1] >= 2.0 * eras[0]
            and rank_corr(rates_hist) >= 0.35)


def rank_corr(v):
    """Spearman-style correlation of the values with time (rank of value vs. position)."""
    n = len(v)
    order = sorted(range(n), key=lambda i: v[i])
    ranks = [0.0] * n
    for r, i in enumerate(order):
        ranks[i] = r
    m = (n - 1) / 2
    num = sum((i - m) * (ranks[i] - m) for i in range(n))
    den = sum((i - m) ** 2 for i in range(n))
    return num / den if den else 0.0


# ---------------------------------------------------------------- markdown
def words_md(conf, cur, disp, out):
    lab = conf_label(conf)
    lines = [f"# {lab} General Conference — emphasized words", "",
             f"Words among the 300 most used in {lab} that were used **at least twice as often** as in all earlier "
             "general conferences since 1971 (per 10,000 words). Sorted from the biggest increase down.", "",
             "| # | Word | Uses | % above past average | Note |", "|---:|---|---:|---:|---|"]
    shown = [r for r in cur if not removed(r)]
    for i, r in enumerate(shown, 1):
        notes = [NOTES[f] for f in r["flags"].split() if f in NOTES]
        if r["near_duplicate_of"]:
            notes.append(f"similar to *{disp.get(r['near_duplicate_of'], r['near_duplicate_of'])}*")
        if r.get("phrase"):
            notes.append("full name counted as one item")
        lines.append(f"| {i} | **{disp.get(r['word'], r['word'])}** | {int(r['count']):,} | {pct(r['ratio'])} | "
                     f"{'; '.join(notes)} |")
    gone = [r for r in cur if removed(r)]
    lines += ["", "*% above past average*: +100% = used twice as often as usual. *Note* marks words that may be noise (names, possessives, everyday "
              "words, near-duplicates) or come mostly from one talk.", ""]
    if gone:
        lines += ["**Removed / merged (Adam's decisions):** " + "; ".join(
            f"{disp.get(r['word'], r['word'])} ({r['reason']})" for r in gone), ""]
    out.write_text("\n".join(lines), encoding="utf-8")


def unique_md(conf, new, disp, out):
    lab = conf_label(conf)
    items = sorted(new, key=lambda r: disp.get(r["word"], r["word"]).lower())
    lines = [f"# {lab} General Conference — unique words", "",
             f"**{len(items)} words** used in {lab} that had never been used in an earlier general conference (since "
             "1971). Number = uses in this conference. Many are names and places from stories.", "",
             "| Word | Uses | Word | Uses | Word | Uses |", "|---|---:|---|---:|---|---:|"]
    for i in range(0, len(items), 3):
        cells = []
        for r in items[i:i + 3]:
            cells += [disp.get(r["word"], r["word"]), r["count"]]
        cells += ["", ""] * (3 - len(items[i:i + 3]))
        lines.append("| " + " | ".join(str(c) for c in cells) + " |")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- charts
def classic_scatter(conf, cur, disp, out):
    pts = [r for r in cur if plain(r)]
    cnt = sorted(int(r["count"]) for r in pts)
    cap = cnt[int(len(cnt) * 0.8)] * 2.0 if len(cnt) > 5 else max(cnt) + 1
    main = [r for r in pts if int(r["count"]) <= cap]
    big = [r for r in pts if int(r["count"]) > cap]
    fig = plt.figure(figsize=(8, 7.2), dpi=200, facecolor=T["panel"])
    ax = fig.add_axes([0.12, 0.12, 0.84, 0.74])
    ax.set_facecolor(T["panel"])
    xs = [int(r["count"]) for r in main]
    ys = [float(r["ratio"]) - 1 for r in main]
    ax.scatter(xs, ys, s=60, color=T["point"], edgecolor="#1E1E1E", linewidth=0.6, zorder=3)
    ax.set_yscale("log", base=2)
    top = 2 ** math.ceil(math.log2(max(ys)))
    ticks = [2 ** k for k in range(0, int(math.log2(top)) + 1)]
    ax.set_ylim(0.9, top * 1.15)
    ax.yaxis.set_major_locator(matplotlib.ticker.FixedLocator(ticks))
    ax.yaxis.set_minor_locator(NullLocator())
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v * 100:.0f}%"))
    ax.set_xlim(0, max(xs) * 1.12)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(labelsize=8)
    ax.set_xlabel("# of Mentions", fontsize=11, fontweight="bold", fontfamily=F)
    ax.set_ylabel("% Increase over Average\n(log scale)", fontsize=11, fontweight="bold", fontfamily=F)
    texts = [ax.text(x, y, disp.get(r["word"], r["word"]), fontsize=8, fontfamily=F, fontweight="bold")
             for r, x, y in zip(main, xs, ys)]
    if big:   # very frequent words (Jesus, Christ…) would squash the x axis: show them in an inset
        ins = ax.inset_axes([0.70, 0.66, 0.28, 0.30])
        ins.set_facecolor("white")
        allx = [int(r["count"]) for r in pts]
        ins.scatter(allx, [float(r["ratio"]) - 1 for r in pts], s=10, color=T["point"])
        ins.set_yscale("log", base=2)
        ins.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v * 100:.0f}%"))
        ins.yaxis.set_minor_locator(NullLocator())
        ins.tick_params(labelsize=5.5)
        for k, r in enumerate(sorted(big, key=lambda r: -float(r["ratio"]))):
            ins.annotate(disp.get(r["word"], r["word"]), (int(r["count"]), float(r["ratio"]) - 1),
                         xytext=(-4, 5 if k % 2 == 0 else -9),     # alternate above/below (Jesus / Christ)
                         textcoords="offset points", ha="right", fontsize=6.5, fontfamily=F, fontweight="bold")
        ins.set_title("all words, incl. the most-used", fontsize=6.5, fontfamily=F)
    adjust_text(texts, x=xs, y=ys, ax=ax, expand=(1.6, 2.0), force_text=(0.4, 0.8),
                arrowprops=dict(arrowstyle="-", color="#1E1E1E", lw=0.6))
    fig.text(0.5, 0.94, "Emphasized Conference Words", ha="center", fontsize=20, fontweight="bold", fontfamily=F)
    fig.text(0.5, 0.905, f"{conf_label(conf)} General Conference · words used at least twice as often as in past "
             "conferences", ha="center", fontsize=9, fontfamily=F)
    fig.savefig(out, facecolor=T["panel"])
    plt.close(fig)


def lollipop(con, conf, items, title, subtitle, out):
    """items: (label, uses, ratio, rates) sorted by ratio desc."""
    n = len(items)
    fig = plt.figure(figsize=(7, 1.4 + 0.42 * n), dpi=200, facecolor="white")
    H = 1.4 + 0.42 * n
    ax = fig.add_axes([0.30, 0.7 / H, 0.38, (H - 1.5) / H])
    yy = list(range(n))[::-1]
    vals = [r - 1 for _, _, r, _ in items]
    ax.hlines(yy, 1, vals, color=T["band"], lw=2.2)
    ax.scatter(vals, yy, s=70, color=T["banner"], zorder=3, edgecolor="white", linewidth=1.2)
    ax.set_xscale("log", base=2)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"+{v * 100:.0f}%"))
    ax.xaxis.set_minor_locator(NullLocator())
    ax.set_yticks(yy)
    ax.set_yticklabels([f"{lab}  ({u})" for lab, u, _, _ in items], fontsize=9, fontfamily=F)
    ax.set_ylim(-0.6, n - 0.4)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.tick_params(axis="x", labelsize=7)
    ax.grid(axis="x", color="#E5E5E5", lw=0.6)
    fig.canvas.draw()
    to_fig = fig.transFigure.inverted()
    for k, (_, _, _, rates) in enumerate(items):
        _, fy = to_fig.transform(ax.transData.transform((1, yy[k])))     # this row's exact height on the page
        a = fig.add_axes([0.72, fy - 0.15 / H, 0.24, 0.30 / H])
        a.fill_between(range(len(rates)), rates, color=T["band"], alpha=0.35, lw=0)
        a.plot(rates, color=T["band"], lw=0.9)
        a.scatter([len(rates) - 1], [rates[-1]], s=12, color=T["banner"], zorder=3)
        a.axis("off")
    _, fy0 = to_fig.transform(ax.transData.transform((1, yy[0])))
    fig.text(0.72, fy0 + 0.22 / H, "1971 → today (uses per 10k words)", fontsize=7, color="#555", fontfamily=F,
             va="bottom")
    fig.text(0.05, (H - 0.45) / H, title, fontsize=16, fontweight="bold", fontfamily=F)
    fig.text(0.05, (H - 0.78) / H, subtitle, fontsize=8, color="#555", fontfamily=F)
    fig.savefig(out)
    plt.close(fig)


def rising_words(con, conf, cur, allw, disp, out):
    pool = [r for r in allw.values() if r["lexicon"] == "False" and r["new_word"] == "False" and r["ratio"]
            and int(r["rank"]) <= 300 and float(r["ratio"]) >= 1.5 and len(r["word"]) > 1]
    names = {r["word"] for r in cur if "name" in r["flags"] or removed(r)}
    items = []
    for r in pool:
        if r["word"] in names:
            continue
        _, rates, _ = series(con, conf, word=r["word"])
        if continual_increase(rates[:-1]):
            items.append((disp.get(r["word"], r["word"]), int(r["count"]), float(r["ratio"]), rates))
    items.sort(key=lambda t: -t[2])
    items = items[:15]
    lollipop(con, conf, items, f"Rising words · {conf_label(conf)}",
             "Used more than the past average AND rising steadily for decades (not a one-time spike)", out)
    return len(items)


def rising_phrases(con, conf, phr, out):
    ids = dict((r[1], r[0]) for r in con.execute("SELECT phrase_id, canonical FROM phrases"))
    items = []
    for r in phr:
        if not r["ratio"] or float(r["ratio"]) < 1.5 or int(r["count"]) < 3 or r["phrase"] not in ids:
            continue
        _, rates, _ = series(con, conf, pid=ids[r["phrase"]])
        if continual_increase(rates[:-1]):
            items.append((r["phrase"], int(r["count"]), float(r["ratio"]), rates))
    items.sort(key=lambda t: -t[2])
    items = items[:15]
    lollipop(con, conf, items, f"Rising phrases · {conf_label(conf)}",
             "Phrases used more than the past average AND rising steadily for decades (standalone uses)", out)
    return len(items)


def topics_vs_past(conf, cur, disp, out):
    # Adam's note #8: rows sorted low -> high going UP the chart (by the topic's total uses), so the
    # biggest topic sits on top; the layout runs top-down, hence the descending sort in topics_layout
    order, layout, seps, y, diam = topics_layout(topics_rows(cur))
    H = max(4.0, y * 0.62 + 1.6)
    fig, ax = plt.subplots(figsize=(10, H), dpi=200)
    _topics_draw(fig, ax, conf, order, layout, seps, y, diam, disp, H)
    fig.savefig(out)
    plt.close(fig)


def topics_rows(cur):
    topics = yaml.safe_load((ROOT / "config/word_topics.yaml").read_text(encoding="utf-8"))
    where = {w: t for t, ws in topics.items() for w in ws}
    rows = {}
    for r in cur:
        if plain(r):
            rows.setdefault(where.get(r["word"], "Other"), []).append(r)
    return rows


def topics_layout(rows):
    """Shared by the PNG and the interactive page: (order, [(topic, row|None, x, y)], separators, height, diam)."""
    order = sorted(rows, key=lambda t: -sum(int(r["count"]) for r in rows[t]))
    maxn = max(int(r["count"]) for t in rows for r in rows[t])
    SMAX = 1700                                     # marker area (pt^2) of the most-used word: AREA ∝ uses

    def diam(r):
        return math.sqrt(SMAX * int(r["count"]) / maxn)

    PT_PER_X, PT_PER_Y = 78, 45                     # approx. points per data unit at the figure size below
    layout, seps, y = [], [], 0.0
    for t in order:
        lanes: list[tuple[float, float]] = []       # (last x, last diameter) per lane
        placed = []
        for r in sorted(rows[t], key=lambda r: float(r["ratio"])):
            x = math.log2(float(r["ratio"]))
            d = diam(r)
            need = lambda ld: max(0.62, (ld + d) / 2 / PT_PER_X + 0.15)   # noqa: E731  bubble or label width
            lane = next((i for i, (lx, ld) in enumerate(lanes) if x - lx >= need(ld)), None)
            if lane is None:
                lanes.append((x, d))
                lane = len(lanes) - 1
            else:
                lanes[lane] = (x, d)
            placed.append((r, x, lane))
        step = (max(diam(r) for r, _, _ in placed) + 16) / PT_PER_Y
        step = max(step, 0.62)
        for r, x, lane in placed:
            layout.append((t, r, x, y + lane * step))
        layout.append((t, None, None, y + (len(lanes) - 1) * step / 2))   # row-label anchor
        y += len(lanes) * step + 0.55
        seps.append(y - 0.55 / 2 - step / 2 + 0.1)
    return order, layout, seps, y, diam


TOPIC_COLORS = [T["banner"], T["band"], T["point"], T["panel"], T["up"], T["right"], "#6A5E9C", "#8C8C8C"]


def _topics_draw(fig, ax, conf, order, layout, seps, y, diam, disp, H):
    fig.subplots_adjust(left=0.2, right=0.97, top=1 - 1.1 / H, bottom=0.55 / H)
    colors = TOPIC_COLORS
    for sy in seps[:-1]:                              # horizontal rule between categories
        ax.axhline(-sy, color="#BBBBBB", lw=0.7, zorder=1)
    for t, r, x, yy in layout:
        c = colors[order.index(t) % len(colors)]
        if r is None:
            ax.text(-0.02, -yy, t.replace(" & ", " &\n"), ha="right", va="center", fontsize=10, fontweight="bold",
                    fontfamily=F, color=c, transform=ax.get_yaxis_transform())
            continue
        n, d = int(r["count"]), diam(r)
        ax.scatter(x, -yy, s=d * d, color=c, alpha=0.85, edgecolor="white", linewidth=0.8, zorder=3)
        label = disp.get(r["word"], r["word"])
        if d >= 15:                                   # the number fits inside the bubble
            ax.text(x, -yy, str(n), ha="center", va="center", fontsize=6.5, color="white", fontweight="bold",
                    fontfamily=F, zorder=4)
        else:
            label += f" ({n})"
        ax.annotate(label, (x, -yy), xytext=(0, -(d / 2 + 2)), textcoords="offset points", ha="center", va="top",
                    fontsize=7.5, fontfamily=F, zorder=4)
    top = max(x for _, r, x, _ in layout if r is not None)
    xt = list(range(1, math.ceil(top) + 1))
    ax.set_xticks(xt)
    ax.set_xticklabels([f"{2 ** k:,}×" for k in xt], fontsize=9)
    ax.set_xlim(0.5, top + 0.6)
    ax.set_ylim(-(y - 0.3), 0.8)
    ax.set_yticks([])
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="x", color="#EEEEEE", lw=0.6, zorder=0)
    ax.set_xlabel("times as often as the average of all earlier conferences (log scale) →", fontsize=9,
                  fontfamily=F)
    fig.text(0.02, 1 - 0.45 / H, f"{conf_label(conf)}: what the speakers emphasized, by topic", fontsize=16,
             fontweight="bold", fontfamily=F)
    fig.text(0.02, 1 - 0.8 / H, "Further right = used more than usual · bubble AREA = uses in this conference · "
             "topics sorted by total uses · groups editable (config/word_topics.yaml)", fontsize=8, color="#555",
             fontfamily=F)


def small_multiples(con, conf, cur, disp, out, n=12):
    pts = [r for r in cur if plain(r)][:n]
    cols = 4
    rws = math.ceil(len(pts) / cols)
    fig, axes = plt.subplots(rws, cols, figsize=(11, 2.3 * rws + 1.2), dpi=200, sharex=True)
    fig.subplots_adjust(top=1 - 1.0 / (2.3 * rws + 1.2), hspace=0.75, wspace=0.25, left=0.04, right=0.98, bottom=0.06)
    tot = dict(con.execute("SELECT conf_key, words FROM conferences"))
    for ax, r in zip(axes.flat, pts):
        if r.get("phrase"):
            pid = con.execute("SELECT phrase_id FROM phrases WHERE canonical=?", (r["word"],)).fetchone()[0]
            confs, rates, counts = series(con, conf, pid=pid)
        else:
            confs, rates, counts = series(con, conf, word=r["word"])
        xv = [int(c[:4]) + (0.25 if c.endswith("04") else 0.75) for c in confs]
        ax.fill_between(xv, rates, color=T["band"], alpha=0.25, lw=0)
        ax.plot(xv, rates, color=T["band"], lw=0.8)
        ax.scatter(xv[-1:], rates[-1:], s=28, color=T["banner"], zorder=3)
        # earlier peak and the talk responsible
        k = max(range(len(confs) - 1), key=lambda i: rates[i])
        pc = confs[k]
        if r.get("phrase"):
            talk = con.execute("SELECT t.title, t.speaker_display, p.standalone FROM phrase_counts p JOIN talks t "
                               "USING(talk_id) WHERE p.phrase_id=? AND t.conf_key=? ORDER BY p.standalone DESC LIMIT 1",
                               (pid, pc)).fetchone()
        else:
            talk = con.execute("SELECT t.title, t.speaker_display, c.count FROM word_counts_raw c JOIN words w "
                               "USING(word_id) JOIN talks t USING(tid) WHERE w.word=? AND t.conf_key=? "
                               "ORDER BY c.count DESC LIMIT 1", (r["word"], pc)).fetchone()
        ax.scatter([xv[k]], [rates[k]], s=14, color=T["point"], zorder=3)
        if talk:
            who = talk[1].replace("President ", "").replace("Elder ", "").replace("Sister ", "").replace("Bishop ", "")
            title = talk[0].strip("“”\"' ")       # some titles already carry quotation marks
            note = f"earlier peak {pc[:4]}: {who},\n“{title[:34]}{'…' if len(title) > 34 else ''}” ({talk[2]}×)"
            ax.annotate(note, (xv[k], rates[k]), xytext=(0.03, 0.97), textcoords="axes fraction", fontsize=5.6,
                        va="top", fontfamily=F, color="#333",
                        arrowprops=dict(arrowstyle="-", color="#999", lw=0.5))
        ax.set_title(f"{disp.get(r['word'], r['word'])}  ({int(r['count'])} uses, {pct(r['ratio'])})", fontsize=9,
                     fontweight="bold", fontfamily=F, loc="left")
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.tick_params(labelsize=6.5)
        ax.set_ylim(0, max(rates) * 1.45)
    for ax in list(axes.flat)[len(pts):]:
        ax.axis("off")
    fig.text(0.04, 1 - 0.35 / (2.3 * rws + 1.2), f"50 years of {conf_label(conf)}'s emphasized words",
             fontsize=16, fontweight="bold", fontfamily=F)
    fig.text(0.04, 1 - 0.65 / (2.3 * rws + 1.2), "Uses per 10,000 words at every general conference since 1971 · "
             "orange dot = this conference · pink dot = the earlier peak and the talk behind it · MOCKUP",
             fontsize=8, color="#555", fontfamily=F)
    fig.savefig(out)
    plt.close(fig)


def main(confs):
    con = sqlite3.connect(ROOT / "data/cbtn.sqlite")
    for conf in confs:
        out = ROOT / "outputs/family_review" / conf
        out.mkdir(parents=True, exist_ok=True)
        cur, allw, new, disp, phr = load(conf)
        words_md(conf, cur, disp, out / f"words_{conf}.md")
        unique_md(conf, new, disp, out / f"unique_words_{conf}.md")
        classic_scatter(conf, cur, disp, out / f"classic_scatter_{conf}.png")
        nw = rising_words(con, conf, cur, allw, disp, out / f"rising_words_{conf}.png")
        npz = rising_phrases(con, conf, phr, out / f"rising_phrases_{conf}.png")
        topics_vs_past(conf, cur, disp, out / f"topics_vs_past_{conf}.png")
        small_multiples(con, conf, cur, disp, out / f"F_small_multiples_{conf}.png")
        print(f"{conf}: {len(cur)} words, {len(new)} unique, rising words {nw}, rising phrases {npz} -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main(sys.argv[1:])

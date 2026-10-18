"""Infographics (PLAN.md §7, docs/graphics_style.md).

Every conference gets the CLASSIC poster (Adam's established layout) plus NEW presentation ideas:
  classic_poster     tall infographic: banner, explainer arrows, emphasized-words scatter (log2 % increase),
                     word/phrase trends (2x2), unique-words cloud, top speakers for two phrases
  rising_words       ranked lollipop of % increase with a 50-year sparkline per word
  fingerprint        heatmap: each emphasized word's rate across every conference since 1971
  phrase_spotlight   phrases: standalone vs nested counts, % vs past, and top speakers since 1971

Data come from the SQLite index (data/cbtn.sqlite or data/legacy.sqlite). Output: PNG (200 dpi) + SVG and a
CSV of the plotted numbers, in outputs/graphics/YYYY-MM/.
"""
from __future__ import annotations

import csv
import math
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.patches import FancyArrow, FancyBboxPatch, Rectangle  # noqa: E402
from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator  # noqa: E402

from .analyze import compare, leader_name_words  # noqa: E402

# ---------------------------------------------------------------------------------------------
# Themes: Adam's palettes (COLOURlovers samples in his decks) mapped to poster roles.
THEMES = {
    "thought_provoking": dict(  # Oct 2022 poster: ECD078 D95B43 C02942 542437 53777A
        banner="#542437", band="#53777A", up="#C02942", right="#D95B43", panel="#53777A",
        point="#2B1220", line="#C02942", header2="#ECD078", card1="#D95B43", card2="#53777A",
        page="#FFFFFF", ink="#1E1E1E"),
    "oct2025": dict(  # Oct 2025 poster (colors picked from ConfByNumbersOct2025.jpg, 2026-10-11)
        banner="#C8501E", band="#0E82A3", up="#F36C0F", right="#12B4E3", panel="#20B29B",
        point="#D23B6B", line="#D23B6B", header2="#C92A5C", card1="#C8501E", card2="#0E7F75",
        page="#FFFFFF", ink="#1E1E1E", banner_ink="#FFFFFF"),
    "goldfish": dict(  # Apr 2025 poster: 69D2E7 A7DBD8 E0E4CC F38630 FA6900
        banner="#FA6900", band="#A7DBD8", up="#FFCEB2", right="#69D2E7", panel="#E0E4CC",
        point="#FA6900", line="#F38630", header2="#69D2E7", card1="#F38630", card2="#69D2E7",
        page="#FFFFFF", ink="#1E1E1E"),
    "oct2020": dict(  # Oct 2020 poster: EF5030 F08E2B F7AC2A 58B6C2 519331
        banner="#EF5030", band="#58B6C2", up="#F7AC2A", right="#F08E2B", panel="#519331",
        point="#EF5030", line="#EF5030", header2="#58B6C2", card1="#F08E2B", card2="#58B6C2",
        page="#FFFFFF", ink="#1E1E1E"),
    "emo_kid": dict(  # sample palette: 556270 4ECDC4 C7F464 FF6B6B C44D58
        banner="#556270", band="#4ECDC4", up="#C44D58", right="#FF6B6B", panel="#556270",
        point="#C7F464", line="#C44D58", header2="#4ECDC4", card1="#FF6B6B", card2="#556270",
        page="#FFFFFF", ink="#1E1E1E"),
    "sugar": dict(  # sample palette: FE4365 FC9D9A F9CDAD C8C8A9 83AF9B
        banner="#FE4365", band="#83AF9B", up="#FC9D9A", right="#F9CDAD", panel="#C8C8A9",
        point="#FE4365", line="#FE4365", header2="#83AF9B", card1="#FC9D9A", card2="#83AF9B",
        page="#FFFFFF", ink="#1E1E1E"),
}
FONT_CANDIDATES = ["Aharoni", "Inter", "Segoe UI", "Arial", "DejaVu Sans"]
MONTH = {4: "April", 10: "October"}


def _font() -> str:
    # Aharoni ships as an Office *cloud font* (downloaded for Office apps only, not installed in Windows), so load
    # the files directly when present
    import glob
    import os
    for p in glob.glob(os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\FontCache\4\CloudFonts\Aharoni\*.ttf")):
        font_manager.fontManager.addfont(p)
    have = {f.name for f in font_manager.fontManager.ttflist}
    return next((f for f in FONT_CANDIDATES if f in have), "DejaVu Sans")


def _lum(hex_):
    r, g, b = (int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4  # noqa: E731
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def on(bg: str) -> str:
    """Readable text color on a background (white or near-black, WCAG contrast)."""
    L = _lum(bg)
    return "#FFFFFF" if (1.05 / (L + 0.05)) >= ((L + 0.05) / 0.05) else "#1E1E1E"


def ink(T: dict, bg: str) -> str:
    """Text color on a theme fill: the theme's banner_ink on the banner-colored fills (Oct 2025: white on orange)."""
    if "banner_ink" in T and bg in (T["banner"], T["card1"]):
        return T["banner_ink"]
    return on(bg)


def conf_label(ck: str) -> str:
    y, m = ck.split("-")
    return f"{MONTH.get(int(m), m)} {y}"


def clean_speaker(s: str) -> str:
    s = re.sub(r"^(By\s+)?(President|Elder|Sister|Bishop|Brother)\s+", "", (s or "").strip(), flags=re.I)
    return s.strip()


# ---------------------------------------------------------------------------------------------
@dataclass
class Data:
    con: sqlite3.Connection
    conf: str

    def confs(self):
        return [r[0] for r in self.con.execute("SELECT conf_key FROM conferences ORDER BY conf_key")]

    def words_total(self, ck):
        return self.con.execute("SELECT words FROM conferences WHERE conf_key=?", (ck,)).fetchone()[0]

    def word_series(self, word):
        d = dict(self.con.execute("SELECT conf_key, count FROM conference_word_counts WHERE word=?", (word,)))
        return [(ck, d.get(ck, 0), self.words_total(ck)) for ck in self.confs() if ck <= self.conf]

    def phrase_series(self, pid):
        d = dict(self.con.execute("SELECT conf_key, standalone FROM conference_phrase_counts WHERE phrase_id=?", (pid,)))
        return [(ck, d.get(ck, 0), self.words_total(ck)) for ck in self.confs() if ck <= self.conf]

    def comparison(self, settings=None, exclude=None, titles_csv=None):
        tgt = Counter(dict(self.con.execute(
            "SELECT word, count FROM conference_word_counts WHERE conf_key=?", (self.conf,))))
        base = Counter(dict(self.con.execute(
            "SELECT word, SUM(count) FROM conference_word_counts WHERE conf_key < ? GROUP BY word", (self.conf,))))
        tu = dict(self.con.execute("SELECT word, talks_using FROM conference_word_counts WHERE conf_key=?", (self.conf,)))
        share = dict(self.con.execute(
            "SELECT w.word, MAX(c.count)*1.0/SUM(c.count) FROM word_counts_raw c JOIN words w USING(word_id) "
            "JOIN talks t USING(tid) WHERE t.conf_key=? GROUP BY w.word", (self.conf,)))
        from .analyze import load_lexicon, load_settings
        names = leader_name_words(titles_csv) if titles_csv else set()
        st = settings or load_settings(Path(__file__).resolve().parents[1] / "config" / "analysis_defaults.yaml",
                                       self.conf)
        return compare(tgt, base, talks_using=tu, top_talk_share=share, settings=st, exclude=exclude,
                       name_words=names, lexicon=load_lexicon(st["lexicon_top"]),
                       function_words=load_lexicon(st["function_word_top"]), common_words=load_lexicon(1000))

    def top_speakers_phrase(self, pid, n=3):
        rows = self.con.execute(
            "SELECT t.speaker_display, SUM(p.standalone) s FROM phrase_counts p JOIN talks t USING(talk_id) "
            "WHERE p.phrase_id=? AND t.conf_key<=? GROUP BY t.speaker_id ORDER BY s DESC LIMIT ?",
            (pid, self.conf, n * 2)).fetchall()
        agg = Counter()
        for name, s in rows:
            agg[clean_speaker(name)] += s
        return agg.most_common(n)

    def phrase_rows(self):
        """Phrase comparison for the target conference (standalone counts, rate vs. all prior)."""
        cur = {r[0]: r for r in self.con.execute(
            "SELECT phrase_id, standalone, total, talks_using FROM conference_phrase_counts WHERE conf_key=?",
            (self.conf,))}
        base = dict(self.con.execute(
            "SELECT phrase_id, SUM(standalone) FROM conference_phrase_counts WHERE conf_key<? GROUP BY phrase_id",
            (self.conf,)))
        t_words = self.words_total(self.conf)
        b_words = self.con.execute("SELECT SUM(words) FROM conferences WHERE conf_key<?", (self.conf,)).fetchone()[0]
        names = dict(self.con.execute("SELECT phrase_id, canonical FROM phrases"))
        cats = dict(self.con.execute("SELECT phrase_id, category FROM phrases"))
        out = []
        for pid, (_, st, tot, tu) in cur.items():
            b = base.get(pid, 0)
            ratio = (st / t_words) / (b / b_words) if b else None
            out.append(dict(phrase_id=pid, phrase=names.get(pid, pid), category=cats.get(pid, ""), standalone=st,
                            total=tot, nested=tot - st, talks=tu, ratio=ratio))
        return out


def pick_emphasized(rows, curation_csv: Path | None, min_count: int, max_n: int = 30):
    """Use Adam's keep/drop decisions if present; otherwise an automatic provisional pick."""
    if curation_csv and curation_csv.exists():
        with open(curation_csv, newline="", encoding="utf-8-sig") as f:
            keep = {r["word"] for r in csv.DictReader(f) if r["decision"].strip().lower() == "keep"}
        if keep:
            return [r for r in rows if r.word in keep], "curated"
    # provisional: the CP-4.1 starting set minus the noise kinds Adam removed by hand (names, possessives, function
    # words, near-duplicates); 'single_talk' words stay (Adam kept Easter, mercy)
    auto = [r for r in rows if r.candidate and r.count >= min_count and not r.name_flag and not r.possessive_flag
            and not r.function_flag and not r.near_duplicate_of]
    auto.sort(key=lambda r: -(r.ratio or 0))
    return auto[:max_n], "provisional (automatic pick - not yet curated)"


# ---------------------------------------------------------------------------------------------
def _log2_pct_axis(ax, ymax_ratio):
    """y = percent increase over past average on a log2 scale, ticks 100%, 200%, 400% ..."""
    ax.set_yscale("log", base=2)
    top = max(2, 2 ** math.ceil(math.log2(max(ymax_ratio - 1, 1.01))))
    ticks = [2 ** k for k in range(0, int(math.log2(top)) + 1)]
    ax.set_ylim(0.9, top * 1.25)
    ax.yaxis.set_major_locator(FixedLocator(ticks))
    ax.yaxis.set_minor_locator(NullLocator())
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v * 100:.0f}%"))


def _place_labels(ax, xs, ys, labels, color, fontsize, font, obstacles=()):
    """Label placement: try positions around each point at growing radii; keep the first that stays inside
    the axes and overlaps no other label or point. Leader line drawn when the label is not adjacent."""
    fig = ax.figure
    fig.canvas.draw()
    trans = ax.transData
    bb = ax.get_window_extent()
    px = [trans.transform((x, y)) for x, y in zip(xs, ys)]
    scale = fig.dpi / 72
    hgt = fontsize * scale * 1.15
    placed = []                          # (x0, y0, x1, y1)
    pts_boxes = [(a - 4 * scale, b - 4 * scale, a + 4 * scale, b + 4 * scale) for a, b in px]
    for ob in obstacles:
        e = ob.get_window_extent()
        pts_boxes.append((e.x0 - 4, e.y0 - 4, e.x1 + 4, e.y1 + 4))

    def free(box):
        x0, y0, x1, y1 = box
        if x0 < bb.x0 + 2 or x1 > bb.x1 - 2 or y0 < bb.y0 + 2 or y1 > bb.y1 - 2:
            return False
        for b in placed + pts_boxes:
            if not (x1 < b[0] or x0 > b[2] or y1 < b[1] or y0 > b[3]):
                return False
        return True

    dirs = [(1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1), (0, 1), (0, -1)]
    order = sorted(range(len(px)), key=lambda i: (px[i][0], -px[i][1]))
    for i in order:
        x, y = px[i]
        w = len(labels[i]) * fontsize * scale * 0.56
        best = None
        for r in [8, 16, 26, 38, 52, 70, 90, 115, 140]:
            for dx, dy in dirs:
                cx, cy = x + dx * r * scale, y + dy * r * scale * 0.8
                x0 = cx if dx >= 0 else cx - w
                if dx == 0:
                    x0 = cx - w / 2
                box = (x0, cy - hgt / 2, x0 + w, cy + hgt / 2)
                if free(box):
                    best = (box, r, dx)
                    break
            if best:
                break
        if not best:                      # give up gracefully: put it right of the point
            box = (x + 6 * scale, y - hgt / 2, x + 6 * scale + w, y + hgt / 2)
            best = (box, 8, 1)
        box, r, dx = best
        placed.append(box)
        tx, ty = trans.inverted().transform(((box[0] + box[2]) / 2, (box[1] + box[3]) / 2))
        ax.annotate(labels[i], xy=(xs[i], ys[i]), xytext=(tx, ty), textcoords="data", ha="center", va="center",
                    fontsize=fontsize, color=color, fontfamily=font, annotation_clip=False, zorder=6,
                    arrowprops=None if r <= 16 else dict(arrowstyle="-", color=color, lw=0.6, shrinkA=2, shrinkB=3))


def _rounded(fig, x, y, w, h, color, r=0.25):
    p = FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}", transform=fig.dpi_scale_trans,
                       facecolor=color, edgecolor="none", zorder=0)
    fig.patches.append(p)


def _rect(fig, x, y, w, h, color):
    fig.patches.append(Rectangle((x, y), w, h, transform=fig.dpi_scale_trans, facecolor=color, edgecolor="none",
                                 zorder=0))


def _text(fig, x, y, s, size, color, weight="bold", ha="center", va="center", font=None, **kw):
    fig.text(x, y, s, transform=fig.dpi_scale_trans, fontsize=size, color=color, fontweight=weight, ha=ha, va=va,
             fontfamily=font, **kw)


def classic_poster(d: Data, emph, trends: list[tuple[str, str, list]], unique_words: list[str],
                   speaker_cards: list[tuple[str, list]], theme: str, out: Path, status: str) -> Path:
    T = THEMES[theme]
    F = _font()
    W = 7.0
    n_cards = len(speaker_cards[:2])
    H = 1.55 + 1.0 + 3.4 + 5.9 + 1.05 + 2 * 2.55 + 0.25 + 1.0 + 2.8 + 1.35 * n_cards + 0.35
    fig = plt.figure(figsize=(W, H), dpi=200, facecolor=T["page"])
    y = H
    # 1 banner
    _rect(fig, 0, y - 1.55, W, 1.55, T["banner"])
    bink = T.get("banner_ink", on(T["banner"]))
    _text(fig, W / 2, y - 0.5, "CONFERENCE…", 34, bink, font=F)
    _text(fig, W / 2, y - 1.1, "…BY THE NUMBERS", 34, bink, font=F)
    y -= 1.55
    # 2 band
    _rect(fig, 0, y - 1.0, W, 1.0, T["band"])
    _text(fig, W / 2, y - 0.5, f"{conf_label(d.conf)} General Conference of\nThe Church of Jesus Christ of "
          f"Latter-day Saints", 14, on(T["band"]), weight="normal", font=F, linespacing=1.15)
    y -= 1.0
    # 3 explainer arrows
    ytop = y - 0.15
    fig.patches.append(FancyArrow(1.55, ytop - 3.0, 0, 2.6, width=1.9, head_width=2.9, head_length=0.8,
                                  length_includes_head=True, transform=fig.dpi_scale_trans, color=T["up"], zorder=0))
    _text(fig, 1.55, ytop - 1.95, "The further up,\nthe more a word\nwas used compared\nto past conferences.", 11,
          on(T["up"]), font=F, linespacing=1.2)
    _text(fig, 1.55, ytop - 2.7, "(100% increase = used twice as\nmuch as the average past conference)", 6.5,
          on(T["up"]), weight="normal", font=F)
    _text(fig, 4.85, ytop - 0.75, "What words were\nemphasized by the\nspeakers?", 17, T["ink"], font=F)
    fig.patches.append(FancyArrow(3.1, ytop - 2.3, 3.7, 0, width=1.15, head_width=1.75, head_length=0.7,
                                  length_includes_head=True, transform=fig.dpi_scale_trans, color=T["right"], zorder=0))
    _text(fig, 4.6, ytop - 2.3, f"The further right, the more\ntimes a word was used in\n{conf_label(d.conf)}"
          " conference", 10, on(T["right"]), font=F, linespacing=1.15)
    y -= 3.4
    # 4 scatter panel
    ph = 5.6
    _rounded(fig, 0.25, y - ph, W - 0.5, ph, T["panel"], r=0.45)
    _text(fig, W / 2, y - 0.45, "Emphasized Conference Words", 18, on(T["panel"]), weight="normal", font=F)
    ax = fig.add_axes([1.15 / W, (y - ph + 0.75) / H, (W - 1.75) / W, (ph - 1.55) / H])
    ax.set_facecolor(T["panel"])
    ax.set_zorder(5)
    tc = on(T["panel"])
    counts = sorted(r.count for r in emph)
    cap = counts[int(len(counts) * 0.75)] * 2.2 if len(counts) > 4 else max(counts) * 1.15
    main = [r for r in emph if r.count <= cap]
    outl = [r for r in emph if r.count > cap]
    xs = [r.count for r in main]
    ys = [max(r.ratio - 1, 1.0) for r in main]
    ax.scatter(xs, ys, s=46, color=T["point"], edgecolor=T["panel"], linewidth=1.2, zorder=3)
    _log2_pct_axis(ax, max(r.ratio for r in emph))
    ax.set_xlim(0, max(xs) * (1.75 if outl else 1.12))
    ins = None
    if outl:   # Adam's Apr 2025 approach: an inset showing all words incl. the very frequent ones
        ins = ax.inset_axes([0.66, 0.1, 0.32, 0.42])
        ins.set_facecolor(T["page"])
        ins.scatter([r.count for r in emph], [max(r.ratio - 1, 1) for r in emph], s=12, color=T["point"])
        ins.set_yscale("log", base=2)
        ins.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v * 100:.0f}%"))
        ins.tick_params(labelsize=5)
        for k, r in enumerate(sorted(outl, key=lambda r: r.count)):
            ins.annotate(r.word, (r.count, max(r.ratio - 1, 1)), xytext=(0, 6 if k % 2 == 0 else -10),
                         textcoords="offset points",
                         ha="center", fontsize=6, fontfamily=F)
        ins.set_title("all words, incl. most-used", fontsize=6, fontfamily=F)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(tc)
    ax.tick_params(colors=tc, labelsize=7)
    ax.set_xlabel("# of Mentions", color=tc, fontsize=9, fontfamily=F)
    ax.set_ylabel("% Increase over Average # of Mentions\n(log scale)", color=tc, fontsize=9, fontfamily=F)
    _place_labels(ax, xs, ys, [r.word for r in main], tc, 7.5, F, obstacles=[ins] if ins else ())
    y -= ph + 0.3
    # 5 trends
    _rect(fig, 0, y - 0.9, W, 0.9, T["header2"])
    _text(fig, W / 2, y - 0.32, "Word and Phrase Trends", 17, on(T["header2"]), weight="normal", font=F)
    _text(fig, W / 2, y - 0.68, "Times used at each general conference since 1971", 9, on(T["header2"]),
          weight="normal", font=F)
    y -= 1.05
    cw, chh = (W - 1.2) / 2, 1.95
    for i, (title, kind, series) in enumerate(trends[:4]):
        cx = 0.55 + (i % 2) * (cw + 0.3)
        cy = y - (i // 2 + 1) * (chh + 0.6) + 0.25
        a = fig.add_axes([cx / W, cy / H, cw / W, chh / H])
        xv = [int(ck[:4]) + (0.33 if ck.endswith("04") else 0.83) for ck, _, _ in series]
        yv = [n for _, n, _ in series]
        a.plot(xv, yv, color=T["line"], lw=1, alpha=0.6, zorder=2)
        a.scatter(xv, yv, s=6, color=T["ink"], zorder=3)
        a.scatter(xv[-1:], yv[-1:], s=40, color=T["line"], edgecolor="white", linewidth=1.2, zorder=4)
        a.set_title(title, fontsize=10, fontweight="bold", fontfamily=F, color=T["ink"])
        a.set_xlim(1970, int(d.conf[:4]) + 2)
        a.tick_params(labelsize=6.5)
        for s in ("top", "right"):
            a.spines[s].set_visible(False)
    y -= 2 * (chh + 0.6) + 0.15
    # 6 unique words
    _rect(fig, 0, y - 0.9, W, 0.9, T["band"])
    _text(fig, W / 2, y - 0.3, f"Unique Words to {conf_label(d.conf)} Conference", 15, on(T["band"]),
          weight="normal", font=F)
    _text(fig, W / 2, y - 0.66, "(never used in a past general conference)", 9, on(T["band"]), weight="normal", font=F)
    y -= 1.0
    if unique_words:
        # Oct 2025 look: ~14 words scattered in staggered rows, in blue / near-black / grey (no extra library)
        import random
        rnd = random.Random(7)
        words = unique_words[:14]
        cols = ["#4A7FD8", "#1E1E1E", "#6B6B6B"]
        per_row = 2
        rows_n = math.ceil(len(words) / per_row)
        for k, w in enumerate(words):
            row, colm = divmod(k, per_row)
            x = (1.6 if colm == 0 else 4.6) + (0.55 if row % 2 else -0.15) + rnd.uniform(-0.35, 0.35)
            yy = y - 0.3 - (row + 0.5) * (2.4 / max(rows_n, 1))
            _text(fig, x, yy, w, rnd.choice([12, 13, 14]), cols[k % 3], weight="normal", font=F)
    y -= 2.8
    # 7 speaker cards
    for j, (phrase, top) in enumerate(speaker_cards[:2]):
        c = T["card1"] if j == 0 else T["card2"]
        _rect(fig, 0, y - 1.35, W, 1.35, c)
        _text(fig, W / 2, y - 0.3, f"Top 3 speakers using “{phrase}” (since 1971):", 12, ink(T, c), font=F)
        lines = "\n".join(f"#{k + 1}  {n}  ({v} mentions)" for k, (n, v) in enumerate(top))
        _text(fig, W / 2, y - 0.85, lines, 11, ink(T, c), weight="normal", font=F, linespacing=1.3)
        y -= 1.35
    _text(fig, W - 0.15, 0.2, f"Source: Author · data {status}", 6.5, "#777777", weight="normal", ha="right", font=F)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out.with_suffix(".png"), dpi=200, facecolor=T["page"])
    fig.savefig(out.with_suffix(".svg"), facecolor=T["page"])
    plt.close(fig)
    return out.with_suffix(".png")


def rising_words(d: Data, emph, theme: str, out: Path, status: str, n: int = 15) -> Path:
    """New idea A: ranked lollipop of % increase with a 50-year sparkline per word."""
    T = THEMES[theme]
    F = _font()
    rows = sorted(emph, key=lambda r: -(r.ratio or 0))[:n]
    H = 1.6 + 0.42 * len(rows)
    fig = plt.figure(figsize=(7, H), dpi=200, facecolor=T["page"])
    _text(fig, 0.35, H - 0.45, f"Rising words · {conf_label(d.conf)}", 17, T["ink"], ha="left", font=F)
    _text(fig, 0.35, H - 0.8, "How much more each word was used than in the average past conference, "
          "and its history since 1971", 8.5, "#555555", weight="normal", ha="left", font=F)
    top = H - 1.15
    ax = fig.add_axes([1.55 / 7, 0.45 / H, 3.0 / 7, (top - 0.45) / H])
    yy = list(range(len(rows)))[::-1]
    vals = [r.ratio - 1 for r in rows]
    ax.hlines(yy, 0.9, vals, color=T["band"], lw=2.2, zorder=1)
    ax.scatter(vals, yy, s=70, color=T["banner"], zorder=3, edgecolor="white", linewidth=1.5)
    ax.set_xscale("log", base=2)
    ax.xaxis.set_major_locator(FixedLocator([1, 2, 4, 8, 16, 32]))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"+{v * 100:.0f}%"))
    ax.xaxis.set_minor_locator(NullLocator())
    ax.set_xlim(0.9, max(vals) * 1.6)
    ax.set_yticks(yy)
    ax.set_yticklabels([f"{r.word}  ({r.count})" for r in rows], fontsize=9, fontfamily=F)
    ax.tick_params(axis="x", labelsize=7, colors="#666666")
    ax.tick_params(axis="y", length=0)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color("#BBBBBB")
    ax.grid(axis="x", color="#EEEEEE", lw=0.8, zorder=0)
    ax.set_ylim(-0.7, len(rows) - 0.3)
    # sparklines
    span = top - 0.45
    rowh = span / len(rows)
    for i, r in enumerate(rows):
        series = d.word_series(r.word)
        rates = [n_ / w * 10000 if w else 0 for _, n_, w in series]
        yc = 0.45 + (len(rows) - 1 - i + 0.5) * rowh
        a = fig.add_axes([4.85 / 7, (yc - rowh * 0.38) / H, 1.85 / 7, rowh * 0.76 / H])
        a.fill_between(range(len(rates)), rates, color=T["band"], alpha=0.5, lw=0)
        a.plot(range(len(rates)), rates, color=T["band"], lw=0.8)
        a.scatter([len(rates) - 1], [rates[-1]], s=12, color=T["banner"], zorder=3)
        a.set_ylim(0, max(rates) * 1.15 or 1)
        a.axis("off")
    _text(fig, 5.77, top + 0.12, "1971 → today (uses per 10k words)", 7, "#666666", weight="normal", font=F)
    _text(fig, 6.85, 0.15, f"Source: Author · data {status}", 6, "#888888", weight="normal", ha="right", font=F)
    fig.savefig(out.with_suffix(".png"), dpi=200, facecolor=T["page"])
    fig.savefig(out.with_suffix(".svg"), facecolor=T["page"])
    plt.close(fig)
    return out.with_suffix(".png")


def fingerprint(d: Data, emph, theme: str, out: Path, status: str, n: int = 14) -> Path:
    """New idea B: each emphasized word's rate in every conference since 1971 (row-normalized heat strip)."""
    T = THEMES[theme]
    F = _font()
    rows = sorted(emph, key=lambda r: -(r.ratio or 0))[:n]
    confs = [ck for ck in d.confs() if ck <= d.conf]
    mat = []
    for r in rows:
        s = d.word_series(r.word)
        rates = [n_ / w * 10000 if w else 0 for _, n_, w in s]
        mx = max(rates) or 1
        mat.append([v / mx for v in rates])
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list("seq", ["#F6F6F4", T["banner"]])   # one hue, light -> dark
    H = 1.7 + 0.32 * len(rows)
    fig = plt.figure(figsize=(7, H), dpi=200, facecolor=T["page"])
    _text(fig, 0.35, H - 0.42, f"Conference fingerprint · {conf_label(d.conf)}", 17, T["ink"], ha="left", font=F)
    _text(fig, 0.35, H - 0.8, "Each row: how often the word was used at every general conference since 1971\n"
          "(darkest = that word's peak). Outlined column = this conference.", 8, "#555555", weight="normal",
          ha="left", va="center", font=F, linespacing=1.3)
    ax = fig.add_axes([1.45 / 7, 0.55 / H, 5.3 / 7, (H - 1.65) / H])
    ax.imshow(mat, aspect="auto", cmap=cmap, interpolation="nearest", vmin=0, vmax=1)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r.word for r in rows], fontsize=8.5, fontfamily=F)
    ticks = [i for i, ck in enumerate(confs) if ck.endswith("-04") and int(ck[:4]) % 10 == 0]
    ax.set_xticks(ticks)
    ax.set_xticklabels([confs[i][:4] for i in ticks], fontsize=7)
    ax.add_patch(Rectangle((len(confs) - 1.5, -0.5), 1, len(rows), fill=False, edgecolor=T["ink"], lw=1.6,
                           clip_on=False))
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    _text(fig, 6.85, 0.15, f"Source: Author · data {status}", 6, "#888888", weight="normal", ha="right", font=F)
    fig.savefig(out.with_suffix(".png"), dpi=200, facecolor=T["page"])
    fig.savefig(out.with_suffix(".svg"), facecolor=T["page"])
    plt.close(fig)
    return out.with_suffix(".png")


def phrase_spotlight(d: Data, prow: list[dict], theme: str, out: Path, status: str, n: int = 12,
                     min_standalone: int = 5, include_people: bool = False) -> Path:
    """New idea C: top phrases by % vs past (standalone), with nested uses shown, plus top speakers."""
    T = THEMES[theme]
    F = _font()
    cand = [p for p in prow if p["ratio"] and p["standalone"] >= min_standalone
            and (include_people or not p["category"].startswith("People"))]
    rows = sorted(cand, key=lambda p: -p["ratio"])[:n]
    H = 2.9 + 0.38 * len(rows)
    fig = plt.figure(figsize=(7, H), dpi=200, facecolor=T["page"])
    _text(fig, 0.35, H - 0.42, f"Phrase spotlight · {conf_label(d.conf)}", 17, T["ink"], ha="left", font=F)
    _text(fig, 0.35, H - 0.76, "Phrases used most above their past average (standalone uses); lighter bar = "
          "uses inside a longer phrase", 8, "#555555", weight="normal", ha="left", font=F)
    ax = fig.add_axes([2.6 / 7, 1.85 / H, 3.0 / 7, (H - 2.75) / H])
    yy = list(range(len(rows)))[::-1]
    ax.barh(yy, [p["standalone"] for p in rows], color=T["banner"], height=0.62, zorder=2)
    ax.barh(yy, [p["nested"] for p in rows], left=[p["standalone"] for p in rows], color=T["banner"], alpha=0.35, height=0.62,
            zorder=2)
    ax.set_yticks(yy)
    ax.set_yticklabels([p["phrase"] for p in rows], fontsize=8.5, fontfamily=F)
    for y_, p in zip(yy, rows):
        ax.text(p["total"] * 1.02 + 0.5, y_, f"+{(p['ratio'] - 1) * 100:.0f}%", va="center", fontsize=7.5,
                color=T["ink"], fontfamily=F)
    ax.set_xlim(0, max(p["total"] for p in rows) * 1.3)
    ax.tick_params(axis="y", length=0)
    ax.tick_params(axis="x", labelsize=7, colors="#666666")
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.set_xlabel("uses this conference", fontsize=8, color="#555555")
    if rows:
        top = d.top_speakers_phrase(rows[0]["phrase_id"])
        _rect(fig, 0.35, 0.3, 6.3, 1.15, T["card1"])
        _text(fig, 3.5, 1.12, f"Most uses of “{rows[0]['phrase']}” since 1971", 10.5, ink(T, T["card1"]), font=F)
        _text(fig, 3.5, 0.65, "   ·   ".join(f"{k + 1}. {nm} ({v})" for k, (nm, v) in enumerate(top)), 8.5,
              ink(T, T["card1"]), weight="normal", font=F)
    _text(fig, 6.85, 0.12, f"Source: Author · data {status}", 6, "#888888", weight="normal", ha="right", font=F)
    fig.savefig(out.with_suffix(".png"), dpi=200, facecolor=T["page"])
    fig.savefig(out.with_suffix(".svg"), facecolor=T["page"])
    plt.close(fig)
    return out.with_suffix(".png")


def write_data(emph, path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["word", "mentions", "ratio_vs_past", "percent_increase", "talks_using"])
        for r in emph:
            w.writerow([r.word, r.count, r.ratio, round((r.ratio - 1) * 100, 1), r.talks_using])


def build_all(db_path: str | Path, conf: str, out_dir: str | Path, *, theme: str = "thought_provoking",
              archive_root: str | Path | None = None,
              curation_csv: Path | None = None, settings: dict | None = None, exclude: set | None = None,
              titles_csv: Path | None = None, trend_terms: list[str] | None = None,
              speaker_phrases: list[str] | None = None, min_count: int = 20) -> dict:
    con = sqlite3.connect(str(db_path))
    d = Data(con, conf)
    rows = d.comparison(settings=settings, exclude=exclude, titles_csv=titles_csv)
    emph, status = pick_emphasized(rows, curation_csv, min_count)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    write_data(emph, out / "emphasized_words_plotted.csv")
    prow = d.phrase_rows()
    pid_by_name = {name.lower(): pid for pid, name in con.execute("SELECT phrase_id, canonical FROM phrases")}
    # trends: given terms, else top phrase + top 3 words
    trends = []
    for term in (trend_terms or []):
        if term.lower() in pid_by_name:
            trends.append((term, "phrase", d.phrase_series(pid_by_name[term.lower()])))
        else:
            trends.append((term, "word", d.word_series(term.lower())))
    if not trends:
        best = sorted([p for p in prow if p["ratio"] and p["standalone"] >= 5], key=lambda p: -p["ratio"])[:2]
        trends = [(p["phrase"], "phrase", d.phrase_series(p["phrase_id"])) for p in best]
        trends += [(r.word, "word", d.word_series(r.word)) for r in emph[: 4 - len(trends)]]
    # unique words: never used before; skip names (mostly capitalized in this conference) and leader names
    caps = set()
    hist = Path(archive_root) / "conferences" / conf / "histogram_words.csv" if archive_root else None
    if hist and hist.exists():
        with open(hist, newline="", encoding="utf-8-sig") as f:
            caps = {r["word"] for r in csv.DictReader(f) if r["display"][:1].isupper()}
    unique = [r.word for r in rows if r.baseline_count == 0 and r.word.isalpha() and len(r.word) >= 4
              and not r.name_flag and r.word not in caps]
    cards = []
    for ph in (speaker_phrases or ["Jesus Christ", "Book of Mormon"]):
        if ph.lower() in pid_by_name:
            cards.append((ph, d.top_speakers_phrase(pid_by_name[ph.lower()])))
    files = {
        "classic": classic_poster(d, emph, trends, unique, cards, theme, out / f"classic_{conf}_{theme}", status),
        "rising_words": rising_words(d, emph, theme, out / f"new_A_rising_words_{conf}_{theme}", status),
        "fingerprint": fingerprint(d, emph, theme, out / f"new_B_fingerprint_{conf}_{theme}", status),
        "phrase_spotlight": phrase_spotlight(d, prow, theme, out / f"new_C_phrase_spotlight_{conf}_{theme}", status),
    }
    return {"status": status, "emphasized": len(emph), "unique_words": len(unique), "files": files}

"""Convert Adam's legacy workbooks into PROVISIONAL archive records (data/legacy_archive/).

Purpose: exercise the whole pipeline (histograms, phrases, DB, analysis) on 1971-2026 text
before the fresh import exists, and give the new import something to diff against.
This is NOT the source of truth; it is never written into archive/.

Legacy clean-up applied (every change logged in qa_flags):
  * paragraphs from a cell that is exactly 'Notes' onward are dropped (old MakeNotesRed logic)
  * short byline-like lines at the top (e.g. 'Acting President of the Council of the Twelve')
    are tagged non_spoken
  * footnote numbers glued to words ('heart5', 'end.5') are removed with a heuristic
  * parentheticals are flagged; high-confidence citations leave spoken_text
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from .archive import Paragraph, Speaker, Talk, write_conference_manifest, write_talk
from .citations import strip_citations
from .leaders import slug
from .legacy import read_capture

GLUED = re.compile(r"(?<=[A-Za-z’'.,;:!?”\)])(\d{1,3})(?=[\s“”\"'’,.;:!?)]|$)")
BYLINE_HINT = re.compile(r"^(of the|acting president|president of|first counselor|second counselor|"
                         r"assistant to|member of|presiding bishop|general president|relief society|"
                         r"young women|primary|sunday school|young men|emeritus|recently released)", re.I)


def clean_paragraphs(paras: list[str]) -> tuple[list[Paragraph], list[str]]:
    flags: list[str] = []
    out: list[Paragraph] = []
    glued = 0
    for i, raw in enumerate(paras):
        txt = " ".join(str(raw).replace("_x000D_", " ").split())
        if txt.strip().lower() in {"notes", "notes:"}:
            flags.append(f"legacy_notes_section_dropped_from_par_{i + 1}")
            break
        kind = "body"
        if re.search(r"Intellectual Reserve|All Rights Reserved|Official Web ?site of The Church", txt, re.I):
            flags.append(f"legacy_site_footer_par_{i + 1}")
            kind = "non_spoken"
        elif i < 2 and len(txt.split()) <= 12 and not txt.endswith((".", "!", "?", ":", "”")) \
                and BYLINE_HINT.search(txt):
            kind = "non_spoken"
            flags.append(f"legacy_byline_par_{i + 1}")
        fixed, n = GLUED.subn("", txt)
        glued += n
        spoken, found = strip_citations(fixed) if kind == "body" else (fixed, [])
        out.append(Paragraph(index=len(out) + 1, raw_text=txt, spoken_text=spoken, kind=kind,
                             parentheticals=[{"text": f.text, "char_offset": f.char_offset, "class": f.cls,
                                              "score": f.score, "rule": f.rule} for f in found]))
    if glued:
        flags.append(f"legacy_glued_numbers_removed:{glued}")
    return out, flags


def import_workbook(path: str | Path, out_root: str | Path, *, sheet: str | None, first_body_row: int,
                    summary_row: int | None, source_label: str) -> Counter:
    talks = read_capture(path, sheet=sheet, first_body_row=first_body_row, summary_row=summary_row)
    stats = Counter()
    order: Counter = Counter()
    by_conf: dict[str, list[str]] = {}
    for lt in talks:
        ck = f"{lt.year:04d}-{lt.month:02d}"
        order[ck] += 1
        paras, flags = clean_paragraphs(lt.paragraphs)
        name = lt.speaker
        t = Talk(
            talk_id=f"{ck}-legacy-{order[ck]:03d}-{slug(name)[:30]}", conference={"year": lt.year, "month": lt.month},
            session="", order_in_session=0, order_in_conference=order[ck], url="", title="",
            speaker=Speaker(name_display=name, name=name, speaker_id=slug(name)),
            summary=lt.summary, paragraphs=paras,
            source={"parser_version": "legacy-import", "workbook": Path(path).name, "column": lt.column,
                    "label": source_label},
            qa_flags=["legacy_source", *flags])
        write_talk(out_root, t)
        by_conf.setdefault(ck, []).append(t.talk_id)
        stats["talks"] += 1
        stats["glued_fixed"] += sum(int(f.split(":")[1]) for f in flags if f.startswith("legacy_glued"))
        stats["citations_removed"] += sum(1 for p in paras for x in p.parentheticals if x["class"] == "citation")
    for ck, ids in by_conf.items():
        write_conference_manifest(out_root, ck, {"conference": ck, "source": source_label, "provisional": True,
                                                 "talk_ids": ids, "counts": {"talks": len(ids)}})
    stats["conferences"] = len(by_conf)
    return stats

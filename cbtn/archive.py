"""Archive (master storage) read/write — PLAN.md §3.1 and §5.2.

archive/conferences/YYYY-MM/
    conference.json
    talks/<SS-OO>_<surname>_<slug>.json   canonical record
    talks/<SS-OO>_<surname>_<slug>.md     human-readable (generated from JSON)
    histogram_words.csv, histogram_phrases.csv, keywords.csv, qa_report.md, analysis/
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterator

SPOKEN_KINDS = {"body", "blockquote", "list_item"}
PARSER_VERSION = "0.1.0"


@dataclass
class Paragraph:
    index: int
    raw_text: str
    spoken_text: str
    kind: str = "body"                      # body | blockquote | list_item | heading | caption | non_spoken
    footnote_refs: list[dict] = field(default_factory=list)      # {"marker": "1", "char_offset": 143}
    parentheticals: list[dict] = field(default_factory=list)     # {"text","char_offset","class","score","rule"}

    @property
    def is_spoken(self) -> bool:
        return self.kind in SPOKEN_KINDS


@dataclass
class Speaker:
    name_display: str
    name: str
    speaker_id: str
    title: str = ""            # Elder / President / Sister / Bishop / Brother as printed for this talk
    calling: str | None = None


@dataclass
class Talk:
    talk_id: str
    conference: dict                     # {"year": 2026, "month": 4}
    session: str
    order_in_session: int
    order_in_conference: int
    url: str
    title: str
    speaker: Speaker
    item_type: str = "talk"              # talk | sustaining | report | video | other
    summary: str = ""
    site_topics: list[str] = field(default_factory=list)
    paragraphs: list[Paragraph] = field(default_factory=list)
    notes: list[dict] = field(default_factory=list)      # {"marker","text","links":[...]}
    source: dict = field(default_factory=dict)
    qa_flags: list[str] = field(default_factory=list)

    @property
    def conf_key(self) -> str:
        return f"{self.conference['year']:04d}-{self.conference['month']:02d}"

    @property
    def counts_toward_histograms(self) -> bool:
        return self.item_type == "talk"

    def spoken_paragraphs(self) -> Iterator[Paragraph]:
        return (p for p in self.paragraphs if p.is_spoken)

    def markers_for(self, p: Paragraph) -> set[str]:
        return {r["marker"] for r in p.footnote_refs}

    def notes_for(self, p: Paragraph) -> list[str]:
        marks = self.markers_for(p)
        return [n["text"] for n in self.notes if str(n.get("marker")) in marks]

    # ---- serialization -------------------------------------------------------------------
    def to_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, d: dict) -> "Talk":
        d = dict(d)
        d["speaker"] = Speaker(**d["speaker"])
        d["paragraphs"] = [Paragraph(**p) for p in d.get("paragraphs", [])]
        return cls(**d)

    def file_stem(self) -> str:
        sur = re.sub(r"[^a-z0-9]+", "", self.speaker.name.split()[-1].lower()) if self.speaker.name else "unknown"
        slug = re.sub(r"[^a-z0-9]+", "-", self.talk_id.split("/")[-1].lower()).strip("-")[:60]
        return f"{self.order_in_conference:03d}_{sur}_{slug}"

    def to_markdown(self) -> str:
        sp = self.speaker
        lines = [
            "---",
            f"talk_id: {self.talk_id}",
            f"conference: {self.conf_key}",
            f"session: {self.session}",
            f"order: {self.order_in_conference}",
            f"title: {json.dumps(self.title, ensure_ascii=False)}",
            f"speaker: {json.dumps(sp.name_display, ensure_ascii=False)}",
            f"speaker_id: {sp.speaker_id}",
            f"calling: {json.dumps(sp.calling, ensure_ascii=False)}",
            f"item_type: {self.item_type}",
            f"url: {self.url}",
            "---",
            "",
            f"# {self.title}",
            f"*{sp.name_display}{' — ' + sp.calling if sp.calling else ''}*",
            "",
        ]
        if self.summary:
            lines += [f"> {self.summary}", "", "*(Summary above is not spoken and is not counted.)*", ""]
        for p in self.paragraphs:
            if not p.is_spoken:
                lines.append(f"<!-- {p.kind}: not counted --> *{p.spoken_text or p.raw_text}*")
            elif p.kind == "blockquote":
                lines.append("> " + p.spoken_text)
            else:
                lines.append(p.spoken_text)
            lines.append("")
        if self.notes:
            lines += ["---", "## Notes (not spoken, not counted)", ""]
            lines += [f"{n['marker']}. {n['text']}" for n in self.notes]
            lines.append("")
        removed = [(p.index, x) for p in self.paragraphs for x in p.parentheticals if x["class"] == "citation"]
        if removed:
            lines += ["## Inline citations removed from counting", ""]
            lines += [f"- ¶{i}: {x['text']}  ({x['rule']})" for i, x in removed]
            lines.append("")
        if self.qa_flags:
            lines += ["## QA flags", ""] + [f"- {q}" for q in self.qa_flags] + [""]
        return "\n".join(lines)


def conference_dir(root: str | Path, conf_key: str) -> Path:
    return Path(root) / "conferences" / conf_key


def write_talk(root: str | Path, talk: Talk) -> Path:
    d = conference_dir(root, talk.conf_key) / "talks"
    d.mkdir(parents=True, exist_ok=True)
    stem = talk.file_stem()
    (d / f"{stem}.json").write_text(json.dumps(talk.to_json(), ensure_ascii=False, indent=1), encoding="utf-8")
    (d / f"{stem}.md").write_text(talk.to_markdown(), encoding="utf-8")
    return d / f"{stem}.json"


def iter_talks(root: str | Path, conf_key: str | None = None) -> Iterator[Talk]:
    base = Path(root) / "conferences"
    dirs = [base / conf_key] if conf_key else sorted(p for p in base.glob("*") if p.is_dir())
    for cd in dirs:
        for f in sorted((cd / "talks").glob("*.json")):
            yield Talk.from_json(json.loads(f.read_text(encoding="utf-8")))


def list_conferences(root: str | Path) -> list[str]:
    base = Path(root) / "conferences"
    return sorted(p.name for p in base.glob("*") if p.is_dir() and re.fullmatch(r"\d{4}-\d{2}", p.name))


def write_conference_manifest(root: str | Path, conf_key: str, manifest: dict) -> Path:
    d = conference_dir(root, conf_key)
    d.mkdir(parents=True, exist_ok=True)
    p = d / "conference.json"
    p.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return p

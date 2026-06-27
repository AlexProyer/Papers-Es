"""
Parser del Markdown filtrado del Proyecto 1 -> lista de PaperObject (dicts).

El formato de cada bloque es 100% regular (ver docs/DATA_CONTRACT.md).
"""
from __future__ import annotations

import hashlib
import re

# Cabecera: **Papers evaluados:** 178 · **Seleccionados:** 18
_EVALUATED = re.compile(r"\*\*Papers evaluados:\*\*\s*(\d+)")
_SELECTED = re.compile(r"\*\*Seleccionados:\*\*\s*(\d+)")

# Encabezado de sección por fuente: "## 🎯 arXiv"
_SECTION = re.compile(r"^##\s+\S+\s+(.+?)\s*$")
# Inicio de paper: "### 1. Título"
_PAPER = re.compile(r"^###\s+(\d+)\.\s+(.+?)\s*$")

_SCORE = re.compile(r"\*\*Score:\*\*\s*`(\d+)/100`")
_REASONS = re.compile(r"\*\*Por qué es relevante:\*\*\s*(.+?)\s*$")
_TOPICS = re.compile(r"🎯\s*temas:\s*(.+?)\s*$")
_AUTHORS = re.compile(r"\*\*Autores:\*\*\s*(.+?)\s*$")
_SOURCE_LINE = re.compile(r"\*\*Fuente:\*\*\s*(.+?)\s*·\s*\*\*Fecha:\*\*\s*(\S+)")
_CATEGORY = re.compile(r"\[([a-zA-Z]+\.[a-zA-Z]+)\]")
_LINK = re.compile(r"\[([^\]]*)\]\((https?://[^)]+)\)")

_AUTHORS_NONE = "Autores no disponibles"


def _make_id(url: str, title: str) -> str:
    m = re.search(r"arxiv\.org/(?:abs|pdf)/([^\s)?#]+)", url or "")
    if m:
        return f"arxiv:{m.group(1)}"
    basis = (url or title or "").strip()
    return "sha1:" + hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


def _split_reasons(raw: str) -> list[str]:
    return [r.strip() for r in raw.split("·") if r.strip()]


def _split_topics(raw: str) -> list[str]:
    return [t.strip() for t in raw.split(",") if t.strip()]


def _parse_block(source: str, rank: int, title: str, lines: list[str]) -> dict:
    paper: dict = {
        "id": "", "rank": rank, "title": title, "authors": [],
        "source": source, "venue": None, "category": None, "date": None,
        "url": "", "pdf_url": None, "score": 0, "topics": [], "reasons": [],
        "abstract_en": "", "abstract_full": False, "summary_es": None,
    }

    abstract_lines: list[str] = []
    in_abstract = False

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("**Resumen:**"):
            in_abstract = True
            continue
        if in_abstract:
            if stripped == "---":
                in_abstract = False
                continue
            abstract_lines.append(stripped)
            continue

        if m := _SCORE.search(stripped):
            paper["score"] = int(m.group(1))
        if m := _REASONS.search(stripped):
            paper["reasons"] = _split_reasons(m.group(1))
            if t := _TOPICS.search(m.group(1)):
                paper["topics"] = _split_topics(t.group(1))
        if m := _AUTHORS.search(stripped):
            authors = m.group(1)
            paper["authors"] = [] if _AUTHORS_NONE in authors else \
                [a.strip() for a in authors.split(",") if a.strip()]
        if m := _SOURCE_LINE.search(stripped):
            venue = m.group(1).strip()
            paper["venue"] = venue
            paper["date"] = m.group(2)
            if c := _CATEGORY.search(venue):
                paper["category"] = c.group(1)
        for label, url in _LINK.findall(stripped):
            if "PDF" in label:
                paper["pdf_url"] = url
            elif "Ver paper" in label or not paper["url"]:
                paper["url"] = url

    abstract = " ".join(l for l in abstract_lines if l).strip()
    paper["abstract_en"] = abstract
    paper["id"] = _make_id(paper["url"], title)
    return paper


def parse_report(md: str, date: str) -> dict:
    """Convierte el Markdown filtrado en el dict del día (sin summary_es aún)."""
    evaluated = int(m.group(1)) if (m := _EVALUATED.search(md)) else None
    selected = int(m.group(1)) if (m := _SELECTED.search(md)) else None

    lines = md.splitlines()
    papers: list[dict] = []
    current_source = "desconocida"

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]

        if m := _SECTION.match(line):
            current_source = m.group(1).strip()
            i += 1
            continue

        if m := _PAPER.match(line):
            rank = int(m.group(1))
            title = m.group(2).strip()
            block: list[str] = []
            i += 1
            while i < n and not _PAPER.match(lines[i]) and not _SECTION.match(lines[i]):
                block.append(lines[i])
                i += 1
            papers.append(_parse_block(current_source, rank, title, block))
            continue

        i += 1

    return {
        "date": date,
        "report_type": "filtrado",
        "evaluated": evaluated,
        "selected": selected,
        "papers": papers,
    }


if __name__ == "__main__":  # smoke test manual
    import json
    import sys
    from sources import fetch_index, resolve_latest_with_report

    found = resolve_latest_with_report(fetch_index())
    if not found:
        print("No hay reportes disponibles", file=sys.stderr)
        sys.exit(1)
    date, md = found
    day = parse_report(md, date)
    print(f"{date}: {len(day['papers'])} papers (evaluados={day['evaluated']})")
    print(json.dumps(day["papers"][0], ensure_ascii=False, indent=2))

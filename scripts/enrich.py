"""
Recupera el abstract COMPLETO desde la API de arXiv (el .md lo trae truncado).

Solo aplica a papers de arXiv. Para otras fuentes se conserva el truncado.
"""
from __future__ import annotations

import re
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET

_ARXIV_API = "https://export.arxiv.org/api/query?id_list={ids}&max_results={n}"
_NS = {"atom": "http://www.w3.org/2005/Atom"}
_USER_AGENT = "papers-es-builder/1.0"


def _bare_arxiv_id(paper_id: str) -> str | None:
    """arxiv:2606.26936v1 -> 2606.26936v1 ; None si no es de arXiv."""
    if not paper_id.startswith("arxiv:"):
        return None
    return paper_id.split(":", 1)[1]


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def fetch_full_abstracts(papers: list[dict], batch: int = 25) -> None:
    """
    Muta in-place: rellena abstract_en con la versión completa y marca
    abstract_full=True para los papers de arXiv que se resuelvan.
    """
    by_id = {}
    for p in papers:
        bare = _bare_arxiv_id(p["id"])
        if bare:
            by_id[bare] = p

    ids = list(by_id.keys())
    for start in range(0, len(ids), batch):
        chunk = ids[start:start + batch]
        url = _ARXIV_API.format(ids=",".join(chunk), n=len(chunk))
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                xml = resp.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError):
            continue

        try:
            root = ET.fromstring(xml)
        except ET.ParseError:
            continue

        for entry in root.findall("atom:entry", _NS):
            raw_id = entry.findtext("atom:id", "", _NS)  # http://arxiv.org/abs/<id>
            m = re.search(r"abs/([^\s/]+)$", raw_id)
            if not m:
                continue
            returned_id = m.group(1)
            summary = _clean(entry.findtext("atom:summary", "", _NS))
            if not summary:
                continue
            # arXiv puede devolver el id con/ sin versión; emparejamos por prefijo.
            target = by_id.get(returned_id)
            if target is None:
                base = returned_id.split("v")[0]
                for cid, p in by_id.items():
                    if cid.split("v")[0] == base:
                        target = p
                        break
            if target is not None:
                target["abstract_en"] = summary
                target["abstract_full"] = True

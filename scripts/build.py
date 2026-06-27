"""
Orquestador del build de papers-es.

Flujo:
  1. Lee el índice del Proyecto 1 y resuelve el reporte filtrado más reciente.
  2. Parsea el Markdown -> papers estructurados.
  3. Recupera abstracts completos de arXiv.
  4. Genera resúmenes en español con Gemini (con caché por id).
  5. Escribe site/data/<fecha>.json y actualiza site/data/index.json.

Uso:
  GEMINI_API_KEY=... py scripts/build.py
  py scripts/build.py --no-gemini      # solo parseo/datos, sin resúmenes
  py scripts/build.py --date 2026-06-26
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import sources
import parse as parser
import enrich
import summarize

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "site", "data")
CACHE_PATH = os.path.join(ROOT, "cache", "summaries.json")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _load_json(path: str, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def _write_json(path: str, obj) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def rebuild_index() -> None:
    """Reconstruye index.json escaneando los archivos de día en site/data/."""
    days = []
    for name in os.listdir(DATA_DIR):
        if name == "index.json" or not name.endswith(".json"):
            continue
        day = _load_json(os.path.join(DATA_DIR, name), None)
        if not day:
            continue
        sources_list = sorted({p.get("source", "?") for p in day.get("papers", [])})
        days.append({
            "date": day["date"],
            "paper_count": len(day.get("papers", [])),
            "sources": sources_list,
            "file": name,
        })
    days.sort(key=lambda d: d["date"], reverse=True)
    _write_json(os.path.join(DATA_DIR, "index.json"), {
        "generated_at": _now(),
        "latest": days[0]["date"] if days else None,
        "days": days,
    })


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="Forzar una fecha YYYY-MM-DD")
    ap.add_argument("--no-gemini", action="store_true",
                    help="No generar resúmenes (solo parseo)")
    ap.add_argument("--no-enrich", action="store_true",
                    help="No recuperar abstracts completos de arXiv")
    args = ap.parse_args()

    # 1. Resolver reporte ---------------------------------------------------
    if args.date:
        md = sources.fetch_filtered_report(args.date)
        if not md:
            print(f"No existe reporte filtrado para {args.date}", file=sys.stderr)
            return 1
        date = args.date
    else:
        dates = sources.fetch_index()
        if not dates:
            print("No se pudo leer el índice del Proyecto 1", file=sys.stderr)
            return 1
        found = sources.resolve_latest_with_report(dates)
        if not found:
            print("No hay ningún reporte filtrado disponible", file=sys.stderr)
            return 1
        date, md = found

    print(f"Reporte resuelto: {date}")

    # 2. Parseo -------------------------------------------------------------
    day = parser.parse_report(md, date)
    papers = day["papers"]
    print(f"  papers parseados: {len(papers)}")

    # 3. Abstracts completos ------------------------------------------------
    if not args.no_enrich:
        enrich.fetch_full_abstracts(papers)
        full = sum(1 for p in papers if p.get("abstract_full"))
        print(f"  abstracts completos de arXiv: {full}/{len(papers)}")

    # 4. Resúmenes en español ----------------------------------------------
    cache = _load_json(CACHE_PATH, {})
    if args.no_gemini or not os.environ.get("GEMINI_API_KEY"):
        if not args.no_gemini:
            print("  GEMINI_API_KEY no definida -> se omiten los resúmenes")
        # Reusar caché si existe, aunque no llamemos a la API.
        for p in papers:
            p["summary_es"] = cache.get(p["id"])
    else:
        cache = summarize.summarize_all(papers, cache)
        _write_json(CACHE_PATH, cache)
        done = sum(1 for p in papers if p.get("summary_es"))
        print(f"  resúmenes generados/reusados: {done}/{len(papers)}")

    # 5. Escribir salida ----------------------------------------------------
    day["generated_at"] = _now()
    _write_json(os.path.join(DATA_DIR, f"{date}.json"), day)
    rebuild_index()
    print(f"OK -> site/data/{date}.json + index.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

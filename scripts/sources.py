"""
Descarga datos del Proyecto 1 (Daily-Papers) vía raw.githubusercontent.com.

Independiente del Proyecto 1: solo consume sus .md publicados por HTTP.
"""
from __future__ import annotations

import re
import urllib.request
import urllib.error

# Repositorio productor (Proyecto 1). Configurable por si cambia el owner/repo.
REPO = "AlexProyer/Daily-Papers"
BRANCH = "main"
RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}"

USER_AGENT = "papers-es-builder/1.0 (+https://github.com)"

# Fila de la tabla del índice: | 2026-06-26 | [..](..) | [..](..) |
_INDEX_ROW = re.compile(r"^\|\s*(\d{4}-\d{2}-\d{2})\s*\|")


def _get(url: str, timeout: int = 30) -> str | None:
    """GET de texto. Devuelve None ante 404 u otros errores recuperables."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    except (urllib.error.URLError, TimeoutError):
        return None


def fetch_index() -> list[str]:
    """Lee reports/README.md y devuelve las fechas disponibles (desc)."""
    text = _get(f"{RAW_BASE}/reports/README.md")
    if not text:
        return []
    dates = []
    for line in text.splitlines():
        m = _INDEX_ROW.match(line.strip())
        if m:
            dates.append(m.group(1))
    # El índice puede no estar ordenado; garantizamos desc por fecha.
    return sorted(set(dates), reverse=True)


def fetch_filtered_report(date: str) -> str | None:
    """Descarga reports/YYYY-MM-DD_filtrado.md. None si no existe."""
    return _get(f"{RAW_BASE}/reports/{date}_filtrado.md")


def resolve_latest_with_report(dates: list[str]) -> tuple[str, str] | None:
    """
    Recorre las fechas (desc) y devuelve (date, markdown) del primer reporte
    filtrado que exista realmente. Resuelve "si no hay datos de hoy, usar el
    más reciente".
    """
    for date in dates:
        md = fetch_filtered_report(date)
        if md:
            return date, md
    return None

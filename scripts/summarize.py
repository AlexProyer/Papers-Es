"""
Genera el resumen en español (summary_es) con la API gratuita de Gemini.

- REST puro (sin SDK), API key en la variable de entorno GEMINI_API_KEY.
- Salida JSON estructurada (responseMimeType + responseSchema).
- Respeta un rate limit suave para la cuota gratuita.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
import urllib.error

MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:generateContent"
)
# Pausa entre llamadas para no exceder la cuota gratuita (req/min).
_SLEEP_SECONDS = float(os.environ.get("GEMINI_SLEEP", "4"))

_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "tldr": {"type": "string"},
        "problema": {"type": "string"},
        "propuesta": {"type": "string"},
        "resultados": {"type": "string"},
        "por_que_importa": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "tldr", "problema", "propuesta", "resultados", "por_que_importa", "tags",
    ],
}

_PROMPT = """Eres un divulgador técnico. Resume en ESPAÑOL claro y conciso el \
siguiente paper académico de IA/ciberseguridad/tecnología para un público \
profesional pero no necesariamente experto en el subtema.

Devuelve un JSON con:
- tldr: una sola frase gancho (máx ~25 palabras).
- problema: qué problema resuelve.
- propuesta: qué propone o cómo lo aborda.
- resultados: resultados clave (incluye números si aparecen).
- por_que_importa: por qué importa para la práctica.
- tags: 3 a 6 etiquetas cortas en español.

No inventes resultados que no estén en el texto. Si algo no aparece, dilo \
brevemente ("el resumen no lo especifica").

TÍTULO: {title}
FUENTE: {venue}
ABSTRACT:
{abstract}
"""


class GeminiError(RuntimeError):
    pass


def _api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise GeminiError("Falta GEMINI_API_KEY en el entorno")
    return key


def _call(prompt: str, key: str, retries: int = 3) -> dict:
    url = _ENDPOINT.format(model=MODEL) + f"?key={key}"
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.4,
            "responseMimeType": "application/json",
            "responseSchema": _RESPONSE_SCHEMA,
        },
    }).encode("utf-8")

    last_err = None
    for attempt in range(retries):
        req = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text)
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in (429, 500, 503):  # rate limit / transitorio
                time.sleep(_SLEEP_SECONDS * (attempt + 2))
                continue
            raise GeminiError(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')}")
        except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as e:
            last_err = e
            time.sleep(_SLEEP_SECONDS * (attempt + 1))
    raise GeminiError(f"Gemini falló tras {retries} intentos: {last_err}")


def summarize(paper: dict, key: str) -> dict:
    """Devuelve un objeto summary_es para el paper dado."""
    prompt = _PROMPT.format(
        title=paper.get("title", ""),
        venue=paper.get("venue") or paper.get("source", ""),
        abstract=paper.get("abstract_en", ""),
    )
    result = _call(prompt, key)
    result["model"] = MODEL
    result["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return result


def summarize_all(papers: list[dict], cache: dict, throttle: bool = True) -> dict:
    """
    Rellena summary_es en cada paper, reutilizando la caché por id.
    Devuelve la caché actualizada. Errores por paper -> summary_es=None.
    """
    key = _api_key()
    for i, p in enumerate(papers):
        pid = p["id"]
        if pid in cache and cache[pid]:
            p["summary_es"] = cache[pid]
            continue
        if not p.get("abstract_en"):
            p["summary_es"] = None
            continue
        try:
            summary = summarize(p, key)
            p["summary_es"] = summary
            cache[pid] = summary
        except GeminiError as e:
            print(f"  ! resumen falló para {pid}: {e}")
            p["summary_es"] = None
        if throttle and i < len(papers) - 1:
            time.sleep(_SLEEP_SECONDS)
    return cache

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

# Cadena de modelos: la cuota diaria gratis es PerModel, así que cuando uno
# se agota (429 PerDay) rotamos al siguiente y sumamos su cupo gratis.
# Configurable con GEMINI_MODELS (lista separada por comas) o GEMINI_MODEL.
_DEFAULT_MODELS = "gemini-2.5-flash-lite,gemini-2.0-flash-lite,gemini-2.0-flash,gemini-2.5-flash"
MODELS = [
    m.strip() for m in
    os.environ.get("GEMINI_MODELS", os.environ.get("GEMINI_MODEL", _DEFAULT_MODELS)).split(",")
    if m.strip()
]
_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:generateContent"
)
# Pausa entre llamadas para no exceder la cuota gratuita.
# El free tier limita por minuto (RPM) y por día (RPD, por modelo).
# 8s => ~7,5 req/min. Además respetamos el retryDelay que envía Google en
# cada 429 por-minuto, así que el ritmo se auto-ajusta si aún es alto.
_SLEEP_SECONDS = float(os.environ.get("GEMINI_SLEEP", "8"))

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


class QuotaExhaustedError(GeminiError):
    """429 por cuota DIARIA (RPD): reintentar hoy es inútil -> abortar."""


def _parse_429(body: str) -> tuple[bool, float | None, str]:
    """
    Devuelve (es_diaria, retry_seconds, detalle) a partir del cuerpo del 429.
    El error de Gemini trae quotaId y un RetryInfo.retryDelay tipo "38s".
    """
    is_daily = False
    retry_seconds = None
    detail = body[:300]
    try:
        err = json.loads(body).get("error", {})
        detail = err.get("message", detail)
        for d in err.get("details", []):
            for v in d.get("violations", []):
                qid = v.get("quotaId", "")
                if "PerDay" in qid:
                    is_daily = True
                detail = qid or detail
            delay = d.get("retryDelay", "")  # p.ej. "38s"
            if delay.endswith("s"):
                try:
                    retry_seconds = float(delay[:-1])
                except ValueError:
                    pass
    except (json.JSONDecodeError, AttributeError):
        pass
    return is_daily, retry_seconds, detail


def _api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise GeminiError("Falta GEMINI_API_KEY en el entorno")
    return key


def _call(prompt: str, key: str, model: str, retries: int = 3) -> dict:
    url = _ENDPOINT.format(model=model) + f"?key={key}"
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
            body = e.read().decode("utf-8", "replace")
            last_err = f"HTTP {e.code}: {body[:300]}"
            if e.code == 429:
                is_daily, retry_s, detail = _parse_429(body)
                if is_daily:
                    # Cuota diaria agotada: no tiene sentido reintentar hoy.
                    raise QuotaExhaustedError(f"cuota diaria agotada ({detail})")
                # Por-minuto: esperar lo que pide Google (con tope) y reintentar.
                wait = retry_s if retry_s else _SLEEP_SECONDS * (attempt + 2)
                time.sleep(min(wait, 90))
                continue
            if e.code in (500, 503):  # transitorio
                time.sleep(_SLEEP_SECONDS * (attempt + 2))
                continue
            raise GeminiError(f"HTTP {e.code}: {body[:300]}")
        except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as e:
            last_err = e
            time.sleep(_SLEEP_SECONDS * (attempt + 1))
    raise GeminiError(f"Gemini falló tras {retries} intentos: {last_err}")


def summarize(paper: dict, key: str, model: str) -> dict:
    """Devuelve un objeto summary_es para el paper dado, con el modelo dado."""
    prompt = _PROMPT.format(
        title=paper.get("title", ""),
        venue=paper.get("venue") or paper.get("source", ""),
        abstract=paper.get("abstract_en", ""),
    )
    result = _call(prompt, key, model)
    result["model"] = model
    result["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return result


def summarize_all(papers: list[dict], cache: dict, throttle: bool = True) -> dict:
    """
    Rellena summary_es en cada paper, reutilizando la caché por id.
    Devuelve la caché actualizada. Errores por paper -> summary_es=None.
    """
    key = _api_key()
    models = list(MODELS) or [_DEFAULT_MODELS.split(",")[0]]
    mi = 0  # índice del modelo activo en la cadena
    print(f"  cadena de modelos: {', '.join(models)}")

    for i, p in enumerate(papers):
        pid = p["id"]
        if pid in cache and cache[pid]:
            p["summary_es"] = cache[pid]
            continue
        if not p.get("abstract_en"):
            p["summary_es"] = None
            continue

        # Intentar con el modelo activo; si su cuota diaria está agotada,
        # rotar al siguiente de la cadena y reintentar el mismo paper.
        while mi < len(models):
            try:
                summary = summarize(p, key, models[mi])
                p["summary_es"] = summary
                cache[pid] = summary
                break
            except QuotaExhaustedError as e:
                print(f"  ~ '{models[mi]}': {e}")
                mi += 1
                if mi < len(models):
                    print(f"  ~ rotando a '{models[mi]}'")
            except GeminiError as e:
                print(f"  ! resumen falló para {pid}: {e}")
                p["summary_es"] = None
                break

        if mi >= len(models):
            # Toda la cadena sin cuota diaria: cortar y conservar la caché.
            print("  ! todos los modelos con cuota diaria agotada -> se detiene "
                  "(los pendientes quedan para el próximo run; caché conservada)")
            p["summary_es"] = None
            break

        if throttle and i < len(papers) - 1:
            time.sleep(_SLEEP_SECONDS)
    return cache

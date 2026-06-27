# 📡 papers-es

Plataforma web pública que publica a diario **resúmenes en español** de los papers
más relevantes de **IA, ciberseguridad y tecnología**.

Es la **cara pública** del ecosistema: consume los datos del proyecto
[Daily-Papers](https://github.com/AlexProyer/Daily-Papers) (el *Paper Radar* que
monitorea arXiv, Semantic Scholar, Papers With Code y HuggingFace), genera
resúmenes en español con Gemini y los publica como sitio estático en GitHub Pages.

```
Daily-Papers (Proyecto 1)          papers-es (Proyecto 2)
  publica reports/*.md   ──HTTP──▶   parse → arXiv → Gemini → JSON → GitHub Pages
```

Los dos repos son **independientes**: papers-es solo *consume* los `.md` publicados
vía `raw.githubusercontent.com` y nunca modifica el Proyecto 1.

## Arquitectura

| Etapa | Archivo | Qué hace |
|-------|---------|----------|
| Fuente | [`scripts/sources.py`](scripts/sources.py) | Descarga el índice y el reporte filtrado del Proyecto 1 |
| Parseo | [`scripts/parse.py`](scripts/parse.py) | Convierte el Markdown en objetos `PaperObject` |
| Enriquecimiento | [`scripts/enrich.py`](scripts/enrich.py) | Recupera el abstract completo desde la API de arXiv |
| Resumen | [`scripts/summarize.py`](scripts/summarize.py) | Genera `summary_es` con Gemini (con caché) |
| Orquestación | [`scripts/build.py`](scripts/build.py) | Une todo y escribe los JSON en `site/data/` |
| Sitio | [`site/`](site/) | HTML/CSS/JS puro: buscador + filtros por tema/fuente/fecha |

El **contrato de datos** completo (formato Markdown de entrada y JSON de salida)
está en [`docs/DATA_CONTRACT.md`](docs/DATA_CONTRACT.md).

## Decisiones de diseño

- **Solo el reporte filtrado** (`*_filtrado.md`, score ≥ 45): más enfocado y menos
  consumo de Gemini.
- **Acceso vía `raw.githubusercontent.com`**: independencia total entre repos.
- **Abstract completo de arXiv**: el `.md` trae el abstract truncado a ~80 palabras;
  se recupera el completo para mejores resúmenes.
- **Caché por `id`** (`cache/summaries.json`): nunca se re-resume un paper ya hecho.
- **Tolerante a fallos**: si no hay reporte de hoy se usa el más reciente; si falla
  un resumen, la tarjeta muestra el abstract en inglés + el link.

## Uso local

Requiere solo **Python 3.10+** (sin dependencias externas).

```bash
# Build sin resúmenes (rápido: parseo + arXiv + JSON)
python scripts/build.py --no-gemini

# Build completo (necesita la API key gratuita de aistudio.google.com)
export GEMINI_API_KEY="tu-clave"
python scripts/build.py

# Forzar una fecha concreta
python scripts/build.py --date 2026-06-26

# Previsualizar el sitio
python -m http.server 8000 --directory site
# -> http://localhost:8000
```

## Configuración en GitHub

1. **Secret**: `Settings → Secrets and variables → Actions → New secret`
   - `GEMINI_API_KEY` = tu clave de [aistudio.google.com](https://aistudio.google.com)
2. **Pages**: `Settings → Pages → Source: GitHub Actions`
3. El workflow [`build.yml`](.github/workflows/build.yml) corre a diario (12:30 UTC,
   tras el Proyecto 1), commitea los datos y despliega a Pages.

### (Opcional) Disparo en tiempo real desde el Proyecto 1

Para reconstruir en cuanto el Proyecto 1 publique (en vez de esperar al cron),
añade en el workflow del Proyecto 1 un step que dispare `repository_dispatch`:

```yaml
- name: Notificar a papers-es
  run: |
    curl -X POST \
      -H "Authorization: Bearer ${{ secrets.PAPERS_ES_PAT }}" \
      -H "Accept: application/vnd.github+json" \
      https://api.github.com/repos/<owner>/papers-es/dispatches \
      -d '{"event_type":"daily-papers-updated"}'
```

(Requiere un PAT con permiso sobre este repo. Es opcional; el cron diario funciona
sin tocar el Proyecto 1.)

## Aviso

Los resúmenes en español son generados por IA y pueden contener errores.
Consulta siempre el paper original enlazado en cada tarjeta.

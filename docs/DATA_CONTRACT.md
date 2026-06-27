# Contrato de datos — papers-es

Este documento define el **formato de intercambio** entre el Proyecto 1
(`Daily-Papers`, productor de datos) y el Proyecto 2 (`papers-es`, sitio público).

Los dos repos son **independientes**. El Proyecto 1 publica únicamente Markdown.
El Proyecto 2 **parsea** ese Markdown y produce los JSON descritos aquí, que son
los únicos artefactos que consume el sitio estático.

```
Daily-Papers  ──(reports/*.md vía raw.githubusercontent.com)──▶  papers-es
   (productor)                                                     (parser → Gemini → JSON → Pages)
```

---

## 1. Origen: formato Markdown del Proyecto 1

### 1.1 Índice — `reports/README.md`

Tabla con una fila por fecha. Se usa para descubrir qué días existen y cuál es el
más reciente (criterio "si no hay datos de hoy, mostrar el más reciente").

```
| Fecha      | Reporte General           | Reporte Filtrado            |
|------------|---------------------------|-----------------------------|
| 2026-06-26 | [...](2026-06-26_general.md) | [...](2026-06-26_filtrado.md) |
```

### 1.2 Reporte consumido — `reports/YYYY-MM-DD_filtrado.md`

> **Decisión:** consumimos **solo el reporte filtrado** (papers curados por temas,
> score ≥ 45). Más enfocado y menos consumo de Gemini.

Cabecera:

```
# 🎯 Paper Radar — Reporte Filtrado (Mis Temas)
**Fecha:** 2026-06-26 · **Papers evaluados:** 178 · **Seleccionados:** 18
```

Secciones por fuente: `## 🎯 arXiv`, `## 🎯 Semantic Scholar`, etc.

Bloque por paper (100 % regular):

```
### 1. <título>
> **Score:** `60/100` `██████░░░░`
> **Por qué es relevante:** 📅 paper reciente (24-48h) · 🎯 temas: vuln & threats, LLM
**Autores:** A, B, C, D
**Fuente:** arXiv [cs.CR] · **Fecha:** 2026-06-25
[🔗 Ver paper](https://arxiv.org/abs/2606.26936v1) · [📄 PDF](https://arxiv.org/pdf/2606.26936v1)
**Resumen:**
<abstract en inglés, TRUNCADO a ~80 palabras, termina en "...">
---
```

**Limitación conocida:** el abstract del `.md` está truncado. El Proyecto 2
recupera el abstract completo desde la API de arXiv antes de resumir.

---

## 2. Salida: JSON de intercambio (lo que consume el sitio)

Todos los archivos viven en `site/data/`. Codificación UTF-8.

### 2.1 `site/data/index.json`

```jsonc
{
  "generated_at": "2026-06-26T12:00:00Z",  // ISO-8601 UTC
  "latest": "2026-06-26",                   // día más reciente con datos
  "days": [                                 // orden descendente por fecha
    {
      "date": "2026-06-26",
      "paper_count": 18,
      "sources": ["arXiv", "HuggingFace"],
      "file": "2026-06-26.json"
    }
  ]
}
```

### 2.2 `site/data/YYYY-MM-DD.json`

```jsonc
{
  "date": "2026-06-26",
  "report_type": "filtrado",
  "evaluated": 178,        // del header del .md (null si no se pudo leer)
  "selected": 18,
  "generated_at": "2026-06-26T12:00:00Z",
  "papers": [ /* PaperObject[] */ ]
}
```

### 2.3 `PaperObject`

| Campo            | Tipo        | Origen                                   | Notas |
|------------------|-------------|------------------------------------------|-------|
| `id`             | string      | derivado                                 | Clave **estable** para caché. `arxiv:<id>` o `sha1:<hash(url\|title)>` |
| `rank`           | number      | `### N.`                                 | Posición en el reporte |
| `title`          | string      | `### N. <título>`                        | |
| `authors`        | string[]    | `**Autores:**`                           | `[]` si "_Autores no disponibles_" |
| `source`         | string      | `**Fuente:**` (primera palabra/marca)    | arXiv, Semantic Scholar, Papers With Code, HuggingFace |
| `venue`          | string      | `**Fuente:**` completo                   | p.ej. `arXiv [cs.CR]` |
| `category`       | string\|null| extraído de `venue`                      | p.ej. `cs.CR` |
| `date`           | string      | `**Fecha:**`                             | `YYYY-MM-DD` |
| `url`            | string      | `[🔗 Ver paper](...)`                     | |
| `pdf_url`        | string\|null| `[📄 PDF](...)`                          | |
| `score`          | number      | `**Score:** \`N/100\``                   | 0–100 |
| `topics`         | string[]    | `🎯 temas: a, b, c`                       | `[]` si no hay |
| `reasons`        | string[]    | `**Por qué es relevante:**` (split ` · `)| Razones del scoring heurístico |
| `abstract_en`    | string      | `**Resumen:**` o API arXiv               | Inglés. Completo si `abstract_full` |
| `abstract_full`  | boolean     | derivado                                 | `true` si se recuperó completo de arXiv |
| `summary_es`     | object\|null| Gemini                                   | Ver 2.4. `null` si falló la generación |

### 2.4 `summary_es` (generado por Gemini)

Cubre los 5 elementos requeridos por el diseño + metadatos.

```jsonc
{
  "tldr": "Una frase gancho que resume el paper.",
  "problema": "Qué problema resuelve.",
  "propuesta": "Qué propone / cómo lo aborda.",
  "resultados": "Resultados clave (números si los hay).",
  "por_que_importa": "Por qué importa para IA / ciberseguridad / tecnología.",
  "tags": ["jailbreak", "LLM", "seguridad"],   // 3–6 etiquetas en español
  "model": "gemini-2.0-flash",
  "generated_at": "2026-06-26T12:01:00Z"
}
```

> El link al paper original **no** se duplica dentro de `summary_es`: ya está en
> `url` / `pdf_url` del `PaperObject`. La UI lo muestra junto al resumen.

---

## 3. Caché — `cache/summaries.json`

Mapa `id → summary_es` commiteado en el repo. Antes de llamar a Gemini, el build
reutiliza el resumen existente por `id`. Esto evita regenerar (y pagar/consumir
cuota) resúmenes ya hechos cuando un mismo paper reaparece o se reconstruye un día.

```jsonc
{
  "arxiv:2606.26936v1": { /* summary_es */ },
  "sha1:9f86d081...":    { /* summary_es */ }
}
```

---

## 4. Garantías de robustez

- Si **no hay** `YYYY-MM-DD_filtrado.md` para hoy → se usa la fecha más reciente
  del índice. El sitio nunca queda vacío.
- Si **falla la generación** de un resumen → `summary_es: null`; la tarjeta del
  paper sigue mostrándose con su abstract en inglés y el link.
- Si **falla la recuperación** del abstract completo → se usa el truncado del `.md`
  (`abstract_full: false`).
- Versionado del contrato: `report_type` y la presencia de `index.json` permiten
  evolucionar el formato sin romper el sitio.

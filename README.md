# Review Analysis

Pipeline para extraer reseñas de apps en Google Play y App Store, analizarlas (sentimiento + tópicos) y obtener hallazgos accionables sobre qué se queja o valora la gente. Ver [PLAN.md](PLAN.md) para la hoja de ruta hacia un entregable compartible (web con el análisis de una empresa).

## Qué hace

1. **Recolección** (`scripts/collect_data.py`): descarga reseñas de App Store (vía RSS feed de iTunes) y Google Play (vía `google-play-scraper`) para una app dada, las deduplica contra lo ya guardado y las acumula en `data/<empresa>/reviews.parquet`.
2. **Análisis** (`scripts/model.py`):
   - Clasifica el sentimiento de cada reseña (positivo/negativo/neutro) con `pysentimiento` (modelo en español).
   - Agrupa las reseñas en tópicos con `BERTopic` + embeddings multilingües (`sentence-transformers`).
   - Genera un resumen por tópico (cantidad de reseñas, rating promedio, % de negativas) ordenado por los tópicos más problemáticos primero. El tópico `-1` (outliers de BERTopic, sin patrón claro) queda marcado con `is_outlier=True` en vez de mezclarse con tópicos reales.

Cada empresa/app analizada vive en su propia carpeta (`data/<empresa>/`), identificada por el `--name` que le pases a los scripts.

## Estructura

```
scripts/
  config.py          # paths por empresa (data/<empresa>/...)
  collect_data.py    # scraping de App Store + Google Play
  model.py           # sentimiento + topic modeling + resumen
data/
  <empresa>/
    reviews.parquet           # reseñas crudas acumuladas (no versionado)
    output/
      reviews_enriched.parquet  # reseñas + sentimiento + tópico
      reviews_enriched.csv      # idem, para abrir en Excel
      topics_summary.csv        # resumen por tópico, ordenado por % negativas
```

`data/` y `.env` están en `.gitignore`: los datos y credenciales no se versionan.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # y completar HF_TOKEN
```

`HF_TOKEN` (Hugging Face) es necesario para descargar los modelos de `pysentimiento`/`sentence-transformers`.

## Uso

1. Correr la recolección, indicando el id de App Store y el package de Google Play de la app:

   ```bash
   python scripts/collect_data.py --name spotify --app-ios 324684580 --pkg com.spotify.music
   ```

2. Correr el análisis (mismo `--name`):

   ```bash
   python scripts/model.py --name spotify
   ```

3. Revisar `data/spotify/output/topics_summary.csv` para ver los tópicos más negativos (mayor `pct_neg`) y priorizar qué atacar primero. `Name` trae las keywords de cada tópico para poder nombrarlo; las filas con `is_outlier=True` son reseñas sin patrón claro, no un tema real.

## Pendientes conocidos

Ver [PLAN.md](PLAN.md) para el detalle completo. Resumen de lo que falta para el entregable compartible:

- Nombrar los tópicos y generar recomendaciones con un LLM (hoy `Name` son keywords crudas de BERTopic, ilegibles para alguien no técnico).
- Serie temporal de sentimiento por versión/mes.
- `dashboard.py` que genere un HTML autocontenido para compartir (hoy el output son CSVs).

# Review Analysis

Pipeline para extraer reseñas de apps en Google Play y App Store, analizarlas (sentimiento + tópicos) y obtener hallazgos accionables sobre qué se queja o valora la gente. Ver [PLAN.md](PLAN.md) para la hoja de ruta hacia un entregable compartible (web con el análisis de una empresa).

## Qué hace

1. **Recolección** (`scripts/collect_data.py`): descarga reseñas de App Store (vía RSS feed de iTunes) y Google Play (vía `google-play-scraper`) para una app dada, las deduplica contra lo ya guardado y las acumula en `data/<empresa>/reviews.parquet`.
2. **Análisis** (`scripts/model.py`):
   - Clasifica el sentimiento de cada reseña (positivo/negativo/neutro) con `pysentimiento` (modelo en español).
   - Agrupa las reseñas en tópicos con `BERTopic` + embeddings multilingües (`sentence-transformers`).
   - Genera un resumen por tópico (cantidad de reseñas, rating promedio, % de negativas) ordenado por los tópicos más problemáticos primero. El tópico `-1` (outliers de BERTopic, sin patrón claro) queda marcado con `is_outlier=True` en vez de mezclarse con tópicos reales.
3. **Nombrado de tópicos** (`scripts/topics_enrich.py`): como no hay API key de Anthropic disponible, el nombrado no es 100% automático — el script exporta keywords + reseñas de muestra por tópico (`export`), un LLM (hoy, Claude en una sesión de Claude Code) escribe nombre/resumen/severidad/recomendación por tópico, y el script vuelca eso a `topics_summary.csv` (`merge`).
4. **Tendencias** (`scripts/trends.py`): sentimiento por mes y comparación entre App Store y Google Play, para detectar si algo empeoró con una versión o si una plataforma tiene peor experiencia que la otra.

Cada empresa/app analizada vive en su propia carpeta (`data/<empresa>/`), identificada por el `--name` que le pases a los scripts.

## Estructura

```
scripts/
  config.py          # paths por empresa (data/<empresa>/...)
  collect_data.py    # scraping de App Store + Google Play
  model.py           # sentimiento + topic modeling + resumen
  topics_enrich.py   # export de muestras por tópico + merge de nombres/recomendaciones
  trends.py          # tendencia mensual + comparación de stores
data/
  <empresa>/
    reviews.parquet           # reseñas crudas acumuladas (no versionado)
    output/
      reviews_enriched.parquet  # reseñas + sentimiento + tópico
      reviews_enriched.csv      # idem, para abrir en Excel
      topics_summary.csv        # resumen por tópico, con name/summary/severity/recommendation
      topic_samples.json        # keywords + muestras por tópico, insumo para el nombrado
      topics_named.json         # nombre/resumen/severidad/recomendación por tópico (lo escribe el LLM)
      sentiment_by_month.csv    # tendencia mensual de sentimiento por store
      store_comparison.csv      # comparación agregada iOS vs Android
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

3. Exportar las muestras para nombrar los tópicos:

   ```bash
   python scripts/topics_enrich.py export --name spotify
   ```

   Esto genera `data/spotify/output/topic_samples.json`. Pedirle a Claude (en una sesión de Claude Code, con este repo abierto) que lo lea y escriba `data/spotify/output/topics_named.json` con `name`/`summary`/`severity`/`recommendation` por cada tópico no outlier.

4. Mergear esos nombres al resumen:

   ```bash
   python scripts/topics_enrich.py merge --name spotify
   ```

5. (Opcional) Tendencias temporales y comparación de stores:

   ```bash
   python scripts/trends.py --name spotify
   ```

6. Revisar `data/spotify/output/topics_summary.csv`: ya viene ordenado por severidad (volumen × % negativas) con nombre y recomendación legibles. Las filas con `is_outlier=True` son reseñas sin patrón claro, no un tema real.

## Pendientes conocidos

Ver [PLAN.md](PLAN.md) para el detalle completo. Resumen de lo que falta para el entregable compartible:

- Automatizar el nombrado de tópicos con la API de Anthropic cuando haya una API key disponible (hoy es un paso manual vía Claude Code).
- `dashboard.py` que genere un HTML autocontenido para compartir (hoy el output son CSVs/JSON).

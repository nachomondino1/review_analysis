# Review Analysis

Pipeline para extraer reseñas de apps en Google Play y App Store, analizarlas (sentimiento + tópicos) y obtener hallazgos accionables sobre qué se queja o valora la gente.

## Qué hace

1. **Recolección** (`scripts/collect_data.py`): descarga reseñas de App Store (vía RSS feed de iTunes) y Google Play (vía `google-play-scraper`) para una app dada, las deduplica contra lo ya guardado y las acumula en `data/reviews.parquet`.
2. **Análisis** (`scripts/model.py`):
   - Clasifica el sentimiento de cada reseña (positivo/negativo/neutro) con `pysentimiento` (modelo en español).
   - Agrupa las reseñas en tópicos con `BERTopic` + embeddings multilingües (`sentence-transformers`).
   - Genera un resumen por tópico (cantidad de reseñas, rating promedio, % de negativas) ordenado por los tópicos más problemáticos primero.

## Estructura

```
scripts/
  collect_data.py   # scraping de App Store + Google Play
  model.py           # sentimiento + topic modeling + resumen
data/
  reviews.parquet           # reseñas crudas acumuladas (no versionado)
  output/
    reviews_enriched.parquet  # reseñas + sentimiento + tópico
    reviews_enriched.csv      # idem, para abrir en Excel
    topics_summary.csv        # resumen por tópico, ordenado por % negativas
```

`data/` y `.env` están en `.gitignore`: los datos y credenciales no se versionan.

## Setup

Requiere un `.env` con:

```
HF_TOKEN=<tu token de Hugging Face>
```

(necesario para descargar los modelos de `pysentimiento`/`sentence-transformers`).

Instalar dependencias (no hay `requirements.txt` todavía — ver sección de pendientes):

```bash
pip install pandas requests google-play-scraper python-dotenv pysentimiento bertopic sentence-transformers
```

## Uso

1. Editar en `scripts/collect_data.py` el `app_ios` (id numérico de App Store) y `pkg` (package name de Google Play) de la app que se quiere analizar.
2. Correr la recolección:

   ```bash
   python scripts/collect_data.py
   ```

3. Correr el análisis:

   ```bash
   python scripts/model.py
   ```

4. Revisar `data/output/topics_summary.csv` para ver los tópicos más negativos (mayor `pct_neg`) y priorizar qué atacar primero. `Name` trae las keywords de cada tópico para poder nombrarlo.

## Pendientes conocidos

- Los parámetros de la app (`app_ios`, `pkg`, país, idioma) están hardcodeados en el script en vez de venir por CLI/config.
- No hay `requirements.txt`/`pyproject.toml` fijando versiones.
- `topic_model.get_topic_info()` no filtra el tópico `-1` (outliers de BERTopic), que puede aparecer en el resumen.

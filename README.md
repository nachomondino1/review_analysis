# Review Analysis

Pipeline para extraer reseñas de apps en Google Play y App Store, analizarlas (sentimiento + tópicos) y obtener hallazgos accionables sobre qué se queja o valora la gente. Ver [PLAN.md](PLAN.md) para la hoja de ruta hacia un entregable compartible (web con el análisis de una empresa) y [APRENDIZAJES.md](APRENDIZAJES.md) para bugs/sesgos no obvios que ya encontramos y por qué.

Organizado en fases al estilo **CRISP-DM**: cada carpeta numerada es una fase, con sus propios scripts.

## Qué hace

1. **Recolección** (`01_data_understanding/collect_data.py`): descarga reseñas de App Store (vía RSS feed de iTunes) y Google Play (vía `google-play-scraper`) para una app dada, las deduplica contra lo ya guardado y las acumula en `data/<empresa>/01_data_understanding/reviews.parquet`. También guarda el **rating oficial agregado** de cada tienda (`store_ratings.json`) — ver nota de metodología más abajo, es importante. Los ids de App Store/Google Play se guardan en `common/companies.csv`: una empresa que ya se corrió antes no necesita pasarlos de nuevo, y una empresa sin presencia en una de las dos tiendas (ej. solo Android) funciona sin problema con el `--app-ios` o `--pkg` que falte.
2. **Limpieza** (`02_data_preparation/clean_reviews.py`): filtra reseñas sin señal real (muy cortas, tipo "buena app") antes de modelar.
3. **Análisis** (`03_modeling/model.py`):
   - Clasifica el sentimiento de cada reseña (positivo/negativo/neutro) con `pysentimiento` (modelo en español).
   - Agrupa las reseñas en tópicos con `BERTopic` + embeddings multilingües (`sentence-transformers`).
   - Genera un resumen por tópico (cantidad de reseñas, rating promedio, % de negativas) ordenado por los tópicos más problemáticos primero. El tópico `-1` (outliers de BERTopic, sin patrón claro) queda marcado con `is_outlier=True` en vez de mezclarse con tópicos reales.
4. **Evaluación / hallazgos** (`04_evaluation/`):
   - `topics_enrich.py`: como no hay API key de Anthropic disponible, el nombrado de tópicos no es 100% automático — el script exporta keywords + reseñas de muestra por tópico (`export`), un LLM (hoy, Claude en una sesión de Claude Code) escribe nombre/resumen/severidad/recomendación por tópico, y el script vuelca eso a `topics_summary.csv` (`merge`).
   - `trends.py`: sentimiento por mes y comparación entre App Store y Google Play, para detectar si algo empeoró con una versión o si una plataforma tiene peor experiencia que la otra.
5. **Deployment** (`05_deployment/dashboard.py`): genera un único HTML autocontenido (`05_deployment/site/<empresa>/index.html`) con resumen ejecutivo, los hallazgos principales (con recomendación y reseñas de ejemplo), un gráfico de tendencia mensual y el detalle completo en una tabla colapsable — listo para compartir por link o archivo adjunto, sin backend ni build step.

Cada empresa/app analizada vive en su propia carpeta (`data/<empresa>/`), identificada por el `--name` que le pases a los scripts. Dentro, los archivos están organizados por fase (mismo esquema CRISP-DM que el resto del repo), no todos sueltos en una sola carpeta `output/`: así agregar una empresa nueva, o una fase nueva en el futuro, no satura una carpeta compartida.

## Estructura

```
common/
  config.py          # paths por empresa (data/<empresa>/<fase>/...), importado por todas las fases
  companies.py        # registro de empresas ya analizadas (lookup/upsert de companies.csv)
  companies.csv        # nombre, app_ios, pkg por empresa — versionado, se edita solo o vía collect_data.py
  check_env.py        # sanity check de que HF_TOKEN está cargado
01_data_understanding/
  collect_data.py     # scraping de App Store + Google Play
02_data_preparation/
  clean_reviews.py    # filtra reseñas sin señal real
03_modeling/
  model.py             # sentimiento + topic modeling + resumen
04_evaluation/
  topics_enrich.py    # export de muestras por tópico + merge de nombres/recomendaciones
  trends.py            # tendencia mensual + comparación de stores
05_deployment/
  dashboard.py        # genera 05_deployment/site/<empresa>/index.html
  site/
    <empresa>/
      index.html       # web autocontenida para compartir (SÍ versionada — ver "Publicar")
data/
  <empresa>/
    01_data_understanding/
      reviews.parquet           # reseñas crudas acumuladas
      store_ratings.json        # rating oficial agregado por tienda (score + cantidad de calificaciones)
    02_data_preparation/
      reviews_clean.parquet     # reseñas filtradas, insumo del modelado
    03_modeling/
      reviews_enriched.parquet  # reseñas + sentimiento + tópico
      reviews_enriched.csv      # idem, para abrir en Excel
      topics_summary.csv        # resumen por tópico; 04_evaluation le agrega name/summary/severity/recommendation
    04_evaluation/
      topic_samples.json        # keywords + muestras por tópico, insumo para el nombrado
      topics_named.json         # nombre/resumen/severidad/recomendación por tópico (lo escribe el LLM)
      sentiment_by_month.csv    # tendencia mensual de sentimiento por store
      store_comparison.csv      # comparación agregada iOS vs Android
```

`data/` y `.env` están en `.gitignore`: los datos crudos/procesados y las credenciales no se versionan. `05_deployment/site/` **sí** se versiona (ver "Publicar" más abajo).

## Publicar (GitHub Pages)

El repo es **público** y tiene GitHub Pages activado sirviendo `main` desde la raíz. Al versionar `05_deployment/site/<empresa>/index.html`, cada dashboard queda accesible en:

```
https://nachomondino1.github.io/review_analysis/05_deployment/site/<empresa>/
```

No hay una página índice que liste las empresas analizadas (decisión deliberada), pero al ser un repo público cualquiera puede encontrar los archivos navegando el código — no depende solo de tener el link. Si en algún momento esto deja de ser aceptable para alguna empresa puntual, la alternativa es no commitear ese `index.html` y mandarlo directo como archivo adjunto (ya lo hacíamos así antes de activar Pages).

Para publicar un dashboard nuevo:

```bash
git add 05_deployment/site/<empresa>
git commit -m "Agregar dashboard de <empresa>"
git push
```

GitHub Pages lo sirve automáticamente unos minutos después del push, sin ningún paso de build.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # y completar HF_TOKEN
```

`HF_TOKEN` (Hugging Face) es necesario para descargar los modelos de `pysentimiento`/`sentence-transformers`.

## Uso

1. Correr la recolección, indicando el id de App Store y/o el package de Google Play de la app (alguno de los dos puede faltar si la app no está en esa tienda):

   ```bash
   python 01_data_understanding/collect_data.py --name spotify --app-ios 324684580 --pkg com.spotify.music
   ```

   La primera vez, los ids quedan guardados en `common/companies.csv`; una corrida posterior solo necesita `--name spotify`, sin repetir los ids.

2. Limpiar las reseñas sin señal real:

   ```bash
   python 02_data_preparation/clean_reviews.py --name spotify
   ```

3. Correr el análisis (mismo `--name`):

   ```bash
   python 03_modeling/model.py --name spotify
   ```

4. Exportar las muestras para nombrar los tópicos:

   ```bash
   python 04_evaluation/topics_enrich.py export --name spotify
   ```

   Esto genera `data/spotify/04_evaluation/topic_samples.json`. Pedirle a Claude (en una sesión de Claude Code, con este repo abierto) que lo lea y escriba `data/spotify/04_evaluation/topics_named.json` con `name`/`summary`/`severity`/`recommendation` por cada tópico no outlier.

5. Mergear esos nombres al resumen:

   ```bash
   python 04_evaluation/topics_enrich.py merge --name spotify
   ```

6. (Opcional) Tendencias temporales y comparación de stores:

   ```bash
   python 04_evaluation/trends.py --name spotify
   ```

7. Revisar `data/spotify/03_modeling/topics_summary.csv`: ya viene ordenado por severidad (volumen × % negativas) con nombre y recomendación legibles. Las filas con `is_outlier=True` son reseñas sin patrón claro, no un tema real.

8. Generar la web para compartir:

   ```bash
   python 05_deployment/dashboard.py --name spotify --display-name "Spotify"
   ```

   Esto genera `05_deployment/site/spotify/index.html`: un único archivo autocontenido (sin backend, sin fetch) con resumen ejecutivo, los hallazgos principales con recomendación y reseñas de ejemplo, un gráfico de tendencia mensual y el detalle completo en una tabla colapsable. Se puede abrir directo en el navegador, subir a GitHub Pages, o mandar como adjunto. `--display-name` es opcional (default: el mismo `--name`) para mostrar un nombre más prolijo que el slug interno.

## ⚠️ Metodología: la muestra de reseñas con texto está sesgada hacia quejas

El scraping (`collect_data.py`) solo puede leer reseñas que tienen **texto escrito**, y las trae ordenadas por más recientes. Eso es una muestra sesgada: la inmensa mayoría de la gente que califica una app solo toca estrellas y nunca escribe nada, y quien sí escribe tiende a hacerlo cuando tiene un problema. En la prueba con Ripio, por ejemplo, el rating oficial de Google Play es 4.65★ sobre 54.268 calificaciones, pero la muestra de reseñas con texto (sort "más recientes") dio un 70% de negativas — representan públicos distintos, no el mismo dato con más o menos ruido.

Por eso el dashboard separa explícitamente:
- **Rating oficial**: viene de `store_ratings.json` (API de iTunes + `google-play-scraper.app()`), cubre todas las calificaciones de la tienda. Es el número que hay que mostrarle a un CEO como "satisfacción general".
- **% negativas / tópicos / hallazgos**: vienen de la muestra de reseñas con texto. Son el insumo correcto para entender **qué** se queja la gente y priorizar qué arreglar — pero no se deben presentar como si midieran la satisfacción general, porque sobre-representan el descontento.

Historia completa de cómo se encontró este sesgo en [APRENDIZAJES.md](APRENDIZAJES.md#2026-10-19--las-reseñas-con-texto-son-una-muestra-sesgada-hacia-las-quejas).

## Pendientes conocidos

Ver [PLAN.md](PLAN.md) para el detalle completo. Resumen de lo que falta:

- Automatizar el nombrado de tópicos con la API de Anthropic cuando haya una API key disponible (hoy es un paso manual vía Claude Code).
- Marcar en el gráfico de tendencia si una versión específica coincide con un salto de negatividad (el dato de `version` existe pero no se cruza visualmente todavía).

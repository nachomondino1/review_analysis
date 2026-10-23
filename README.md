# Review Analysis

Pipeline para extraer reseñas de apps en Google Play y App Store, analizarlas (sentimiento + tópicos) y obtener hallazgos accionables sobre qué se queja o valora la gente. Ver [PLAN.md](PLAN.md) para la hoja de ruta hacia un entregable compartible (web con el análisis de una empresa) y [APRENDIZAJES.md](APRENDIZAJES.md) para bugs/sesgos no obvios que ya encontramos y por qué.

Organizado en fases al estilo **CRISP-DM**: cada carpeta numerada es una fase, con sus propios scripts.

## Qué hace

1. **Recolección, una fuente por script** (`01_data_understanding/collect_initial_data/collect_*.py`): cada fuente escribe su propio archivo `<fuente>_<empresa>.<formato>`, nunca pisa el de otra fuente.
   - `collect_ios_reviews.py`: reseñas de App Store (RSS de iTunes) → `ios_<empresa>.parquet`.
   - `collect_android_reviews.py`: reseñas de Google Play (`google-play-scraper`) → `android_<empresa>.parquet`.
   - `collect_store_ratings.py`: **rating oficial agregado** de cada tienda (API de iTunes + ficha de Google Play) → `store_ratings_<empresa>.json` — ver nota de metodología más abajo, es importante.

   Las dos primeras deduplican contra lo ya guardado. Los ids de App Store/Google Play se guardan en `common/companies.csv`: una empresa que ya se corrió antes no necesita pasarlos de nuevo, y una empresa sin presencia en una de las dos tiendas (ej. solo Android) funciona sin problema sin correr el script de la tienda que le falta.
2. **Descripción de datos** (`01_data_understanding/describe_data.py`): documenta formato, tamaño, variables y disponibilidad de cada fuente por separado (una `<fuente>_description.md` por fuente, ya que cada una tiene su propio esquema/grano) — tarea de "Data Description" de CRISP-DM, no transforma nada.
3. **Integración** (`02_data_preparation/integrate_data.py`): junta las fuentes de reseñas con texto (ios_reviews + android_reviews) en un solo dataset por empresa (`integrated_<empresa>.parquet`), con una columna `fuente` que identifica de dónde vino cada fila. `store_ratings` queda afuera a propósito: es una fila por tienda (rating agregado), una unidad de análisis distinta a una fila por reseña — se consume directo desde su propio JSON, sin integrar.
4. **Limpieza** (`02_data_preparation/clean_reviews.py`): sobre el dataset integrado, filtra reseñas sin señal real (muy cortas, tipo "buena app") antes de modelar.
5. **Análisis** (`03_modeling/model.py`):
   - Clasifica el sentimiento de cada reseña (positivo/negativo/neutro) con `pysentimiento` (modelo en español).
   - Agrupa las reseñas en tópicos con `BERTopic` + embeddings multilingües (`sentence-transformers`), con `nr_topics="auto"` para fusionar tópicos casi idénticos (sin esto, Ripio daba 37 tópicos; con esto, 18 — varios eran variantes del mismo elogio genérico o del mismo problema de login).
   - Genera un resumen por tópico (cantidad de reseñas, rating promedio, % de negativas) ordenado por los tópicos más problemáticos primero. El tópico `-1` (outliers de BERTopic, sin patrón claro) queda marcado con `is_outlier=True` en vez de mezclarse con tópicos reales.
6. **Evaluación / hallazgos** (`04_evaluation/`):
   - `topics_enrich.py`: como no hay API key de Anthropic disponible, el nombrado de tópicos no es 100% automático — el script exporta keywords + reseñas de muestra por tópico (`export`), un LLM (hoy, Claude en una sesión de Claude Code) escribe nombre/resumen/severidad/recomendación por tópico, y el script vuelca eso a `topics_summary.csv` (`merge`).
   - `trends.py`: sentimiento por mes y comparación entre App Store y Google Play, para detectar si algo empeoró con una versión o si una plataforma tiene peor experiencia que la otra.
7. **Deployment** (`05_deployment/dashboard.py`): genera un único HTML autocontenido (`site/<empresa>.html`) con resumen ejecutivo, los hallazgos principales (con recomendación y reseñas de ejemplo), una comparación de "últimos 3 meses vs. histórico completo" (con un chip de Mejorando/Empeorando/Estable) y el detalle completo en una tabla colapsable — listo para compartir por link o archivo adjunto, sin backend ni build step. También regenera `index.html` en la raíz del repo (home del dominio de GitHub Pages), con el listado de empresas analizadas.

Cada empresa/app analizada vive en su propia carpeta (`data/<empresa>/`), identificada por el `--name` que le pases a los scripts. Dentro, los archivos están organizados por fase (mismo esquema CRISP-DM que el resto del repo), no todos sueltos en una sola carpeta `output/`: así agregar una empresa nueva, o una fase nueva en el futuro, no satura una carpeta compartida.

## Estructura

```
common/
  config.py          # paths por empresa (data/<empresa>/<fase>/...), importado por todas las fases
  companies.py        # registro de empresas ya analizadas (lookup/upsert de companies.csv)
  companies.csv        # nombre, app_ios, pkg por empresa — versionado, se edita solo o vía collect_*.py
  check_env.py        # sanity check de que HF_TOKEN está cargado
01_data_understanding/
  collect_initial_data/
    collect_ios_reviews.py      # fuente 1: scraping de App Store
    collect_android_reviews.py  # fuente 2: scraping de Google Play
    collect_store_ratings.py    # fuente 3: rating oficial agregado por tienda
  describe_data.py            # describe cada fuente por separado, en un .md unificado
02_data_preparation/
  integrate_data.py   # integra ios_reviews + android_reviews (NO store_ratings) en un dataset, con columna "fuente"
  clean_reviews.py    # filtra reseñas sin señal real, sobre el dataset integrado
03_modeling/
  model.py             # sentimiento + topic modeling + resumen
04_evaluation/
  topics_enrich.py    # export de muestras por tópico + merge de nombres/recomendaciones
  trends.py            # tendencia mensual + comparación de stores
  version_breakout.py  # quiebre de % negativas atado a una versión específica
05_deployment/
  dashboard.py        # genera site/<empresa>.html y regenera index.html (ambos en la raíz, no acá)
index.html            # listado de empresas analizadas — home del dominio de GitHub Pages (se regenera solo)
site/
  <empresa>.html       # web autocontenida de esa empresa para compartir (SÍ versionado — ver "Publicar")
data/
  <empresa>/
    01_data_understanding/
      ios_<empresa>.parquet              # fuente 1: reseñas crudas de App Store
      android_<empresa>.parquet          # fuente 2: reseñas crudas de Google Play
      store_ratings_<empresa>.json       # fuente 3: rating oficial agregado por tienda (score + cantidad de calificaciones)
      <fuente>_description.{md,json}     # describe_data.py, una por fuente
    02_data_preparation/
      integrated_<empresa>.parquet  # ios_reviews + android_reviews integradas, con columna "fuente" (store_ratings no entra)
      reviews_clean.parquet         # reseñas filtradas, insumo del modelado
    03_modeling/
      reviews_enriched.parquet  # reseñas + sentimiento + tópico
      reviews_enriched.csv      # idem, para abrir en Excel
      topics_summary.csv        # resumen por tópico; 04_evaluation le agrega name/summary/severity/recommendation
    04_evaluation/
      topic_samples.json        # keywords + muestras por tópico, insumo para el nombrado
      topics_named.json         # nombre/resumen/severidad/recomendación por tópico (lo escribe el LLM)
      sentiment_by_month.csv    # tendencia mensual de sentimiento por store
      store_comparison.csv      # comparación agregada iOS vs Android
      version_breakout.json     # quiebre de % negativas por versión, si hay uno real (null si no)
```

`data/` y `.env` están en `.gitignore`: los datos crudos/procesados y las credenciales no se versionan. `site/` **sí** se versiona (ver "Publicar" más abajo).

## Publicar (GitHub Pages)

El repo es **público** y tiene GitHub Pages activado sirviendo `main` desde la raíz. Al versionar `site/<empresa>.html`, cada dashboard queda accesible en:

```
https://nachomondino1.github.io/review_analysis/<empresa>.html
```

`index.html` (en la raíz) lista todas las empresas analizadas y es lo que se ve en `https://nachomondino1.github.io/review_analysis/` — se regenera automáticamente cada vez que corre `dashboard.py`, escaneando los `.html` existentes en `site/`. Al ser un repo público, de todas formas cualquiera puede encontrar los archivos navegando el código, liste o no el índice. Si en algún momento esto deja de ser aceptable para alguna empresa puntual, la alternativa es no commitear ese `.html` y mandarlo directo como archivo adjunto (ya lo hacíamos así antes de activar Pages).

Para publicar un dashboard nuevo:

```bash
git add site/
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

1. Correr la recolección de cada fuente, indicando el id de App Store y/o el package de Google Play de la app (alguno de los dos puede faltar si la app no está en esa tienda):

   ```bash
   python 01_data_understanding/collect_initial_data/collect_ios_reviews.py --name spotify --app-ios 324684580
   python 01_data_understanding/collect_initial_data/collect_android_reviews.py --name spotify --pkg com.spotify.music
   python 01_data_understanding/collect_initial_data/collect_store_ratings.py --name spotify
   ```

   La primera vez, los ids quedan guardados en `common/companies.csv`; una corrida posterior solo necesita `--name spotify`, sin repetir los ids. Si la app no está en una de las dos tiendas, se omite el script de esa fuente.

2. (Opcional, documentación) Describir cada fuente:

   ```bash
   python 01_data_understanding/describe_data.py --name spotify
   ```

3. Integrar las reseñas con texto (iOS + Android) en un solo dataset (store_ratings no entra: distinta unidad de análisis):

   ```bash
   python 02_data_preparation/integrate_data.py --name spotify
   ```

4. Limpiar las reseñas sin señal real:

   ```bash
   python 02_data_preparation/clean_reviews.py --name spotify
   ```

5. Correr el análisis (mismo `--name`):

   ```bash
   python 03_modeling/model.py --name spotify
   ```

6. Exportar las muestras para nombrar los tópicos:

   ```bash
   python 04_evaluation/topics_enrich.py export --name spotify
   ```

   Esto genera `data/spotify/04_evaluation/topic_samples.json`. Pedirle a Claude (en una sesión de Claude Code, con este repo abierto) que lo lea y escriba `data/spotify/04_evaluation/topics_named.json` con `name`/`summary`/`severity`/`recommendation` por cada tópico no outlier.

7. Mergear esos nombres al resumen:

   ```bash
   python 04_evaluation/topics_enrich.py merge --name spotify
   ```

8. (Opcional) Tendencias temporales y comparación de stores:

   ```bash
   python 04_evaluation/trends.py --name spotify
   ```

8b. (Opcional) Buscar si hay un quiebre de % negativas atado a una versión específica (ej. "se rompió en la v5.45.0"), no solo una tendencia de calendario:

   ```bash
   python 04_evaluation/version_breakout.py --name spotify
   ```

   Compara "desde esa versión en adelante" contra "antes" (exige que la caída se sostenga en las versiones siguientes, no un pico de una sola versión), y solo reporta un quiebre si además pasa un test de significancia de dos proporciones (p < 0.05) — no alcanza con un salto grande de puntos porcentuales si la muestra es chica.

9. Revisar `data/spotify/03_modeling/topics_summary.csv`: ya viene ordenado por severidad (volumen × % negativas) con nombre y recomendación legibles. Las filas con `is_outlier=True` son reseñas sin patrón claro, no un tema real.

10. Generar la web para compartir:

   ```bash
   python 05_deployment/dashboard.py --name spotify --display-name "Spotify"
   ```

   Esto genera `site/spotify.html`: un único archivo autocontenido (sin backend, sin fetch) con resumen ejecutivo, los hallazgos principales con recomendación y reseñas de ejemplo, una comparación de "últimos 3 meses vs. histórico completo" y el detalle completo en una tabla colapsable. Se puede abrir directo en el navegador, subir a GitHub Pages, o mandar como adjunto. `--display-name` es opcional (default: el mismo `--name`) para mostrar un nombre más prolijo que el slug interno.

   `--competitor <nombre>` (opcional) agrega una sección comparando el rating oficial contra un competidor puntual (sus ids tienen que estar ya cargados en `common/companies.csv`, aunque no se le haya corrido el pipeline completo — alcanza con `app_ios`/`pkg`). Ej.: `--competitor bitso` en el análisis de Ripio. Es trabajo específico para esa empresa (no una plantilla reciclable para cualquier otra), y sirve como evidencia de que el análisis no se hizo en automático para mandárselo a todo el mundo por igual.

## ⚠️ Metodología: la muestra de reseñas con texto está sesgada hacia quejas

El scraping (`collect_ios_reviews.py` / `collect_android_reviews.py`) solo puede leer reseñas que tienen **texto escrito**, y las trae ordenadas por más recientes. Eso es una muestra sesgada: la inmensa mayoría de la gente que califica una app solo toca estrellas y nunca escribe nada, y quien sí escribe tiende a hacerlo cuando tiene un problema. En la prueba con Ripio, por ejemplo, el rating oficial de Google Play es 4.65★ sobre 54.268 calificaciones, pero la muestra de reseñas con texto (sort "más recientes") dio un 70% de negativas — representan públicos distintos, no el mismo dato con más o menos ruido.

Por eso el dashboard separa explícitamente:
- **Rating oficial**: viene de `store_ratings.json` (API de iTunes + `google-play-scraper.app()`), cubre todas las calificaciones de la tienda. Es el número que hay que mostrarle a un CEO como "satisfacción general".
- **% negativas / tópicos / hallazgos**: vienen de la muestra de reseñas con texto. Son el insumo correcto para entender **qué** se queja la gente y priorizar qué arreglar — pero no se deben presentar como si midieran la satisfacción general, porque sobre-representan el descontento.

Historia completa de cómo se encontró este sesgo en [APRENDIZAJES.md](APRENDIZAJES.md#2026-10-19--las-reseñas-con-texto-son-una-muestra-sesgada-hacia-las-quejas).

## Pendientes conocidos

Ver [PLAN.md](PLAN.md) para el detalle completo. Resumen de lo que falta:

- Automatizar el nombrado de tópicos con la API de Anthropic cuando haya una API key disponible (hoy es un paso manual vía Claude Code).
- Cruzar el dato de `version` con la comparación de tendencia, para poder decir "empeoró a partir de la v4.2" en vez de solo "empeoró en los últimos 3 meses".

# Review Analysis

Pipeline para extraer reseñas de apps en Google Play y App Store, analizarlas (sentimiento + tópicos) y obtener hallazgos accionables sobre qué se queja o valora la gente. Ver [PLAN.md](PLAN.md) para la hoja de ruta hacia un entregable compartible (web con el análisis de una empresa) y [APRENDIZAJES.md](APRENDIZAJES.md) para bugs/sesgos no obvios que ya encontramos y por qué.

Organizado en fases al estilo **CRISP-DM**: cada carpeta numerada es una fase. Dos fases (`01_business_understanding/` y `05_evaluation/`) no tienen scripts — son documentos, porque esas tareas son juicio humano, no cálculos.

## Ver el sitio en localhost

El sitio (`site/*.html` + `index.html`) es HTML estático — no hace falta backend ni build step, solo un servidor simple para que el browser lo sirva por HTTP (abrirlo con `file://` directo también funciona, pero el link entre `index.html` y cada `site/<empresa>.html`, y el `<link>` a `site/styles.css`, son relativos, así que un server evita sorpresas). Todas las páginas comparten un único `site/styles.css` (en vez de tener el CSS embebido en cada HTML): un cambio de diseño se hace una sola vez y se ve en todas las empresas sin tener que regenerar nada — eso sí, ya no son archivos 100% sueltos: abrir un `<empresa>.html` sin su `styles.css` al lado se ve sin estilos.

```bash
python3 -m http.server 8000
```

Después abrir [http://localhost:8000](http://localhost:8000) (el índice con el listado de empresas) o directo `http://localhost:8000/site/<empresa>.html`. Si todavía no corriste `06_deployment/generate_site.py --name <empresa>` para esa empresa, `site/` no va a tener su HTML — ver paso 12 de "Uso" más abajo.

## Qué hace

1. **Entendimiento del negocio** (`01_business_understanding/BUSINESS_UNDERSTANDING.md`): objetivo de negocio, situación (qué datos hay y qué sesgo tienen), objetivo técnico y criterio de éxito — se lee antes de tocar código, no se corre nada.
2. **Recolección, una fuente por script** (`02_data_understanding/collect_initial_data/collect_*.py`): cada fuente escribe su propio archivo `<fuente>_<empresa>.<formato>`, nunca pisa el de otra fuente.
   - `collect_ios_reviews.py`: reseñas de App Store (RSS de iTunes) → `ios_<empresa>.parquet`.
   - `collect_android_reviews.py`: reseñas de Google Play (`google-play-scraper`) → `android_<empresa>.parquet`.
   - `collect_store_ratings.py`: **rating oficial agregado** de cada tienda (API de iTunes + ficha de Google Play) → `store_ratings_<empresa>.json` — ver nota de metodología más abajo, es importante.

   Las dos primeras deduplican contra lo ya guardado. Los ids de App Store/Google Play se guardan en `data/companies.csv`: una empresa que ya se corrió antes no necesita pasarlos de nuevo, y una empresa sin presencia en una de las dos tiendas (ej. solo Android) funciona sin problema sin correr el script de la tienda que le falta.
3. **Descripción de datos** (`02_data_understanding/describe_data.py`): documenta formato, tamaño, variables y disponibilidad de cada fuente por separado (una `<fuente>_description.md` por fuente, ya que cada una tiene su propio esquema/grano) — tarea de "Data Description" de CRISP-DM, no transforma nada.
4. **Integración** (`03_data_preparation/integrate_data.py`): junta las fuentes de reseñas con texto (ios_reviews + android_reviews) en un solo dataset por empresa (`integrated_<empresa>.parquet`); la columna `store` que ambas ya traen identifica el origen de cada fila, sin agregar una columna redundante. `store_ratings` queda afuera a propósito: es una fila por tienda (rating agregado), una unidad de análisis distinta a una fila por reseña — se consume directo desde su propio JSON, sin integrar.
5. **Construcción de variables** (`03_data_preparation/construct_data.py`): deriva `month` (YYYY-MM), `text_length` (largo del texto) y `rating_bucket` (positiva/neutra/negativa a partir de las estrellas, un sentimiento "barato" independiente del modelo NLP) — tarea de "Construct Data" de CRISP-DM.
5b. **Selección de variables** (`03_data_preparation/select_data.py`, opcional/exploratorio): corre correlación (Pearson/Spearman) o comparación por grupo (Kruskal-Wallis) entre variables, para chequear con números si una variable derivada trae señal real antes de asumirlo (ej. en Ripio, las reseñas negativas duplican en largo a las positivas, diferencia estadísticamente significativa) — tarea de "Select Data" de CRISP-DM.
6. **Limpieza** (`03_data_preparation/clean_reviews.py`): sobre el dataset con variables derivadas, filtra reseñas sin señal real (muy cortas, tipo "buena app") antes de modelar.
7. **Modelado** (`04_modeling/`), las 4 tareas de "Modeling" de CRISP-DM — construir los modelos y evaluar si dan resultados confiables, antes de interpretarlos en términos de negocio:
   - `analyze_sentiment_topics.py`: clasifica el sentimiento de cada reseña (positivo/negativo/neutro) con `pysentimiento` (modelo en español) y agrupa las reseñas en tópicos con `BERTopic` + embeddings multilingües (`sentence-transformers`), con `nr_topics="auto"` para fusionar tópicos casi idénticos (sin esto, Ripio daba 37 tópicos; con esto, 18). Genera un resumen por tópico (cantidad de reseñas, rating promedio, % de negativas) ordenado por los más problemáticos primero. Imprime dos chequeos de calidad del modelo ("Assess model"): `sentiment_mismatch` (% de reseñas donde el sentimiento del texto discrepa de `rating_bucket`, ej. 5 estrellas con texto que el modelo lee como negativo) y `% outliers` (reseñas que BERTopic no pudo agrupar en ningún tópico, tópico `-1`) — si cualquiera de los dos da alto, conviene desconfiar de los hallazgos antes de reportarlos.
   - `topics_enrich.py`: como no hay API key de Anthropic disponible, el nombrado de tópicos no es 100% automático — el script exporta keywords + reseñas de muestra por tópico (`export`), un LLM (hoy, Claude en una sesión de Claude Code) escribe nombre/resumen/severidad/recomendación por tópico, y el script vuelca eso a `topics_summary.csv` (`merge`).
   - `trends.py`: sentimiento por mes y comparación entre App Store y Google Play.
   - `version_breakout.py`: busca si el % de negativas tuvo un quiebre real atado a una versión específica, con test de significancia antes de reportarlo.
8. **Evaluación** (`05_evaluation/EVALUATION.md`): antes de publicar, responder a mano las 3 tareas de "Evaluation" de CRISP-DM — ¿los hallazgos cumplen el criterio de negocio (5.1)?, ¿se corrió todo bien (5.2)?, ¿deploy, iterar, o no hay suficiente volumen para un análisis serio (5.3)? Tampoco tiene scripts: es un checklist que usa los números que ya imprimió `04_modeling/analyze_sentiment_topics.py`.
9. **Deployment** (`06_deployment/generate_site.py`): genera `site/<empresa>.html` (datos embebidos, estilos en `site/styles.css` compartido con todas las empresas) con resumen ejecutivo, los hallazgos principales (con recomendación y reseñas de ejemplo), una comparación de "últimos 3 meses vs. histórico completo" (con un chip de Mejorando/Empeorando/Estable) y el detalle completo en una tabla colapsable — listo para compartir por link, sin backend ni build step. También regenera `index.html` en la raíz del repo (home del dominio de GitHub Pages), con el listado de empresas analizadas.

Cada empresa/app analizada vive en su propia carpeta (`data/<empresa>/`), identificada por el `--name` que le pases a los scripts. Dentro, los archivos están organizados por fase (mismo esquema CRISP-DM que el resto del repo), no todos sueltos en una sola carpeta `output/`: así agregar una empresa nueva, o una fase nueva en el futuro, no satura una carpeta compartida.

## Estructura

```
common/
  config.py          # paths por empresa (data/<empresa>/<fase>/...), importado por todas las fases
  companies_registry.py        # registro de empresas ya analizadas (lookup/upsert de companies.csv)
  check_env.py        # sanity check de que HF_TOKEN está cargado
data/
  companies.csv        # nombre, app_ios, pkg por empresa — versionado, se edita solo o vía collect_*.py
01_business_understanding/
  BUSINESS_UNDERSTANDING.md  # objetivo de negocio, situación, objetivo técnico, criterio de éxito (sin scripts)
02_data_understanding/
  collect_initial_data/
    collect_ios_reviews.py      # fuente 1: scraping de App Store
    collect_android_reviews.py  # fuente 2: scraping de Google Play
    collect_store_ratings.py    # fuente 3: rating oficial agregado por tienda
  describe_data.py            # describe cada fuente por separado, en un .md unificado
03_data_preparation/
  integrate_data.py    # integra ios_reviews + android_reviews (NO store_ratings) en un dataset; "store" ya identifica el origen
  construct_data.py    # deriva month, text_length, rating_bucket sobre el dataset integrado
  select_data.py       # correlación/comparación por grupo entre variables, para chequear señal antes de modelar
  clean_reviews.py     # filtra reseñas sin señal real, sobre el dataset con variables derivadas
04_modeling/
  analyze_sentiment_topics.py             # sentimiento + topic modeling + resumen + chequeos de calidad del modelo
  topics_enrich.py    # export de muestras por tópico + merge de nombres/recomendaciones
  trends.py            # tendencia mensual + comparación de stores
  version_breakout.py  # quiebre de % negativas atado a una versión específica
05_evaluation/
  EVALUATION.md        # checklist de las 3 tareas de Evaluation de CRISP-DM (sin scripts)
06_deployment/
  generate_site.py        # genera site/<empresa>.html y regenera index.html (ambos en la raíz, no acá)
index.html            # listado de empresas analizadas — home del dominio de GitHub Pages (se regenera solo)
site/
  <empresa>.html       # web de esa empresa para compartir (SÍ versionado — ver "Publicar")
  styles.css           # CSS compartido por index.html y todos los <empresa>.html
data/
  <empresa>/
    02_data_understanding/
      ios_<empresa>.parquet              # fuente 1: reseñas crudas de App Store
      android_<empresa>.parquet          # fuente 2: reseñas crudas de Google Play
      store_ratings_<empresa>.json       # fuente 3: rating oficial agregado por tienda (score + cantidad de calificaciones)
      <fuente>_description.{md,json}     # describe_data.py, una por fuente
    03_data_preparation/
      integrated_<empresa>.parquet   # ios_reviews + android_reviews integradas, identificadas por "store" (store_ratings no entra)
      constructed_<empresa>.parquet # + month, text_length, rating_bucket
      reviews_clean.parquet         # reseñas filtradas, insumo del modelado
    04_modeling/
      reviews_enriched.parquet  # reseñas + sentimiento + tópico + sentiment_mismatch
      reviews_enriched.csv      # idem, para abrir en Excel
      topics_summary.csv        # resumen por tópico; topics_enrich.py le agrega name/summary/severity/recommendation
      topic_samples.json        # keywords + muestras por tópico, insumo para el nombrado
      topics_named.json         # nombre/resumen/severidad/recomendación por tópico (lo escribe el LLM)
      sentiment_by_month.csv    # tendencia mensual de sentimiento por store
      store_comparison.csv      # comparación agregada iOS vs Android
      version_breakout.json     # quiebre de % negativas por versión, si hay uno real (null si no)
```

`01_business_understanding/` y `05_evaluation/` no generan nada en `data/<empresa>/` — son documentos de proceso, no fases con output por empresa.

`site/` e `index.html` quedan en la **raíz del repo**, no dentro de `06_deployment/`: GitHub Pages "clásico" (deploy from branch) solo sirve desde la raíz o `/docs`, nunca una carpeta anidada (ver `common/config.py` y `APRENDIZAJES.md`).

`data/` y `.env` están en `.gitignore`: los datos crudos/procesados y las credenciales no se versionan. `site/` **sí** se versiona (ver "Publicar" más abajo).

## Publicar (GitHub Pages)

El repo es **público** y tiene GitHub Pages activado sirviendo `main` desde la raíz. Al versionar `site/<empresa>.html`, cada dashboard queda accesible en:

```
https://nachomondino1.github.io/review_analysis/<empresa>.html
```

`index.html` (en la raíz) lista todas las empresas analizadas y es lo que se ve en `https://nachomondino1.github.io/review_analysis/` — se regenera automáticamente cada vez que corre `generate_site.py`, escaneando los `.html` existentes en `site/`. Al ser un repo público, de todas formas cualquiera puede encontrar los archivos navegando el código, liste o no el índice. Si en algún momento esto deja de ser aceptable para alguna empresa puntual, la alternativa es no commitear ese `.html` y mandarlo directo como archivo adjunto (ya lo hacíamos así antes de activar Pages).

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

0. Leer [`01_business_understanding/BUSINESS_UNDERSTANDING.md`](01_business_understanding/BUSINESS_UNDERSTANDING.md) si es la primera vez que se corre el pipeline (no hay nada que ejecutar, es contexto).

1. Correr la recolección de cada fuente, indicando el id de App Store y/o el package de Google Play de la app (alguno de los dos puede faltar si la app no está en esa tienda):

   ```bash
   python 02_data_understanding/collect_initial_data/collect_ios_reviews.py --name spotify --app-ios 324684580
   python 02_data_understanding/collect_initial_data/collect_android_reviews.py --name spotify --pkg com.spotify.music
   python 02_data_understanding/collect_initial_data/collect_store_ratings.py --name spotify
   ```

   La primera vez, los ids quedan guardados en `data/companies.csv`; una corrida posterior solo necesita `--name spotify`, sin repetir los ids. Si la app no está en una de las dos tiendas, se omite el script de esa fuente.

2. (Opcional, documentación) Describir cada fuente:

   ```bash
   python 02_data_understanding/describe_data.py --name spotify
   ```

3. Integrar las reseñas con texto (iOS + Android) en un solo dataset (store_ratings no entra: distinta unidad de análisis):

   ```bash
   python 03_data_preparation/integrate_data.py --name spotify
   ```

4. Derivar variables nuevas (`month`, `text_length`, `rating_bucket`):

   ```bash
   python 03_data_preparation/construct_data.py --name spotify
   ```

4b. (Opcional) Chequear si esas variables derivadas traen señal real antes de llevarlas a modelado:

   ```bash
   python 03_data_preparation/select_data.py --name spotify
   ```

5. Limpiar las reseñas sin señal real:

   ```bash
   python 03_data_preparation/clean_reviews.py --name spotify
   ```

6. Correr el análisis (mismo `--name`):

   ```bash
   python 04_modeling/analyze_sentiment_topics.py --name spotify
   ```

7. Exportar las muestras para nombrar los tópicos:

   ```bash
   python 04_modeling/topics_enrich.py export --name spotify
   ```

   Esto genera `data/spotify/04_modeling/topic_samples.json`. Pedirle a Claude (en una sesión de Claude Code, con este repo abierto) que lo lea y escriba `data/spotify/04_modeling/topics_named.json` con `name`/`summary`/`severity`/`recommendation` por cada tópico no outlier.

8. Mergear esos nombres al resumen:

   ```bash
   python 04_modeling/topics_enrich.py merge --name spotify
   ```

9. (Opcional) Tendencias temporales y comparación de stores:

   ```bash
   python 04_modeling/trends.py --name spotify
   ```

9b. (Opcional) Buscar si hay un quiebre de % negativas atado a una versión específica (ej. "se rompió en la v5.45.0"), no solo una tendencia de calendario:

   ```bash
   python 04_modeling/version_breakout.py --name spotify
   ```

   Compara "desde esa versión en adelante" contra "antes" (exige que la caída se sostenga en las versiones siguientes, no un pico de una sola versión), y solo reporta un quiebre si además pasa un test de significancia de dos proporciones (p < 0.05) — no alcanza con un salto grande de puntos porcentuales si la muestra es chica.

10. Revisar `data/spotify/04_modeling/topics_summary.csv`: ya viene ordenado por severidad (volumen × % negativas) con nombre y recomendación legibles. Las filas con `is_outlier=True` son reseñas sin patrón claro, no un tema real.

11. **Evaluar** con el checklist de [`05_evaluation/EVALUATION.md`](05_evaluation/EVALUATION.md) antes de publicar: ¿los hallazgos tienen volumen/severidad suficientes?, ¿`% outliers`/`% sentiment_mismatch` dan razonables?, ¿deploy, iterar, o no da para un análisis serio?

12. Generar la web para compartir:

   ```bash
   python 06_deployment/generate_site.py --name spotify --display-name "Spotify"
   ```

   Esto genera `site/spotify.html` (sin backend, sin fetch de datos — los datos quedan embebidos en el HTML, solo el CSS viene de `site/styles.css` compartido) con resumen ejecutivo, los hallazgos principales con recomendación y reseñas de ejemplo, una comparación de "últimos 3 meses vs. histórico completo" y el detalle completo en una tabla colapsable. Se puede abrir directo en el navegador o subir a GitHub Pages; para mandarlo como adjunto suelto hay que incluir también `site/styles.css`. `--display-name` es opcional (default: el mismo `--name`) para mostrar un nombre más prolijo que el slug interno.

   `--competitor <nombre>` (opcional) agrega una sección comparando el rating oficial contra un competidor puntual (sus ids tienen que estar ya cargados en `data/companies.csv`, aunque no se le haya corrido el pipeline completo — alcanza con `app_ios`/`pkg`). Ej.: `--competitor bitso` en el análisis de Ripio. Es trabajo específico para esa empresa (no una plantilla reciclable para cualquier otra), y sirve como evidencia de que el análisis no se hizo en automático para mandárselo a todo el mundo por igual.

## ⚠️ Metodología: la muestra de reseñas con texto está sesgada hacia quejas

El scraping (`collect_ios_reviews.py` / `collect_android_reviews.py`) solo puede leer reseñas que tienen **texto escrito**, y las trae ordenadas por más recientes. Eso es una muestra sesgada: la inmensa mayoría de la gente que califica una app solo toca estrellas y nunca escribe nada, y quien sí escribe tiende a hacerlo cuando tiene un problema. En la prueba con Ripio, por ejemplo, el rating oficial de Google Play es 4.65★ sobre 54.268 calificaciones, pero la muestra de reseñas con texto (sort "más recientes") dio un 70% de negativas — representan públicos distintos, no el mismo dato con más o menos ruido.

Por eso el dashboard separa explícitamente:
- **Rating oficial**: viene de `store_ratings_<empresa>.json` (API de iTunes + `google-play-scraper.app()`), cubre todas las calificaciones de la tienda. Es el número que hay que mostrarle a un CEO como "satisfacción general".
- **% negativas / tópicos / hallazgos**: vienen de la muestra de reseñas con texto. Son el insumo correcto para entender **qué** se queja la gente y priorizar qué arreglar — pero no se deben presentar como si midieran la satisfacción general, porque sobre-representan el descontento.

Historia completa de cómo se encontró este sesgo en [APRENDIZAJES.md](APRENDIZAJES.md#2026-10-19--las-reseñas-con-texto-son-una-muestra-sesgada-hacia-las-quejas).

## Pendientes conocidos

Ver [PLAN.md](PLAN.md) para el detalle completo. Resumen de lo que falta:

- Automatizar el nombrado de tópicos con la API de Anthropic cuando haya una API key disponible (hoy es un paso manual vía Claude Code).
- Cruzar el dato de `version` con la comparación de tendencia, para poder decir "empeoró a partir de la v4.2" en vez de solo "empeoró en los últimos 3 meses".

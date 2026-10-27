# Plan: de script a entregable para una empresa

Objetivo del hito: dado el nombre/ids de una app, generar un **análisis accionable de sus reseñas** y una **web compartible** (link, no un CSV) para mandarle a un CEO. El fin último es conseguir trabajo mostrando trabajo real, así que lo que importa priorizar es: **que el output se vea profesional y diga algo accionable**, antes que robustecer el pipeline interno.

Arquitectura de referencia: Arquetipo B del `DATA_FLOW_PLAYBOOK_unificado.md` (fuente → enriquecimiento con caché → modelo → `generate_site.py` → un solo HTML autocontenido, `make publish`). Para el diseño del HTML, `DESIGN_PLAYBOOK_unificado.md` (tokens, tipografía, componentes — ya pensado para "producto personal cuidado", que es exactamente el tono que querés para este caso).

Prioridad: **tiempo primero**. Cada fase asume que la anterior ya te sirve para mostrarle algo a alguien. No hace falta terminar una fase entera para arrancar la siguiente si lo que falta no bloquea una demo.

---

## Fase 0 — Dejar lo que ya existe usable (horas, no días)

Lo mínimo para poder correr el flujo de punta a punta sin tocar código a mano cada vez.

- [ ] **Parametrizar la app por CLI**, no hardcodeada en `collect_data.py`. Algo simple: `python 01_data_understanding/collect_data.py --app-ios 324684580 --pkg com.spotify.music --name "Spotify"`. Sin esto, cada empresa nueva es editar código.
- [ ] **`requirements.txt`** (o `pyproject.toml`) con versiones fijadas. 10 minutos, evita que el entorno se rompa en el peor momento (justo cuando le estás armando el análisis a alguien).
- [ ] **Separar carpetas de output por empresa**: `data/<empresa>/reviews.parquet`, `data/<empresa>/output/...`. Hoy todo pisa `data/reviews.parquet` sin importar qué app corriste antes — con una sola empresa a la vez no se nota, pero en cuanto quieras tener 2-3 análisis guardados para mostrar, se pisan.
- [ ] **Filtrar el tópico `-1`** (outliers de BERTopic) del resumen, o marcarlo explícitamente como "sin patrón claro" — hoy puede aparecer mezclado con tópicos reales en el CSV.
- [ ] Mover el `app_ios`/`pkg` hardcodeado de `analyze_sentiment_topics.py`/`collect_data.py` a un único `config.py` por corrida (lee de CLI o de un `empresas.yaml` chico), para no tener el nombre de la empresa duplicado en dos scripts.

**Resultado de esta fase:** podés correr `python 01_data_understanding/collect_data.py --app-ios X --pkg Y --name Z && python 02_data_preparation/clean_reviews.py --name Z && python 03_modeling/analyze_sentiment_topics.py --name Z` para cualquier empresa sin editar código.

## Fase 1 — El análisis tiene que decir algo accionable (el corazón del valor)

Esto es lo que diferencia "corrí un notebook de NLP" de "te traigo 3 cosas que podés arreglar esta semana". Es la fase de mayor impacto por hora invertida.

- [x] **Nombrar los tópicos con un LLM, no con las keywords crudas de BERTopic.** Hecho en `04_evaluation/topics_enrich.py` (`export`/`merge`) con nombre, resumen, severidad y recomendación por tópico. **Decisión:** no hay API key de Anthropic disponible (el plan Pro de claude.ai no la incluye), así que el nombrado no quedó automatizado vía API — el script exporta las muestras y el nombrado lo hace Claude en una sesión de Claude Code, que después mergea el resultado. Si en el futuro hay una API key, se puede automatizar sin cambiar el contrato del `topics_named.json`.
- [x] **Agregar una recomendación por tópico negativo**, no solo el diagnóstico. Incluido en el mismo paso: `topics_summary.csv` queda ordenado por severidad (`n × pct_neg`) con `recommendation` por tópico.
- [x] **Serie temporal simple**: `04_evaluation/trends.py` genera `sentiment_by_month.csv` (sentimiento por mes y store).
- [x] **Comparar rating de Play Store vs App Store**: `04_evaluation/trends.py` genera `store_comparison.csv`.
- [ ] Dejar **afuera por ahora** (no vale el tiempo para la v1): entrenar un clasificador propio de sentimiento, multi-idioma más allá de es/en, dashboards interactivos con filtros complejos, comparación contra competidores.
- [x] **Hallazgo crítico de metodología (2026-10-19, probando con Ripio real):** el rating "promedio" calculado sobre la muestra de reseñas scrapeadas (2.25★) no se parecía en nada al rating oficial de las tiendas (4.61★ ponderado, sobre 62.767 calificaciones). Causa: el scraping solo puede leer reseñas con **texto**, ordenadas por más recientes — una muestra que sobre-representa quejas, porque la inmensa mayoría de quien solo toca estrellas nunca escribe nada. **Fix:** `collect_data.py` ahora también guarda el rating oficial agregado por tienda (`store_ratings.json`, vía API de iTunes + `google_play_scraper.app()`), y el dashboard lo muestra como "Rating oficial" separado de "% negativas en la muestra", con una nota de metodología explícita. Ver sección de metodología en el README. Esto era bloqueante: mostrarle a un CEO un 2.25★ cuando su rating real es 4.61★ hubiera sido un error de credibilidad grave.

**Resultado de esta fase:** `topics_summary` deja de ser un CSV técnico y pasa a ser 5-8 hallazgos con nombre, severidad y una sugerencia concreta — el insumo real de la web.

## Fase 2 — La web para compartir (Arquetipo B: `generate_site.py` → 1 HTML)

No hace falta hosting, backend, ni build step. Un solo HTML autocontenido con los datos embebidos, que se sube a cualquier lado (GitHub Pages, o directo como adjunto/link de Drive) y se ve bien en el celular del CEO.

- [x] **`05_deployment/generate_site.py`**: lee `reviews_enriched.parquet` y `topics_summary.csv` (ya con nombres/recomendaciones de la Fase 1), y genera `site/<empresa>.html` (+ `index.html` en la raíz con el listado) con los datos embebidos directo en el HTML (sin fetch, sin modo de falla de red).
- [x] **Contenido del HTML**:
  1. Resumen ejecutivo: N° de reseñas, rating promedio, % negativas, cantidad de hallazgos a atender.
  2. Hasta 6 hallazgos principales (severidad alta/media) con nombre, chip de severidad, resumen, recomendación y 2 reseñas textuales de ejemplo — ordenados por severidad real (volumen × % negativas).
  3. Comparación "últimos 3 meses vs. histórico completo" con un chip de Mejorando/Empeorando/Estable — reemplaza al gráfico de línea mensual (ver [APRENDIZAJES.md, 2026-10-20](APRENDIZAJES.md#2026-10-20--un-gráfico-de-línea-no-responde-cómo-venimos-si-la-dirección-es-ambigua): un gráfico donde "sube" es ambiguo —¿sube el % negativas (malo) o el rating (bueno)?— no responde la pregunta real de forma directa).
  4. Tabla completa de tópicos en `<details>`, colapsada por default.
  - **Resuelto (2026-10-21):** `04_evaluation/version_breakout.py` cruza sentimiento con `version` — compara "desde una versión en adelante" contra "antes" (exige que la caída se sostenga, no un pico de una versión aislada) y exige significancia estadística (test de dos proporciones, p < 0.05) antes de reportar nada. **Nota (mismo día):** la primera versión del script sí encontró un salto en Ripio (android v5.45.0, +24 pts) pero con solo 19 reseñas de esa versión — el usuario cuestionó la muestra, y con el método corregido (persistencia + significancia) ese salto no se sostuvo. Ver [APRENDIZAJES.md, 2026-10-21](APRENDIZAJES.md#2026-10-21--un-salto-grande-con-muestra-chica-puede-ser-ruido-no-señal).
- [x] **Diseño**: tokens del Design Playbook (colores, Inter, cards, dark mode automático), acento propio (verde azulado, no reusado de otro proyecto).
- [x] **Probado en 320px/375px y sin viewport** (ver `read_page`/`javascript_tool` del navegador): sin overflow de página; encontramos y arreglamos un bug real (`minmax(280px,...)` en los grids no encogía por debajo de 280px) y envolvimos la tabla de detalle en su propio scroll-container en vez de dejarla empujar la página.
- [x] **Decisión (2026-10-19):** el `site/` generado vive dentro de `05_deployment/` (no en la raíz del repo), para que quede junto al script que lo genera. **Decisión relacionada:** dentro de `data/<empresa>/` los outputs ya no van todos a una sola carpeta `output/` plana — cada fase tiene su propia subcarpeta (`01_data_understanding/`, `02_data_preparation/`, `03_modeling/`, `04_evaluation/`), igual que a nivel raíz del repo, para que agregar una fase o una empresa no infle una carpeta compartida. Ver [[feedback_crispdm_structure]] en memoria.

**Resultado de esta fase:** un link (o archivo HTML) que le mandás a alguien y entiende en 30 segundos qué está pasando con las reseñas de su app, sin que vos estés al lado explicando.

## Fase 3 — Pulido para el pitch (si da el tiempo antes de mandarlo)

- [ ] Branding mínimo: tu nombre/firma al pie ("Análisis armado por [vos] — [contacto]"), para que quede claro quién lo hizo.
- [ ] Un PDF/export o captura, por si el canal de contacto no permite mandar un link a HTML.
- [ ] `Makefile` con `make run EMPRESA=spotify` que encadene collect → model → dashboard, para que la próxima empresa sea un solo comando (ver Fase 0).
- [ ] Caché de reseñas ya scrapeadas por empresa (ya lo tenés parcialmente en `collect_data.py` vía dedupe) para no re-scrapear si volvés a correr el análisis con ajustes del LLM.

**Explícitamente fuera de la v1** (no vale el tiempo hasta tener 1-2 casos reales mostrados): multi-tenant con login, actualización automática/cron, comparación histórica entre empresas, API propia, tests exhaustivos más allá de un smoke test manual del flujo completo.

---

## Orden recomendado de ejecución

1. Fase 0 completa (es rápida y desbloquea todo lo demás).
2. Fase 1 completa — es donde está el valor real para la empresa.
3. Fase 2 hasta tener algo mostrable, aunque sea con diseño default sin pulir.
4. Volver y pulir diseño (Fase 2 cola + Fase 3) **recién con una empresa real de prueba**, para no pulir sobre datos ficticios.

**Criterio de "listo para mandar a un CEO":** corriste el flujo completo con una app real (puede ser una empresa cualquiera para probar, no necesita ser el target), el HTML abre bien en mobile y desktop, los 3-5 hallazgos principales tienen nombre y recomendación legible (no jerga de BERTopic), y no hay ningún dato roto o `NaN` visible en la página.

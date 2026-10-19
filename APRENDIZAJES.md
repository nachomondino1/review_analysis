# Aprendizajes

Lecciones no obvias que encontramos construyendo este proyecto — bugs reales,
sesgos de datos, decisiones de diseño que no salían a la primera. A diferencia
de [PLAN.md](PLAN.md) (qué falta hacer) y de los commits (qué cambió), esto es
**por qué** algo que parecía correcto no lo era, para no volver a pisar el
mismo problema en el futuro o en otro proyecto similar.

Se agrega una entrada nueva cada vez que algo nos sorprende o nos hace
corregir un supuesto, no cada vez que se agrega una feature. Organizado por
fase de CRISP-DM (misma estructura de carpetas que el resto del repo), porque
el tipo de sorpresa que aparece suele ser propio de esa etapa: en recolección
son sesgos de la fuente, en modelado son particularidades del algoritmo, en
deployment son bugs de la capa de presentación.

---

## 01 — Data Understanding

### 2026-10-19 — Las reseñas con texto son una muestra sesgada hacia las quejas

**Qué pasó:** corriendo el análisis completo con Ripio (datos reales), el
dashboard mostraba 2.25★ de rating promedio y 70% de reseñas negativas. El
usuario desconfió porque el rating real de Ripio en las tiendas es bueno, y
pidió verificar que no fuera un error de id de app.

**Qué encontramos:** la app era la correcta (mismos ids que App Store/Google
Play). El problema era la muestra:
- Rating oficial real: **4.37★** en App Store (8.501 calificaciones) y
  **4.65★** en Google Play (54.266 calificaciones) — vía API de iTunes
  (`lookup`) y `google_play_scraper.app()`.
- De esas 54.266 calificaciones de Google Play, solo **14.041 tienen texto
  escrito**. El scraping solo puede leer reseñas con texto, y las trajimos
  ordenadas por "más recientes".
- Quien solo toca estrellas y no escribe nada (la inmensa mayoría) nunca
  entra al dataset. Quien sí se toma el trabajo de escribir tiende a hacerlo
  cuando tiene un problema. Ordenar por "más recientes" además puede capturar
  justo una racha de incidentes puntuales.

Resultado: el 70% de negativas no estaba mal calculado — es un número real
sobre la muestra que tenemos — pero esa muestra **no representa a la base de
usuarios general**, y mostrarlo como si fuera "la satisfacción de los
usuarios" habría sido engañoso.

**Cómo lo resolvimos:** `collect_data.py` ahora también guarda el rating
oficial agregado de cada tienda (`store_ratings.json`), y el dashboard lo
muestra como una métrica separada ("Rating oficial") de las métricas que
vienen de la muestra de texto ("% negativas en la muestra"), con una nota de
metodología explícita en la web. Ver sección correspondiente en el
[README](README.md#%EF%B8%8F-metodología-la-muestra-de-reseñas-con-texto-está-sesgada-hacia-quejas).

**Lección generalizable:** cualquier análisis de texto que dependa de
"reseñas escritas" (no solo reviews de apps — también comentarios, tickets de
soporte, posts en redes) es una muestra autoseleccionada por quien decide
escribir, y esa decisión casi nunca es aleatoria. Antes de presentar una
métrica derivada de texto libre como si representara a "los usuarios" en
general, conseguir un número de referencia poblacional (rating agregado,
NPS, lo que exista) y mostrarlo al lado, no en su reemplazo.

---

## 03 — Modeling

### 2026-10-19 — El tópico `-1` de BERTopic no es un tema, es "no encajó en ninguno"

**Qué pasó:** el resumen por tópico (`topics_summary.csv`) mezclaba el
tópico `-1` (que BERTopic usa para reseñas que no agrupó en ningún cluster)
con los tópicos reales, ordenado solo por `% negativas`. Podía aparecer
entre los primeros puestos sin ser un hallazgo real.

**Cómo lo resolvimos:** se marca explícitamente con `is_outlier=True` en
`03_modeling/model.py`, se excluye de los hallazgos del dashboard y del
nombrado con LLM, y se muestra aparte en la tabla de detalle como "Sin
patrón claro".

**Lección generalizable:** cuando un modelo de clustering tiene una
categoría especial para "no clasificado" (BERTopic, DBSCAN, HDBSCAN, etc.),
tratarla como dato de primera clase desde el esquema de salida, no como un
cluster más — si no, tarde o temprano termina mezclada en un ranking o un
resumen como si fuera una categoría real.

---

## 04 — Evaluation

### 2026-10-19 — Nombrar tópicos con LLM sin tener una API key de Anthropic

**Qué pasó:** la idea original era llamar a la API de Claude para nombrar
los tópicos de BERTopic automáticamente. El usuario no tiene una
`ANTHROPIC_API_KEY` (el plan Pro de claude.ai no la incluye; son productos
separados con facturación distinta).

**Cómo lo resolvimos:** en vez de bloquear la feature o pedirle que pague
por una API key, se partió el paso en dos: `topics_enrich.py export` deja
las keywords + reseñas de muestra en un JSON, y el nombrado lo hace Claude
Code en la misma sesión de trabajo (sin costo de API), para después volcar
el resultado con `topics_enrich.py merge`. No es 100% automático (necesita
una sesión de Claude Code por corrida), pero no tiene costo ni requiere
setup de facturación.

**Lección generalizable:** "necesito un LLM para este paso" no siempre
significa "necesito una API key" — si el consumidor del pipeline ya está
trabajando con un asistente en una sesión interactiva, partir el paso en
export/import deterministas permite que el asistente haga el trabajo de
lenguaje natural sin pasar por una API externa. Vale la pena ofrecer esto
como alternativa antes de asumir que hace falta una key.

---

## 05 — Deployment

### 2026-10-19 — `minmax(Npx, 1fr)` en una grilla CSS no encoge por debajo de `Npx`

**Qué pasó:** probando el dashboard en un viewport muy angosto, las cards de
hallazgos y de stats desbordaban la página (`scrollWidth > innerWidth`)
aunque el CSS parecía "responsive" con `grid-template-columns: repeat(auto-fit,
minmax(280px, 1fr))`.

**Por qué pasa:** `minmax(280px, 1fr)` le pone un piso de 280px a cada
columna sin importar cuánto espacio real haya — por debajo de ese ancho, la
grilla fuerza overflow en vez de encoger.

**Cómo lo resolvimos:** `minmax(min(280px, 100%), 1fr)` — el `min()` hace
que el piso de la columna sea 280px o el 100% del contenedor, lo que sea
menor, así nunca fuerza más ancho del que hay disponible.

**Lección generalizable:** cualquier `minmax(Npx, 1fr)` en un layout que
tiene que andar en mobile necesita el wrapper `min(Npx, 100%)`, no solo
`auto-fit`/`auto-fill`. Verificar overflow con `scrollWidth`/`innerWidth`
por script, no solo mirando un screenshot a un ancho fijo — a 320-375px a
veces no se nota, pero en viewports más angostos (o con texto más largo) sí.

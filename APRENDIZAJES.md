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

### 2026-10-19 — `min_topic_size` fijo rompe el modelado en empresas chicas

**Qué pasó:** probando con Beelup (74 reseñas con texto, bastante menos que
Ripio o Spotify), BERTopic con `min_topic_size=20` (fijo) no pudo formar
**ningún** tópico real: las 74 reseñas cayeron todas en el outlier `-1`. El
dashboard hubiera mostrado "0 hallazgos" para una empresa que en realidad
tenía quejas bien claras y repetidas (la app es un simple link a una web que
además anda mal).

**Cómo lo resolvimos:** `min_topic_size` ahora se calcula con
`min_topic_size_for(n_docs)` en `03_modeling/model.py` — escala con el
tamaño del corpus (`n_docs // 10`), con un piso de 5 para no generar tópicos
de 2-3 reseñas sin sentido. Con ese cambio, Beelup formó 2 tópicos reales
sobre 70 de las 74 reseñas.

**Lección generalizable:** cualquier hiperparámetro de modelado calibrado
"a ojo" contra el primer dataset que se prueba (acá, Spotify con miles de
reseñas) hay que revisarlo contra el caso chico antes de asumir que
generaliza — un pipeline que corre sin error pero devuelve "sin resultados"
para un dataset chico es un bug silencioso, no una empresa sin problemas
que reportar. Probar siempre con al menos un caso grande y uno chico antes
de dar una fase por terminada.

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

---

### 2026-10-19 — El gráfico de tendencia se vuelve ilegible con todo el historial

**Qué pasó:** en Ripio, `sentiment_by_month.csv` tenía datos desde 2021
(121 filas, dos stores). El gráfico SVG graficaba **todos** los meses: en
desktop se veía apretado, y en mobile quedaba un zigzag denso e ilegible
(puntos y etiquetas de mes superpuestos), aunque los datos en sí estaban
bien.

**Cómo lo resolvimos:** `build_chart_svg` ahora corta a los últimos 12
meses (`MAX_MONTHS_IN_CHART`) y, si hay más historial, lo aclara con una
nota ("Mostrando los últimos 12 meses..."). También salteamos etiquetas de
mes cuando hay muchas (máximo ~6 visibles) para que no se solapen.

**Lección generalizable:** un gráfico de serie temporal diseñado y probado
con pocos puntos de datos (semanas de prueba) no necesariamente escala bien
cuando el dataset real tiene años de historia. Para un resumen ejecutivo,
la tendencia reciente (semanas/meses) suele ser más accionable que el
historial completo — recortar la ventana no es "perder información", es
priorizar qué se puede leer de un vistazo. Probar visualizaciones con el
caso "mucho volumen de tiempo", no solo con "muchas categorías" o "mucho
texto".

---

### 2026-10-20 — GitHub Pages "clásico" no sirve carpetas anidadas

**Qué pasó:** `dashboard.py` escribía en `05_deployment/site/`, y las URLs
públicas quedaban con ese prefijo completo
(`.../05_deployment/site/ripio.html`) — incómodo para compartir.

**Qué evaluamos:** GitHub Pages "deploy from branch" (el modo simple, sin
Actions) solo puede servir desde la raíz del repo o una carpeta `/docs` en
la raíz — nunca una carpeta anidada como `05_deployment/site/`. Para
servir esa carpeta tal cual habría hecho falta un workflow de GitHub
Actions (`upload-pages-artifact` + `deploy-pages`), que sí puede publicar
cualquier carpeta como raíz del sitio.

**Cómo lo resolvimos:** se evaluó explícitamente el trade-off y, con
preferencia declarada por la simplicidad, se eligió mover la carpeta
generada a `site/` en la raíz del repo (un solo cambio en `config.py`) en
vez de agregar un workflow de Actions. El código del generador
(`dashboard.py`) se queda en `05_deployment/`; solo cambia dónde aterriza
el archivo que genera.

**Lección generalizable:** separar "dónde vive el código que genera algo"
de "dónde tiene que aterrizar lo generado" no rompe ninguna convención —
es normal que un generador en `src/` o `05_deployment/` escriba su output
en `docs/`, `site/` o `dist/` en la raíz, porque esa ubicación responde a
una restricción externa (acá, GitHub Pages), no a la organización del
código. Antes de agregar infraestructura nueva (un workflow de CI/CD) para
preservar una convención de carpetas, vale la pena preguntar si mover
solo el output es más simple — en este caso lo era.

---

### 2026-10-20 — Un gráfico de línea no responde "¿cómo venimos?" si la dirección es ambigua

**Qué pasó:** después de arreglar el eje Y del gráfico de tendencia mensual
(agregando los números de porcentaje), el usuario señaló que seguía sin
servir: "si sube es malo, lo cual es contraintuitivo". El gráfico graficaba
% de reseñas negativas por mes — una línea que sube visualmente se lee
como "mejora" por default (intuición común: arriba = mejor), pero acá
arriba significaba más quejas.

**Cómo lo resolvimos:** se reemplazó el gráfico de línea completo por una
comparación directa de dos números: "últimos 3 meses" vs. "histórico
completo" (rating, % negativas, n), con un chip de texto explícito —
"Mejorando" (verde) / "Empeorando" (rojo) / "Estable" (gris) — calculado
sobre la diferencia real de % negativas, no inferido de la forma de una
curva. Si la muestra reciente es muy chica (< 5 reseñas), la sección se
omite en vez de forzar una comparación poco confiable.

**Lección generalizable:** un gráfico de tendencia solo es intuitivo
cuando "arriba/sube" coincide con "mejor" para cualquier lector a primera
vista. Si la métrica que se grafica es "negativa por naturaleza" (quejas,
errores, tasa de abandono), invertir el eje ayuda poco porque igual hay
que leer la leyenda para confirmar qué significa la dirección. Cuando la
pregunta real es "¿mejoramos o empeoramos?" (una comparación de dos
períodos), a veces la respuesta más clara no es un gráfico en absoluto,
sino el número y una palabra con color: "Mejorando" / "Empeorando". No
toda serie temporal necesita visualizarse como serie temporal.

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

---

### 2026-10-20 — Reusar un componente "pill" para una oración larga desborda la página

**Qué pasó:** el chip "Mejorando/Empeorando" de la entrada anterior usaba la
clase `.chip` (pensada para texto corto tipo "ALTA", `white-space: nowrap`
implícito en el patrón de pill) para una oración completa ("Mejorando: 12.5
puntos porcentuales menos reseñas negativas que el histórico"). En mobile,
el texto no podía hacer wrap y la página desbordaba horizontalmente.

**Cómo lo resolvimos:** se creó un componente nuevo (`.trend-banner`, un
bloque normal con padding y color, no un pill) para texto largo con
semántica de color, dejando `.chip` solo para etiquetas cortas de una
palabra o dos.

**Lección generalizable:** un componente visual "pill/badge" (`border-radius:
999px`, una sola línea) está implícitamente pensado para texto corto y fijo
— cuando el contenido real es una oración variable, usarlo igual (aunque
visualmente se vea bien en el caso de prueba) es una deuda que aparece en
el primer texto más largo de lo esperado. Elegir el componente por la forma
del contenido (¿es una etiqueta corta y fija, o una oración que puede
variar en longitud?), no por cuál ya existía con el color que hacía falta.

De paso, en el mismo cambio: la etiqueta decía "12 pts" para una diferencia
de puntos porcentuales (57.8% vs 70.3%), y el usuario lo leyó como si el
valor real fuera 0.12. El cálculo era correcto, pero la abreviatura sin
unidad explícita generaba la misma clase de ambigüedad que el eje del
gráfico sin etiquetar (ver entrada del eje Y, arriba): cualquier número
que mezcle escalas (fracción 0-1 vs. porcentaje 0-100 vs. "puntos") necesita
la unidad escrita en el texto, no asumida por contexto.

---

### 2026-10-21 — Un salto grande con muestra chica puede ser ruido, no señal

**Qué pasó:** la primera versión de `version_breakout.py` encontró "un
quiebre real" en Ripio: la versión 5.45.0 pasaba de 70.7% a 94.7% de
negativas. El usuario cuestionó el hallazgo apenas vio el dato de
respaldo: esa versión tenía solo **19 reseñas** — un 94.7% sobre una
muestra así (~18 de 19) puede ser una racha de mala suerte, no un cambio
real de comportamiento de usuarios.

**Cómo lo resolvimos:** dos cambios al método, no solo subir el umbral de
N:
1. Comparar **"desde la versión en adelante"** contra "antes", en vez de
   la versión sola contra el acumulado anterior. Así exige que la caída se
   sostenga en todas las versiones siguientes, no que sea un pico aislado
   de una sola versión con pocos datos.
2. Agregar un **test de proporciones de dos muestras** (scipy) y exigir
   significancia (p < 0.05) antes de reportar cualquier cosa.

Con ese cambio, el "quiebre" de Ripio dejó de aparecer — no se sostenía
en las versiones posteriores ni pasaba el test de significancia. El
sistema prefiere no afirmar nada a afirmar algo que no se puede sostener.

**Lección generalizable:** cualquier comparación de dos proporciones
(% negativas, % de churn, tasa de conversión, lo que sea) necesita un
umbral de volumen **y** un test de significancia antes de presentarse como
un hecho — un umbral de volumen por sí solo (ej. "al menos 15 reseñas")
es arbitrario y no dice si la diferencia observada es distinguible de
azar. Cuando el objetivo del hallazgo es ser citable y defendible ante
alguien que lo va a cuestionar (un CEO, en este caso), el criterio de
"¿me animo a decir esto con un número específico de 2 decimales?" tiene
que estar respaldado por el mismo rigor que un hallazgo que se publicaría
en cualquier otro contexto donde importa la precisión.

---

## 03 — Modeling (cont.)

### 2026-10-21 — 37 tópicos era ruido: fusionar los parecidos con `nr_topics="auto"`

**Qué pasó:** el usuario notó que 37 tópicos para Ripio era demasiado —
varios eran variantes casi idénticas del mismo elogio genérico ("excelente
aplicación", "buena aplicación", "muy buena aplicación"...) o del mismo
problema de login, solo separados porque HDBSCAN los veía como clusters
distintos en el espacio de embeddings.

**Cómo lo resolvimos:** se agregó `nr_topics="auto"` a la construcción de
`BERTopic` en `03_modeling/model.py`. Es un mecanismo nativo de la
librería: después de clusterizar, fusiona los tópicos cuya representación
de palabras clave (c-TF-IDF) es más parecida entre sí, de forma iterativa,
hasta que no quede ningún par "demasiado similar". No hay que elegir un
número fijo de tópicos a mano.

Con Ripio bajó de 37 a 18 tópicos (17 reales + el outlier `-1`), y los
hallazgos quedaron más representativos: "Reclamos de dinero/transferencias
sin respuesta de soporte" pasó a ser un solo tópico de 952 reseñas en vez
de estar repartido en varias variantes chicas.

**Lección generalizable:** en clustering no supervisado, "cuántos grupos
salieron" no es solo función de los datos — depende de los hiperparámetros
del algoritmo de clustering (acá, `min_cluster_size`/`min_topic_size` de
HDBSCAN). Cuando el resultado tiene muchos grupos casi idénticos
semánticamente, el síntoma no es "hacen falta más reglas de negocio para
unirlos a mano" — es que el paso de fusión posterior (que casi todas las
librerías de topic modeling ofrecen) no se está usando. Revisar esa opción
antes de construir lógica de deduplicación manual.

### 2026-10-23 — Categorías de tópicos ad hoc por empresa: "Dinero" mezclaba cuatro cosas distintas

**Qué pasó:** `topics_enrich.py` le pedía a Claude inventar categorías
libres por empresa ("una palabra, raíz cuadrada del número de tópicos").
En Belo, "Dinero" terminó agrupando pagos que se descuentan sin
acreditarse (falla de confianza/seguridad), problemas de emisión de
tarjeta, operatoria con pesos argentinos (transacción normal) y elogios
genéricos a pagar con la app — cuatro preguntas distintas bajo un mismo
label. El usuario lo notó mirando el dashboard. Al revisar Ripio (análisis
previo, mismo mecanismo) tenía el mismo problema: su "Dinero" mezclaba
"depósito no se acredita, sin respuesta de soporte" (confianza/seguridad)
con "compra de cripto rechazada" (operatoria) y "satisfacción con la
tarjeta" (producto).

**Por qué pasaba:** sin una lista fija, cada corrida de `topics_enrich.py`
resuelve la taxonomía desde cero, sin memoria de cómo se categorizó la
empresa anterior — el label "Dinero" es intuitivo pero en realidad mezcla
dos ejes ("qué tan grave/urgente es" vs. "qué parte del producto está en
juego"), que es justo el anti-patrón de "un campo de categorización = un
solo eje" ya documentado en el playbook de datos para fuentes en prosa.

**Cómo lo resolvimos:** `common/categories.py` define una taxonomía FIJA
y compartida entre todas las empresas, un solo eje ("¿qué área funcional
del producto está en juego?"). Primera versión: 10 categorías finas
(Acceso, Transacciones, Tarjeta, Cripto/Cambio, Costos, Seguridad,
Soporte, Rendimiento, Usabilidad, Otros). El usuario la simplificó a 6
(Acceso, Pagos, Comisiones, Interfaz, Soporte, Otros) — fusiona
Transacciones/Tarjeta/Cripto/Seguridad en "Pagos" y Rendimiento/Usabilidad
en "Interfaz" — más legible en el bubble chart a costa de perder alguna
distinción fina (ej. "Seguridad" ya no resalta aparte de una demora común
de transferencia; la severidad/recomendación de cada tópico individual
sigue capturando esa diferencia, solo que no en el agrupado visual).
`topics_enrich.py` instruye usar esta lista en vez de inventar una por
empresa, y `merge` imprime un WARNING si aparece una categoría fuera de
la allowlist. Se recategorizaron Belo y Ripio con la taxonomía final.

**Lección generalizable:** un campo de categorización no es solo "una
palabra corta que agrupe"; tiene que responder una sola pregunta de forma
consistente. Cuando ese campo se re-genera por un LLM en cada corrida sin
una lista fija como ancla, el riesgo no es solo inconsistencia de nombres
entre corridas (ej. "Dinero" una vez, "Pagos" la próxima) — es mezclar
ejes distintos dentro de una misma corrida, porque nada obliga a chequear
contra una pregunta fija. La solución es la misma que en Arquetipo C
(fuente en prosa): un enum cerrado y documentado en código cuando el
campo se usa para agrupar/comparar (acá, el bubble chart del dashboard),
no una convención de texto libre regenerada cada vez.

### 2026-10-23 — `min_topic_size` fijo por tamaño de corpus no alcanza: Lemon Cash dio 82 tópicos

**Qué pasó:** `min_topic_size_for(n)` escala el umbral hacia abajo para
corpus chicos pero tiene un techo fijo (`MIN_TOPIC_SIZE_DEFAULT=20`) para
cualquier corpus de más de 200 reseñas — el mismo valor que le vino bien a
Ripio (12098 reseñas → 18 tópicos) y Belo (6930 → 11). Con Lemon Cash
(15917 reseñas, más features: cripto, cashback, tarjeta, transferencias
internacionales) ese mismo `min_topic_size=20` dio 82 tópicos no-outlier,
puro ruido con variantes casi idénticas (ej. "código SMS no llega" /
"video de verificación falla" / "validando identidad" / "recuperar clave"
repartidos en 4+ tópicos separados que eran, en esencia, el mismo
problema de acceso).

**Por qué pasaba:** el número de tópicos no es función solo del tamaño
del corpus — depende de cuán diversa es la temática real. Un umbral fijo
calibrado contra 1-2 casos previos no generaliza a una empresa con más
líneas de producto. Subir `min_topic_size` a mano por empresa (como se
hizo una vez con Ripio) no escala: hay que probarlo cada vez.

**Cómo lo resolvimos:** en `04_modeling/model.py`, después de fitear
BERTopic con el `min_topic_size` calculado, si el resultado supera
`MAX_TOPICS=30` tópicos no-outlier, se duplica `min_topic_size` y se
reintenta (hasta `MIN_TOPIC_SIZE_MAX_RETRIES=4` veces). Con Lemon Cash,
un solo reintento (20→40) bajó de 82 a 29 tópicos — dentro del límite,
sin tocar código a mano por empresa.

**Lección generalizable:** cuando un hiperparámetro de clustering se
calibra contra el tamaño de la entrada pero el resultado real depende de
otra variable que no se puede medir de antemano (acá, la diversidad
temática del corpus), la solución robusta es un **reintento adaptativo
con criterio de parada explícito** (acá, un techo de tópicos), no afinar
el valor a mano la primera vez que falla ni subir el default global sin
verificar que sigue andando bien en los casos que ya funcionaban.

### 2026-10-23 — "Otros" mezclaba satisfacción general real con ruido sin contenido, y la taxonomía era universal en vez de por rubro

**Qué pasó:** revisando las 5 empresas ya categorizadas con la taxonomía
de 6 categorías (ver entrada anterior), "Otros" resultó ser el segundo o
tercer bucket más grande en casi todas (1.5%–25% del volumen) — no por
ser poco frecuente, sino porque ahí caía cualquier elogio o queja sin una
función específica ("buena experiencia general", "el mejor exchange",
"funciona bien"). Eso diluye el bubble chart: "Otros" termina siendo una
burbuja grande que no dice nada. Peor, el mismo tipo de contenido caía en
categorías distintas según la corrida: en Belo, el tópico dominante
(4217 reseñas, 81% negativas, la propia descripción decía "sin función
específica") había quedado forzado en "Acceso" solo porque mencionaba de
paso "bloqueos de cuenta" — eso hacía ver a Belo con un problema de
Acceso del 70% cuando el acceso puntual era en realidad <1%. Ripio tenía
el mismo patrón (tópico "errores genéricos, no funciona nada" en
Acceso) y un caso de inconsistencia interna: "lentitud en depósitos y
retiros" en Interfaz mientras tópicos gemelos de demoras de transferencia
estaban en Pagos. Además, la taxonomía estaba escrita como un único eje
universal para "todas las empresas", pero en realidad solo tiene sentido
dentro de un mismo rubro (fintech) — una app de agrotech no tiene
"Comisiones" ni "tarjeta física/virtual" como áreas funcionales.

**Cómo lo resolvimos:** en `common/categories.py`, 1) `CATEGORIES_BY_DOMAIN`
pasa a ser un dict por rubro (hoy solo `"fintech"`) en vez de una lista
plana, para no forzar los tópicos de un rubro nuevo a encajar en la lista
de otro; 2) dentro de fintech, "Otros" se separó en dos: **"General"**
(sentimiento claro —positivo o negativo— sobre la app/marca en su
conjunto, sin función específica: lealtad, recomendación, "no funciona
nada") y **"Ruido"** (ni siquiera se entiende el tema o el sentimiento:
texto ilegible, rating condicionado sin desarrollar). Se recategorizaron
a mano los tópicos ya nombrados de las 5 empresas con este criterio
(incluida la corrección de Belo/Ripio de arriba) y se regeneraron
`topics_summary.csv` y los sitios con `topics_enrich.py merge` +
`dashboard.py`.

**Lección generalizable:** un bucket catch-all ("Otros", "Varios",
"General") suele estar mezclando dos preguntas distintas sin que nadie lo
note hasta que se mide el volumen que absorbe: "no tengo una categoría
para esto" (señal real que falta un bucket) vs. "no hay nada que
categorizar" (ruido genuino). Si el catch-all es grande, vale la pena
abrirlo y mirar qué hay adentro antes de asumir que "no es accionable
por definición" — y una taxonomía "fija y compartida" solo es válida
dentro del universo donde el eje tiene sentido (un rubro), nunca across
dominios con estructuras funcionales distintas.

### 2026-10-23 — `nr_topics="auto"` fusionó el 60% de Belo en un solo tópico

**Qué pasó:** revisando el tamaño de los tópicos de Belo (a raíz de la
reclasificación de categorías de la entrada anterior), el tópico 0
("quejas generales") tenía 4217 de 6930 reseñas — 60.9% de todo el
corpus, 76% del no-outlier. Eso no es un tema, es que el modelo no separó
nada: mezclaba actualizaciones, bloqueos de cuenta y demoras en un solo
cluster. Comparando con las otras empresas, el tópico más grande de cada
una estaba entre 5.8% (Ripio) y 18.7% (Balanz) — Belo era un outlier
claro.

**Por qué pasaba:** `nr_topics="auto"` (agregado en la entrada del
2026-10-21 para fusionar variantes casi idénticas en Lemon Cash) decide
cuánto fusionar según una similitud fija entre tópicos, no según un
objetivo de cantidad ni de balance de tamaños — y es errático en ambas
direcciones. Se comprobó con un experimento controlado (mismo texto y
embeddings, reusados desde `reviews_enriched.parquet` para no recalcular
sentiment): sin fusión automática, Belo daba 42-48 tópicos con el más
grande en 12-20% del corpus (saludable); con `nr_topics="auto"`, fusionó
hasta solo 14 tópicos con uno absorbiendo 55% (en otra corrida, el 76%
ya visto en producción). Reducir a un número fijo tampoco es monótono:
probando `reduce_topics(nr_topics=N)` sobre el mismo fit crudo, N=30 dio
13.6% de tópico más grande, N=25 dio 62.3%, N=20 dio 25.2%, N=15 dio
17.7% — la fusión jerárquica puede saltar a un mega-merge en un nivel de
corte y no en el vecino, sin que el tamaño del corpus lo explique.
Ripio, en paralelo, mostraba el síntoma opuesto: varios tópicos
casi-duplicados sin fusionar (ver sus propias recomendaciones: "consolidar
con el tópico 17/18/10/15/21") — "auto" tampoco fusionaba lo que sí
debía.

**Cómo lo resolvimos:** en `04_modeling/model.py`, se reemplazó
`nr_topics="auto"` por una reducción controlada: ajustar sin fusión, y
solo si el resultado natural supera `MAX_TOPICS` (30), reducir con
`reduce_topics(nr_topics=MAX_TOPICS)` — un objetivo explícito, no una
decisión heurística de "hasta dónde fusionar". Se agregó además
`MAX_TOPIC_SHARE=0.35`: si el tópico más grande supera esa fracción del
corpus no-outlier (señal de que el ajuste no separó bien, igual que
demasiados tópicos), se duplica `min_topic_size` y se reintenta con el
mismo mecanismo de reintentos que ya existía. Validado con un
experimento sobre las 4 empresas con datos cacheados: las 4 convergieron
a 29 tópicos con el más grande entre 13-16.6%, sin necesitar reintentos.
Se re-corrió el pipeline completo para Belo (quedó en 29 tópicos, el más
grande en 8.5%) y se renombraron sus tópicos desde cero.

**Lección generalizable:** un parámetro que "fusiona lo parecido" según
un umbral de similitud fijo optimiza para una sola forma de fallar
(demasiados tópicos casi-duplicados) y puede fallar silenciosamente en
la forma opuesta (fusionar temas realmente distintos en un mega-tópico)
sin que nada lo señale, porque el chequeo de calidad que ya existía
(`n_topics <= MAX_TOPICS`) no mide balance de tamaños, solo cantidad. Si
el objetivo real tiene dos formas de fallar, el chequeo de calidad tiene
que cubrir las dos — acá, además de "no demasiados tópicos" hacía falta
"ningún tópico demasiado grande". Y cuando un heurístico de "auto"
decide algo no controlable por el caller (cuánto fusionar), preferir un
objetivo explícito y verificable (reducir a N exacto) sobre confiar en
que el heurístico generalice a corpus distintos.

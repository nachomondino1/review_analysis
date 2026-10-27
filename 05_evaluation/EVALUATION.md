# Evaluation

Fase 5 de CRISP-DM. Tampoco tiene scripts propios: a diferencia de las fases
anteriores, estas 3 tareas son juicio humano sobre los resultados de
`04_modeling/`, no cálculos — no hay nada que un script pueda decidir solo.
Se responde esto **antes de correr `06_deployment/generate_site.py`** para una
empresa.

## 5.1 Evaluate results

¿Los hallazgos cumplen el criterio de negocio de `01_business_understanding`
("al menos 1 hallazgo accionable con volumen/severidad suficientes")?
Chequear con los números que ya imprime `04_modeling/analyze_sentiment_topics.py`:

- **`% outliers`** (tópico `-1` de BERTopic): si es muy alto, el modelo no
  separó bien el corpus — desconfiar de los tópicos que sí formó.
- **`% sentiment_mismatch`**: si es muy alto, el sentimiento calculado no es
  confiable como está (puede ser un corpus con mucho sarcasmo, o un corpus
  chico donde cualquier discrepancia pesa mucho).
- **Volumen por tópico**: un tópico con pocas reseñas no es un hallazgo, es
  ruido — `topics_enrich.py` ya prioriza por severidad (volumen × % negativas)
  antes de nombrarlos, pero el volumen absoluto hay que mirarlo igual.
- **`version_breakout.py`**: si no encontró nada, no forzar un hallazgo ahí —
  "no hay quiebre de versión" es un resultado válido, no una falla.

No hay un umbral fijo documentado todavía para "alto" en los dos primeros —
se evalúa caso a caso, comparando contra los análisis previos (Beelup,
Ripio) como referencia.

## 5.2 Review process

¿Se corrieron todas las fases en orden, sin saltos? ¿Se usaron los datos de
la fuente correcta (`store_ratings` para el rating oficial, no la muestra de
texto, para no repetir el error de `[[project_review_sampling_bias]]`)?
¿Algún paso dio un resultado raro que se ignoró en vez de investigarse?

Ejemplo real de esta tarea ya aplicada (no hipotético): `version_breakout.py`
encontró un salto grande en Ripio (Android v5.45.0, +24 pts) con solo 19
reseñas de esa versión; se cuestionó la muestra y, con el método corregido
(exigir persistencia + significancia), el salto no se sostuvo. Ver
`APRENDIZAJES.md`, 2026-10-21.

## 5.3 Determine next steps

Con 5.1 y 5.2 resueltos, decidir una de tres:

- **Deploy**: correr `06_deployment/generate_site.py` y publicar.
- **Iterar**: volver a una fase anterior (ej. ajustar `min_topic_size`,
  revisar `clean_reviews.py`, pedir más volumen de reseñas) antes de publicar.
- **Nuevo proyecto/análisis**: la empresa no tiene suficiente volumen de
  reseñas con texto para un análisis serio (ver `describe_data.py` de
  `02_data_understanding`) — documentarlo y no forzar un entregable vacío.

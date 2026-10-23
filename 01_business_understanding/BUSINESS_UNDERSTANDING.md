# Business Understanding

Fase 1 de CRISP-DM. No tiene scripts propios: es el marco que justifica las
decisiones técnicas de las fases siguientes — se lee antes de tocar código,
no se genera corriendo nada.

## 1.1 Determine business objectives

Dado el nombre/ids de una app, producir un **análisis accionable de sus
reseñas** y entregarlo como una **web compartible por link** (no un CSV ni un
notebook) para mandarle a un founder/CEO.

El objetivo de negocio de fondo (de quien construye este pipeline, no de la
empresa analizada) es **conseguir trabajo mostrando trabajo real**: el
criterio de éxito no es solo técnico, es que el output se vea profesional y
diga algo que el founder no sabía, al primer vistazo, sin que se lo tengan
que explicar.

## 1.2 Assess situation

- **Datos disponibles:** reseñas públicas de App Store y Google Play
  (scrapeables sin acceso privilegiado) + rating oficial agregado de cada
  tienda (público, vía APIs). No hay acceso a datos internos de la empresa
  (tickets de soporte, NPS, analytics de producto) — el análisis se arma
  100% a partir de lo que cualquiera puede ver desde afuera.
- **Restricción conocida y crítica:** el scraping solo puede leer reseñas con
  **texto escrito**, una muestra sesgada hacia quejas (quien solo califica
  con estrellas y no escribe nunca, que es la mayoría, no entra). Mostrarle a
  un CEO un % de negativas de la muestra como si fuera la satisfacción real
  del público sería un error de credibilidad grave — ver nota de metodología
  en el [README](../README.md) y [[project_review_sampling_bias]] en memoria.
- **Recursos:** sin presupuesto para APIs pagas (no hay API key de Anthropic
  disponible); el nombrado de tópicos se hace con un LLM en una sesión de
  Claude Code, no vía API automatizada.
- **Riesgo principal:** sacar conclusiones de muestras chicas (ej. "se rompió
  en la v5.45.0" con 19 reseñas de esa versión) — ya pasó una vez y no se
  sostuvo con un test de significancia (ver `APRENDIZAJES.md`, 2026-10-21).
- **Riesgo de defensibilidad del valor:** un análisis de reseñas públicas con
  sentimiento + tópicos es, hoy, algo que el propio founder podría pedirle a
  un LLM y tener en pocos minutos — el pipeline en sí no es la parte
  defendible del trabajo. Lo que no es trivialmente reproducible, y por
  ende donde está el valor real frente al CEO, es: 1) el control de sesgo de
  muestreo (comparar rating oficial vs. muestra de texto, en vez de reportar
  el segundo como si fuera el primero), 2) exigir persistencia +
  significancia estadística antes de afirmar un quiebre de versión (evita el
  falso positivo que ya pasó con Ripio), y 3) el entregable pulido y
  compartible por link, no un volcado de un prompt. Si el análisis no deja
  esto explícito (metodología visible, no solo el resultado), pierde su
  argumento de por qué pagar por él en vez de pedírselo a un LLM.

## 1.3 Determine data mining goals

Traducción técnica del objetivo de negocio:

1. **Clasificar sentimiento** de cada reseña (positivo/negativo/neutro).
2. **Agrupar en tópicos** las reseñas para encontrar patrones de queja/elogio
   recurrentes, sin que un humano tenga que leer cientos de reseñas sueltas.
3. **Priorizar** esos tópicos por severidad (volumen × % de negativas), no
   mostrar una lista plana.
4. **Detectar tendencia temporal** y, si existe, un quiebre de % de negativas
   atado a una versión específica — con significancia estadística exigida
   antes de reportarlo como un hecho.
5. Criterio de éxito medible por análisis: **al menos 1 hallazgo accionable
   con volumen y severidad suficientes** para justificar la web (si no hay
   ningún hallazgo real, no tiene sentido generar el entregable — ver
   `05_evaluation/`).

## 1.4 Produce project plan

Ver [PLAN.md](../PLAN.md) para la hoja de ruta completa (fases, qué está
hecho y qué falta) y [APRENDIZAJES.md](../APRENDIZAJES.md) para los
sesgos/bugs no obvios ya encontrados. El pipeline en sí (fases 02-06 de este
repo) es la implementación de ese plan.

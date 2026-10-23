# 02 — Data preparation

`integrate_data.py`: integra las 3 fuentes de `01_data_understanding` (ios_reviews, android_reviews, store_ratings) en un solo dataset por empresa, con una columna `fuente` que identifica de dónde vino cada fila. Escribe `data/<empresa>/02_data_preparation/integrated_<empresa>.parquet`.

```bash
python 02_data_preparation/integrate_data.py --name <empresa>
```

`clean_reviews.py`: filtra reseñas sin señal real (muy cortas, tipo "buena app") antes de modelar, sobre el dataset integrado. Escribe `data/<empresa>/02_data_preparation/reviews_clean.parquet`.

```bash
python 02_data_preparation/clean_reviews.py --name <empresa>
```

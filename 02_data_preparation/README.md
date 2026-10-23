# 02 — Data preparation

`integrate_data.py`: integra las fuentes de reseñas con texto de `01_data_understanding` (ios_reviews, android_reviews) en un solo dataset por empresa; la columna `store` que ya traen ambas (ios/android) identifica el origen de cada fila, sin agregar una columna redundante. `store_ratings` queda afuera: es una fila por tienda (rating agregado), otra unidad de análisis — se consume directo desde su propio JSON. Escribe `data/<empresa>/02_data_preparation/integrated_<empresa>.parquet`.

```bash
python 02_data_preparation/integrate_data.py --name <empresa>
```

`clean_reviews.py`: filtra reseñas sin señal real (muy cortas, tipo "buena app") antes de modelar, sobre el dataset integrado. Escribe `data/<empresa>/02_data_preparation/reviews_clean.parquet`.

```bash
python 02_data_preparation/clean_reviews.py --name <empresa>
```

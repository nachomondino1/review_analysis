# 02 — Data preparation

`clean_reviews.py`: filtra reseñas sin señal real (muy cortas, tipo "buena app") antes de modelar. Lee `data/<empresa>/reviews.parquet` y escribe `data/<empresa>/reviews_clean.parquet`.

```bash
python 02_data_preparation/clean_reviews.py --name <empresa>
```

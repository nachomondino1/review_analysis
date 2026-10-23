"""
Construye/deriva variables nuevas a partir del dataset integrado (tarea de
"Construct Data" de CRISP-DM): no limpia ni filtra nada, solo agrega
columnas calculadas a partir de las que ya existen.

Variables derivadas:
  - month: "YYYY-MM" de la fecha de la reseña. Varios scripts de 04_evaluation
    necesitan agrupar por mes; calcularlo una sola vez acá evita repetir la
    misma conversión de timezone en cada script.
  - text_length: cantidad de caracteres del texto. clean_reviews.py ya lo
    necesitaba para filtrar reseñas sin señal real, pero lo recalculaba y
    descartaba; ahora queda como columna, disponible para analizar (ej.
    ¿las reseñas más largas tienden a ser más negativas?).
  - rating_bucket: positiva (4-5) / neutra (3) / negativa (1-2), derivado
    directo de las estrellas. Es un "sentimiento barato" independiente del
    modelo NLP de 03_modeling — sirve de chequeo cruzado: si rating_bucket
    y el sentiment del modelo discrepan mucho en una reseña, es una señal
    rara (texto sarcástico, rating mal puesto) que hoy no se detecta.

Uso: python 02_data_preparation/construct_data.py --name <empresa>
Lee data/<empresa>/02_data_preparation/integrated_<empresa>.parquet
Escribe data/<empresa>/02_data_preparation/constructed_<empresa>.parquet
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from config import Paths  # noqa: E402

RATING_BUCKET = {1: "negativa", 2: "negativa", 3: "neutra", 4: "positiva", 5: "positiva"}


def construct(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["month"] = df["date"].dt.tz_convert("UTC").dt.strftime("%Y-%m")
    df["text_length"] = df["text"].str.len()
    df["rating_bucket"] = df["rating"].map(RATING_BUCKET)
    return df


def run(paths: Paths) -> pd.DataFrame:
    df = pd.read_parquet(paths.integrated)
    df = construct(df)
    paths.ensure_dirs()
    df.to_parquet(paths.constructed)
    print(f"{len(df)} filas con variables derivadas -> {paths.constructed.resolve()}")
    return df


def parse_args():
    p = argparse.ArgumentParser(description="Deriva variables nuevas (month, text_length, rating_bucket) sobre el dataset integrado.")
    p.add_argument("--name", required=True, help="Nombre de la empresa/app")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(Paths(args.name))

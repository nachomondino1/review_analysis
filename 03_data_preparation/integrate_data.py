"""
Integra las fuentes de reseñas con texto de 02_data_understanding
(ios_reviews, android_reviews) en un único dataset. No agrega una columna
identificadora de fuente propia: la columna "store" (ios/android), que ya
viene en ambos archivos, identifica el origen de cada fila sin duplicarla.

store_ratings queda afuera a propósito: es una fila por tienda con el rating
oficial agregado sobre TODAS las calificaciones, una unidad de análisis
distinta a una fila por reseña con texto. Integrarlo en el mismo dataset
mezclaría dos granos distintos en una sola tabla (ver DECISIONS/APRENDIZAJES
sobre el sesgo de la muestra con texto vs. el rating oficial) — se consume
por separado, directo desde store_ratings_<empresa>.json.

Uso: python 03_data_preparation/integrate_data.py --name <empresa>
Escribe data/<empresa>/03_data_preparation/integrated_<empresa>.parquet
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from config import Paths  # noqa: E402


def load_reviews_source(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def integrate(paths: Paths) -> pd.DataFrame:
    parts = [
        load_reviews_source(paths.ios_reviews),
        load_reviews_source(paths.android_reviews),
    ]
    parts = [p for p in parts if not p.empty]
    if not parts:
        raise SystemExit("Ni ios_reviews ni android_reviews existen todavía. Correr los collect_*_reviews.py primero.")

    df = pd.concat(parts, ignore_index=True)
    return df


def parse_args():
    p = argparse.ArgumentParser(description="Integra las fuentes de reseñas con texto de una empresa en un solo dataset.")
    p.add_argument("--name", required=True, help="Nombre de la empresa/app")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    paths = Paths(args.name)
    paths.ensure_dirs()

    df = integrate(paths)
    df.to_parquet(paths.integrated)

    print(df.groupby("store").size())
    print(f"{len(df)} filas integradas -> {paths.integrated.resolve()}")

"""
Integra las 3 fuentes de 01_data_understanding (ios_reviews, android_reviews,
store_ratings) en un único dataset, con una columna "fuente" que identifica
de dónde vino cada fila.

Las fuentes tienen grano distinto a propósito: ios_reviews/android_reviews
son una fila por reseña con texto (sesgadas hacia quejas); store_ratings es
una fila por tienda con el rating oficial agregado sobre TODAS las
calificaciones. Integrarlas no borra esa diferencia: la columna "fuente"
deja filtrar por grano después (ver DECISIONS/APRENDIZAJES sobre el sesgo de
la muestra con texto vs. el rating oficial).

Uso: python 02_data_preparation/integrate_data.py --name <empresa>
Escribe data/<empresa>/02_data_preparation/integrated_<empresa>.parquet
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from config import Paths  # noqa: E402


def load_reviews_source(path: Path, fuente: str) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(path)
    df["fuente"] = fuente
    return df


def load_store_ratings_source(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    data = json.loads(path.read_text())
    rows = []
    for store, stats in data.items():
        rows.append({
            "fuente": "store_ratings",
            "store": store,
            "score": stats.get("score"),
            "ratings_count": stats.get("ratings_count"),
        })
    return pd.DataFrame(rows)


def integrate(paths: Paths) -> pd.DataFrame:
    parts = [
        load_reviews_source(paths.ios_reviews, "ios_reviews"),
        load_reviews_source(paths.android_reviews, "android_reviews"),
        load_store_ratings_source(paths.store_ratings_json),
    ]
    parts = [p for p in parts if not p.empty]
    if not parts:
        raise SystemExit("Ninguna de las 3 fuentes existe todavía. Correr los collect_*.py primero.")

    # outer concat a propósito: cada fuente trae columnas distintas (review_id,
    # text, version vs. score, ratings_count) y las que no aplican a una fila
    # quedan NaN, sin forzar un esquema común que no existe en el dominio.
    df = pd.concat(parts, ignore_index=True)
    return df


def parse_args():
    p = argparse.ArgumentParser(description="Integra las 3 fuentes de datos de una empresa en un solo dataset.")
    p.add_argument("--name", required=True, help="Nombre de la empresa/app")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    paths = Paths(args.name)
    paths.ensure_dirs()

    df = integrate(paths)
    df.to_parquet(paths.integrated)

    print(df.groupby("fuente").size())
    print(f"{len(df)} filas integradas -> {paths.integrated.resolve()}")

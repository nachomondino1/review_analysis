"""
Filtra reseñas sin señal real (muy cortas, tipo "buena app") antes de modelar.
Corre sobre el dataset integrado (integrate_data.py): ios_reviews + android_reviews.
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from config import Paths  # noqa: E402

MIN_LEN = 15


def run(paths: Paths) -> pd.DataFrame:
    df = pd.read_parquet(paths.integrated)
    df = df[df["text"].str.len() > MIN_LEN].copy()
    paths.ensure_dirs()
    df.to_parquet(paths.reviews_clean)
    print(f"{len(df)} reseñas limpias -> {paths.reviews_clean.resolve()}")
    return df


def parse_args():
    p = argparse.ArgumentParser(description="Filtra reseñas sin señal real antes de modelar.")
    p.add_argument("--name", required=True, help="Nombre de la empresa/app")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(Paths(args.name))

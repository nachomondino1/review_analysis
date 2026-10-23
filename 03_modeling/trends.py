"""
Tendencia temporal de sentimiento y comparación App Store vs Google Play.

Uso: python 03_modeling/trends.py --name <empresa>
Genera:
  - data/<empresa>/03_modeling/sentiment_by_month.csv   (mes, store, n, pct_neg, avg_rating)
  - data/<empresa>/03_modeling/store_comparison.csv      (store, n, avg_rating, pct_neg)
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from config import Paths  # noqa: E402


def run(paths: Paths):
    df = pd.read_parquet(paths.reviews_enriched_parquet)  # "month" ya viene de construct_data.py

    by_month = (df.groupby(["month", "store"])
                .agg(n=("text", "size"),
                     avg_rating=("rating", "mean"),
                     pct_neg=("sentiment", lambda s: (s == "NEG").mean()))
                .round(3).reset_index())
    paths.ensure_dirs()
    by_month.to_csv(paths.sentiment_by_month_csv, index=False, encoding="utf-8-sig")

    by_store = (df.groupby("store")
                .agg(n=("text", "size"),
                     avg_rating=("rating", "mean"),
                     pct_neg=("sentiment", lambda s: (s == "NEG").mean()))
                .round(3).reset_index())
    by_store.to_csv(paths.store_comparison_csv, index=False, encoding="utf-8-sig")

    print(by_month.tail(12))
    print(by_store)
    print(f"Guardado en {paths.sentiment_by_month_csv.resolve()} y {paths.store_comparison_csv.resolve()}")


def parse_args():
    p = argparse.ArgumentParser(description="Tendencia temporal de sentimiento + comparación de stores.")
    p.add_argument("--name", required=True, help="Nombre de la empresa/app")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(Paths(args.name))

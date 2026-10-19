"""
Tendencia temporal de sentimiento y comparación App Store vs Google Play.

Uso: python 04_evaluation/trends.py --name <empresa>
Genera:
  - data/<empresa>/output/sentiment_by_month.csv   (mes, store, n, pct_neg, avg_rating)
  - data/<empresa>/output/store_comparison.csv      (store, n, avg_rating, pct_neg)
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from config import Paths  # noqa: E402


def run(paths: Paths):
    df = pd.read_parquet(paths.reviews_enriched_parquet)
    df["month"] = df["date"].dt.tz_convert("UTC").dt.strftime("%Y-%m")

    by_month = (df.groupby(["month", "store"])
                .agg(n=("text", "size"),
                     avg_rating=("rating", "mean"),
                     pct_neg=("sentiment", lambda s: (s == "NEG").mean()))
                .round(3).reset_index())
    by_month_path = paths.output_dir / "sentiment_by_month.csv"
    by_month.to_csv(by_month_path, index=False, encoding="utf-8-sig")

    by_store = (df.groupby("store")
                .agg(n=("text", "size"),
                     avg_rating=("rating", "mean"),
                     pct_neg=("sentiment", lambda s: (s == "NEG").mean()))
                .round(3).reset_index())
    by_store_path = paths.output_dir / "store_comparison.csv"
    by_store.to_csv(by_store_path, index=False, encoding="utf-8-sig")

    print(by_month.tail(12))
    print(by_store)
    print(f"Guardado en {by_month_path.resolve()} y {by_store_path.resolve()}")


def parse_args():
    p = argparse.ArgumentParser(description="Tendencia temporal de sentimiento + comparación de stores.")
    p.add_argument("--name", required=True, help="Nombre de la empresa/app")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(Paths(args.name))

"""
Busca si el % de reseñas negativas tuvo un quiebre real atado a una versión
específica de la app, no solo "empeoró en los últimos meses" — permite decir
"se rompió en la v7.2" en vez de "empeoró este trimestre".

Metodología: para cada store, agrupa por versión (ordenadas por su primera
fecha vista — la fecha real de lanzamiento no está disponible por este medio,
se aproxima con la primera reseña de esa versión), y compara cada versión
contra el acumulado de TODAS las versiones anteriores. Se descartan
versiones con poco volumen propio o poca base acumulada previa, para no
reportar un quiebre que en realidad es ruido de pocas reseñas.

Uso: python 04_evaluation/version_breakout.py --name <empresa>
Genera data/<empresa>/04_evaluation/version_breakout.json
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from config import Paths  # noqa: E402

MIN_VERSION_N = 15     # reseñas de la versión candidata, para que su % no sea ruido
MIN_BEFORE_N = 30       # reseñas acumuladas previas, para que la base de comparación sea sólida
MIN_DELTA_PTS = 10      # diferencia mínima en puntos porcentuales para considerarlo un quiebre real


def find_breakout(reviews: pd.DataFrame) -> dict | None:
    candidates = []

    for store, store_df in reviews.groupby("store"):
        by_version = (store_df.groupby("version")
                      .agg(n=("text", "size"),
                           pct_neg=("sentiment", lambda s: (s == "NEG").mean()),
                           first_date=("date", "min"))
                      .sort_values("first_date"))

        cum_neg = 0
        cum_n = 0
        for version, row in by_version.iterrows():
            if cum_n >= MIN_BEFORE_N and row["n"] >= MIN_VERSION_N:
                pct_before = cum_neg / cum_n
                delta = row["pct_neg"] - pct_before  # positivo = empeoró
                candidates.append({
                    "store": store,
                    "version": str(version),
                    "release_approx": row["first_date"].strftime("%Y-%m-%d"),
                    "n_version": int(row["n"]),
                    "pct_neg_version": round(float(row["pct_neg"]) * 100, 1),
                    "pct_neg_before": round(float(pct_before) * 100, 1),
                    "n_before": int(cum_n),
                    "delta": round(float(delta) * 100, 1),
                })
            cum_neg += row["n"] * row["pct_neg"]
            cum_n += row["n"]

    if not candidates:
        return None

    worst = max(candidates, key=lambda c: c["delta"])
    if worst["delta"] < MIN_DELTA_PTS:
        return None
    return worst


def run(paths: Paths) -> dict | None:
    reviews = pd.read_parquet(paths.reviews_enriched_parquet)
    reviews = reviews.dropna(subset=["version"])
    breakout = find_breakout(reviews)
    paths.ensure_dirs()
    paths.version_breakout_json.write_text(json.dumps(breakout, ensure_ascii=False, indent=2))
    return breakout


def parse_args():
    p = argparse.ArgumentParser(description="Busca un quiebre de % negativas atado a una versión específica.")
    p.add_argument("--name", required=True, help="Nombre de la empresa/app")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    breakout = run(Paths(args.name))
    if breakout:
        print(f"Quiebre encontrado: {breakout['store']} v{breakout['version']} "
              f"({breakout['release_approx']}) — {breakout['pct_neg_before']}% -> {breakout['pct_neg_version']}% "
              f"negativas (+{breakout['delta']} pts)")
    else:
        print("No se encontró un quiebre de versión significativo (o no hay suficiente volumen por versión).")

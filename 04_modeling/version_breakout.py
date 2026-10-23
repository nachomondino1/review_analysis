"""
Busca si el % de reseñas negativas tuvo un quiebre real atado a una versión
específica de la app, no solo "empeoró en los últimos meses" — permite decir
"se rompió en la v7.2" en vez de "empeoró este trimestre".

Metodología: para cada store, agrupa por versión (ordenadas por su primera
fecha vista — la fecha real de lanzamiento no está disponible por este medio,
se aproxima con la primera reseña de esa versión). Para cada versión V
candidata compara DOS BLOQUES:
  - "antes de V": todas las reseñas con fecha anterior a la primera de V.
  - "desde V en adelante": todas las reseñas de V y de toda versión posterior.
Comparar contra "desde V en adelante" (no solo contra V sola) exige que la
caída se sostenga en las versiones siguientes, no que sea un pico aislado de
una sola versión con pocas reseñas — una versión sola con n chico puede dar
un % extremo por puro ruido de muestra.

Además, antes de reportar nada se corre un test de proporciones (dos
muestras, scipy) y se exige significancia (p < P_VALUE_MAX): con muestras
chicas, una diferencia de puntos porcentuales grande puede no ser
estadísticamente distinguible de azar, y no se quiere reportar eso como un
hecho firme.

Solo se evalúan versiones lanzadas en los últimos RECENT_WINDOW_MONTHS: con
una app de varios años de historia, comparar "las primeras semanas de la
app" contra "todo lo que vino después" da un delta grande y p-value chico
por puro desbalance de muestra (n_before chico, n_onward enorme), no porque
esa versión vieja haya roto algo — es un quiebre de versión espurio, no uno
real. Limitar a versiones recientes asegura que el hallazgo responda la
pregunta de negocio real: "¿una versión reciente rompió algo?".

Uso: python 04_modeling/version_breakout.py --name <empresa>
Genera data/<empresa>/04_modeling/version_breakout.json
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd
from scipy.stats import norm

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from config import Paths  # noqa: E402

MIN_ONWARD_N = 30       # reseñas desde la versión candidata en adelante, para que su % no sea ruido
MIN_BEFORE_N = 30       # reseñas previas, para que la base de comparación sea sólida
MIN_DELTA_PTS = 10      # diferencia mínima en puntos porcentuales para considerarlo un quiebre real
P_VALUE_MAX = 0.05      # significancia exigida al test de dos proporciones
RECENT_WINDOW_MONTHS = 18  # solo evaluar versiones lanzadas en esta ventana (ver nota abajo)


def two_proportion_test(neg1: int, n1: int, neg2: int, n2: int) -> float:
    """p-value de un test de dos proporciones (dos colas). neg/n son conteos, no fracciones."""
    p1, p2 = neg1 / n1, neg2 / n2
    p_pool = (neg1 + neg2) / (n1 + n2)
    se = (p_pool * (1 - p_pool) * (1 / n1 + 1 / n2)) ** 0.5
    if se == 0:
        return 1.0
    z = (p1 - p2) / se
    return 2 * (1 - norm.cdf(abs(z)))


def find_breakout(reviews: pd.DataFrame) -> dict | None:
    candidates = []

    for store, store_df in reviews.groupby("store"):
        by_version = (store_df.groupby("version")
                      .agg(n=("text", "size"),
                           n_neg=("sentiment", lambda s: int((s == "NEG").sum())),
                           first_date=("date", "min"))
                      .sort_values("first_date"))

        max_date = store_df["date"].max()
        recent_cutoff = max_date - pd.DateOffset(months=RECENT_WINDOW_MONTHS)

        versions = list(by_version.index)
        for i, version in enumerate(versions):
            # Solo versiones lanzadas recientemente: con apps de varios años de
            # historia, un corte en una versión vieja compara "las primeras
            # semanas de la app" contra "todo lo que vino después" — un
            # desbalance de muestra que da "significativo" por volumen, no
            # porque esa versión puntual haya roto algo (ver nota en README /
            # caso real documentado en el repo).
            if by_version.loc[version, "first_date"] < recent_cutoff:
                continue

            before = by_version.iloc[:i]
            onward = by_version.iloc[i:]
            n_before, neg_before = int(before["n"].sum()), int(before["n_neg"].sum())
            n_onward, neg_onward = int(onward["n"].sum()), int(onward["n_neg"].sum())

            if n_before < MIN_BEFORE_N or n_onward < MIN_ONWARD_N:
                continue

            pct_before = neg_before / n_before
            pct_onward = neg_onward / n_onward
            delta = pct_onward - pct_before
            if delta < MIN_DELTA_PTS / 100:
                continue

            p_value = two_proportion_test(neg_before, n_before, neg_onward, n_onward)
            if p_value >= P_VALUE_MAX:
                continue

            candidates.append({
                "store": store,
                "version": str(version),
                "release_approx": by_version.loc[version, "first_date"].strftime("%Y-%m-%d"),
                "n_onward": n_onward,
                "pct_neg_onward": round(pct_onward * 100, 1),
                "pct_neg_before": round(pct_before * 100, 1),
                "n_before": n_before,
                "delta": round(delta * 100, 1),
                "p_value": round(p_value, 4),
            })

    if not candidates:
        return None

    return max(candidates, key=lambda c: c["delta"])


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
              f"({breakout['release_approx']}) — {breakout['pct_neg_before']}% -> {breakout['pct_neg_onward']}% "
              f"negativas (+{breakout['delta']} pts, n={breakout['n_onward']}, p={breakout['p_value']})")
    else:
        print("No se encontró un quiebre de versión significativo (o no hay suficiente volumen/significancia).")

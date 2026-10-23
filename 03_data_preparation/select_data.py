"""
Tarea de "Select Data" de CRISP-DM: antes de modelar, chequea con números si
una variable derivada (construct_data.py) realmente trae señal, en vez de
asumirlo. Corre sobre el dataset construido (constructed_<empresa>.parquet).

No decide solo ("text_length entra, chau") — imprime la correlación y deja
que la lea un humano, porque "hay correlación" no siempre significa "conviene
usarla" (ej. acá el largo del texto es, en parte, un artefacto del filtro de
MIN_LEN de clean_reviews.py, no una señal 100% limpia).

Dos funciones reusables:
  - correlate_numeric(df, x, y): dos variables numéricas (ej. text_length vs
    rating). Reporta Pearson (relación lineal) y Spearman (relación
    monótona, más robusta para una ordinal como rating).
  - compare_by_group(df, numeric_col, group_col): una numérica contra una
    categórica (ej. text_length vs rating_bucket). Reporta medias/medianas
    por grupo + test de Kruskal-Wallis (no asume distribución normal; el
    largo de texto suele venir con cola larga).

Uso:
  python 03_data_preparation/select_data.py --name <empresa>
      corre el set de pares candidatos por default (ver CANDIDATE_PAIRS).
  python 03_data_preparation/select_data.py --name <empresa> --x text_length --y rating
      corre un par numérico-numérico puntual.
  python 03_data_preparation/select_data.py --name <empresa> --x text_length --group rating_bucket
      corre una comparación numérica-categórica puntual.
"""
import argparse
import sys
from pathlib import Path

import pandas as pd
from scipy.stats import kruskal, pearsonr, spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from config import Paths  # noqa: E402

# Pares que tiene sentido chequear antes de decidir qué llevar a 04_modeling.
CANDIDATE_NUMERIC_PAIRS = [("text_length", "rating")]
CANDIDATE_GROUP_PAIRS = [("text_length", "rating_bucket"), ("text_length", "store")]


def correlate_numeric(df: pd.DataFrame, x: str, y: str) -> dict:
    sub = df[[x, y]].dropna()
    r, p_pearson = pearsonr(sub[x], sub[y])
    rho, p_spearman = spearmanr(sub[x], sub[y])
    return {
        "x": x, "y": y, "n": len(sub),
        "pearson_r": round(r, 3), "pearson_p": round(p_pearson, 4),
        "spearman_rho": round(rho, 3), "spearman_p": round(p_spearman, 4),
    }


def compare_by_group(df: pd.DataFrame, numeric_col: str, group_col: str) -> dict:
    sub = df[[numeric_col, group_col]].dropna()
    groups = [g[numeric_col].values for _, g in sub.groupby(group_col)]
    stat, p = kruskal(*groups) if len(groups) > 1 else (None, None)
    by_group = (sub.groupby(group_col)[numeric_col]
                .agg(n="size", media="mean", mediana="median")
                .round(1).to_dict(orient="index"))
    return {
        "numeric_col": numeric_col, "group_col": group_col,
        "by_group": by_group,
        "kruskal_stat": round(stat, 2) if stat is not None else None,
        "kruskal_p": round(p, 4) if p is not None else None,
    }


def interpret_p(p: float) -> str:
    return "diferencia significativa (p < 0.05)" if p is not None and p < 0.05 else "sin diferencia significativa"


def print_numeric_result(res: dict):
    print(f"\n{res['x']} vs {res['y']} (n={res['n']})")
    print(f"  Pearson:  r={res['pearson_r']} (p={res['pearson_p']})")
    print(f"  Spearman: rho={res['spearman_rho']} (p={res['spearman_p']})")
    print(f"  -> {interpret_p(res['pearson_p'])}")


def print_group_result(res: dict):
    print(f"\n{res['numeric_col']} por {res['group_col']}:")
    for group, stats in res["by_group"].items():
        print(f"  {group}: n={int(stats['n'])}, media={stats['media']}, mediana={stats['mediana']}")
    print(f"  Kruskal-Wallis: H={res['kruskal_stat']} (p={res['kruskal_p']}) -> {interpret_p(res['kruskal_p'])}")


def parse_args():
    p = argparse.ArgumentParser(description="Correlaciona variables del dataset construido, para decidir qué llevar a 04_modeling.")
    p.add_argument("--name", required=True, help="Nombre de la empresa/app")
    p.add_argument("--x", default=None, help="Variable numérica (ej. text_length). Si se omite, corre los pares candidatos por default.")
    p.add_argument("--y", default=None, help="Otra variable numérica, para correlacionar con --x")
    p.add_argument("--group", default=None, help="Variable categórica (ej. rating_bucket, store), para comparar --x por grupo")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    paths = Paths(args.name)
    df = pd.read_parquet(paths.constructed)

    if args.x and args.y:
        print_numeric_result(correlate_numeric(df, args.x, args.y))
    elif args.x and args.group:
        print_group_result(compare_by_group(df, args.x, args.group))
    elif args.x:
        raise SystemExit("Con --x hace falta también --y (numérica-numérica) o --group (numérica-categórica).")
    else:
        print(f"=== {args.name}: pares candidatos por default ===")
        for x, y in CANDIDATE_NUMERIC_PAIRS:
            print_numeric_result(correlate_numeric(df, x, y))
        for x, group in CANDIDATE_GROUP_PAIRS:
            print_group_result(compare_by_group(df, x, group))

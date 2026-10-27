"""
Recalcula, por TÓPICO, a partir de review_audit.csv (una fila por oración —
ver 05_export_review_audit.py):
  - n: cuántas reseñas DISTINTAS mencionan el tópico (no cuántas oraciones:
    una reseña con 3 oraciones sobre lo mismo cuenta 1 vez).
  - pct_neg: % de esas MENCIONES (oraciones) que son negativas — más preciso
    que el % de la reseña entera, porque una reseña puede hablar bien de un
    tema y mal de otro en la misma reseña.
  - rating: promedio de estrellas de esas mismas reseñas.
  - avg_confidence: confianza promedio del modelo en el sentimiento de esas
    oraciones — un tópico con pct_neg alto pero confianza baja es una señal
    a tomar con pinzas, no un hallazgo sólido.

Reemplaza a 02_refine_topic_sentiment.py: ese script agrupaba TODAS las
oraciones de las reseñas que BERTopic puso en un tópico (blanket), mientras
que acá cada oración ya viene atribuida a su tópico específico por keywords
(ver 05_export_review_audit.py) — más preciso cuando una reseña toca varios
temas. El resumen por categoría en el sitio (generate_site.py) no necesita
tocarse: ya suma estos valores por tópico agrupando por su columna
"category".

Escribe n/pct_neg/rating/avg_confidence en topics_summary.csv, por tópico
(join vía la columna "topic"). No toca name/summary/severity/recommendation
ni category — esos siguen viniendo de topics_named.json (03_topics_enrich.py).

Uso: python 04_modeling/topics/06_summarize_category_sentiment.py --name <empresa>
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "common"))
from config import Paths  # noqa: E402


def run(paths: Paths):
    if not paths.review_audit_csv.exists():
        raise SystemExit(f"No existe {paths.review_audit_csv} — correr primero 05_export_review_audit.py.")

    audit = pd.read_csv(paths.review_audit_csv)
    audit = audit[audit["topic"].notna() & (audit["topic"] != "")]
    if audit.empty:
        raise SystemExit("review_audit.csv no tiene ninguna oración clasificada en un tópico.")
    audit["topic"] = audit["topic"].astype(int)

    reviews = pd.read_parquet(paths.reviews_enriched_parquet).set_index("review_id")["rating"]

    agg = audit.groupby("topic").agg(
        n=("review_id", "nunique"),
        pct_neg=("sentence_sentiment", lambda s: (s == "NEG").mean()),
        avg_confidence=("sentence_confidence", "mean"),
    ).round(6)
    # rating también recalculado sobre las reseñas que efectivamente mencionan
    # el tópico (antes podía quedar desactualizado si "n" cambió acá).
    agg["rating"] = audit.groupby("topic")["review_id"].apply(
        lambda ids: round(float(reviews.loc[ids.unique()].mean()), 2)
    )

    summary = pd.read_csv(paths.topics_summary_csv)
    if "avg_confidence" not in summary.columns:
        summary["avg_confidence"] = pd.NA

    print("Tópico -> n reseñas, % negativas, rating, confianza promedio (antes -> después):")
    for topic, row in agg.iterrows():
        mask = summary["topic"] == topic
        if not mask.any():
            continue
        name = summary.loc[mask, "name"].iloc[0] if "name" in summary.columns else ""
        before_n = summary.loc[mask, "n"].iloc[0]
        before_pct = summary.loc[mask, "pct_neg"].iloc[0]
        summary.loc[mask, "n"] = int(row["n"])
        summary.loc[mask, "pct_neg"] = row["pct_neg"]
        summary.loc[mask, "avg_confidence"] = row["avg_confidence"]
        summary.loc[mask, "rating"] = row["rating"]
        print(f"  {topic} [{name}]: n {before_n}->{int(row['n'])}, pct_neg {before_pct:.1%}->{row['pct_neg']:.1%}, "
              f"rating {row['rating']}★, confianza {row['avg_confidence']:.1%}")

    summary = summary.sort_values(["is_outlier", "pct_neg"], ascending=[True, False])
    summary.to_csv(paths.topics_summary_csv, index=False, encoding="utf-8-sig")
    print(f"Guardado en {paths.topics_summary_csv.resolve()}")


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--name", required=True, help="Nombre de la empresa/app")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(Paths(args.name))

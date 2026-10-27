"""
Exporta una tabla (CSV) con una fila por ORACIÓN/split de cada reseña — no
una fila por reseña — para poder chequear a ojo si el modelo clasifica bien
a nivel de detalle real: texto de la oración, categoría que le detectó y
sentimiento de esa oración. "review_id" identifica a qué reseña pertenece
cada oración, para poder agrupar y ver cómo quedó partida una reseña
puntual.

Cada oración se compara contra las keywords de TODAS las categorías de la
empresa, no solo la del tópico que le tocó a su reseña: una reseña puede
hablar de varios temas (ver topics_named.json), y restringir la búsqueda a
la categoría dominante de la reseña entera dejaba casi todo sin clasificar.

Si una oración menciona más de una categoría, se emite una fila por cada
una (no se concatenan en una sola celda) — más fácil de filtrar/pivotear
en una planilla. Si no menciona ninguna, la fila queda con category vacío.

No modifica ningún dato de la empresa (reviews_enriched.parquet,
topics_summary.csv): solo lee y arma una tabla aparte. Pensado para correr
después de refine_topic_sentiment.py y topics_enrich.py merge (necesita la
categoría y las keywords de cada tópico ya asignadas).

Al final imprime y guarda la cobertura de categorización (cuántas oraciones
quedaron SIN ninguna categoría asignada y la confianza promedio del
modelo) — un % de sin-categoría alto es la señal de que las keywords por
categoría de esta empresa están incompletas, no de que las reseñas no
hablen de nada puntual.

Uso: python 04_modeling/export_review_audit.py --name <empresa>
Escribe data/<empresa>/04_modeling/topics/review_audit.csv
y data/<empresa>/04_modeling/topics/review_audit_stats.json
"""
import argparse
import json
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

import pandas as pd
from pysentimiento import create_analyzer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from config import Paths  # noqa: E402


def split_sentences(text: str) -> list[str]:
    text = text.replace("\n", ". ")
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if len(p.strip()) > 2]


def topic_keywords(name: str) -> list[str]:
    """'5_no_deja_me_registrarme' -> ['no','deja','me','registrarme'] (saca el índice inicial)."""
    if not isinstance(name, str):
        return []
    return [p for p in name.split("_")[1:] if len(p) > 2]


def matching_categories(sentence: str, keywords_by_category: dict[str, list[str]]) -> list[str]:
    low = sentence.lower()
    return [cat for cat, kws in keywords_by_category.items()
            if any(re.search(rf"\b{re.escape(kw.lower())}", low) for kw in kws)]


def run(paths: Paths):
    df = pd.read_parquet(paths.reviews_enriched_parquet)
    summary = pd.read_csv(paths.topics_summary_csv)
    if "category" not in summary.columns:
        raise SystemExit("topics_summary.csv no tiene tópicos nombrados todavía — correr topics_enrich.py merge primero.")

    # Keywords de TODAS las categorías de la empresa (unión de las keywords de
    # cada tópico que cae en esa categoría), para poder buscarlas en cualquier
    # oración sin importar de qué reseña venga.
    keywords_by_category: dict[str, list[str]] = {}
    for _, row in summary.iterrows():
        if not row["category"]:
            continue
        keywords_by_category.setdefault(row["category"], []).extend(topic_keywords(row["Name"]))

    analyzer = create_analyzer(task="sentiment", lang="es")

    rows = []
    for _, review in df.iterrows():
        for order, sentence in enumerate(split_sentences(review["text"])):
            cats = matching_categories(sentence, keywords_by_category)
            pred = analyzer.predict(sentence)
            base = {
                "review_id": review["review_id"],
                "sentence_order": order,
                "sentence": sentence,
                "sentence_sentiment": pred.output,
                "sentence_confidence": round(pred.probas[pred.output], 4),
            }
            if cats:
                for cat in cats:
                    rows.append({**base, "category": cat})
            else:
                rows.append({**base, "category": ""})

    out = pd.DataFrame(rows, columns=["review_id", "sentence_order", "sentence", "category",
                                       "sentence_sentiment", "sentence_confidence"])
    out.to_csv(paths.review_audit_csv, index=False, encoding="utf-8-sig")
    print(f"{len(out)} filas ({df['review_id'].nunique()} reseñas) -> {paths.review_audit_csv.resolve()}")

    # Cobertura a nivel ORACIÓN, no fila (una oración con 2 categorías no debe
    # contarse 2 veces): una oración "tiene categoría" si al menos una de sus
    # filas la tiene.
    has_category = out.groupby(["review_id", "sentence_order"]).agg(
        has_category=("category", lambda s: bool((s != "").any())),
        confidence=("sentence_confidence", "first"),
    )
    n_sentences = len(has_category)
    n_with_category = int(has_category["has_category"].sum())
    pct_with_category = n_with_category / n_sentences if n_sentences else 0.0
    conf_with = has_category.loc[has_category["has_category"], "confidence"].mean()
    conf_without = has_category.loc[~has_category["has_category"], "confidence"].mean()

    stats = {
        "n_sentences": n_sentences,
        "n_with_category": n_with_category,
        "n_without_category": n_sentences - n_with_category,
        "pct_with_category": round(pct_with_category, 4),
        "avg_confidence_overall": round(float(has_category["confidence"].mean()), 4),
        "avg_confidence_with_category": round(float(conf_with), 4) if pd.notna(conf_with) else None,
        "avg_confidence_without_category": round(float(conf_without), 4) if pd.notna(conf_without) else None,
    }
    paths.review_audit_stats_json.write_text(json.dumps(stats, indent=2, ensure_ascii=False))

    print(f"\nCobertura de categorización: {n_with_category}/{n_sentences} oraciones ({pct_with_category:.1%}) "
          f"— confianza promedio {stats['avg_confidence_overall']:.1%} "
          f"(con categoría {stats['avg_confidence_with_category']:.1%}, "
          f"sin categoría {stats['avg_confidence_without_category']:.1%})")
    if pct_with_category < 0.5:
        print(f"⚠️  Menos de la mitad de las oraciones quedaron sin categoría: revisar las keywords por "
              f"categoría en topics_summary.csv (columna Name) — probablemente faltan variantes, no que "
              f"las reseñas no hablen de temas puntuales.")
    print(f"Guardado en {paths.review_audit_stats_json.resolve()}")


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--name", required=True, help="Nombre de la empresa/app")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(Paths(args.name))

"""
Exporta una tabla (CSV) con una fila por ORACIÓN/split de cada reseña — no
una fila por reseña — para poder chequear a ojo si el modelo clasifica bien
a nivel de detalle real: texto de la oración, categoría que le detectó (por
las keywords del tópico asignado a la reseña) y sentimiento de esa oración.
"review_id" identifica a qué reseña pertenece cada oración, para poder
agrupar y ver cómo quedó partida una reseña puntual.

Si una oración menciona más de una categoría, se emite una fila por cada
una (no se concatenan en una sola celda) — más fácil de filtrar/pivotear
en una planilla. Si no menciona ninguna, la fila queda con category vacío.

No modifica ningún dato de la empresa (reviews_enriched.parquet,
topics_summary.csv): solo lee y arma una tabla aparte. Pensado para correr
después de refine_topic_sentiment.py y topics_enrich.py merge (necesita la
categoría y las keywords de cada tópico ya asignadas).

Uso: python 04_modeling/export_review_audit.py --name <empresa>
Escribe data/<empresa>/04_modeling/topics/review_audit.csv
"""
import argparse
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


def matching_categories(sentence: str, category: str, keywords: list[str]) -> list[str]:
    if not keywords:
        return []
    low = sentence.lower()
    return [category] if any(re.search(rf"\b{re.escape(kw.lower())}", low) for kw in keywords) else []


def run(paths: Paths):
    df = pd.read_parquet(paths.reviews_enriched_parquet)
    summary = pd.read_csv(paths.topics_summary_csv)
    if "category" not in summary.columns:
        raise SystemExit("topics_summary.csv no tiene tópicos nombrados todavía — correr topics_enrich.py merge primero.")

    topic_to_category = summary.set_index("topic")["category"].to_dict()
    topic_to_keywords = {row["topic"]: topic_keywords(row["Name"]) for _, row in summary.iterrows()}

    analyzer = create_analyzer(task="sentiment", lang="es")

    rows = []
    for _, review in df.iterrows():
        topic = review["topic"]
        category = topic_to_category.get(topic, "")
        keywords = topic_to_keywords.get(topic, [])
        for order, sentence in enumerate(split_sentences(review["text"])):
            cats = matching_categories(sentence, category, keywords)
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


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--name", required=True, help="Nombre de la empresa/app")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(Paths(args.name))

"""
Recalcula el "% negativas" de topics_summary.csv a partir de sentimiento por
ORACIÓN en vez de por reseña entera, SIN re-clusterizar — lee el "topic" que
ya tiene cada reseña en reviews_enriched.parquet (de analyze_sentiment_topics.py
o de una categorización manual) y solo refina esa columna.

Por qué existe este script aparte: correr analyze_sentiment_topics.py de
nuevo para agregar esto re-ejecuta BERTopic (UMAP no tiene seed fija), lo que
reordena/renumera los tópicos y pisa el nombre/severidad/categoría/
recomendación que ya se habían curado a mano en topics_named.json (ver
APRENDIZAJES.md, caso belo). Este script en cambio es no-destructivo: toca
una sola columna de topics_summary.csv y nunca toca reviews_enriched.parquet
ni la asignación de tópico de ninguna reseña.

Qué NO hace: no recalcula "severity" — un cambio de % puede ameritar subir o
bajar la severidad (ver my-board-game-collection, categoría Estabilidad:
33%->60% al pasar a nivel oración), pero eso requiere criterio humano sobre
el caso puntual, no una regla genérica. Si el % cambió sensiblemente para
algún tópico, revisar a mano si la severidad en topics_named.json sigue
siendo la correcta y volver a correr topics_enrich.py merge.

Uso: python 04_modeling/refine_topic_sentiment.py --name <empresa>
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


def run(paths: Paths):
    if not paths.reviews_enriched_parquet.exists() or not paths.topics_summary_csv.exists():
        raise SystemExit(f"Faltan {paths.reviews_enriched_parquet.name} o {paths.topics_summary_csv.name} — "
                          "correr primero analyze_sentiment_topics.py.")

    df = pd.read_parquet(paths.reviews_enriched_parquet)
    summary = pd.read_csv(paths.topics_summary_csv)
    if "topic" not in df.columns:
        raise SystemExit("reviews_enriched.parquet no tiene columna 'topic'.")

    analyzer = create_analyzer(task="sentiment", lang="es")

    rows = [{"topic": topic, "sentence": s}
            for topic, text in zip(df["topic"], df["text"])
            for s in split_sentences(text)]
    sent_df = pd.DataFrame(rows)
    sent_df["sentiment"] = [p.output for p in analyzer.predict(sent_df["sentence"].tolist())]
    pct_neg_by_topic = sent_df.groupby("topic")["sentiment"].apply(lambda s: (s == "NEG").mean())

    before = summary.set_index("topic")["pct_neg"].to_dict()
    summary["pct_neg"] = summary["topic"].map(pct_neg_by_topic).round(6)
    summary = summary.sort_values(["is_outlier", "pct_neg"], ascending=[True, False])
    summary.to_csv(paths.topics_summary_csv, index=False, encoding="utf-8-sig")

    print("pct_neg actualizado (por reseña entera -> por oración):")
    for _, row in summary.iterrows():
        old = before.get(row["topic"])
        name = row.get("name") if isinstance(row.get("name"), str) and row.get("name") else row.get("Name", "")
        if old is not None:
            print(f"  tópico {row['topic']:>4} [{name}]: {old:.1%} -> {row['pct_neg']:.1%}")
    print(f"Guardado en {paths.topics_summary_csv.resolve()}")


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--name", required=True, help="Nombre de la empresa/app")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(Paths(args.name))

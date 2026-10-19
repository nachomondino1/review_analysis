import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()  # va primero, antes de los imports de HF

import pandas as pd
from pysentimiento import create_analyzer
from bertopic import BERTopic
from sentence_transformers import SentenceTransformer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from config import Paths  # noqa: E402

OUTLIER_TOPIC = -1  # BERTopic: reseñas sin patrón claro, no es un tópico real


def parse_args():
    p = argparse.ArgumentParser(description="Analiza sentimiento y tópicos de las reseñas de una empresa.")
    p.add_argument("--name", required=True, help="Nombre de la empresa/app (debe coincidir con el usado en collect_data.py)")
    return p.parse_args()


def run(paths: Paths):
    df = pd.read_parquet(paths.reviews_clean)  # ya filtrado en 02_data_preparation

    sent = create_analyzer(task="sentiment", lang="es")
    df["sentiment"] = [p.output for p in sent.predict(df["text"].tolist())]

    emb = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    topic_model = BERTopic(language="multilingual", min_topic_size=20)
    df["topic"], _ = topic_model.fit_transform(
        df["text"].tolist(), emb.encode(df["text"].tolist(), show_progress_bar=True)
    )

    # Resumen por tópico (antes se calculaba y se descartaba)
    summary = (df.groupby("topic")
       .agg(n=("text", "size"), rating=("rating", "mean"),
            pct_neg=("sentiment", lambda s: (s == "NEG").mean()))
       .sort_values("pct_neg", ascending=False))

    # Agrego keywords para poder nombrar cada tópico
    info = topic_model.get_topic_info().set_index("Topic")[["Name"]]
    summary = summary.join(info)

    # El tópico -1 son outliers de BERTopic, no un tema real: se marca aparte
    summary["is_outlier"] = summary.index == OUTLIER_TOPIC

    paths.ensure_dirs()
    df.to_parquet(paths.reviews_enriched_parquet)  # fuente de verdad, reusable
    df.to_csv(paths.reviews_enriched_csv, index=False, encoding="utf-8-sig")  # para abrir en Excel
    summary.to_csv(paths.topics_summary_csv, encoding="utf-8-sig")

    return summary


if __name__ == "__main__":
    args = parse_args()
    paths = Paths(args.name)
    summary = run(paths)
    print(summary.head(15))

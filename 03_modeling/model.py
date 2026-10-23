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
MIN_TOPIC_SIZE_DEFAULT = 20
MIN_TOPIC_SIZE_FLOOR = 5

# Mapea la etiqueta de pysentimiento al mismo vocabulario que rating_bucket
# (construct_data.py), para poder cruzarlas.
SENTIMENT_TO_BUCKET = {"POS": "positiva", "NEU": "neutra", "NEG": "negativa"}


def min_topic_size_for(n_docs: int) -> int:
    """
    min_topic_size=20 fijo no forma ningún tópico real en datasets chicos (ej.
    74 reseñas): todo cae en el outlier -1. Lo escala con el tamaño del corpus,
    con un piso para no generar tópicos de 2-3 reseñas sin sentido.
    """
    return max(MIN_TOPIC_SIZE_FLOOR, min(MIN_TOPIC_SIZE_DEFAULT, n_docs // 10))


def parse_args():
    p = argparse.ArgumentParser(description="Analiza sentimiento y tópicos de las reseñas de una empresa.")
    p.add_argument("--name", required=True, help="Nombre de la empresa/app (debe coincidir con el usado en collect_ios_reviews.py / collect_android_reviews.py)")
    return p.parse_args()


def run(paths: Paths):
    df = pd.read_parquet(paths.reviews_clean)  # ya filtrado en 02_data_preparation

    sent = create_analyzer(task="sentiment", lang="es")
    df["sentiment"] = [p.output for p in sent.predict(df["text"].tolist())]

    # Chequeo cruzado contra rating_bucket (construct_data.py): si el modelo de
    # sentimiento del texto discrepa con las estrellas que puso el usuario, es
    # una reseña rara (sarcasmo, rating mal puesto, texto que no acompaña la
    # estrella) que vale la pena poder filtrar aparte.
    df["sentiment_mismatch"] = df["sentiment"].map(SENTIMENT_TO_BUCKET) != df["rating_bucket"]
    print(f"sentiment_mismatch: {df['sentiment_mismatch'].sum()}/{len(df)} reseñas ({df['sentiment_mismatch'].mean():.1%})")

    emb = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    topic_model = BERTopic(
        language="multilingual",
        min_topic_size=min_topic_size_for(len(df)),
        nr_topics="auto",  # fusiona tópicos cuyas palabras clave son casi iguales (ej. variantes de "excelente app")
    )
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

    # Chequeo de calidad del modelo de tópicos: si una fracción grande de las
    # reseñas no se pudo agrupar en ningún tópico, el modelo no separó bien el
    # corpus (corpus chico, min_topic_size mal calibrado, etc.) y conviene
    # desconfiar de los tópicos que sí formó antes de reportarlos como hallazgo.
    outlier_pct = (df["topic"] == OUTLIER_TOPIC).mean()
    print(f"outliers (tópico -1): {(df['topic'] == OUTLIER_TOPIC).sum()}/{len(df)} reseñas ({outlier_pct:.1%})")

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

import argparse
import re
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
MAX_TOPICS = 30  # más que esto es ruido (variantes casi idénticas), no hallazgos nuevos
MAX_TOPIC_SHARE = 0.35  # un solo tópico no debería ser "el tema" de más de un tercio del corpus
MIN_TOPIC_SIZE_MAX_RETRIES = 4

# Mapea la etiqueta de pysentimiento al mismo vocabulario que rating_bucket
# (construct_data.py), para poder cruzarlas.
SENTIMENT_TO_BUCKET = {"POS": "positiva", "NEU": "neutra", "NEG": "negativa"}


def split_sentences(text: str) -> list[str]:
    """
    Partir una reseña en oraciones (por ".", "!", "?"), para poder calcular
    sentimiento por oración en vez de por reseña entera — una reseña mixta
    como "Los filtros son buenísimos. Pero se traba al sincronizar." no
    debería contar entera como un solo sentimiento para el tópico que le
    tocó (BERTopic asigna un tópico dominante por reseña, no por oración).
    """
    text = text.replace("\n", ". ")
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if len(p.strip()) > 2]


def topic_pct_neg_by_sentence(df: pd.DataFrame, sent_analyzer) -> pd.Series:
    """
    % de negativas por tópico calculado sobre oraciones, no sobre reseñas
    enteras: evita que una reseña con sentimiento mixto (parte elogia, parte
    se queja) se cuente entera hacia el lado que predomina. Cada reseña
    aporta sus propias oraciones al tópico que BERTopic ya le asignó (no se
    reasignan oraciones a otros tópicos: esta es una mejora de precisión del
    % negativas, no una re-categorización por aspecto — ver APRENDIZAJES.md
    para por qué no se generalizó la versión por keywords/rubro).
    """
    rows = [{"topic": topic, "sentence": s}
            for topic, text in zip(df["topic"], df["text"])
            for s in split_sentences(text)]
    sent_df = pd.DataFrame(rows)
    sent_df["sentiment"] = [p.output for p in sent_analyzer.predict(sent_df["sentence"].tolist())]
    return sent_df.groupby("topic")["sentiment"].apply(lambda s: (s == "NEG").mean())


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
    df = pd.read_parquet(paths.reviews_clean)  # ya filtrado en 03_data_preparation

    sent = create_analyzer(task="sentiment", lang="es")
    df["sentiment"] = [p.output for p in sent.predict(df["text"].tolist())]

    # Chequeo cruzado contra rating_bucket (construct_data.py): si el modelo de
    # sentimiento del texto discrepa con las estrellas que puso el usuario, es
    # una reseña rara (sarcasmo, rating mal puesto, texto que no acompaña la
    # estrella) que vale la pena poder filtrar aparte.
    df["sentiment_mismatch"] = df["sentiment"].map(SENTIMENT_TO_BUCKET) != df["rating_bucket"]
    print(f"sentiment_mismatch: {df['sentiment_mismatch'].sum()}/{len(df)} reseñas ({df['sentiment_mismatch'].mean():.1%})")

    emb = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    embeddings = emb.encode(df["text"].tolist(), show_progress_bar=True)

    # min_topic_size_for(n) alcanza para la mayoría de los corpus, pero no es
    # función solo del tamaño: un corpus con temática más diversa (más
    # features/casos de uso distintos) puede seguir fragmentándose en decenas
    # de variantes casi idénticas (ej. "no llega el código"/"código no llega"
    # como tópicos separados). nr_topics="auto" (probado antes acá) decide
    # solo cuánto fusionar según una similitud fija entre tópicos, y eso es
    # errático: en Lemon Cash dejaba casi-duplicados sin fusionar, y en Belo
    # fusionó demasiado y mandó el 55-76% de las reseñas no-outlier a un solo
    # tópico ("quejas generales" mezclando actualizaciones + bloqueos de
    # cuenta + demoras, temas en realidad distintos). En vez de eso: ajustar
    # sin fusión automática, y si el ajuste natural da más de MAX_TOPICS,
    # reducir con un objetivo explícito (reduce_topics a MAX_TOPICS, no más)
    # en vez de dejar que "auto" decida hasta dónde fusionar. Si aun así un
    # solo tópico se queda con más de MAX_TOPIC_SHARE del corpus no-outlier,
    # es la misma señal que demasiados tópicos: el ajuste no separó bien el
    # corpus, y conviene subir min_topic_size y reintentar.
    min_topic_size = min_topic_size_for(len(df))
    for attempt in range(MIN_TOPIC_SIZE_MAX_RETRIES):
        topic_model = BERTopic(language="multilingual", min_topic_size=min_topic_size)
        topics, _ = topic_model.fit_transform(df["text"].tolist(), embeddings)
        n_topics = len(set(topics) - {OUTLIER_TOPIC})
        if n_topics > MAX_TOPICS:
            topic_model.reduce_topics(df["text"].tolist(), nr_topics=MAX_TOPICS)
            topics = topic_model.topics_
            n_topics = len(set(topics) - {OUTLIER_TOPIC})

        non_outlier = pd.Series(topics)
        non_outlier = non_outlier[non_outlier != OUTLIER_TOPIC]
        top_share = non_outlier.value_counts().iloc[0] / len(non_outlier) if len(non_outlier) else 0

        if n_topics <= MAX_TOPICS and top_share <= MAX_TOPIC_SHARE:
            break
        print(f"min_topic_size={min_topic_size} dio {n_topics} tópicos, el más grande con "
              f"{top_share:.1%} del corpus no-outlier (ruido o tópico mega) — subiendo umbral y reintentando")
        min_topic_size *= 2
    df["topic"] = topics

    # Resumen por tópico (antes se calculaba y se descartaba)
    summary = (df.groupby("topic")
       .agg(n=("text", "size"), rating=("rating", "mean"))
       .join(topic_pct_neg_by_sentence(df, sent).rename("pct_neg"))
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

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()  # va primero, antes de los imports de HF

import pandas as pd
from pysentimiento import create_analyzer
from bertopic import BERTopic
from sentence_transformers import SentenceTransformer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "common"))
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
    # corpus.
    #
    # Subir min_topic_size y reintentar (comportamiento original) resuelve
    # el mega-tópico en corpus grandes (miles de reseñas): valida en Belo,
    # Lemon Cash, Ripio — ver APRENDIZAJES.md 2026-10-21. Pero en un corpus
    # chico (~200 reseñas, ej. Board Game Stats) hace lo contrario de lo que
    # hace falta: un umbral más alto deja MENOS reseñas por cluster válido,
    # así que todo termina en outlier en vez de separarse mejor — y eso
    # pasaba el chequeo de calidad sin querer, porque top_share se calculaba
    # como 0 cuando no quedaba ningún tópico no-outlier (0/0), en vez de
    # tratarse como el peor caso posible (ver APRENDIZAJES.md 2026-10-29).
    # Solución: generar candidatos subiendo Y bajando desde el valor base
    # (acotado por el piso), probar todos hasta MIN_TOPIC_SIZE_MAX_RETRIES,
    # y quedarse con el mejor resultado visto (no el último) si ninguno
    # cumple los dos umbrales — explícito en vez de aceptar un resultado
    # inservible en silencio.
    base = min_topic_size_for(len(df))
    candidates, seen = [base], {base}
    inc = dec = base
    while len(candidates) < MIN_TOPIC_SIZE_MAX_RETRIES * 2:
        dec = max(MIN_TOPIC_SIZE_FLOOR, dec // 2)
        inc = inc * 2
        for v in (dec, inc):
            if v not in seen:
                candidates.append(v)
                seen.add(v)
        if dec == MIN_TOPIC_SIZE_FLOOR and len(candidates) >= MIN_TOPIC_SIZE_MAX_RETRIES:
            break
    candidates = candidates[:MIN_TOPIC_SIZE_MAX_RETRIES]

    best = None  # (top_share, -n_topics, min_topic_size, topics, topic_model) — menor top_share gana, empate a más tópicos
    for min_topic_size in candidates:
        topic_model = BERTopic(language="multilingual", min_topic_size=min_topic_size)
        topics, _ = topic_model.fit_transform(df["text"].tolist(), embeddings)
        n_topics = len(set(topics) - {OUTLIER_TOPIC})
        if n_topics > MAX_TOPICS:
            topic_model.reduce_topics(df["text"].tolist(), nr_topics=MAX_TOPICS)
            topics = topic_model.topics_
            n_topics = len(set(topics) - {OUTLIER_TOPIC})

        non_outlier = pd.Series(topics)
        non_outlier = non_outlier[non_outlier != OUTLIER_TOPIC]
        # 0 tópicos no-outlier es el peor caso (no 0% de "tópico mega" — ver
        # docstring arriba), así que cuenta como top_share=1.0, no 0.
        top_share = non_outlier.value_counts().iloc[0] / len(non_outlier) if len(non_outlier) else 1.0

        candidate_key = (top_share, -n_topics)
        if best is None or candidate_key < best[0]:
            best = (candidate_key, min_topic_size, topics, topic_model, n_topics, top_share)

        if n_topics <= MAX_TOPICS and top_share <= MAX_TOPIC_SHARE:
            break
        print(f"min_topic_size={min_topic_size} dio {n_topics} tópicos, el más grande con "
              f"{top_share:.1%} del corpus no-outlier (ruido o tópico mega) — probando otro umbral")

    _, min_topic_size, topics, topic_model, n_topics, top_share = best
    if not (n_topics <= MAX_TOPICS and top_share <= MAX_TOPIC_SHARE):
        print(f"⚠️ Ningún min_topic_size probado cumplió los umbrales — se queda con el mejor "
              f"(min_topic_size={min_topic_size}, {n_topics} tópicos, {top_share:.1%} el más grande). "
              f"Desconfiar más de lo normal de estos tópicos al nombrarlos (03_topics_enrich.py).")
    df["topic"] = topics

    # Resumen por tópico (antes se calculaba y se descartaba). pct_neg acá es
    # rápido y por reseña entera; 04_modeling/topics/02_refine_topic_sentiment.py lo
    # refina después a nivel oración sin tener que re-clusterizar (ver su
    # docstring para por qué eso importa).
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

"""
Agrega "sentiment_confidence" a reviews_enriched.parquet: la probabilidad
que pysentimiento le dio a la etiqueta que terminó asignando (ej. si dijo
POS con 92% de probabilidad, confidence=0.92). Sirve para priorizar
ejemplos en el sitio: ante dos reseñas negativas, la que el modelo clasificó
con más confianza es más representativa que una ambigua.

No toca "sentiment" ni "topic" — solo agrega una columna nueva. No
re-clusteriza, no re-nombra tópicos: igual de seguro que
refine_topic_sentiment.py (mismo motivo, ver su docstring).

Uso: python 04_modeling/add_sentiment_confidence.py --name <empresa>
"""
import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

import pandas as pd
from pysentimiento import create_analyzer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from config import Paths  # noqa: E402


def run(paths: Paths):
    df = pd.read_parquet(paths.reviews_enriched_parquet)
    analyzer = create_analyzer(task="sentiment", lang="es")
    preds = analyzer.predict(df["text"].tolist())
    df["sentiment_confidence"] = [p.probas[p.output] for p in preds]
    df.to_parquet(paths.reviews_enriched_parquet)
    df.to_csv(paths.reviews_enriched_csv, index=False, encoding="utf-8-sig")
    print(f"sentiment_confidence agregado a {len(df)} reseñas "
          f"(promedio {df['sentiment_confidence'].mean():.1%}) -> {paths.reviews_enriched_parquet.resolve()}")


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--name", required=True, help="Nombre de la empresa/app")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(Paths(args.name))

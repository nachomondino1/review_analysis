"""
MVP: traduce a español las reseñas que no están en español, para que
pysentimiento y las keywords de categorización (afinadas para español, ver
APRENDIZAJES.md) puedan leerlas — sin esto, una app con reseñas en inglés
da 100% outliers en el topic modeling (pasó con Board Game Stats,
2026-10-29). Corre DESPUÉS de clean_reviews.py y ANTES del modelado; es
opcional (solo hace falta si `--name` tiene reseñas en otro idioma) e
idempotente (si se corre dos veces, la segunda detecta "es" en el texto ya
traducido y no vuelve a tocarlo).

Traductor local (Helsinki-NLP/opus-mt-en-es vía transformers), no la API
no oficial de Google Translate: gratis, sin rate-limit ni dependencia de
un servicio externo, mismo approach que ya usamos para pysentimiento y
sentence-transformers. Ver "plan a futuro" en APRENDIZAJES.md para un
modelo de sentimiento nativo en inglés en vez de traducir + reusar
pysentimiento — este script es el MVP mientras tanto.

Uso: python 03_data_preparation/translate_reviews.py --name <empresa>
Sobreescribe data/<empresa>/03_data_preparation/reviews_clean.parquet,
agregando "text_original" (el texto sin traducir) y "detected_lang".
"""
import argparse
import sys
from pathlib import Path

import pandas as pd
from langdetect import DetectorFactory, detect

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from config import Paths  # noqa: E402

DetectorFactory.seed = 0  # langdetect no es determinístico por default

TRANSLATABLE_LANG = "en"  # MVP: solo inglés->español (ver docstring, "plan a futuro")
MODEL_NAME = "Helsinki-NLP/opus-mt-en-es"
BATCH_SIZE = 16


def detect_lang(text: str) -> str:
    try:
        return detect(text)
    except Exception:
        return "unknown"  # texto vacío/demasiado corto para detectar con confianza


def translate_batch(texts: list[str]) -> list[str]:
    # Import diferido (pesado) y carga directa de modelo/tokenizer en vez del
    # pipeline("translation") de transformers: ese task de conveniencia fue
    # removido en transformers 5.x (modelos seq2seq tipo MarianMT siguen
    # andando con generate() directo, solo cambió el wrapper).
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME)
    out = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i:i + BATCH_SIZE]
        inputs = tokenizer(batch, return_tensors="pt", padding=True, truncation=True, max_length=512)
        generated = model.generate(**inputs, max_length=512)
        out.extend(tokenizer.batch_decode(generated, skip_special_tokens=True))
    return out


def run(paths: Paths) -> pd.DataFrame:
    df = pd.read_parquet(paths.reviews_clean)
    df["detected_lang"] = df["text"].map(detect_lang)

    to_translate = df["detected_lang"] == TRANSLATABLE_LANG
    n_translate = int(to_translate.sum())
    if n_translate == 0:
        print(f"0 reseñas en inglés sobre {len(df)} — nada para traducir.")
        return df

    df["text_original"] = df["text"]
    translated = translate_batch(df.loc[to_translate, "text"].tolist())
    df.loc[to_translate, "text"] = translated

    paths.ensure_dirs()
    df.to_parquet(paths.reviews_clean)
    print(f"{n_translate}/{len(df)} reseñas traducidas de inglés -> {paths.reviews_clean.resolve()}")
    return df


def parse_args():
    p = argparse.ArgumentParser(description="Traduce a español las reseñas en inglés (MVP, ver docstring).")
    p.add_argument("--name", required=True, help="Nombre de la empresa/app")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(Paths(args.name))

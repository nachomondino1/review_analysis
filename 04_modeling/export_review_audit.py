"""
Exporta un Markdown legible por humano con el detalle de CADA reseña: texto
completo, cómo se partió en oraciones, qué categoría menciona cada oración
(por keywords del tópico que le tocó) y qué sentimiento le asignó el modelo
a cada una — más el sentimiento y la confianza de la reseña completa. Un CSV
no se puede hojear para chequear a ojo si el modelo clasifica bien; esto sí.

No modifica ningún dato de la empresa (reviews_enriched.parquet,
topics_summary.csv): solo lee y arma un reporte aparte. Pensado para correr
después de refine_topic_sentiment.py y topics_enrich.py merge (necesita la
categoría y el nombre de cada tópico ya asignados).

Uso: python 04_modeling/export_review_audit.py --name <empresa>
Escribe data/<empresa>/04_modeling/topics/review_audit.md
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

SENTIMENT_EMOJI = {"POS": "🟢", "NEU": "⚪", "NEG": "🔴"}


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

    # Keywords por categoría propia de esta reseña: el tópico que BERTopic/la
    # categorización manual le asignó a CADA reseña, no todas las keywords de
    # todas las categorías (si no, cualquier reseña "matchearía" con medio
    # vocabulario de la empresa).
    topic_to_category = summary.set_index("topic")["category"].to_dict()
    topic_to_name = summary.set_index("topic")["name"].to_dict()
    topic_to_keywords = {row["topic"]: topic_keywords(row["Name"]) for _, row in summary.iterrows()}

    analyzer = create_analyzer(task="sentiment", lang="es")
    has_confidence = "sentiment_confidence" in df.columns

    lines = [f"# Auditoría de clasificación — {paths.slug}", "",
             f"{len(df)} reseñas. Para cada una: texto completo, oraciones, categoría que menciona cada "
             "oración (según las keywords del tópico asignado a la reseña) y sentimiento de esa oración.",
             "Pensado para chequear a ojo si el modelo clasifica bien, no para publicar.", ""]

    df = df.sort_values("date", ascending=False)
    for _, row in df.iterrows():
        topic = row["topic"]
        category = topic_to_category.get(topic, "(sin categoría)")
        keywords = topic_to_keywords.get(topic, [])
        date_fmt = pd.to_datetime(row["date"]).strftime("%d/%m/%Y")
        conf = f" (confianza {row['sentiment_confidence']:.0%})" if has_confidence else ""

        lines.append(f"## {date_fmt} · {row['store']} · {row['rating']}★ · "
                     f"{SENTIMENT_EMOJI.get(row['sentiment'], '')} {row['sentiment']}{conf}")
        topic_name = topic_to_name.get(topic)
        topic_name = topic_name if isinstance(topic_name, str) and topic_name else f"tópico {topic}"
        lines.append(f"**Tópico asignado:** {category} — *{topic_name}*")
        lines.append("")
        lines.append(f"> {row['text']}".replace("\n", "\n> "))
        lines.append("")
        lines.append("| Oración | Categoría que menciona | Sentimiento de la oración |")
        lines.append("|---|---|---|")
        for sentence in split_sentences(row["text"]):
            cats = matching_categories(sentence, {category: keywords}) if keywords else []
            cats_label = ", ".join(cats) if cats else "—"
            pred = analyzer.predict(sentence)
            lines.append(f"| {sentence} | {cats_label} | {SENTIMENT_EMOJI.get(pred.output, '')} {pred.output} |")
        lines.append("")
        lines.append("---")
        lines.append("")

    paths.review_audit_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"Guardado en {paths.review_audit_md.resolve()}")


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--name", required=True, help="Nombre de la empresa/app")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(Paths(args.name))

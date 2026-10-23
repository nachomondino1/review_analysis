"""
Enriquecer topics_summary.csv con nombre legible, severidad y recomendación
por tópico. No llama a ningún LLM por API: el nombrado lo hace Claude Code
en la sesión que te está ayudando (no hay API key de Anthropic disponible),
a partir de las muestras que exporta este script.

Uso:
  1) python 04_modeling/topics_enrich.py export --name <empresa>
     -> genera data/<empresa>/04_modeling/topic_samples.json con keywords +
        reseñas de muestra por tópico, priorizado por severidad
        (volumen * % negativas). El tópico -1 (outlier) se incluye al final,
        marcado, pero no hace falta nombrarlo.

  2) Pedirle a Claude (en esta sesión) que lea ese JSON y escriba
     data/<empresa>/04_modeling/topics_named.json con, por cada "topic" no
     outlier: name, summary, severity ("alta"/"media"/"baja"), recommendation,
     y category (una palabra; agrupa tópicos afines — como guía de cuántos
     grupos usar, la raíz cuadrada del número de tópicos no-outlier da un
     número razonable de categorías, ni una por tópico ni una sola para todos).

  3) python 04_modeling/topics_enrich.py merge --name <empresa>
     -> vuelca esas columnas a topics_summary.csv (sobrescribe el archivo,
        agregando name/summary/severity/recommendation/category).
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from config import Paths  # noqa: E402

SAMPLES_PER_TOPIC = 5


def export_samples(paths: Paths):
    df = pd.read_parquet(paths.reviews_enriched_parquet)
    summary = pd.read_csv(paths.topics_summary_csv)

    # priorizar por severidad real: volumen * % negativas, outlier al final
    summary["_priority"] = summary["n"] * summary["pct_neg"]
    summary = summary.sort_values(["is_outlier", "_priority"], ascending=[True, False])

    topics = []
    for _, row in summary.iterrows():
        topic_id = int(row["topic"])
        sample_texts = (df[df["topic"] == topic_id]["text"]
                        .dropna().head(SAMPLES_PER_TOPIC).tolist())
        topics.append({
            "topic": topic_id,
            "is_outlier": bool(row["is_outlier"]),
            "keywords": row["Name"],
            "n": int(row["n"]),
            "avg_rating": round(float(row["rating"]), 2),
            "pct_neg": round(float(row["pct_neg"]), 3),
            "sample_reviews": sample_texts,
        })

    paths.topic_samples_json.write_text(json.dumps(topics, ensure_ascii=False, indent=2))
    print(f"Guardado en {paths.topic_samples_json.resolve()}")
    print("Pedile a Claude que lea ese archivo y escriba "
          f"{paths.topics_named_json} con name/summary/severity/recommendation "
          "por cada tópico no outlier.")


def merge_names(paths: Paths):
    if not paths.topics_named_json.exists():
        raise SystemExit(f"No existe {paths.topics_named_json}. Corré primero 'export' y pedile a Claude que lo genere.")

    named = {str(t["topic"]): t for t in json.loads(paths.topics_named_json.read_text())}
    summary = pd.read_csv(paths.topics_summary_csv)

    for col in ["name", "summary", "severity", "recommendation", "category"]:
        summary[col] = summary["topic"].astype(str).map(lambda t: named.get(t, {}).get(col, ""))

    summary.loc[summary["is_outlier"], ["name", "summary", "severity", "recommendation", "category"]] = (
        "Sin patrón claro", "Reseñas que no forman un tema reconocible.", "", "", ""
    )

    summary = summary.sort_values(["is_outlier", "pct_neg"], ascending=[True, False])
    summary.to_csv(paths.topics_summary_csv, index=False, encoding="utf-8-sig")
    print(f"Actualizado {paths.topics_summary_csv.resolve()}")


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["export", "merge"])
    p.add_argument("--name", required=True, help="Nombre de la empresa/app")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    paths = Paths(args.name)
    if args.command == "export":
        export_samples(paths)
    else:
        merge_names(paths)

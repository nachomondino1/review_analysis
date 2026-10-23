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
     y category — una de la taxonomía fija del rubro en common/categories.py
     (CATEGORIES_BY_DOMAIN[--domain]), la misma lista para todas las empresas
     de ese rubro. No inventar una categoría nueva por empresa: la gracia de
     un eje fijo es que "Seguridad" en una empresa del rubro signifique lo
     mismo que en otra y los bubble charts sean comparables. Si de verdad
     ningún valor de la lista encaja, agregarlo a esa entrada de
     CATEGORIES_BY_DOMAIN (con su descripción de cuándo usarlo) en vez de
     escribir uno suelto en el JSON. Si la app es de otro rubro (ej:
     agrotech), usar --domain para esa lista o crear una nueva si no existe
     aún — no forzar sus tópicos a la lista de otro rubro. "General" vs
     "Ruido": si el comentario expresa un sentimiento claro (positivo o
     negativo) sobre la app/marca en su conjunto aunque sea breve o genérico
     ("funciona bien", "la mejor billetera"), es "General"; si ni siquiera se
     entiende el tema o el sentimiento (texto ilegible, rating condicionado
     sin desarrollar), es "Ruido".

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
from categories import allowed as allowed_categories  # noqa: E402

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


def merge_names(paths: Paths, domain: str):
    if not paths.topics_named_json.exists():
        raise SystemExit(f"No existe {paths.topics_named_json}. Corré primero 'export' y pedile a Claude que lo genere.")

    named = {str(t["topic"]): t for t in json.loads(paths.topics_named_json.read_text())}
    summary = pd.read_csv(paths.topics_summary_csv)

    bad = {t["category"] for t in named.values() if t.get("category") and t["category"] not in allowed_categories(domain)}
    if bad:
        print(f"WARNING: categorías fuera de la taxonomía fija del rubro '{domain}' (common/categories.py): {sorted(bad)}")

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
    p.add_argument("--domain", default="fintech", help="Rubro (key en CATEGORIES_BY_DOMAIN), default fintech")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    paths = Paths(args.name)
    if args.command == "export":
        export_samples(paths)
    else:
        merge_names(paths, args.domain)

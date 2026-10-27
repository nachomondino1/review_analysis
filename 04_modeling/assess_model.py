"""
Evalúa el estado del modelado de TODAS las empresas (no una puntual, como el
resto de 04_modeling/) — para saber de un vistazo qué empresa está bien
servida por el pipeline y cuál necesita atención (pocas categorías, baja
cobertura de keywords, sentimiento mal distribuido, etc.) antes de confiar
en sus hallazgos.

Por empresa, a partir de topics_summary.csv, review_audit.csv y
review_audit_stats.json (los que existan — una empresa puede no haber
llegado a correr todo el flujo todavía):
  - tópicos: cuántos en total y cuántos reales (no outlier de BERTopic)
  - categorías: cuántas y cuáles
  - oraciones: cuántas en total, cuántas con tópico/categoría asignado (%)
  - sentimiento promedio de las oraciones (% positivas/neutras/negativas)
  - confianza promedio del modelo

Imprime una tabla comparativa y un assessment en texto por empresa
(advierte cobertura baja, pocas categorías, etc. — mismo criterio que la
advertencia de 05_export_review_audit.py, pero across empresas). Guarda
además data/model_assessment.md (no es de una empresa puntual, por eso no
usa common/config.py Paths).

Uso: python 04_modeling/assess_model.py [--name <empresa> ...]
Sin --name, evalúa todas las que tengan data/<empresa>/04_modeling/topics/topics_summary.csv.
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from config import ROOT, Paths  # noqa: E402

COVERAGE_WARNING_THRESHOLD = 0.5
MIN_CATEGORIES_WARNING = 3


def discover_companies() -> list[str]:
    data_dir = ROOT / "data"
    return sorted(
        p.parent.parent.parent.name
        for p in data_dir.glob("*/04_modeling/topics/topics_summary.csv")
    )


def assess_one(name: str) -> dict:
    paths = Paths(name)
    row = {"empresa": name}

    if not paths.topics_summary_csv.exists():
        row["estado"] = "sin modelar (no corrió analyze_sentiment_topics.py)"
        return row

    summary = pd.read_csv(paths.topics_summary_csv)
    real = summary[~summary["is_outlier"]] if "is_outlier" in summary.columns else summary.iloc[0:0]
    row["n_topicos_total"] = len(summary)
    row["n_topicos_reales"] = len(real)
    row["n_resenas"] = (
        int(pd.read_parquet(paths.reviews_enriched_parquet, columns=["review_id"]).shape[0])
        if paths.reviews_enriched_parquet.exists() else None
    )

    if "category" in summary.columns:
        cats = sorted(c for c in real["category"].dropna().unique() if c)
        row["n_categorias"] = len(cats)
        row["categorias"] = ", ".join(cats) if cats else "(ninguna)"
    else:
        row["n_categorias"] = 0
        row["categorias"] = "(tópicos sin nombrar — falta topics_enrich.py merge)"

    if paths.review_audit_stats_json.exists():
        import json
        stats = json.loads(paths.review_audit_stats_json.read_text())
        row["n_oraciones"] = stats["n_sentences"]
        row["pct_con_topico"] = stats["pct_with_category"]  # topic y category se asignan juntos
        row["pct_con_categoria"] = stats["pct_with_category"]
        row["confianza_prom"] = stats["avg_confidence_overall"]
    else:
        row["n_oraciones"] = None
        row["pct_con_topico"] = None
        row["pct_con_categoria"] = None
        row["confianza_prom"] = None

    if paths.review_audit_csv.exists():
        audit = pd.read_csv(paths.review_audit_csv)
        # Una oración puede tener varias filas (una por tópico que menciona);
        # para el sentimiento promedio se cuenta cada oración una sola vez.
        unique_sentences = audit.drop_duplicates(["review_id", "sentence_order"])
        dist = unique_sentences["sentence_sentiment"].value_counts(normalize=True)
        row["pct_positivas"] = round(float(dist.get("POS", 0)), 4)
        row["pct_neutras"] = round(float(dist.get("NEU", 0)), 4)
        row["pct_negativas"] = round(float(dist.get("NEG", 0)), 4)
    else:
        row["pct_positivas"] = row["pct_neutras"] = row["pct_negativas"] = None

    row["estado"] = "ok"
    return row


def print_assessment(row: dict):
    name = row["empresa"]
    if row.get("estado") != "ok":
        print(f"\n### {name}: {row.get('estado')}")
        return

    print(f"\n### {name}")
    print(f"  Reseñas con texto analizadas: {row['n_resenas']}")
    print(f"  Tópicos: {row['n_topicos_reales']} reales ({row['n_topicos_total']} total con outlier)")
    print(f"  Categorías ({row['n_categorias']}): {row['categorias']}")
    if row["n_oraciones"] is not None:
        print(f"  Oraciones: {row['n_oraciones']} — con tópico/categoría: {row['pct_con_categoria']:.1%}")
        print(f"  Confianza promedio del modelo: {row['confianza_prom']:.1%}")
    else:
        print("  Oraciones: no se corrió 05_export_review_audit.py todavía")
    if row["pct_positivas"] is not None:
        print(f"  Sentimiento de las oraciones: {row['pct_positivas']:.1%} positivas, "
              f"{row['pct_neutras']:.1%} neutras, {row['pct_negativas']:.1%} negativas")

    warnings = []
    if row["n_categorias"] and row["n_categorias"] < MIN_CATEGORIES_WARNING:
        warnings.append(f"pocas categorías ({row['n_categorias']}) — ¿el rubro en common/categories.py le queda chico?")
    if row["pct_con_categoria"] is not None and row["pct_con_categoria"] < COVERAGE_WARNING_THRESHOLD:
        warnings.append(f"cobertura de categorización baja ({row['pct_con_categoria']:.1%}) — revisar keywords por tópico")
    if row["n_topicos_reales"] == 0:
        warnings.append("0 tópicos reales: todo cayó en el outlier de BERTopic, no hay nada que mostrar en el sitio")
    for w in warnings:
        print(f"  ⚠️  {w}")


def markdown_table(rows: list[dict], columns: list[tuple[str, str]]) -> str:
    """columns: [(clave_en_row, encabezado)]. Formatea % y floats a texto legible."""
    def fmt(v):
        if v is None:
            return "-"
        if isinstance(v, float) and 0 <= v <= 1:
            return f"{v:.1%}"
        return str(v)

    headers = [h for _, h in columns]
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for row in rows:
        lines.append("| " + " | ".join(fmt(row.get(k)) for k, _ in columns) + " |")
    return "\n".join(lines)


def build_markdown(rows: list[dict]) -> str:
    lines = ["# Assessment del modelado, todas las empresas", ""]
    ok_rows = [r for r in rows if r.get("estado") == "ok"]
    if ok_rows:
        lines.append(markdown_table(ok_rows, [
            ("empresa", "Empresa"), ("n_resenas", "Reseñas"), ("n_topicos_reales", "Tópicos"),
            ("n_categorias", "N° categorías"), ("categorias", "Categorías"),
            ("n_oraciones", "Oraciones"), ("pct_con_categoria", "% con categoría"),
            ("confianza_prom", "Confianza prom."), ("pct_negativas", "% negativas"),
        ]))
        lines.append("")
    other = [r for r in rows if r.get("estado") != "ok"]
    if other:
        lines.append("## Sin evaluar")
        for r in other:
            lines.append(f"- **{r['empresa']}**: {r['estado']}")
    return "\n".join(lines)


def run(names: list[str] | None):
    names = names or discover_companies()
    if not names:
        raise SystemExit("No hay ninguna empresa con topics_summary.csv — correr el pipeline de 04_modeling primero.")

    rows = [assess_one(name) for name in names]
    for row in rows:
        print_assessment(row)

    out_path = ROOT / "data" / "model_assessment.md"
    out_path.write_text(build_markdown(rows), encoding="utf-8")
    print(f"\nGuardado en {out_path.resolve()}")


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--name", action="append", help="Empresa a evaluar (repetible). Sin esto, evalúa todas.")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(args.name)

"""
Describe los datos crudos de 01_data_understanding para una empresa: formato,
tamaño, variables y su tipo, y disponibilidad real de cada atributo (nulos).
Es la tarea de "Data Description" de CRISP-DM — no transforma ni limpia nada,
solo documenta lo que hay antes de integrar ni preparar.

Analiza cada fuente por separado (ios_reviews, android_reviews,
store_ratings) porque cada una tiene su propio esquema/grano — mezclarlas de
entrada escondería diferencias reales (ver integrate_data.py en
02_data_preparation para la integración de las 3 en un solo dataset). El
resultado se vuelca en un único .md con una sección por fuente, para no
tener que abrir 3 archivos sueltos para ver el panorama completo.

Uso: python 01_data_understanding/describe_data.py --name <empresa>
Lee data/<empresa>/01_data_understanding/{ios,android,store_ratings}_<empresa>.*
y escribe data_description.md (unificado, para leer) y <fuente>_description.json
por fuente (para otros scripts) en la misma carpeta.
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from config import Paths  # noqa: E402

# Pandas usa dtypes numéricos para columnas que en este dominio son
# categóricas (ids, estrellas 1-5) o booleanas; mapear a mano en vez de
# confiar en dtype crudo, que mentiría ("rating" es int64 pero es categórica
# ordinal, no una magnitud continua).
REVIEW_FIELD_KINDS = {
    "review_id": "categórica (identificador único)",
    "store": "categórica (ios / android)",
    "date": "fecha/hora",
    "rating": "categórica ordinal (1-5 estrellas)",
    "text": "texto libre",
    "version": "categórica (versión de la app)",
}


def describe_reviews_table(path: Path, fuente: str) -> dict:
    if not path.exists():
        return {"fuente": fuente, "exists": False}

    df = pd.read_parquet(path)
    n_rows, n_cols = df.shape
    fields = {}
    for col in df.columns:
        non_null = int(df[col].notna().sum())
        fields[col] = {
            "kind": REVIEW_FIELD_KINDS.get(col, str(df[col].dtype)),
            "dtype_pandas": str(df[col].dtype),
            "non_null_count": non_null,
            "null_count": n_rows - non_null,
            "availability_pct": round(non_null / n_rows * 100, 1) if n_rows else 0,
            "n_unique": int(df[col].nunique(dropna=True)),
        }

    return {
        "fuente": fuente,
        "exists": True,
        "format": "parquet",
        "file_size_bytes": path.stat().st_size,
        "n_records": n_rows,
        "n_fields": n_cols,
        "fields": fields,
        "rating_distribution": df["rating"].value_counts().sort_index().to_dict() if "rating" in df.columns else None,
        "date_range": {
            "min": str(df["date"].min()),
            "max": str(df["date"].max()),
        } if "date" in df.columns and n_rows else None,
        "duplicate_review_ids": int(df["review_id"].duplicated().sum()) if "review_id" in df.columns else None,
    }


def describe_store_ratings(path: Path) -> dict:
    if not path.exists():
        return {"fuente": "store_ratings", "exists": False}

    data = json.loads(path.read_text())
    stores = {}
    for store, stats in data.items():
        stores[store] = {
            "score_available": stats.get("score") is not None,
            "ratings_count_available": stats.get("ratings_count") is not None,
            "score": stats.get("score"),
            "ratings_count": stats.get("ratings_count"),
        }
    return {
        "fuente": "store_ratings",
        "exists": True,
        "format": "json",
        "file_size_bytes": path.stat().st_size,
        "n_records": len(stores),  # una fila por tienda
        "fields": {
            "store": {"kind": "categórica (ios / android)"},
            "score": {"kind": "numérica continua (rating promedio 1-5)"},
            "ratings_count": {"kind": "numérica discreta (cantidad de calificaciones)"},
        },
        "stores": stores,
    }


def build_source_section(desc: dict) -> list[str]:
    lines = [f"## {desc['fuente']}", ""]

    if not desc["exists"]:
        lines.append("No existe todavía (correr el `collect_*.py` de esta fuente primero).")
        return lines

    size_kb = round(desc["file_size_bytes"] / 1024, 1)
    lines.append(f"- **Formato:** {desc['format']} ({size_kb} KB)")
    lines.append(f"- **Registros:** {desc['n_records']}" + (f" x {desc['n_fields']} campos" if "n_fields" in desc else ""))

    if desc.get("date_range"):
        lines.append(f"- **Rango de fechas:** {desc['date_range']['min']} → {desc['date_range']['max']}")
    if desc.get("duplicate_review_ids") is not None:
        lines.append(f"- **review_id duplicados:** {desc['duplicate_review_ids']}")
    if desc.get("rating_distribution"):
        lines.append(f"- **Distribución de rating:** {desc['rating_distribution']}")

    lines += ["", "| Campo | Tipo | Disponibilidad | Valores únicos |", "|---|---|---|---|"]
    for name, info in desc["fields"].items():
        if "availability_pct" in info:
            total = info["non_null_count"] + info["null_count"]
            lines.append(
                f"| `{name}` | {info['kind']} | {info['availability_pct']}% "
                f"({info['non_null_count']}/{total}) | {info['n_unique']} |"
            )
        else:
            lines.append(f"| `{name}` | {info['kind']} | - | - |")

    if desc.get("stores"):
        lines += ["", "**Detalle por tienda:**", "", "| Tienda | Score | Cantidad de calificaciones |", "|---|---|---|"]
        for store, info in desc["stores"].items():
            score = info["score"] if info["score_available"] else "sin dato"
            count = info["ratings_count"] if info["ratings_count_available"] else "sin dato"
            lines.append(f"| {store} | {score} | {count} |")

    return lines


def print_summary(empresa: str, desc: dict):
    print(f"\n=== {empresa} — {desc['fuente']} ===")
    if not desc["exists"]:
        print("no existe todavía")
        return
    print(f"{desc['format']}, {desc['file_size_bytes']:,} bytes, {desc['n_records']} registros".replace(",", "."))
    for name, info in desc["fields"].items():
        if "availability_pct" in info:
            print(f"  - {name}: {info['kind']} | disponible {info['availability_pct']}% | {info['n_unique']} valores únicos")
        else:
            print(f"  - {name}: {info['kind']}")


def parse_args():
    p = argparse.ArgumentParser(description="Describe cada fuente de datos cruda recolectada para una empresa.")
    p.add_argument("--name", required=True, help="Nombre de la empresa/app (debe coincidir con los collect_*.py)")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    paths = Paths(args.name)

    sources = [
        describe_reviews_table(paths.ios_reviews, "ios_reviews"),
        describe_reviews_table(paths.android_reviews, "android_reviews"),
        describe_store_ratings(paths.store_ratings_json),
    ]

    md_lines = [f"# Descripción de datos — {args.name}", ""]
    for desc in sources:
        print_summary(args.name, desc)

        json_path = paths.understanding_dir / f"{desc['fuente']}_description.json"
        json_path.write_text(json.dumps({"empresa": args.name, **desc}, indent=2, ensure_ascii=False, default=str))

        md_lines += build_source_section(desc) + [""]

    md_path = paths.understanding_dir / "data_description.md"
    md_path.write_text("\n".join(md_lines).rstrip() + "\n")
    print(f"\nGuardado en {md_path.resolve()} (unificado, para leer)")

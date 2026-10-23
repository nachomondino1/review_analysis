"""
Fuente 2: reseñas de Google Play (con texto), para una empresa.

Uso: python 01_data_understanding/collect_android_reviews.py --name <empresa> [--pkg <package>]
Escribe data/<empresa>/01_data_understanding/android_<empresa>.parquet
"""
import argparse
import sys
from pathlib import Path

import pandas as pd
from google_play_scraper import Sort, reviews

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "common"))
from config import Paths  # noqa: E402
import companies  # noqa: E402


def fetch_android(pkg: str, country="ar", lang="es", count=5000) -> pd.DataFrame:
    revs, _ = reviews(pkg, lang=lang, country=country,
                      sort=Sort.NEWEST, count=count)
    return pd.DataFrame({
        "review_id": [r["reviewId"] for r in revs],
        "store": "android",
        "date": [r["at"] for r in revs],
        "rating": [r["score"] for r in revs],
        "text": [r["content"] for r in revs],
        "version": [r["reviewCreatedVersion"] for r in revs],
    })


def update(paths: Paths, pkg: str) -> pd.DataFrame:
    new = fetch_android(pkg)
    new["date"] = pd.to_datetime(new["date"], utc=True)
    paths.ensure_dirs()
    if paths.android_reviews.exists():
        new = pd.concat([pd.read_parquet(paths.android_reviews), new])
    df = new.drop_duplicates("review_id").sort_values("date")
    df.to_parquet(paths.android_reviews)
    return df


def parse_args():
    p = argparse.ArgumentParser(description="Descarga reseñas de Google Play para una empresa.")
    p.add_argument("--name", required=True, help="Nombre de la empresa/app (define la carpeta data/<name>/)")
    p.add_argument("--pkg", default=None, help="package name de la app en Google Play (omitir si ya está en common/companies.csv)")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()

    pkg = args.pkg
    if pkg is None:
        known = companies.lookup(args.name)
        pkg = known["pkg"] if known else None
        if pkg is None:
            raise SystemExit(f"No tengo pkg para '{args.name}'. Pasá --pkg la primera vez.")
        print(f"Usando pkg guardado para '{args.name}': {pkg}")
    else:
        known = companies.lookup(args.name) or {"app_ios": None}
        companies.upsert(args.name, known.get("app_ios"), pkg)

    paths = Paths(args.name)
    df = update(paths, pkg)
    print(f"{len(df)} reseñas de Android -> {paths.android_reviews.resolve()}")

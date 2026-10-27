"""
Fuente 3: rating oficial agregado por tienda (iTunes lookup API + ficha de
Google Play), para una empresa. Calculado sobre TODAS las calificaciones
(toquen estrellas o escriban texto) — a diferencia de las otras dos fuentes,
que solo pueden traer reseñas con texto y están sesgadas hacia quejas.

Uso: python 02_data_understanding/collect_store_ratings.py --name <empresa>
Escribe data/<empresa>/02_data_understanding/store_ratings_<empresa>.json
"""
import argparse
import json
import sys
from pathlib import Path

import requests
from google_play_scraper import app as gp_app

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "common"))
from config import Paths  # noqa: E402
import companies_registry as companies  # noqa: E402


def fetch_store_ratings(app_ios: int | None, pkg: str | None, country="ar", lang="es") -> dict:
    ios_stats = {"score": None, "ratings_count": None}
    if app_ios:
        ios = requests.get(f"https://itunes.apple.com/lookup?id={app_ios}&country={country}", timeout=15).json()
        ios_result = (ios.get("results") or [{}])[0]
        ios_stats = {"score": ios_result.get("averageUserRating"), "ratings_count": ios_result.get("userRatingCount")}

    android_stats = {"score": None, "ratings_count": None}
    if pkg:
        android = gp_app(pkg, lang=lang, country=country)
        android_stats = {"score": android.get("score"), "ratings_count": android.get("ratings")}

    return {"ios": ios_stats, "android": android_stats}


def parse_args():
    p = argparse.ArgumentParser(description="Descarga el rating oficial agregado por tienda para una empresa.")
    p.add_argument("--name", required=True, help="Nombre de la empresa/app (debe tener app_ios y/o pkg en data/companies.csv)")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()

    known = companies.lookup(args.name)
    if known is None:
        raise SystemExit(f"No conozco a '{args.name}' en data/companies.csv. Correr primero collect_ios_reviews.py o collect_android_reviews.py.")

    paths = Paths(args.name)
    paths.ensure_dirs()
    ratings = fetch_store_ratings(known["app_ios"], known["pkg"])
    paths.store_ratings_json.write_text(json.dumps(ratings, indent=2))
    print(ratings)
    print(f"Guardado en {paths.store_ratings_json.resolve()}")

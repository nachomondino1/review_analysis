import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd
import requests
from google_play_scraper import Sort, app as gp_app, reviews

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from config import Paths  # noqa: E402


def fetch_ios(app_id: int, country="ar", pages=10) -> pd.DataFrame:
    rows = []
    for p in range(1, pages + 1):
        url = (f"https://itunes.apple.com/{country}/rss/customerreviews/"
               f"page={p}/id={app_id}/sortby=mostrecent/json")
        r = requests.get(url, timeout=15)
        if r.status_code != 200:
            break
        entries = r.json().get("feed", {}).get("entry", [])
        if isinstance(entries, dict):
            entries = [entries]
        for e in entries:
            if "im:rating" not in e:  # la 1ra entry a veces es metadata de la app
                continue
            rows.append({
                "review_id": e["id"]["label"],
                "store": "ios",
                "date": e["updated"]["label"],
                "rating": int(e["im:rating"]["label"]),
                "text": e["content"]["label"],
                "version": e["im:version"]["label"],
            })
        time.sleep(1)
    return pd.DataFrame(rows)


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


def fetch_store_ratings(app_ios: int, pkg: str, country="ar", lang="es") -> dict:
    """
    Rating/conteo oficial agregado de cada tienda, calculado sobre TODAS las
    calificaciones (toquen estrellas o escriban texto). Separado de las reseñas
    scrapeadas a propósito: el scraping solo puede leer reseñas con texto,
    ordenadas por más recientes, y esa muestra está sesgada hacia quejas (quien
    solo puso estrellas y no escribió nunca entra al dataset de texto). Mostrar
    el % de negativas de la muestra como si fuera el rating real del público
    general es engañoso.
    """
    ios = requests.get(f"https://itunes.apple.com/lookup?id={app_ios}&country={country}", timeout=15).json()
    ios_result = (ios.get("results") or [{}])[0]

    android = gp_app(pkg, lang=lang, country=country)

    return {
        "ios": {
            "score": ios_result.get("averageUserRating"),
            "ratings_count": ios_result.get("userRatingCount"),
        },
        "android": {
            "score": android.get("score"),
            "ratings_count": android.get("ratings"),
        },
    }


def update(paths: Paths, app_ios: int, pkg: str) -> pd.DataFrame:
    new = pd.concat([fetch_ios(app_ios), fetch_android(pkg)], ignore_index=True)
    new["date"] = pd.to_datetime(new["date"], utc=True)
    paths.ensure_dirs()
    if paths.reviews.exists():
        new = pd.concat([pd.read_parquet(paths.reviews), new])
    df = new.drop_duplicates("review_id").sort_values("date")
    df.to_parquet(paths.reviews)
    return df


def parse_args():
    p = argparse.ArgumentParser(description="Descarga reseñas de App Store + Google Play para una empresa.")
    p.add_argument("--name", required=True, help="Nombre de la empresa/app (define la carpeta data/<name>/)")
    p.add_argument("--app-ios", type=int, required=True, help="id numérico de la app en App Store")
    p.add_argument("--pkg", required=True, help="package name de la app en Google Play")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    paths = Paths(args.name)
    df = update(paths, app_ios=args.app_ios, pkg=args.pkg)
    print(df.groupby("store").size())
    print(f"Guardado en {paths.reviews.resolve()}")

    ratings = fetch_store_ratings(args.app_ios, args.pkg)
    paths.store_ratings_json.write_text(json.dumps(ratings, indent=2))
    print(ratings)
    print(f"Guardado en {paths.store_ratings_json.resolve()}")

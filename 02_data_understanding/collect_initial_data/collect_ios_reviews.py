"""
Fuente 1: reseñas de App Store (RSS, con texto), para una empresa.

Uso: python 02_data_understanding/collect_ios_reviews.py --name <empresa> [--app-ios <id>]
Escribe data/<empresa>/02_data_understanding/ios_<empresa>.parquet
"""
import argparse
import sys
import time
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "common"))
from config import Paths  # noqa: E402
import companies_registry as companies  # noqa: E402


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


def update(paths: Paths, app_ios: int, country="ar") -> pd.DataFrame:
    new = fetch_ios(app_ios, country=country)
    if not new.empty:
        new["date"] = pd.to_datetime(new["date"], utc=True)
    paths.ensure_dirs()
    if paths.ios_reviews.exists():
        new = pd.concat([pd.read_parquet(paths.ios_reviews), new])
    df = new.drop_duplicates("review_id").sort_values("date")
    df.to_parquet(paths.ios_reviews)
    return df


def parse_args():
    p = argparse.ArgumentParser(description="Descarga reseñas de App Store para una empresa.")
    p.add_argument("--name", required=True, help="Nombre de la empresa/app (define la carpeta data/<name>/)")
    p.add_argument("--app-ios", type=int, default=None, help="id numérico de la app en App Store (omitir si ya está en data/companies.csv)")
    p.add_argument("--country", default="ar", help="país del RSS de reseñas (default: ar). Usar otro si la app no tiene reseñas en el store argentino.")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()

    app_ios = args.app_ios
    if app_ios is None:
        known = companies.lookup(args.name)
        app_ios = known["app_ios"] if known else None
        if app_ios is None:
            raise SystemExit(f"No tengo app_ios para '{args.name}'. Pasá --app-ios la primera vez.")
        print(f"Usando app_ios guardado para '{args.name}': {app_ios}")
    else:
        known = companies.lookup(args.name) or {"pkg": None}
        companies.upsert(args.name, app_ios, known.get("pkg"))

    paths = Paths(args.name)
    df = update(paths, app_ios, country=args.country)
    print(f"{len(df)} reseñas de iOS -> {paths.ios_reviews.resolve()}")

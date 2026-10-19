"""
Registro de empresas/apps ya analizadas: evita tener que volver a buscar en
las tiendas el id de App Store / package de Google Play cada vez que se
retoma una empresa. Fuente de verdad chica, versionada (CSV, editable a mano).
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
COMPANIES_CSV = ROOT / "common" / "companies.csv"
COLUMNS = ["name", "app_ios", "pkg"]


def load() -> pd.DataFrame:
    if not COMPANIES_CSV.exists():
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_csv(COMPANIES_CSV, dtype={"name": str, "pkg": str})


def lookup(name: str) -> dict | None:
    df = load()
    match = df[df["name"].str.lower() == name.lower()]
    if match.empty:
        return None
    row = match.iloc[0]
    app_ios = row["app_ios"]
    return {
        "app_ios": int(app_ios) if pd.notna(app_ios) else None,
        "pkg": row["pkg"] if pd.notna(row["pkg"]) else None,
    }


def upsert(name: str, app_ios: int | None, pkg: str | None) -> None:
    df = load()
    mask = df["name"].str.lower() == name.lower()
    if mask.any():
        df.loc[mask, "app_ios"] = app_ios
        df.loc[mask, "pkg"] = pkg
    else:
        df = pd.concat([df, pd.DataFrame([{"name": name, "app_ios": app_ios, "pkg": pkg}])], ignore_index=True)
    df = df.sort_values("name")
    COMPANIES_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(COMPANIES_CSV, index=False)

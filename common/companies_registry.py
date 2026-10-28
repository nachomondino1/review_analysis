"""
Registro de empresas/apps ya analizadas: evita tener que volver a buscar en
las tiendas el id de App Store / package de Google Play cada vez que se
retoma una empresa. Fuente de verdad chica, versionada (CSV, editable a mano).
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
COMPANIES_CSV = ROOT / "data" / "companies.csv"
COLUMNS = ["name", "app_ios", "pkg", "domain"]


def load() -> pd.DataFrame:
    if not COMPANIES_CSV.exists():
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_csv(COMPANIES_CSV, dtype={"name": str, "pkg": str, "app_ios": "Int64"})
    if "domain" not in df.columns:
        df["domain"] = pd.NA
    return df


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
        "domain": row["domain"] if pd.notna(row["domain"]) else None,
    }


def upsert(name: str, app_ios: int | None, pkg: str | None, domain: str | None = None) -> None:
    """
    `domain` es opcional y solo se pisa si se pasa explícitamente (default
    None no borra un domain ya cargado a mano) — collect_*.py siguen
    llamando a upsert() sin ese argumento, y no deben pisarlo con None cada
    vez que corren.
    """
    df = load()
    mask = df["name"].str.lower() == name.lower()
    if mask.any():
        df.loc[mask, "app_ios"] = app_ios
        df.loc[mask, "pkg"] = pkg
        if domain is not None:
            df.loc[mask, "domain"] = domain
    else:
        df = pd.concat([df, pd.DataFrame([{"name": name, "app_ios": app_ios, "pkg": pkg, "domain": domain}])], ignore_index=True)
    df["app_ios"] = df["app_ios"].astype("Int64")  # entero nullable: evita que un NaN en otra fila fuerce float (1221006761.0)
    df = df.sort_values("name")
    COMPANIES_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(COMPANIES_CSV, index=False)

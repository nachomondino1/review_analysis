import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not slug:
        raise ValueError(f"nombre de empresa inválido: {name!r}")
    return slug


class Paths:
    def __init__(self, empresa: str):
        self.slug = slugify(empresa)
        self.base = ROOT / "data" / self.slug
        self.reviews = self.base / "reviews.parquet"
        self.output_dir = self.base / "output"
        self.reviews_enriched_parquet = self.output_dir / "reviews_enriched.parquet"
        self.reviews_enriched_csv = self.output_dir / "reviews_enriched.csv"
        self.topics_summary_csv = self.output_dir / "topics_summary.csv"

    def ensure_dirs(self):
        self.output_dir.mkdir(parents=True, exist_ok=True)

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
        self.reviews_clean = self.base / "reviews_clean.parquet"
        self.output_dir = self.base / "output"
        self.reviews_enriched_parquet = self.output_dir / "reviews_enriched.parquet"
        self.reviews_enriched_csv = self.output_dir / "reviews_enriched.csv"
        self.topics_summary_csv = self.output_dir / "topics_summary.csv"
        self.topic_samples_json = self.output_dir / "topic_samples.json"
        self.topics_named_json = self.output_dir / "topics_named.json"
        self.sentiment_by_month_csv = self.output_dir / "sentiment_by_month.csv"
        self.store_comparison_csv = self.output_dir / "store_comparison.csv"
        self.site_dir = ROOT / "site" / self.slug
        self.site_html = self.site_dir / "index.html"

    def ensure_dirs(self):
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def ensure_site_dir(self):
        self.site_dir.mkdir(parents=True, exist_ok=True)

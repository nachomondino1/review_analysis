import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not slug:
        raise ValueError(f"nombre de empresa inválido: {name!r}")
    return slug


class Paths:
    """
    Paths de una empresa, en espejo de las fases del repo (CRISP-DM):
    data/<empresa>/<fase>/archivo — cada fase agrega sus propios archivos a su
    propia carpeta, nunca a una carpeta "output" compartida que crece sin límite
    a medida que se suman fases o empresas.
    """

    def __init__(self, empresa: str):
        self.slug = slugify(empresa)
        self.base = ROOT / "data" / self.slug

        self.understanding_dir = self.base / "01_data_understanding"
        self.preparation_dir = self.base / "02_data_preparation"
        self.modeling_dir = self.base / "03_modeling"
        self.evaluation_dir = self.base / "04_evaluation"

        self.reviews = self.understanding_dir / "reviews.parquet"
        self.store_ratings_json = self.understanding_dir / "store_ratings.json"
        self.reviews_clean = self.preparation_dir / "reviews_clean.parquet"
        self.reviews_enriched_parquet = self.modeling_dir / "reviews_enriched.parquet"
        self.reviews_enriched_csv = self.modeling_dir / "reviews_enriched.csv"
        self.topics_summary_csv = self.modeling_dir / "topics_summary.csv"
        self.topic_samples_json = self.evaluation_dir / "topic_samples.json"
        self.topics_named_json = self.evaluation_dir / "topics_named.json"
        self.sentiment_by_month_csv = self.evaluation_dir / "sentiment_by_month.csv"
        self.store_comparison_csv = self.evaluation_dir / "store_comparison.csv"
        self.version_breakout_json = self.evaluation_dir / "version_breakout.json"

        # En la raíz del repo (no bajo 05_deployment/) porque GitHub Pages
        # "clásico" (deploy from branch) solo sirve desde la raíz o /docs,
        # nunca una carpeta anidada — ver DECISIONS/APRENDIZAJES.
        self.site_dir = ROOT / "site"
        self.site_html = self.site_dir / f"{self.slug}.html"

    def ensure_dirs(self):
        for d in (self.understanding_dir, self.preparation_dir, self.modeling_dir, self.evaluation_dir):
            d.mkdir(parents=True, exist_ok=True)

    def ensure_site_dir(self):
        self.site_dir.mkdir(parents=True, exist_ok=True)

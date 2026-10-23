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

        self.understanding_dir = self.base / "02_data_understanding"
        self.preparation_dir = self.base / "03_data_preparation"
        self.modeling_dir = self.base / "04_modeling"

        # Una fuente = un archivo, nombrado "<fuente>_<empresa>.<formato>" (ver
        # 02_data_understanding/collect_*.py): cada script de collect toca un
        # solo archivo, nunca pisa el de otra fuente.
        self.ios_reviews = self.understanding_dir / f"ios_{self.slug}.parquet"
        self.android_reviews = self.understanding_dir / f"android_{self.slug}.parquet"
        self.store_ratings_json = self.understanding_dir / f"store_ratings_{self.slug}.json"

        # 03_data_preparation, en orden de pipeline:
        self.integrated = self.preparation_dir / f"integrated_{self.slug}.parquet"    # ios_reviews + android_reviews juntas (integrate_data.py)
        self.constructed = self.preparation_dir / f"constructed_{self.slug}.parquet"  # + month/text_length/rating_bucket (construct_data.py)
        self.reviews_clean = self.preparation_dir / "reviews_clean.parquet"           # constructed sin reseñas sin señal real (clean_reviews.py)
        self.reviews_enriched_parquet = self.modeling_dir / "reviews_enriched.parquet"
        self.reviews_enriched_csv = self.modeling_dir / "reviews_enriched.csv"
        self.topics_summary_csv = self.modeling_dir / "topics_summary.csv"
        # Hallazgos derivados del modelo (nombrado de tópicos, tendencia, quiebre
        # de versión): siguen operando sobre la salida de model.py, no evalúan
        # nada contra un criterio de negocio — por eso viven en 04_modeling, no
        # en una fase "04_evaluation" que terminaba sin nada propio adentro.
        self.topic_samples_json = self.modeling_dir / "topic_samples.json"
        self.topics_named_json = self.modeling_dir / "topics_named.json"
        self.sentiment_by_month_csv = self.modeling_dir / "sentiment_by_month.csv"
        self.store_comparison_csv = self.modeling_dir / "store_comparison.csv"
        self.version_breakout_json = self.modeling_dir / "version_breakout.json"

        # En la raíz del repo (no bajo 06_deployment/) porque GitHub Pages
        # "clásico" (deploy from branch) solo sirve desde la raíz o /docs,
        # nunca una carpeta anidada — ver DECISIONS/APRENDIZAJES.
        self.site_dir = ROOT / "site"
        self.site_html = self.site_dir / f"{self.slug}.html"

    def ensure_dirs(self):
        for d in (self.understanding_dir, self.preparation_dir, self.modeling_dir):
            d.mkdir(parents=True, exist_ok=True)

    def ensure_site_dir(self):
        self.site_dir.mkdir(parents=True, exist_ok=True)

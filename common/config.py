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

        # 02_data_understanding se divide en dos carpetas (mismo criterio que
        # los scripts: collect_initial_data/ ya existe como carpeta de
        # scripts, acá es su contraparte de datos; describe_data/ para lo que
        # describe_data.py documenta sobre esos datos crudos).
        self.collect_dir = self.understanding_dir / "collect_initial_data"
        self.describe_dir = self.understanding_dir / "describe_data"

        # Una fuente = un archivo, nombrado "<fuente>_<empresa>.<formato>" (ver
        # 02_data_understanding/collect_*.py): cada script de collect toca un
        # solo archivo, nunca pisa el de otra fuente.
        self.ios_reviews = self.collect_dir / f"ios_{self.slug}.parquet"
        self.android_reviews = self.collect_dir / f"android_{self.slug}.parquet"
        self.store_ratings_json = self.collect_dir / f"store_ratings_{self.slug}.json"

        # 03_data_preparation, en orden de pipeline (flat: son solo 3 archivos
        # con nombres ya bien descriptivos, no hace falta subdividir):
        self.integrated = self.preparation_dir / f"integrated_{self.slug}.parquet"    # ios_reviews + android_reviews juntas (integrate_data.py)
        self.constructed = self.preparation_dir / f"constructed_{self.slug}.parquet"  # + month/text_length/rating_bucket (construct_data.py)
        self.reviews_clean = self.preparation_dir / "reviews_clean.parquet"           # constructed sin reseñas sin señal real (clean_reviews.py)

        # 04_modeling se divide en dos carpetas según qué pregunta responden:
        # topics/ = "de qué hablan las reseñas y qué tan grave es cada tema"
        # (01_analyze_sentiment_topics.py -> 02_refine_topic_sentiment.py ->
        # 03_topics_enrich.py export/merge, en ese orden); trends/ = "cómo viene
        # cambiando en el tiempo" (trends.py, version_breakout.py — ambos
        # opcionales y leen reviews_enriched.parquet, no dependen de
        # 03_topics_enrich.py). Ningún otro criterio de corte (por tipo de
        # archivo, por fecha) separa tan bien "qué" de "cuándo".
        self.topics_dir = self.modeling_dir / "topics"
        self.trends_dir = self.modeling_dir / "trends"

        self.reviews_enriched_parquet = self.topics_dir / "reviews_enriched.parquet"
        self.reviews_enriched_csv = self.topics_dir / "reviews_enriched.csv"
        self.topics_summary_csv = self.topics_dir / "topics_summary.csv"
        self.topic_samples_json = self.topics_dir / "topic_samples.json"
        self.topics_named_json = self.topics_dir / "topics_named.json"
        self.review_audit_csv = self.topics_dir / "review_audit.csv"  # para QA manual (ver 05_export_review_audit.py), una fila por oración
        self.review_audit_stats_json = self.topics_dir / "review_audit_stats.json"  # cobertura de categorización, mismo script

        self.sentiment_by_month_csv = self.trends_dir / "sentiment_by_month.csv"
        self.store_comparison_csv = self.trends_dir / "store_comparison.csv"
        self.version_breakout_json = self.trends_dir / "version_breakout.json"

        # En la raíz del repo (no bajo 06_deployment/) porque GitHub Pages
        # "clásico" (deploy from branch) solo sirve desde la raíz o /docs,
        # nunca una carpeta anidada — ver DECISIONS/APRENDIZAJES.
        self.site_dir = ROOT / "site"
        self.site_html = self.site_dir / f"{self.slug}.html"

    def ensure_dirs(self):
        for d in (self.collect_dir, self.describe_dir, self.preparation_dir, self.topics_dir, self.trends_dir):
            d.mkdir(parents=True, exist_ok=True)

    def ensure_site_dir(self):
        self.site_dir.mkdir(parents=True, exist_ok=True)

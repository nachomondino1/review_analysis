"""
Genera un único HTML autocontenido con el análisis de una empresa, para
compartir por link/archivo (sin backend, sin build step).

Uso: python 05_deployment/dashboard.py --name <empresa>
Lee los outputs de 03_modeling y 04_evaluation; escribe site/<empresa>.html
y regenera index.html en la raíz del repo con el listado de empresas
(para que GitHub Pages lo muestre como home del dominio).
"""
import argparse
import html
import json
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "01_data_understanding"))
from config import Paths, ROOT  # noqa: E402
import companies  # noqa: E402
from collect_data import fetch_store_ratings  # noqa: E402

SEVERITY_LABEL = {"alta": "Alta", "media": "Media", "baja": "Baja"}
TOP_FINDINGS_MAX = 6
SAMPLES_PER_FINDING = 2


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def load_data(paths: Paths):
    summary = pd.read_csv(paths.topics_summary_csv)
    reviews = pd.read_parquet(paths.reviews_enriched_parquet)
    store_ratings = json.loads(paths.store_ratings_json.read_text()) if paths.store_ratings_json.exists() else None
    return summary, reviews, store_ratings


def build_official_rating(store_ratings: dict | None) -> dict | None:
    """
    Rating ponderado sobre TODAS las calificaciones de las tiendas (toquen
    estrellas o no escriban texto) — no se puede derivar de `summary`, que solo
    cubre la muestra de reseñas con texto que el scraping puede leer.
    """
    if not store_ratings:
        return None
    rows = [r for r in store_ratings.values() if r.get("score") and r.get("ratings_count")]
    if not rows:
        return None
    total = sum(r["ratings_count"] for r in rows)
    weighted = sum(r["score"] * r["ratings_count"] for r in rows) / total
    return {"score": round(weighted, 2), "count": total}


STORE_LABEL = {"ios": "App Store", "android": "Google Play"}


def build_version_breakout_section(paths: Paths) -> str:
    """
    Si 04_evaluation/version_breakout.py encontró un quiebre real (ver ese
    script para la metodología), lo muestra como un hecho concreto y citable
    ("se rompió en la v5.45.0, no 'empeoró este trimestre'") — más difícil de
    replicar al toque que un resumen genérico, porque exige cruzar sentimiento
    con la columna `version` y descartar ruido de volumen bajo.
    """
    if not paths.version_breakout_json.exists():
        return ""
    breakout = json.loads(paths.version_breakout_json.read_text())
    if not breakout:
        return ""

    store_label = STORE_LABEL.get(breakout["store"], breakout["store"])
    note = (
        f"La versión {breakout['version']} de {store_label} (lanzada ~{breakout['release_approx']}) "
        f"marca un quiebre real: pasó de {breakout['pct_neg_before']}% a {breakout['pct_neg_version']}% "
        f"de reseñas negativas (+{breakout['delta']} puntos porcentuales), sobre {breakout['n_version']} "
        f"reseñas de esa versión y {breakout['n_before']} previas."
    )
    return f'<div class="trend-banner trend-bad">{esc(note)}</div>'


def build_competitor_section(official: dict | None, empresa_display: str, competitor_name: str) -> str:
    """
    Compara el rating oficial de la empresa contra un competidor puntual
    (ids ya cargados en common/companies.csv). Es trabajo específico para
    esta empresa, no reciclable al toque para otra: justamente por eso sirve
    como evidencia de que el análisis no es una plantilla mandada a todos.
    """
    if not official:
        return ""
    comp = companies.lookup(competitor_name)
    if comp is None or (comp["app_ios"] is None and comp["pkg"] is None):
        return ""
    comp_official = build_official_rating(fetch_store_ratings(comp["app_ios"], comp["pkg"]))
    if not comp_official:
        return ""

    diff = official["score"] - comp_official["score"]
    competitor_display = competitor_name.title()
    if diff >= 0.1:
        note_class, note = "trend-good", f"{empresa_display} califica {diff:.1f} puntos mejor que {competitor_display}"
    elif diff <= -0.1:
        note_class, note = "trend-bad", f"{empresa_display} califica {abs(diff):.1f} puntos peor que {competitor_display}"
    else:
        note_class, note = "trend-flat", f"{empresa_display} y {competitor_display} califican parecido"

    html_out = f'''
    <div class="recency-grid">
      <div class="recency-card">
        <div class="recency-label">{esc(empresa_display)}</div>
        <div class="recency-value">{official["score"]}★</div>
        <div class="recency-sub">{official["count"]:,} calificaciones</div>
      </div>
      <div class="recency-arrow">vs.</div>
      <div class="recency-card">
        <div class="recency-label">{esc(competitor_display)}</div>
        <div class="recency-value">{comp_official["score"]}★</div>
        <div class="recency-sub">{comp_official["count"]:,} calificaciones</div>
      </div>
    </div>
    <div class="trend-banner {note_class}">{esc(note)}</div>
    '''
    return html_out.replace(",", ".")  # miles con punto, consistente con el resto del dashboard


def build_summary_stats(summary: pd.DataFrame) -> dict:
    real = summary[~summary["is_outlier"]]
    total_n = int(summary["n"].sum())
    pct_neg = round(float((summary["pct_neg"] * summary["n"]).sum() / total_n * 100), 1)
    n_findings = int((real["severity"].isin(["alta", "media"])).sum())
    return {
        "total_n": total_n,
        "pct_neg": pct_neg,
        "n_findings": n_findings,
    }


def build_findings(summary: pd.DataFrame, reviews: pd.DataFrame) -> list[dict]:
    real = summary[~summary["is_outlier"]].copy()
    real["_priority"] = real["n"] * real["pct_neg"]
    real = real[real["severity"].isin(["alta", "media"])].sort_values("_priority", ascending=False)
    real = real.head(TOP_FINDINGS_MAX)

    findings = []
    for _, row in real.iterrows():
        topic_reviews = reviews[reviews["topic"] == row["topic"]]
        neg = topic_reviews[topic_reviews["sentiment"] == "NEG"]["text"].dropna()
        samples = (neg if len(neg) >= SAMPLES_PER_FINDING else topic_reviews["text"].dropna()).head(SAMPLES_PER_FINDING).tolist()
        findings.append({
            "name": row["name"],
            "summary": row["summary"],
            "recommendation": row["recommendation"],
            "severity": row["severity"],
            "n": int(row["n"]),
            "pct_neg": round(float(row["pct_neg"]) * 100, 1),
            "samples": samples,
        })
    return findings


RECENT_MONTHS = 3
MIN_SAMPLE_FOR_COMPARISON = 5  # con menos reseñas, el % no es confiable para comparar
TREND_THRESHOLD_PTS = 3  # diferencia de puntos porcentuales para no llamarlo "estable"


def build_recency_comparison(reviews: pd.DataFrame) -> str:
    """
    Responde "¿cómo vienen las reseñas últimamente respecto de siempre?" de
    forma directa: últimos N meses vs. histórico completo, con un chip que dice
    explícitamente si mejoró o empeoró (en vez de un gráfico de línea donde
    "sube" es ambiguo — ¿sube el % de negativas, que es malo, o sube el
    rating, que es bueno? — confuso incluso con eje bien etiquetado).
    """
    if reviews is None or reviews.empty or "date" not in reviews.columns:
        return ""

    dates = pd.to_datetime(reviews["date"], utc=True)
    cutoff = dates.max() - pd.DateOffset(months=RECENT_MONTHS)
    recent = reviews[dates >= cutoff]
    if len(recent) < MIN_SAMPLE_FOR_COMPARISON or len(reviews) < MIN_SAMPLE_FOR_COMPARISON:
        return ""

    def stats(df):
        return {
            "n": len(df),
            "rating": round(float(df["rating"].mean()), 2),
            "pct_neg": round(float((df["sentiment"] == "NEG").mean() * 100), 1),
        }

    recent_s, all_s = stats(recent), stats(reviews)
    delta = recent_s["pct_neg"] - all_s["pct_neg"]  # positivo = empeoró (más % negativas)

    if delta <= -TREND_THRESHOLD_PTS:
        trend_class, trend_label = "trend-good", f"Mejorando: {abs(delta):.1f} puntos porcentuales menos reseñas negativas que el histórico"
    elif delta >= TREND_THRESHOLD_PTS:
        trend_class, trend_label = "trend-bad", f"Empeorando: {delta:.1f} puntos porcentuales más reseñas negativas que el histórico"
    else:
        trend_class, trend_label = "trend-flat", "Estable respecto del histórico"

    return f'''
    <div class="recency-grid">
      <div class="recency-card">
        <div class="recency-label">Últimos {RECENT_MONTHS} meses</div>
        <div class="recency-value">{recent_s["rating"]}★</div>
        <div class="recency-sub">{recent_s["pct_neg"]}% negativas · {recent_s["n"]} reseñas</div>
      </div>
      <div class="recency-arrow">vs.</div>
      <div class="recency-card">
        <div class="recency-label">Histórico completo</div>
        <div class="recency-value">{all_s["rating"]}★</div>
        <div class="recency-sub">{all_s["pct_neg"]}% negativas · {all_s["n"]} reseñas</div>
      </div>
    </div>
    <div class="trend-banner {trend_class}">{esc(trend_label)}</div>
    '''


def build_table_rows(summary: pd.DataFrame) -> str:
    ordered = summary.sort_values(["is_outlier", "pct_neg"], ascending=[True, False])
    rows = []
    for _, row in ordered.iterrows():
        name = row["name"] if pd.notna(row["name"]) and row["name"] else row["Name"]
        severity = row["severity"] if pd.notna(row["severity"]) and row["severity"] else "-"
        rows.append(
            f"<tr><td>{esc(name)}</td><td class='num'>{int(row['n'])}</td>"
            f"<td class='num'>{round(float(row['rating']), 2)}</td>"
            f"<td class='num'>{round(float(row['pct_neg']) * 100, 1)}%</td>"
            f"<td>{esc(severity)}</td></tr>"
        )
    return "".join(rows)


SEVERITY_CLASS = {"alta": "sev-alta", "media": "sev-media", "baja": "sev-baja"}


def render_findings_html(findings: list[dict]) -> str:
    cards = []
    for f in findings:
        samples_html = "".join(f"<li>“{esc(s)}”</li>" for s in f["samples"])
        cards.append(f'''
        <article class="finding-card">
          <div class="finding-head">
            <h3>{esc(f["name"])}</h3>
            <span class="chip {SEVERITY_CLASS.get(f["severity"], "")}">{esc(SEVERITY_LABEL.get(f["severity"], f["severity"]))}</span>
          </div>
          <p class="finding-meta">{f["n"]} reseñas · {f["pct_neg"]}% negativas</p>
          <p>{esc(f["summary"])}</p>
          <p class="recommendation"><strong>Recomendación:</strong> {esc(f["recommendation"])}</p>
          {f"<ul class='samples'>{samples_html}</ul>" if samples_html else ""}
        </article>
        ''')
    return "".join(cards)


TEMPLATE = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Análisis de reseñas — {empresa}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet" media="print" onload="this.media='all'">
<style>
:root {{
  --bg: #fafaf8;
  --bg-subtle: #f2f1ed;
  --surface: #ffffff;
  --text: #1a1a17;
  --muted: #6f6d67;
  --muted-soft: #a19e96;
  --border: #e4e2dc;
  --border-soft: #ecebe6;
  --accent: #2f6f62;
  --accent-soft: color-mix(in srgb, var(--accent) 12%, transparent);
  --accent-contrast: #ffffff;
  --good: #16a34a; --warn: #d97706; --bad: #dc2626;
  --radius-sm: 8px; --radius: 12px; --radius-lg: 16px;
  --shadow-xs: 0 1px 2px rgba(20,19,15,.05);
  --shadow-sm: 0 1px 3px rgba(20,19,15,.06), 0 1px 2px rgba(20,19,15,.04);
  --shadow-lg: 0 18px 32px -10px rgba(20,19,15,.16), 0 4px 10px rgba(20,19,15,.06);
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #0f1218; --bg-subtle: #1a202b; --surface: #181e29;
    --text: #e6e8ec; --muted: #9aa3b2; --muted-soft: #6b7585;
    --border: #2a3342; --border-soft: #212836;
    --accent: #4f9686;
    --shadow-xs: 0 1px 2px rgba(0,0,0,.4);
    --shadow-sm: 0 1px 3px rgba(0,0,0,.45);
    --shadow-lg: 0 18px 32px -10px rgba(0,0,0,.6);
  }}
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0; background: var(--bg); color: var(--text);
  font-family: Inter, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  font-size: 14px; line-height: 1.55; -webkit-font-smoothing: antialiased;
}}
.container {{ max-width: 960px; margin: 0 auto; padding: 24px 24px 64px; }}
@media (max-width: 640px) {{ .container {{ padding: 16px 16px 48px; }} }}
header.page-head {{
  position: sticky; top: 0; z-index: 10; background: color-mix(in srgb, var(--bg) 85%, transparent);
  backdrop-filter: blur(14px); border-bottom: 1px solid var(--border-soft);
  padding: 16px 24px; display: flex; align-items: center; gap: 10px;
}}
@media (max-width: 640px) {{ header.page-head {{ padding: 12px 16px; }} }}
header.page-head h1 {{ font-size: 1.1rem; font-weight: 700; margin: 0; }}
header.page-head .sub {{ color: var(--muted); font-size: 0.8rem; }}
h2 {{ font-size: 1.1rem; font-weight: 700; letter-spacing: -0.01em; margin: 40px 0 16px; }}
.stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(min(150px, 100%), 1fr)); gap: 12px; margin-top: 16px; }}
.stat-card {{
  background: var(--surface); border: 1px solid var(--border-soft); border-radius: var(--radius);
  box-shadow: var(--shadow-xs); padding: 16px;
}}
.stat-card .value {{ font-size: 1.75rem; font-weight: 800; letter-spacing: -0.02em; }}
.stat-card .label {{ color: var(--muted-soft); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 700; margin-top: 4px; }}
.findings-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(min(280px, 100%), 1fr)); gap: 14px; }}
.finding-card {{
  background: var(--surface); border: 1px solid var(--border-soft); border-radius: var(--radius);
  box-shadow: var(--shadow-xs); padding: 18px;
}}
.finding-head {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; }}
.finding-head h3 {{ font-size: 1rem; font-weight: 700; margin: 0; }}
.finding-meta {{ color: var(--muted); font-size: 0.78rem; margin: 6px 0 10px; }}
.recommendation {{ background: var(--bg-subtle); border-radius: var(--radius-sm); padding: 10px 12px; margin-top: 10px; }}
.samples {{ list-style: none; padding: 0; margin: 10px 0 0; color: var(--muted); font-size: 0.85rem; }}
.samples li {{ padding: 6px 0; border-top: 1px dashed var(--border-soft); }}
.chip {{
  display: inline-block; padding: 3px 10px; border-radius: 999px; font-size: 0.68rem;
  font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; white-space: nowrap;
}}
.sev-alta {{ background: color-mix(in srgb, var(--bad) 17%, transparent); color: var(--bad); }}
.sev-media {{ background: color-mix(in srgb, var(--warn) 17%, transparent); color: var(--warn); }}
.sev-baja {{ background: var(--bg-subtle); color: var(--muted); }}
.recency-grid {{ display: flex; align-items: center; gap: 16px; margin-top: 8px; flex-wrap: wrap; }}
.recency-card {{
  background: var(--surface); border: 1px solid var(--border-soft); border-radius: var(--radius);
  box-shadow: var(--shadow-xs); padding: 16px 20px; flex: 1; min-width: 150px;
}}
.recency-label {{ color: var(--muted-soft); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 700; }}
.recency-value {{ font-size: 1.75rem; font-weight: 800; letter-spacing: -0.02em; margin-top: 4px; }}
.recency-sub {{ color: var(--muted); font-size: 0.8rem; margin-top: 4px; }}
.recency-arrow {{ color: var(--muted-soft); font-weight: 700; font-size: 0.85rem; flex: 0 0 auto; }}
.trend-banner {{
  margin-top: 12px; padding: 10px 14px; border-radius: var(--radius-sm);
  font-weight: 700; font-size: 0.85rem; white-space: normal; max-width: 100%;
}}
.trend-good {{ background: color-mix(in srgb, var(--good) 17%, transparent); color: var(--good); }}
.trend-bad {{ background: color-mix(in srgb, var(--bad) 17%, transparent); color: var(--bad); }}
.trend-flat {{ background: var(--bg-subtle); color: var(--muted); }}
details.detail-table {{ margin-top: 8px; }}
details.detail-table summary {{ cursor: pointer; font-weight: 600; padding: 8px 0; }}
.table-scroll {{ overflow-x: auto; margin-top: 8px; }}
table {{ width: 100%; min-width: 420px; border-collapse: collapse; font-size: 0.85rem; }}
th {{ background: var(--bg-subtle); text-transform: uppercase; font-size: 0.68rem; color: var(--muted); text-align: left; padding: 8px 10px; }}
td {{ padding: 8px 10px; border-top: 1px solid var(--border-soft); }}
td.num, th.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
footer {{ margin-top: 48px; padding-top: 16px; border-top: 1px solid var(--border-soft); color: var(--muted-soft); font-size: 0.78rem; }}
.empty {{ color: var(--muted); text-align: center; padding: 24px; }}
.methodology-note {{ color: var(--muted); font-size: 0.8rem; margin-top: 12px; max-width: 70ch; }}
</style>
</head>
<body>
<header class="page-head">
  <div>
    <h1>📊 {empresa}</h1>
    <div class="sub">Análisis de reseñas de usuarios · generado {fecha}</div>
  </div>
</header>
<div class="container">

  <section>
    <h2>Resumen ejecutivo</h2>
    <div class="stats-grid">
      <div class="stat-card"><div class="value">{official_rating}</div><div class="label">Rating oficial ({official_count})</div></div>
      <div class="stat-card"><div class="value">{total_n}</div><div class="label">Reseñas con texto analizadas</div></div>
      <div class="stat-card"><div class="value">{pct_neg}%</div><div class="label">Negativas en la muestra</div></div>
      <div class="stat-card"><div class="value">{n_findings}</div><div class="label">Hallazgos a atender</div></div>
    </div>
    <p class="methodology-note">El rating oficial surge de todas las calificaciones en las tiendas. El resto de las métricas de este informe se basan en una muestra de reseñas con texto, que tiende a sobre-representar quejas frente a quien solo califica con estrellas — son el insumo correcto para entender <em>qué</em> se queja la gente, no para medir la satisfacción general.</p>
  </section>

  <section>
    <h2>Principales hallazgos</h2>
    <div class="findings-grid">
      {findings_html}
    </div>
  </section>

  {trend_section}

  {competitor_section}

  <section>
    <h2>Detalle completo por tópico</h2>
    <details class="detail-table">
      <summary>Ver los {n_topics} tópicos detectados</summary>
      <div class="table-scroll">
        <table>
          <thead><tr><th>Tópico</th><th class="num">N</th><th class="num">Rating</th><th class="num">% negativas</th><th>Severidad</th></tr></thead>
          <tbody>{table_rows}</tbody>
        </table>
      </div>
    </details>
  </section>

  <footer>
    Análisis generado automáticamente a partir de reseñas públicas de App Store y Google Play.
  </footer>
</div>
</body>
</html>
"""


def render(paths: Paths, empresa_display: str, competitor: str | None = None) -> str:
    summary, reviews, store_ratings = load_data(paths)
    stats = build_summary_stats(summary)
    official = build_official_rating(store_ratings)
    findings = build_findings(summary, reviews)
    findings_html = render_findings_html(findings) or '<p class="empty">No se detectaron hallazgos negativos relevantes.</p>'
    recency_html = build_recency_comparison(reviews)
    breakout_html = build_version_breakout_section(paths)
    trend_section = (
        f'<section><h2>¿Cómo vienen últimamente?</h2>{recency_html}{breakout_html}</section>' if (recency_html or breakout_html) else ""
    )
    table_rows = build_table_rows(summary)

    competitor_html = build_competitor_section(official, empresa_display, competitor) if competitor else ""
    competitor_section = (
        f'<section><h2>Comparado con la competencia</h2>{competitor_html}</section>' if competitor_html else ""
    )

    return TEMPLATE.format(
        empresa=esc(empresa_display),
        fecha=pd.Timestamp.now().strftime("%Y-%m-%d"),
        official_rating=f'{official["score"]}★' if official else "N/D",
        official_count=f'{official["count"]:,} calificaciones'.replace(",", ".") if official else "sin dato",
        total_n=stats["total_n"],
        pct_neg=stats["pct_neg"],
        n_findings=stats["n_findings"],
        findings_html=findings_html,
        trend_section=trend_section,
        competitor_section=competitor_section,
        n_topics=len(summary),
        table_rows=table_rows,
    )


INDEX_TEMPLATE = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Análisis de reseñas — empresas</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet" media="print" onload="this.media='all'">
<style>
:root {{
  --bg: #fafaf8; --surface: #ffffff; --text: #1a1a17; --muted: #6f6d67;
  --border-soft: #ecebe6; --accent: #2f6f62; --radius: 12px;
  --shadow-xs: 0 1px 2px rgba(20,19,15,.05);
}}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg: #0f1218; --surface: #181e29; --text: #e6e8ec; --muted: #9aa3b2; --border-soft: #212836; --accent: #4f9686; }}
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--text); font-family: Inter, system-ui, sans-serif; font-size: 14px; line-height: 1.55; }}
.container {{ max-width: 640px; margin: 0 auto; padding: 32px 24px 64px; }}
h1 {{ font-size: 1.3rem; font-weight: 800; }}
ul {{ list-style: none; padding: 0; margin: 24px 0 0; display: flex; flex-direction: column; gap: 10px; }}
a.company-link {{
  display: block; background: var(--surface); border: 1px solid var(--border-soft); border-radius: var(--radius);
  box-shadow: var(--shadow-xs); padding: 14px 16px; color: var(--text); text-decoration: none; font-weight: 600;
}}
a.company-link:hover {{ border-color: var(--accent); }}
</style>
</head>
<body>
<div class="container">
  <h1>📊 Análisis de reseñas</h1>
  <ul>
    {items}
  </ul>
</div>
</body>
</html>
"""


def build_index(site_dir: Path, root: Path):
    """
    Escanea site/*.html y arma un índice con links. Se escribe en la raíz del
    repo (no en site/) para que GitHub Pages lo muestre como home del dominio
    (.../review_analysis/), que de otra forma da 404 al no haber nada ahí.
    """
    pages = sorted(site_dir.glob("*.html"))
    items = []
    for page in pages:
        match = re.search(r"<title>Análisis de reseñas — (.*?)</title>", page.read_text(encoding="utf-8"))
        name = match.group(1) if match else page.stem
        items.append(f'<li><a class="company-link" href="{site_dir.name}/{page.name}">{esc(name)}</a></li>')
    (root / "index.html").write_text(
        INDEX_TEMPLATE.format(items="\n    ".join(items)), encoding="utf-8"
    )


def parse_args():
    p = argparse.ArgumentParser(description="Genera el HTML autocontenido para compartir el análisis.")
    p.add_argument("--name", required=True, help="Nombre de la empresa/app (debe coincidir con el usado en las fases previas)")
    p.add_argument("--display-name", default=None, help="Nombre a mostrar en la web (default: --name tal cual)")
    p.add_argument("--competitor", default=None, help="Nombre de un competidor ya cargado en common/companies.csv, para comparar rating oficial")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    paths = Paths(args.name)
    html_out = render(paths, args.display_name or args.name, competitor=args.competitor)
    paths.ensure_site_dir()
    paths.site_html.write_text(html_out, encoding="utf-8")
    print(f"Guardado en {paths.site_html.resolve()}")
    build_index(paths.site_dir, ROOT)
    print(f"Índice actualizado en {(ROOT / 'index.html').resolve()}")

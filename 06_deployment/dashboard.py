"""
Genera un único HTML autocontenido con el análisis de una empresa, para
compartir por link/archivo (sin backend, sin build step).

Uso: python 06_deployment/dashboard.py --name <empresa>
Lee los outputs de 04_modeling; escribe site/<empresa>.html
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
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "02_data_understanding" / "collect_initial_data"))
from config import Paths, ROOT  # noqa: E402
import companies  # noqa: E402
from collect_store_ratings import fetch_store_ratings  # noqa: E402

SEVERITY_LABEL = {"alta": "Alta", "media": "Media", "baja": "Baja"}
TOP_FINDINGS_MAX = 3  # minimalismo: 3 hallazgos que se leen, no 6 que se scrollean
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


IOS_RSS_PAGE_CAP = 500  # itunes.apple.com/.../rss/customerreviews pagina hasta 10 páginas de 50 y no da más


def build_ios_cap_note(reviews: pd.DataFrame, store_ratings: dict | None) -> str:
    """
    La RSS pública de reseñas de iOS (ver collect_ios_reviews.py) tiene un
    techo duro de ~500 reseñas con texto, venga o no venga acompañado de
    más — a diferencia de Android, donde reviews_all() trae todas las
    disponibles. Si iOS pegó en ese techo, el "solo estrellas" de la barra
    de arriba está inflado: una parte de ese resto puede tener texto
    también, simplemente no lo podemos leer.
    """
    if reviews is None or "store" not in reviews.columns or not store_ratings:
        return ""
    ios_n = int((reviews["store"] == "ios").sum())
    ios_official = (store_ratings.get("ios") or {}).get("ratings_count")
    if not ios_official or ios_n < IOS_RSS_PAGE_CAP * 0.9 or ios_official <= ios_n:
        return ""
    ios_official_fmt = f'{ios_official:,}'.replace(",", ".")
    return (
        f'<p class="methodology-note">⚠️ La API pública de reseñas de iOS solo deja leer las últimas '
        f'~{IOS_RSS_PAGE_CAP}, aunque haya más: de las {ios_official_fmt} calificaciones de iOS, este '
        f'análisis pudo leer el texto de {ios_n}. Una parte del resto puede tener texto también — no '
        f'figuran acá porque la tienda no las deja leer, no porque no existan. Android no tiene ese '
        f'límite (se leyeron todas las disponibles).</p>'
    )


def build_composition_bar(official: dict | None, total_n: int, ios_cap_note: str = "") -> str:
    """
    De todas las calificaciones de las tiendas, cuántas traen texto (la única
    porción que este análisis puede leer) y cuántas son solo estrellas —
    bien grande y visual, para que el % de negativas de más abajo no se lea
    como si describiera a todos los usuarios, sino solo a esta porción, y
    para que quede clarísimo cuál de las dos es la que se analiza después.
    """
    if not official or not official.get("count"):
        return ""
    total_official = official["count"]
    pct_text = max(0.0, min(100.0, round(total_n / total_official * 100, 1)))
    pct_no_text = round(100 - pct_text, 1)
    n_no_text = total_official - total_n
    total_n_fmt = f'{total_n:,}'.replace(",", ".")
    n_no_text_fmt = f'{n_no_text:,}'.replace(",", ".")
    total_official_fmt = f'{total_official:,}'.replace(",", ".")

    return f'''
    <div class="composition">
      <p class="composition-intro">De las <strong>{total_official_fmt} reseñas</strong>, algunas tienen texto y otras no:</p>
      <div class="composition-stats">
        <div class="comp-stat comp-stat--text">
          <div class="comp-pct">{pct_text}%</div>
          <div class="comp-label">📝 Con texto ({total_n_fmt} reseñas)</div>
        </div>
        <div class="comp-stat comp-stat--notext">
          <div class="comp-pct">{pct_no_text}%</div>
          <div class="comp-label">⭐ Solo estrellas ({n_no_text_fmt} reseñas)</div>
        </div>
      </div>
      <div class="composition-bar">
        <div class="composition-fill composition-fill--text" style="width:{pct_text}%"></div>
        <div class="composition-fill composition-fill--notext" style="width:{pct_no_text}%"></div>
      </div>
      <p class="composition-callout">👇 A partir de acá, el análisis usa <strong>solo el {pct_text}% que tiene texto</strong> ({total_n_fmt} reseñas) — es la única porción que se puede leer.</p>
      {ios_cap_note}
    </div>
    '''


STORE_LABEL = {"ios": "App Store", "android": "Google Play"}


def build_version_breakout_section(paths: Paths) -> str:
    """
    Si 04_modeling/version_breakout.py encontró un quiebre real (ver ese
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
        f"Desde la versión {breakout['version']} de {store_label} (lanzada ~{breakout['release_approx']}) "
        f"en adelante, el % de negativas pasó de {breakout['pct_neg_before']}% a {breakout['pct_neg_onward']}% "
        f"(+{breakout['delta']} puntos porcentuales) y se sostiene en esa versión y las siguientes "
        f"({breakout['n_onward']} reseñas, contra {breakout['n_before']} previas) — diferencia "
        f"estadísticamente significativa (p = {breakout['p_value']})."
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
    total_n = int(summary["n"].sum())
    pct_neg = round(float((summary["pct_neg"] * summary["n"]).sum() / total_n * 100), 1)
    return {
        "total_n": total_n,
        "pct_neg": pct_neg,
    }


def build_categories(summary: pd.DataFrame) -> list[dict]:
    """
    Agrupa los tópicos (no outlier) en sus categorías de una palabra, asignadas
    a mano en topics_named.json junto con el resto del enriquecimiento (ver
    topics_enrich.py) — no hay una cantidad fija de categorías: la raíz
    cuadrada del número de tópicos es solo una guía orientativa de cuántos
    grupos tienen sentido, no una regla que el código fuerce.
    """
    if "category" not in summary.columns:
        return []
    real = summary[~summary["is_outlier"]].copy()
    real = real[real["category"].notna() & (real["category"] != "")]
    if real.empty:
        return []

    grouped = real.groupby("category").apply(
        lambda g: pd.Series({
            "n": int(g["n"].sum()),
            "pct_neg": round(float((g["pct_neg"] * g["n"]).sum() / g["n"].sum() * 100), 1),
        }),
        include_groups=False,
    ).reset_index()
    grouped["n"] = grouped["n"].astype(int)
    return grouped.sort_values("pct_neg", ascending=False).to_dict("records")


def pct_to_color(pct_neg: float) -> str:
    """Interpola verde (0% negativas) -> ámbar (50%) -> rojo (100%) en RGB."""
    stops = [(0, (22, 163, 74)), (50, (217, 119, 6)), (100, (220, 38, 38))]
    pct_neg = max(0.0, min(100.0, pct_neg))
    (p0, c0), (p1, c1) = (stops[0], stops[1]) if pct_neg <= 50 else (stops[1], stops[2])
    t = (pct_neg - p0) / (p1 - p0) if p1 != p0 else 0
    r, g, b = (round(c0[i] + (c1[i] - c0[i]) * t) for i in range(3))
    return f'#{r:02x}{g:02x}{b:02x}'


BUBBLE_MIN_PX, BUBBLE_MAX_PX = 56, 160


def build_category_topics(summary: pd.DataFrame) -> dict[str, list[str]]:
    """Nombres de los tópicos (ya nombrados por Claude) que componen cada
    categoría, para la explicación expandible de qué incluye cada burbuja."""
    if "category" not in summary.columns or "name" not in summary.columns:
        return {}
    real = summary[~summary["is_outlier"]].copy()
    real = real[real["category"].notna() & (real["category"] != "")]
    if real.empty:
        return {}
    real = real.sort_values("pct_neg", ascending=False)
    return {
        category: [row["name"] for _, row in group.iterrows() if pd.notna(row["name"]) and row["name"]]
        for category, group in real.groupby("category")
    }


def render_categories_html(categories: list[dict], category_topics: dict[str, list[str]] | None = None) -> str:
    if not categories:
        return ""
    max_n = max(c["n"] for c in categories)
    bubbles = []
    for c in sorted(categories, key=lambda c: c["n"], reverse=True):
        scale = (c["n"] / max_n) ** 0.5 if max_n else 0  # área ~ n, no diámetro ~ n
        size = round(BUBBLE_MIN_PX + (BUBBLE_MAX_PX - BUBBLE_MIN_PX) * scale)
        color = pct_to_color(c["pct_neg"])
        pct_round = round(c["pct_neg"])
        font_size = max(10, min(14, round(size / 8)))
        item_width = max(size, 90)
        bubbles.append(f'''
        <div class="bubble-item" style="width:{item_width}px;">
          <div class="bubble-slot" style="height:{BUBBLE_MAX_PX}px;">
            <div class="bubble" style="width:{size}px;height:{size}px;background:{color};font-size:{font_size}px;"
                 title="{esc(c["category"])}: {c["n"]} reseñas, {pct_round}% negativas">
              {esc(c["category"])}
            </div>
          </div>
          <div class="bubble-pct" style="color:{color};">{pct_round}% negativas</div>
          <div class="bubble-n">{c["n"]} reseñas</div>
        </div>
        ''')
    legend = f'''
    <div class="bubble-legend">
      <span>Tamaño = volumen de reseñas</span>
      <span class="bubble-legend-scale">
        <span class="bubble-legend-dot" style="background:{pct_to_color(0)}"></span>Menos negativas
        <span class="bubble-legend-dot" style="background:{pct_to_color(100)}"></span>Más negativas
      </span>
    </div>
    '''
    explain = ""
    if category_topics:
        items = []
        for c in sorted(categories, key=lambda c: c["n"], reverse=True):
            topics = category_topics.get(c["category"]) or []
            if not topics:
                continue
            items.append(
                f'<div class="cat-explain-item"><dt>{esc(c["category"])}</dt>'
                f'<dd>{esc(" · ".join(topics))}</dd></div>'
            )
        if items:
            explain = (
                f'<details class="cat-explain"><summary>Qué incluye cada categoría</summary>'
                f'<dl>{"".join(items)}</dl></details>'
            )
    return (
        f'<div class="subsection"><h3>Por categoría</h3>'
        f'{legend}'
        f'<div class="bubble-chart">{"".join(bubbles)}</div>'
        f'{explain}</div>'
    )


def build_findings(summary: pd.DataFrame, reviews: pd.DataFrame) -> list[dict]:
    real = summary[~summary["is_outlier"]].copy()
    real["_priority"] = real["n"] * real["pct_neg"]
    real = real[real["severity"].isin(["alta", "media"])].sort_values("_priority", ascending=False)
    real = real.head(TOP_FINDINGS_MAX)

    has_category = "category" in real.columns

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
            "category": row["category"] if has_category and pd.notna(row["category"]) and row["category"] else None,
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
        <div class="recency-label">Histórico completo</div>
        <div class="recency-value">{all_s["rating"]}★</div>
        <div class="recency-sub">{all_s["pct_neg"]}% negativas · {all_s["n"]} reseñas</div>
      </div>
      <div class="recency-arrow">vs.</div>
      <div class="recency-card">
        <div class="recency-label">Últimos {RECENT_MONTHS} meses</div>
        <div class="recency-value">{recent_s["rating"]}★</div>
        <div class="recency-sub">{recent_s["pct_neg"]}% negativas · {recent_s["n"]} reseñas</div>
      </div>
    </div>
    <div class="trend-banner {trend_class}">{esc(trend_label)}</div>
    '''


def build_table_rows(summary: pd.DataFrame) -> str:
    has_category = "category" in summary.columns
    ordered = summary.sort_values(["is_outlier", "pct_neg"], ascending=[True, False])
    rows = []
    for _, row in ordered.iterrows():
        name = row["name"] if pd.notna(row["name"]) and row["name"] else row["Name"]
        severity = row["severity"] if pd.notna(row["severity"]) and row["severity"] else "-"
        category_cell = ""
        if has_category:
            category = row["category"] if pd.notna(row["category"]) and row["category"] else "-"
            category_cell = f"<td>{esc(category)}</td>"
        rows.append(
            f"<tr><td>{esc(name)}</td>{category_cell}<td class='num'>{int(row['n'])}</td>"
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
        category_chip = f'<span class="chip chip-category">{esc(f["category"])}</span>' if f.get("category") else ""
        cards.append(f'''
        <article class="finding-card">
          <div class="finding-head">
            <h3>{esc(f["name"])}</h3>
            <span class="chip {SEVERITY_CLASS.get(f["severity"], "")}">{esc(SEVERITY_LABEL.get(f["severity"], f["severity"]))}</span>
          </div>
          <p class="finding-meta">{category_chip}{f["n"]} reseñas · {f["pct_neg"]}% negativas</p>
          <p>{esc(f["summary"])}</p>
          <p class="recommendation"><strong>Recomendación:</strong> {esc(f["recommendation"])}</p>
          {f"<ul class='samples'>{samples_html}</ul>" if samples_html else ""}
        </article>
        ''')
    return "".join(cards)


TEMPLATE = """<!doctype html>
<html lang="es">
<head>
<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-1LQM1V95FR"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('js', new Date());
  gtag('config', 'G-1LQM1V95FR');
</script>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Análisis de reseñas de la app de {empresa}</title>
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
  --good: #16a34a; --warn: #d97706; --bad: #dc2626; --info: #3f5c8a;
  --goal-bg: var(--accent);
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
    --accent: #4f9686; --info: #5ac8fa; --goal-bg: #2f6f62;
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
.container {{ max-width: 1280px; margin: 0 auto; padding: 24px 24px 64px; }}
@media (max-width: 640px) {{ .container {{ padding: 16px 16px 48px; }} }}
header.page-head {{
  position: sticky; top: 0; z-index: 10; background: color-mix(in srgb, var(--bg) 85%, transparent);
  backdrop-filter: blur(14px); border-bottom: 1px solid var(--border-soft);
  padding: 16px 24px; display: flex; align-items: center; gap: 10px;
}}
@media (max-width: 640px) {{ header.page-head {{ padding: 12px 16px; }} }}
header.page-head h1 {{ font-size: 1.1rem; font-weight: 700; margin: 0; }}
header.page-head .sub {{ color: var(--muted); font-size: 0.8rem; }}
h3 {{ font-size: 0.95rem; font-weight: 700; letter-spacing: -0.01em; margin: 24px 0 8px; color: var(--muted); }}
.goal-banner {{
  background: var(--goal-bg); color: var(--accent-contrast); border-radius: var(--radius-lg);
  padding: 26px 28px; margin-top: 0; box-shadow: var(--shadow-lg);
}}
.goal-badge {{
  display: inline-block; font-size: 0.7rem; font-weight: 800; letter-spacing: 0.06em; text-transform: uppercase;
  background: rgba(255,255,255,0.16); padding: 5px 12px; border-radius: 999px; margin-bottom: 16px;
}}
.goal-main {{ display: flex; align-items: center; justify-content: space-between; gap: 24px; flex-wrap: wrap; }}
.goal-left {{ flex: 1 1 320px; }}
.goal-eyebrow {{
  font-size: 0.85rem; font-weight: 700; letter-spacing: -0.01em; opacity: 0.85; margin-bottom: 6px;
}}
.goal-question {{
  font-size: 1.65rem; font-weight: 800; letter-spacing: -0.02em; line-height: 1.25;
}}
@media (max-width: 640px) {{ .goal-question {{ font-size: 1.3rem; }} }}
.goal-hero {{
  flex: 0 0 auto; background: rgba(255,255,255,0.14); border-radius: var(--radius);
  padding: 14px 24px; text-align: center; min-width: 150px;
}}
.goal-hero-value {{ font-size: 2.4rem; font-weight: 800; letter-spacing: -0.02em; line-height: 1; }}
.goal-hero-label {{ font-size: 0.72rem; font-weight: 700; margin-top: 6px; opacity: 0.85; line-height: 1.3; }}
.goal-steps {{
  display: flex; align-items: center; flex-wrap: wrap; gap: 8px 10px; margin-top: 20px;
}}
.goal-step {{
  display: flex; align-items: center; gap: 6px; font-size: 0.8rem; font-weight: 700;
  background: rgba(255,255,255,0.12); padding: 6px 12px; border-radius: 999px;
}}
.goal-step-icon {{ font-size: 0.9rem; }}
.goal-step-arrow {{ opacity: 0.55; font-weight: 700; }}
.goal-urgent-row {{ display: flex; flex-wrap: wrap; gap: 12px; margin-top: 18px; }}
.goal-urgent {{
  display: flex; align-items: flex-start; gap: 10px; padding: 14px 16px; flex: 1 1 260px;
  background: var(--surface); color: var(--text); border-radius: var(--radius); box-shadow: var(--shadow-sm);
}}
.goal-urgent-icon {{ font-size: 1.1rem; flex-shrink: 0; line-height: 1.4; }}
.goal-urgent-label {{
  font-size: 0.68rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.05em; color: var(--bad);
}}
.goal-urgent-name {{ font-weight: 700; font-size: 0.92rem; margin-top: 2px; }}
.goal-urgent-meta {{ font-size: 0.78rem; color: var(--muted); margin-top: 2px; }}
.part {{
  margin-top: 40px; padding: 28px; border: 1px solid var(--border-soft); border-radius: var(--radius);
  background: color-mix(in srgb, var(--surface) 60%, transparent);
}}
.part:first-child {{ margin-top: 0; }}
.part--store {{ border-top: 4px solid var(--info); }}
.part--text {{ border-top: 4px solid var(--warn); }}
.part-title .kw {{ font-weight: 800; }}
.part--store .kw {{ color: var(--info); }}
.part--text .kw {{ color: var(--warn); }}
.part-eyebrow {{
  font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.08em; font-weight: 800; color: var(--muted-soft);
}}
.part-title {{ font-size: 1.3rem; font-weight: 800; letter-spacing: -0.01em; margin: 4px 0 20px; }}
.part-scope {{ color: var(--muted); font-size: 0.85rem; margin: -8px 0 20px; }}
.subsection {{ margin-top: 32px; }}
.stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(min(200px, 100%), 1fr)); gap: 12px; margin-top: 16px; }}
.stat-card {{
  background: var(--surface); border: 1px solid var(--border-soft);
  border-radius: var(--radius); box-shadow: var(--shadow-xs); padding: 16px;
}}
.stat-card .value {{ font-size: 1.75rem; font-weight: 800; letter-spacing: -0.02em; }}
.stat-card .label {{ color: var(--muted-soft); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 700; margin-top: 4px; }}
.bubble-legend {{
  display: flex; flex-wrap: wrap; gap: 8px 20px; margin-bottom: 16px; font-size: 0.78rem; color: var(--muted);
}}
.bubble-legend-scale {{ display: flex; align-items: center; gap: 6px; }}
.bubble-legend-dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%; }}
.bubble-legend-dot + .bubble-legend-dot {{ margin-left: 10px; }}
.bubble-chart {{
  display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: center;
  gap: 20px 16px; padding: 8px 0 4px;
}}
.bubble-item {{ display: flex; flex-direction: column; align-items: center; }}
.bubble-slot {{ display: flex; align-items: flex-end; justify-content: center; }}
.bubble {{
  border-radius: 50%; display: flex; align-items: center; justify-content: center;
  color: #fff; font-weight: 800; box-shadow: var(--shadow-sm); flex-shrink: 0;
  text-align: center; line-height: 1.15; padding: 10%; box-sizing: border-box;
  overflow-wrap: break-word; word-break: break-word;
}}
.bubble-pct {{ font-weight: 700; font-size: 0.82rem; margin-top: 8px; text-align: center; }}
.bubble-n {{ color: var(--muted); font-size: 0.72rem; margin-top: 2px; text-align: center; }}
.cat-explain {{ margin-top: 20px; font-size: 0.85rem; }}
.cat-explain summary {{
  cursor: pointer; font-weight: 700; color: var(--muted); user-select: none;
}}
.cat-explain summary:hover {{ color: var(--text); }}
.cat-explain dl {{ margin: 14px 0 0; display: flex; flex-direction: column; gap: 10px; }}
.cat-explain-item dt {{ font-weight: 700; font-size: 0.82rem; }}
.cat-explain-item dd {{ margin: 2px 0 0; color: var(--muted); line-height: 1.5; }}
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
.chip-category {{ background: var(--accent-soft); color: var(--accent); margin-right: 8px; }}
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
table.sortable th[data-sort] {{ cursor: pointer; user-select: none; white-space: nowrap; }}
table.sortable th[data-sort]:hover {{ color: var(--text); }}
table.sortable th.sorted-asc::after {{ content: " \\25B2"; }}
table.sortable th.sorted-desc::after {{ content: " \\25BC"; }}
.table-hint {{ color: var(--muted-soft); font-size: 0.72rem; margin-top: 6px; }}
footer {{ margin-top: 48px; padding-top: 16px; border-top: 1px solid var(--border-soft); color: var(--muted-soft); font-size: 0.78rem; }}
.empty {{ color: var(--muted); text-align: center; padding: 24px; }}
.methodology-note {{ color: var(--muted); font-size: 0.8rem; margin-top: 12px; }}
.composition {{ margin-top: 20px; }}
.composition-intro {{ font-size: 0.85rem; color: var(--muted); margin: 0 0 10px; }}
.composition-stats {{ display: flex; flex-wrap: wrap; gap: 24px; }}
.comp-stat {{ flex: 1 1 160px; }}
.comp-pct {{ font-size: 2rem; font-weight: 800; letter-spacing: -0.02em; line-height: 1.1; }}
.comp-stat--text .comp-pct {{ color: var(--warn); }}
.comp-stat--notext .comp-pct {{ color: var(--muted-soft); }}
.comp-label {{ font-size: 0.8rem; color: var(--muted); margin-top: 2px; }}
.composition-bar {{
  display: flex; height: 22px; border-radius: 999px; overflow: hidden; margin-top: 12px;
  border: 1px solid var(--border-soft);
}}
.composition-fill {{ height: 100%; }}
.composition-fill--text {{ background: var(--warn); }}
.composition-fill--notext {{ background: var(--border-soft); }}
.composition-callout {{
  margin-top: 14px; padding: 12px 16px; border-radius: var(--radius);
  background: color-mix(in srgb, var(--warn) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--warn) 28%, transparent);
  font-size: 0.85rem; color: var(--text);
}}
</style>
</head>
<body>
<header class="page-head">
  <div>
    <h1>📊 Análisis de reseñas de {empresa}</h1>
    <div class="sub">Generado {fecha}</div>
  </div>
</header>
<div class="container">

  <div class="goal-banner">
    <div class="goal-badge">📊 Informe ejecutivo · {fecha}</div>
    <div class="goal-main">
      <div class="goal-left">
        <div class="goal-eyebrow">{empresa} en Google Play y App Store</div>
        <div class="goal-question">¿Qué podemos mejorar en la app según el feedback del usuario?</div>
      </div>
      <div class="goal-hero">
        <div class="goal-hero-value">{official_rating}</div>
        <div class="goal-hero-label">Rating oficial<br>({official_count})</div>
      </div>
    </div>
    <div class="goal-steps">
      <div class="goal-step"><span class="goal-step-icon">📱</span>Reseñas de App Store y Google Play</div>
      <div class="goal-step-arrow">→</div>
      <div class="goal-step"><span class="goal-step-icon">🤖</span>Analizadas con Machine Learning</div>
      <div class="goal-step-arrow">→</div>
      <div class="goal-step"><span class="goal-step-icon">🏷️</span>Sentimiento por categoría y tópico</div>
    </div>
    {top_finding_html}
  </div>

  <div class="part part--store">
    <div class="part-eyebrow">Parte 1</div>
    <h2 class="part-title">Resumen de <span class="kw">todas</span> las reseñas</h2>
    <div class="stats-grid">
      <div class="stat-card"><div class="value">{official_count_num}</div><div class="label">Reseñas totales en las tiendas</div></div>
      <div class="stat-card"><div class="value">{official_rating}</div><div class="label">Rating oficial de las tiendas ({official_count})</div></div>
    </div>
    {composition_html}
    {competitor_section}
  </div>

  <div class="part part--text">
    <div class="part-eyebrow">Parte 2</div>
    <h2 class="part-title">Análisis de reseñas <span class="kw">que tienen texto</span></h2>
    <p class="part-scope">Todo lo que sigue en esta sección — tendencia, categorías, hallazgos y el detalle por tópico — está calculado <strong>únicamente sobre las {total_n_fmt} reseñas con texto</strong>, no sobre el total de la tienda.</p>
    <div class="stats-grid">
      <div class="stat-card"><div class="value">{total_n_fmt}</div><div class="label">Reseñas totales con texto analizadas</div></div>
      <div class="stat-card"><div class="value">{pct_neg}%</div><div class="label">Negativas sobre {total_n_fmt} reseñas con texto</div></div>
    </div>
    <div class="subsection">{trend_html}</div>

    {categories_section}

    <div class="subsection">
      <h3>Top 3 tópicos</h3>
      <div class="findings-grid">
        {findings_html}
      </div>
    </div>

    <div class="subsection">
      <h3>Detalle completo por tópico</h3>
      <details class="detail-table">
        <summary>Ver los {n_topics} tópicos detectados</summary>
        <div class="table-scroll">
          <table class="sortable">
            <thead><tr>
              <th data-sort="text">Tópico</th>{table_category_header}
              <th class="num" data-sort="num">N</th>
              <th class="num" data-sort="num">Rating</th>
              <th class="num" data-sort="num">% negativas</th>
              <th data-sort="text">Severidad</th>
            </tr></thead>
            <tbody>{table_rows}</tbody>
          </table>
        </div>
        <p class="table-hint">Click en un encabezado para ordenar por esa columna.</p>
      </details>
    </div>
  </div>

  <footer>
    Análisis generado automáticamente a partir de reseñas públicas de App Store y Google Play.
  </footer>
</div>
<script>
(function () {{
  document.querySelectorAll("table.sortable").forEach(function (table) {{
    var tbody = table.tBodies[0];
    var headers = table.tHead.rows[0].cells;
    Array.prototype.forEach.call(headers, function (th, colIndex) {{
      if (!th.hasAttribute("data-sort")) return;
      th.addEventListener("click", function () {{
        var type = th.getAttribute("data-sort");
        var asc = th.getAttribute("data-dir") !== "asc";
        Array.prototype.forEach.call(headers, function (h) {{
          h.removeAttribute("data-dir");
          h.classList.remove("sorted-asc", "sorted-desc");
        }});
        th.setAttribute("data-dir", asc ? "asc" : "desc");
        th.classList.add(asc ? "sorted-asc" : "sorted-desc");

        var rows = Array.prototype.slice.call(tbody.rows);
        rows.sort(function (a, b) {{
          var av = a.cells[colIndex].textContent.trim();
          var bv = b.cells[colIndex].textContent.trim();
          if (type === "num") {{
            av = parseFloat(av.replace(/[^0-9.-]/g, "")) || 0;
            bv = parseFloat(bv.replace(/[^0-9.-]/g, "")) || 0;
            return asc ? av - bv : bv - av;
          }}
          return asc ? av.localeCompare(bv, "es") : bv.localeCompare(av, "es");
        }});
        rows.forEach(function (row) {{ tbody.appendChild(row); }});
      }});
    }});
  }});
}})();
</script>
</body>
</html>
"""


def render(paths: Paths, empresa_display: str, competitor: str | None = None) -> str:
    summary, reviews, store_ratings = load_data(paths)
    stats = build_summary_stats(summary)
    official = build_official_rating(store_ratings)
    ios_cap_note = build_ios_cap_note(reviews, store_ratings)
    composition_html = build_composition_bar(official, stats["total_n"], ios_cap_note)
    categories = build_categories(summary)
    categories_section = render_categories_html(categories, build_category_topics(summary))
    findings = build_findings(summary, reviews)
    findings_html = render_findings_html(findings) or '<p class="empty">No se detectaron hallazgos negativos relevantes.</p>'

    def urgent_card(icon: str, label: str, name: str, n: int, pct_neg: float) -> str:
        return f'''
        <div class="goal-urgent">
          <span class="goal-urgent-icon">{icon}</span>
          <div>
            <div class="goal-urgent-label">{label}</div>
            <div class="goal-urgent-name">{esc(name)}</div>
            <div class="goal-urgent-meta">{n} reseñas · {pct_neg}% negativas</div>
          </div>
        </div>
        '''

    urgent_cards = []
    if categories:
        top_category = categories[0]
        urgent_cards.append(urgent_card("📂", "Categoría más urgente", top_category["category"], top_category["n"], top_category["pct_neg"]))
    if findings:
        top = findings[0]
        urgent_cards.append(urgent_card("🚨", "Tópico más urgente", top["name"], top["n"], top["pct_neg"]))
    top_finding_html = f'<div class="goal-urgent-row">{"".join(urgent_cards)}</div>' if urgent_cards else ""
    # Minimalismo: mostrar un solo banner de tendencia, no los dos apilados.
    # El quiebre de versión es el hallazgo más fuerte y citable (persistencia +
    # significancia ya exigidas en version_breakout.py) — si existe, gana;
    # si no, cae al genérico "últimos N meses vs. histórico".
    breakout_html = build_version_breakout_section(paths)
    recency_html = build_recency_comparison(reviews)
    trend_body = breakout_html or recency_html
    trend_note = ""
    if not breakout_html and recency_html and official:
        trend_note = (
            f'<p class="methodology-note">El histórico completo es más bajo que el {official["score"]}★ '
            f'analizado antes, puesto que las opiniones que tienen texto por su naturaleza '
            f'<strong>tienden a ser más negativas</strong> que el promedio general — quien solo puntúa con '
            f'estrellas casi nunca escribe para elogiar.</p>'
        )
    trend_html = f'<h3>¿Cómo vienen últimamente?</h3>{trend_body}{trend_note}' if trend_body else ""
    table_rows = build_table_rows(summary)
    table_category_header = '<th data-sort="text">Categoría</th>' if "category" in summary.columns else ""

    competitor_html = build_competitor_section(official, empresa_display, competitor) if competitor else ""
    competitor_section = (
        f'<div class="subsection"><h3>Comparado con la competencia</h3>{competitor_html}</div>' if competitor_html else ""
    )

    return TEMPLATE.format(
        empresa=esc(empresa_display),
        fecha=pd.Timestamp.now().strftime("%Y-%m-%d"),
        official_rating=f'{official["score"]}★' if official else "N/D",
        official_count=f'{official["count"]:,} calificaciones'.replace(",", ".") if official else "sin dato",
        official_count_num=f'{official["count"]:,}'.replace(",", ".") if official else "N/D",
        total_n=stats["total_n"],
        total_n_fmt=f'{stats["total_n"]:,}'.replace(",", "."),
        pct_neg=stats["pct_neg"],
        composition_html=composition_html,
        categories_section=categories_section,
        findings_html=findings_html,
        top_finding_html=top_finding_html,
        trend_html=trend_html,
        competitor_section=competitor_section,
        n_topics=len(summary),
        table_category_header=table_category_header,
        table_rows=table_rows,
    )


INDEX_TEMPLATE = """<!doctype html>
<html lang="es">
<head>
<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-1LQM1V95FR"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('js', new Date());
  gtag('config', 'G-1LQM1V95FR');
</script>
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
        match = re.search(r"<title>Análisis de reseñas de la app de (.*?)</title>", page.read_text(encoding="utf-8"))
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

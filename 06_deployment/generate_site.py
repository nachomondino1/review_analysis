"""
Genera el HTML con el análisis de una empresa, para compartir por link
(sin backend, sin build step). Los datos quedan embebidos en el HTML; los
estilos viven en site/css/components/base.css (compartido) + site/css/pages/empresa.css
(propio de esta página) — un cambio de diseño compartido no implica regenerar
los HTML de todas las empresas.

Uso: python 06_deployment/generate_site.py --name <empresa>
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
import companies_registry as companies  # noqa: E402
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


def build_composition_bar(official: dict | None, total_n: int, avg_rating_text: float | None, ios_cap_note: str = "") -> str:
    """
    De todas las calificaciones de las tiendas, cuántas traen texto (la única
    porción que este análisis puede leer) y cuántas son solo estrellas —
    como un split visual (total + rating oficial -> dos ramas con flecha),
    no una barra + números sueltos. El número grande de cada rama es la
    CANTIDAD de reseñas (no el %), para mantener la misma unidad que el
    "reseñas totales" del origen — el % queda como dato secundario en el
    label. La rama "con texto" muestra además su rating promedio (★, misma
    unidad que el rating oficial, para comparar de un vistazo sin traducir
    mentalmente un % a estrellas); la rama "sin texto" no tiene texto ni
    rating propio que mostrar y lo dice explícito en vez de omitirlo.
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
    neg_sub = f'<div class="split-branch-sub">Promedio: {avg_rating_text}★</div>' if avg_rating_text is not None else ""

    return f'''
    <div class="composition">
      <div class="split-flow">
        <div class="split-origin">
          <div class="split-origin-stat">
            <div class="split-origin-value">{total_official_fmt}</div>
            <div class="split-origin-label">Reseñas totales</div>
          </div>
          <div class="split-origin-stat">
            <div class="split-origin-value">{official["score"]}★</div>
            <div class="split-origin-label">Rating oficial</div>
          </div>
        </div>
        <div class="split-branches">
          <div class="split-branch split-branch--text">
            <span class="split-arrow" aria-hidden="true">↳</span>
            <div class="split-branch-num">
              <div class="split-branch-value">{total_n_fmt}</div>
              <div class="split-branch-unit">reseñas</div>
            </div>
            <div class="split-branch-body">
              <div class="split-branch-label"><strong>Con texto</strong> · {pct_text}% del total</div>
              {neg_sub}
            </div>
          </div>
          <div class="split-branch split-branch--notext">
            <span class="split-arrow" aria-hidden="true">↳</span>
            <div class="split-branch-num">
              <div class="split-branch-value">{n_no_text_fmt}</div>
              <div class="split-branch-unit">reseñas</div>
            </div>
            <div class="split-branch-body">
              <div class="split-branch-label"><strong>Solo estrellas</strong> · {pct_no_text}% del total</div>
              <div class="split-branch-sub">Sin texto no se puede medir sentimiento</div>
            </div>
          </div>
        </div>
      </div>
      <p class="composition-callout">👇 A partir de acá, el análisis usa <strong>solo el {pct_text}% que tiene texto</strong> ({total_n_fmt} reseñas) — es la única porción que se puede leer.</p>
      {ios_cap_note}
    </div>
    '''


STORE_LABEL = {"ios": "App Store", "android": "Google Play"}


def build_version_breakout_section(paths: Paths) -> str:
    """
    Si 04_modeling/trends/version_breakout.py encontró un quiebre real (ver ese
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
    (ids ya cargados en data/companies.csv). Es trabajo específico para
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


def build_summary_stats(reviews: pd.DataFrame) -> dict:
    """
    Total de reseñas con texto y su % de negativas, calculado directo sobre
    `reviews` (no sumando "n" por tópico): si los tópicos no son mutuamente
    excluyentes (ej. categorización por aspecto, donde una reseña puede
    mencionar más de un tema), sumar "n" por tópico cuenta reseñas más de
    una vez y da un total inflado.
    """
    total_n = int(len(reviews))
    pct_neg = round(float((reviews["sentiment"] == "NEG").mean() * 100), 1) if total_n else 0.0
    return {
        "total_n": total_n,
        "pct_neg": pct_neg,
    }


CATEGORIES_EXCLUDED_FROM_BUBBLES = {"General", "Ruido"}


def build_categories(summary: pd.DataFrame) -> list[dict]:
    """
    Agrupa los tópicos (no outlier) en sus categorías de una palabra, asignadas
    a mano en topics_named.json junto con el resto del enriquecimiento (ver
    03_topics_enrich.py) — no hay una cantidad fija de categorías: la raíz
    cuadrada del número de tópicos es solo una guía orientativa de cuántos
    grupos tienen sentido, no una regla que el código fuerce.

    "General" y "Ruido" quedan afuera del bubble chart: no son un área
    funcional del producto (que es lo que el chart compara), sino "opinión
    sin apuntar a algo puntual" y "sin contenido interpretable" — mezclarlas
    con Acceso/Pagos/etc. no ayuda a decidir dónde actuar.
    """
    if "category" not in summary.columns:
        return []
    real = summary[~summary["is_outlier"]].copy()
    real = real[real["category"].notna() & (real["category"] != "")]
    real = real[~real["category"].isin(CATEGORIES_EXCLUDED_FROM_BUBBLES)]
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


SAMPLES_PER_BUBBLE = 3


def category_slug(category: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", category.lower()).strip("-")


def split_sentences_simple(text: str) -> list[str]:
    """Split liviano para resaltar — ver split_sentences en 01_analyze_sentiment_topics.py (misma idea, duplicado
    a propósito: generate_site.py no importa del paso de modelado)."""
    text = text.replace("\n", ". ")
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if len(p.strip()) > 2]


def topic_keywords(name: str) -> list[str]:
    """'5_no_deja_me_registrarme' -> ['no','deja','me','registrarme'] (saca el índice numérico inicial)."""
    if not isinstance(name, str):
        return []
    parts = name.split("_")[1:]
    return [p for p in parts if len(p) > 2]


def highlight_relevant_sentence(text: str, keywords: list[str]) -> str:
    """
    Resalta la primera oración de la reseña que menciona alguna keyword del
    tópico — una reseña puede hablar de varios temas (ver findings de
    my-board-game-collection), así que mostrarla entera sin marcar dónde
    habla de ESTA categoría obliga a releerla entera para encontrar la parte
    relevante.
    """
    sentences = split_sentences_simple(text)
    if not sentences:
        return esc(text)
    low_kws = [k.lower() for k in keywords]
    out = []
    for s in sentences:
        low = s.lower()
        if any(re.search(rf"\b{re.escape(k)}", low) for k in low_kws):
            out.append(f"<mark>{esc(s)}</mark>")
        else:
            out.append(esc(s))
    return " ".join(out)


def build_category_detail_sections(summary: pd.DataFrame, reviews: pd.DataFrame) -> str:
    """
    Panel oculto por categoría (debajo del bubble chart, no en la burbuja
    misma): al hacer click en una burbuja, JS muestra el panel de esa
    categoría y hace scroll hasta acá. Separa ejemplos en positivas/negativas
    y resalta, dentro de cada reseña, la oración que efectivamente habla de
    la categoría (puede ser una reseña con varios temas mezclados).
    """
    if "category" not in summary.columns:
        return ""
    real = summary[~summary["is_outlier"]].copy()
    real = real[real["category"].notna() & (real["category"] != "")]
    real = real[~real["category"].isin(CATEGORIES_EXCLUDED_FROM_BUBBLES)]
    if real.empty:
        return ""

    has_confidence = "sentiment_confidence" in reviews.columns
    RECENT_POOL = 10  # entre las más recientes, se eligen las de clasificación más confiable

    panels = []
    for category, group in real.groupby("category"):
        cat_reviews = reviews[reviews["topic"].isin(group["topic"])]
        keywords = [kw for name in group["Name"].dropna() for kw in topic_keywords(name)]

        def render_side(label: str, sentiment: str, css: str) -> str:
            sub = cat_reviews[cat_reviews["sentiment"] == sentiment].dropna(subset=["text"])
            if sub.empty:
                return f'<div class="cat-detail-col"><h4 class="cat-detail-col-title {css}">{label}</h4><p class="empty">Sin ejemplos.</p></div>'
            # Entre las más recientes, priorizar las que el modelo clasificó con más
            # confianza (y más texto: una reseña de una palabra da poco contexto para
            # confiar en su sentimiento) — no ordenar solo por fecha, porque la reseña
            # más nueva puede ser la más ambigua de todas.
            recent = sub.sort_values("date", ascending=False).head(RECENT_POOL)
            sort_cols = ["sentiment_confidence", "text_length"] if has_confidence else ["text_length"]
            recent = recent.sort_values(sort_cols, ascending=False).head(SAMPLES_PER_BUBBLE)
            items = "".join(
                f'<li><div class="cat-detail-date">{pd.to_datetime(row["date"]).strftime("%d/%m/%Y")}</div>'
                f'{highlight_relevant_sentence(row["text"], keywords)}</li>'
                for _, row in recent.iterrows()
            )
            return f'<div class="cat-detail-col"><h4 class="cat-detail-col-title {css}">{label}</h4><ul class="cat-detail-list">{items}</ul></div>'

        panels.append(f'''
        <div class="category-detail" id="cat-detail-{category_slug(category)}" hidden>
          <h4 class="category-detail-title">{esc(category)}</h4>
          <div class="cat-detail-cols">
            {render_side("👍 Positivas", "POS", "cat-detail-col-title--pos")}
            {render_side("👎 Negativas", "NEG", "cat-detail-col-title--neg")}
          </div>
        </div>
        ''')
    return "".join(panels)


def render_categories_html(categories: list[dict], category_topics: dict[str, list[str]] | None = None,
                            category_detail_html: str = "") -> str:
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
        slug = category_slug(c["category"])
        bubbles.append(f'''
        <div class="bubble-item" style="width:{item_width}px;">
          <button type="button" class="bubble-trigger" aria-expanded="false" data-target="cat-detail-{slug}">
            <div class="bubble-slot" style="height:{BUBBLE_MAX_PX}px;">
              <div class="bubble" style="width:{size}px;height:{size}px;background:{color};font-size:{font_size}px;"
                   title="{esc(c["category"])}: {c["n"]} reseñas, {pct_round}% negativas">
                {esc(c["category"])}
              </div>
            </div>
            <div class="bubble-pct" style="color:{color};">{pct_round}% negativas</div>
            <div class="bubble-n">{c["n"]} reseñas · ver ejemplos</div>
          </button>
        </div>
        ''')
    legend = f'''
    <div class="bubble-legend">
      <span>Tamaño = volumen de reseñas · click en una burbuja para ver ejemplos</span>
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
        f'<div class="subsection"><h3>¿Qué opina el cliente por categoría?</h3>'
        f'{legend}'
        f'<div class="bubble-chart">{"".join(bubbles)}</div>'
        f'{explain}'
        f'<div class="category-detail-wrap">{category_detail_html}</div>'
        f'</div>'
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


def build_sparkline_svg(months: list[str], monthly_pct_neg: list[float], trend_class: str,
                         recent_from_month: str, historical_avg: float) -> str:
    """
    12 puntos (o los que haya) de % negativas por mes, en el tono de
    "de-énfasis" (--muted-soft), con eje Y (min/max del rango) y eje X
    (primer/último mes) explícitos — un gráfico sin ejes no se puede leer,
    solo "intuir". Dos marcas extra para que el gráfico no "contradiga" al
    chip de arriba: el chip compara el promedio de los ÚLTIMOS N MESES
    contra TODO el histórico (años), no mes a mes — sin esto, un mes
    puntual subiendo al final del gráfico parece desmentir un chip que dice
    "mejorando" cuando en realidad comparan ventanas distintas. Entonces:
    (1) los puntos dentro de la ventana "últimos N meses" se marcan en el
    color de la tendencia, el resto en gris; (2) una línea punteada marca
    el promedio histórico, para comparar el nivel actual contra esa
    referencia en vez de contra el mes inmediato anterior.
    """
    if len(monthly_pct_neg) < 2:
        return ""
    w, h, pad = 260, 48, 6
    values_with_ref = monthly_pct_neg + [historical_avg]
    lo, hi = min(values_with_ref), max(values_with_ref)
    span = (hi - lo) or 1  # evita división por cero si todos los meses dan igual
    n = len(monthly_pct_neg)
    xs = [pad + i * (w - 2 * pad) / (n - 1) for i in range(n)]
    ys = [pad + (h - 2 * pad) * (1 - (v - lo) / span) for v in monthly_pct_neg]
    path = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(zip(xs, ys)))
    ref_y = pad + (h - 2 * pad) * (1 - (historical_avg - lo) / span)
    trend_color = {"trend-good": "var(--good)", "trend-bad": "var(--bad)", "trend-flat": "var(--muted)"}[trend_class]

    recent_dots = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{4 if i == n - 1 else 3}" fill="{trend_color}" stroke="var(--surface)" stroke-width="2" />'
        for i, (x, y, m) in enumerate(zip(xs, ys, months)) if m >= recent_from_month
    )

    def month_label(m: str) -> str:
        year, month = m.split("-")
        return f"{month}/{year[2:]}"

    return f'''
    <div class="sparkline-chart">
      <div class="sparkline-caption"><span>% negativas por mes</span><span class="sparkline-legend"><span class="sparkline-legend-dot" style="background:{trend_color}"></span>últimos {month_label(recent_from_month)}–{month_label(months[-1])}<span class="sparkline-legend-dash"></span>promedio histórico</span></div>
      <div class="sparkline-row">
        <div class="sparkline-yaxis"><span>{hi:.1f}%</span><span>{lo:.1f}%</span></div>
        <svg class="sparkline" viewBox="0 0 {w} {h}" preserveAspectRatio="none" role="img" aria-label="% de reseñas negativas por mes, de {month_label(months[0])} a {month_label(months[-1])}; promedio histórico {historical_avg}%">
          <line x1="{pad}" y1="{ref_y:.1f}" x2="{w - pad}" y2="{ref_y:.1f}" stroke="var(--muted-soft)" stroke-width="1" stroke-dasharray="3,3" />
          <path d="{path}" fill="none" stroke="var(--muted-soft)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" />
          {recent_dots}
        </svg>
      </div>
      <div class="sparkline-xaxis"><span>{month_label(months[0])}</span><span>{month_label(months[-1])}</span></div>
    </div>
    '''


def build_recency_comparison(reviews: pd.DataFrame) -> str:
    """
    Responde "¿cómo vienen las reseñas últimamente respecto de siempre?" con
    UN solo número titular (% negativas de los últimos N meses) + el delta
    contra el histórico + un sparkline de la tendencia mensual — en vez de 4
    números sueltos en 2 cards. El sparkline grafica una sola métrica
    (% negativas) de punta a punta, así "sube" tiene un solo significado
    posible (nunca mezcla con rating, que subiría por motivos opuestos).
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
        trend_class, trend_label = "trend-good", f"{abs(delta):.1f} puntos menos que el histórico ({all_s['pct_neg']}%)"
    elif delta >= TREND_THRESHOLD_PTS:
        trend_class, trend_label = "trend-bad", f"{delta:.1f} puntos más que el histórico ({all_s['pct_neg']}%)"
    else:
        trend_class, trend_label = "trend-flat", f"Estable respecto del histórico ({all_s['pct_neg']}%)"

    monthly = (reviews.assign(_neg=(reviews["sentiment"] == "NEG"))
               .groupby("month")["_neg"].mean().mul(100).round(1))
    monthly = monthly.sort_index().tail(12)
    sparkline_html = build_sparkline_svg(
        monthly.index.tolist(), monthly.tolist(), trend_class,
        recent_from_month=cutoff.strftime("%Y-%m"), historical_avg=all_s["pct_neg"],
    )

    return f'''
    <div class="trend-tile">
      <div class="trend-tile-main">
        <div class="recency-label">Negativas, últimos {RECENT_MONTHS} meses ({recent_s["n"]} reseñas)</div>
        <div class="recency-value">{recent_s["pct_neg"]}%</div>
        <div class="trend-banner {trend_class}">{esc(trend_label)}</div>
      </div>
      {sparkline_html}
    </div>
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
<link rel="stylesheet" href="css/components/base.css">
<link rel="stylesheet" href="css/pages/empresa.css">
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
    <h2 class="part-title">¿Qué dicen <span class="kw">todas</span> las calificaciones de la tienda?</h2>
    {composition_html}
    {competitor_section}
  </div>

  <div class="part part--text">
    <div class="part-eyebrow">Parte 2</div>
    <h2 class="part-title">¿Qué dicen las reseñas <span class="kw">que tienen texto</span>?</h2>
    <p class="part-scope">Todo lo que sigue en esta sección — tendencia, categorías, hallazgos y el detalle por tópico — está calculado <strong>únicamente sobre las {total_n_fmt} reseñas con texto</strong>, no sobre el total de la tienda.</p>
    <div class="subsection">{trend_html}</div>

    {categories_section}

    <!-- Temporalmente ocultas a pedido del usuario mientras se prueba el panel de
         ejemplos por categoría (debajo del bubble chart) — el código que arma
         findings_html/table_rows sigue intacto, solo no se renderiza acá.
    <div class="subsection">
      <h3>¿Cuáles son los problemas más urgentes?</h3>
      <div class="findings-grid">
        {findings_html}
      </div>
    </div>

    <div class="subsection">
      <h3>¿Qué dice cada tópico en detalle?</h3>
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
    -->
  </div>

  <footer>
    Análisis generado automáticamente a partir de reseñas públicas de App Store y Google Play.
  </footer>
</div>
<script>
(function () {{
  var bubbleButtons = document.querySelectorAll(".bubble-trigger");
  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  bubbleButtons.forEach(function (btn) {{
    var targetId = btn.getAttribute("data-target");
    var panel = targetId && document.getElementById(targetId);
    if (!panel) return;
    btn.addEventListener("click", function () {{
      var open = btn.getAttribute("aria-expanded") === "true";
      bubbleButtons.forEach(function (b) {{
        b.setAttribute("aria-expanded", "false");
        var p = document.getElementById(b.getAttribute("data-target"));
        if (p) p.setAttribute("hidden", "");
      }});
      if (!open) {{
        btn.setAttribute("aria-expanded", "true");
        panel.removeAttribute("hidden");
        panel.scrollIntoView({{behavior: reduceMotion ? "auto" : "smooth", block: "start"}});
      }}
    }});
  }});
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
    stats = build_summary_stats(reviews)
    official = build_official_rating(store_ratings)
    ios_cap_note = build_ios_cap_note(reviews, store_ratings)
    avg_rating_text = round(float(reviews["rating"].mean()), 2) if reviews is not None and not reviews.empty else None
    composition_html = build_composition_bar(official, stats["total_n"], avg_rating_text, ios_cap_note)
    categories = build_categories(summary)
    categories_section = render_categories_html(categories, build_category_topics(summary), build_category_detail_sections(summary, reviews))
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
    trend_html = f'<h3>¿Cómo vienen últimamente?</h3>{trend_body}' if trend_body else ""
    table_rows = build_table_rows(summary)
    table_category_header = '<th data-sort="text">Categoría</th>' if "category" in summary.columns else ""

    competitor_html = build_competitor_section(official, empresa_display, competitor) if competitor else ""
    competitor_section = (
        f'<div class="subsection"><h3>¿Cómo comparás con la competencia?</h3>{competitor_html}</div>' if competitor_html else ""
    )

    return TEMPLATE.format(
        empresa=esc(empresa_display),
        fecha=pd.Timestamp.now().strftime("%Y-%m-%d"),
        official_rating=f'{official["score"]}★' if official else "N/D",
        official_count=f'{official["count"]:,} calificaciones'.replace(",", ".") if official else "sin dato",
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
<link rel="stylesheet" href="site/css/components/base.css">
<link rel="stylesheet" href="site/css/pages/index.css">
</head>
<body class="index-page">
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
    p = argparse.ArgumentParser(description="Genera el HTML para compartir el análisis (estilos en site/css/, compartidos entre empresas).")
    p.add_argument("--name", required=True, help="Nombre de la empresa/app (debe coincidir con el usado en las fases previas)")
    p.add_argument("--display-name", default=None, help="Nombre a mostrar en la web (default: --name tal cual)")
    p.add_argument("--competitor", default=None, help="Nombre de un competidor ya cargado en data/companies.csv, para comparar rating oficial")
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

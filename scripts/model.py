from dotenv import load_dotenv
load_dotenv()  # va primero, antes de los imports de HF

import pandas as pd
from pysentimiento import create_analyzer
from bertopic import BERTopic
from sentence_transformers import SentenceTransformer
from pathlib import Path

OUT_DIR = Path("data/output")


df = pd.read_parquet("data/reviews.parquet")
df = df[df["text"].str.len() > 15].copy()  # filtrar ruido ("buena app")

sent = create_analyzer(task="sentiment", lang="es")
df["sentiment"] = [p.output for p in sent.predict(df["text"].tolist())]

emb = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
topic_model = BERTopic(language="multilingual", min_topic_size=20)
df["topic"], _ = topic_model.fit_transform(
    df["text"].tolist(), emb.encode(df["text"].tolist(), show_progress_bar=True)
)

# Resumen por tópico (antes se calculaba y se descartaba)
summary = (df.groupby("topic")
   .agg(n=("text", "size"), rating=("rating", "mean"),
        pct_neg=("sentiment", lambda s: (s == "NEG").mean()))
   .sort_values("pct_neg", ascending=False))

# Agrego keywords para poder nombrar cada tópico
info = topic_model.get_topic_info().set_index("Topic")[["Name"]]
summary = summary.join(info)

df.to_parquet(OUT_DIR / "reviews_enriched.parquet")  # fuente de verdad, reusable
df.to_csv(OUT_DIR / "reviews_enriched.csv", index=False, encoding="utf-8-sig")  # para abrir en Excel
summary.to_csv(OUT_DIR / "topics_summary.csv", encoding="utf-8-sig")

print(summary.head(15))
"""
Extrae keywords del campo "Name" de un tópico (c-TF-IDF de BERTopic, ej.
"5_no_deja_me_registrarme") para el matching por keywords de
04_modeling/topics/05_export_review_audit.py y generate_site.py.

Filtra stopwords y palabras demasiado genéricas del español: BERTopic a
veces saca como top-words de un tópico palabras función ("para", "muy",
"con") o verbos/adjetivos tan frecuentes que aparecen en cualquier
sentimiento ("problema", "funciona", "excelente") — sobre todo en tópicos
de elogios genéricos, que por naturaleza no tienen vocabulario distintivo.
Sin este filtro, una sola keyword así hace que el tópico "matchee" miles de
oraciones que no tienen nada que ver (visto en producción: un tópico de 189
reseñas pasó a "matchear" 3147 por tener "muy" como keyword — ver
APRENDIZAJES.md).
"""
import re

STOPWORDS = {
    # artículos, preposiciones, conjunciones, pronombres
    "que", "con", "para", "por", "como", "pero", "las", "los", "una", "uno",
    "del", "les", "nos", "sus", "este", "esta", "esa", "ese", "eso", "esto",
    "sin", "sobre", "entre", "cuando", "donde", "porque", "también", "tambien",
    "ahora", "siempre", "nunca", "aún", "aun", "solo", "sólo", "ser", "estar",
    "está", "estan", "están", "son", "fue", "han", "hay", "soy", "era", "eres",
    "sido", "tengo", "tiene", "tuve", "hace", "hizo", "desde", "hasta", "cada",
    "todo", "toda", "todos", "todas", "otro", "otra", "mas", "más", "mis", "tus",
    "él", "ella", "ellos", "ellas", "yo", "usted", "ustedes", "the", "and", "for",
    "with", "that", "this", "are", "was", "have", "has",
    # demasiado genéricas / aparecen en cualquier sentimiento, no distinguen tema
    "muy", "buena", "bueno", "buenas", "buenos", "excelente", "excelentes",
    "funciona", "problema", "problemas", "gracias", "genial", "mal", "mala",
    "cosas", "vez", "siempre", "nada", "todo",
}


def topic_keywords(name: str) -> list[str]:
    """'5_no_deja_me_registrarme' -> ['no','deja','me','registrarme'] (saca el índice inicial)."""
    if not isinstance(name, str):
        return []
    return [p for p in name.split("_")[1:] if len(p) > 2 and p.lower() not in STOPWORDS]


def highlight_pattern(keyword: str) -> str:
    """Patrón de regex con bordes de palabra para buscar `keyword` en un texto."""
    return rf"\b{re.escape(keyword.lower())}"

"""
Taxonomías de categorías para agrupar tópicos (ver 03_topics_enrich.py).

Un solo eje: "¿qué área funcional del producto está en juego en este
tópico?" — no mezclar con otros ejes (severidad, sentimiento, volumen: esos
ya son columnas propias).

La lista es fija y compartida entre empresas DEL MISMO RUBRO (ej: todas las
fintech/exchanges), no una por empresa: así "Pagos" en Belo significa lo
mismo que "Pagos" en Ripio, y los bubble charts se pueden comparar entre
análisis de ese rubro. Pero no es un eje universal para cualquier app: un
rubro distinto (agrotech, delivery, etc.) tiene áreas funcionales distintas
y necesita su propia lista bajo una key nueva en CATEGORIES_BY_DOMAIN.

Agregar una categoría nueva a una lista existente solo si un tópico real no
encaja en ninguna de las de ese rubro — no crear una ad hoc por empresa en
el topics_named.json. Si aparece un rubro nuevo, agregar una key nueva acá
en vez de forzar los tópicos a la lista de otro rubro.
"""

CATEGORIES_BY_DOMAIN = {
    # "Otros" original mezclaba dos cosas muy distintas: satisfacción/queja
    # general sin función específica (volumen real, señal de marca/lealtad)
    # y ruido sin contenido interpretable (rating condicionado, texto
    # ilegible). Mezclarlas infla un bucket "Otros" que no dice nada — se
    # separan en "General" (señal real) y "Ruido" (no accionable). Ver
    # APRENDIZAJES.md para el detalle de la revisión que motivó el split.
    "fintech": {
        "Acceso": "Login, registro, verificación de identidad/DNI, SMS/2FA, mails de confirmación, onboarding.",
        "Pagos": "Depósitos, retiros, transferencias, compra/venta de cripto, acreditaciones, reembolsos, tarjeta física/virtual.",
        "Comisiones": "Costos de transacción, tarifas por operativa, percepción de precio/caro.",
        "Interfaz": "Rendimiento, bugs, UI/UX, compatibilidad Android/iOS, actualizaciones en tiendas, publicidad.",
        "Soporte": "Tickets de atención, resolución de reclamos, servicio al cliente.",
        "General": "Opinión (positiva o negativa) sobre la app/marca en su conjunto, sin apuntar a una función "
                    "específica: satisfacción o lealtad general, recomendación, \"funciona bien\"/\"no funciona "
                    "nada\" sin más detalle. Si el comentario sí señala una función puntual (pagos, acceso, etc.) "
                    "va en esa categoría aunque sea breve, no acá.",
        "Ruido": "Reseñas sin contenido interpretable para el negocio: calificación condicionada a algo puntual "
                 "sin desarrollarlo, texto demasiado corto o con palabras sueltas sin sentido claro.",
    },
    "juegos-de-mesa": {
        "Sincronización y datos": "Sync con servicios externos (ej. BoardGameGeek), backups, pérdida o "
                                   "duplicación de la colección/listas guardadas, falta de respaldo en la nube.",
        "Cuenta": "Login, registro, crear usuario, compartir colección con otros usuarios.",
        "Estabilidad": "Crashes, freezes, bloqueos, publicidad intrusiva que interrumpe el uso.",
        "Localización": "Idioma de la app o de los resultados de búsqueda, traducciones faltantes o parciales.",
        "Funcionalidad": "Features faltantes o pedidos de mejora (filtros, escaneo de código de barras, fotos "
                          "de portada, bitácora de partidas, contadores, etc.), UI/UX puntual de una pantalla.",
        "General": "Opinión (positiva o negativa) sobre la app en su conjunto, sin apuntar a una función "
                   "específica: satisfacción o lealtad general, \"muy útil\"/\"no me gustó\" sin más detalle. "
                   "Si el comentario sí señala una función puntual, va en esa categoría aunque sea breve, no acá.",
        "Ruido": "Reseñas sin contenido interpretable para el negocio: calificación condicionada a algo puntual "
                 "sin desarrollarlo, texto demasiado corto o con palabras sueltas sin sentido claro.",
    },
}

DEFAULT_DOMAIN = "fintech"


def allowed(domain: str = DEFAULT_DOMAIN) -> set[str]:
    if domain not in CATEGORIES_BY_DOMAIN:
        raise KeyError(
            f"No hay taxonomía para el rubro '{domain}'. "
            f"Rubros disponibles: {sorted(CATEGORIES_BY_DOMAIN)}. "
            "Agregalo en CATEGORIES_BY_DOMAIN si es un rubro nuevo."
        )
    return set(CATEGORIES_BY_DOMAIN[domain])

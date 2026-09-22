"""Productos relacionados a un repuesto dado ("sustitutos sugeridos").

Reutiliza el MISMO motor TF-IDF + coseno que ya rankea los candidatos del
asistente (SimilitudTfidfCoseno): la diferencia es de dónde sale la consulta.
En el asistente la consulta es el texto que escribió el usuario; acá es el
propio repuesto que se está mirando (nombre + descripción + categoría), así
que el ranking termina midiendo "qué tan parecido es este producto a aquel".

No hay ningún LLM externo en este flujo — es el mismo modelo propio del
curso, entrenado/calculado en memoria a partir del catálogo real.
"""
import logging

from app.recommender.client_backend import buscar_en_catalogo, obtener_repuesto
from app.recommender.tfidf_cosine import SimilitudTfidfCoseno

logger = logging.getLogger(__name__)

# Debajo de esto la "similitud" es ruido de vocabulario compartido (dos
# productos que solo coinciden en palabras genéricas como "kit" o "12v"),
# y mostrarlos como sugerencia le resta credibilidad al resto.
UMBRAL_SIMILITUD = 0.05

# Cuántos candidatos pedirle al backend. El endpoint /api/repuestos topa en
# 100 por página; con catálogos mayores, el filtro por categoría de abajo es
# lo que mantiene el conjunto relevante.
MAX_CANDIDATOS = 100

# Si la categoría trae menos de esto, el corpus queda demasiado pequeño para
# que el IDF signifique algo y se complementa con el catálogo general.
MIN_CANDIDATOS_UTILES = 8

_estrategia = SimilitudTfidfCoseno()


def _texto_consulta(repuesto: dict) -> str:
    return " ".join(
        str(repuesto.get(campo) or "")
        for campo in ("nombre", "descripcion", "categoria")
    ).strip()


def _reunir_candidatos(repuesto: dict) -> list[dict]:
    """Candidatos a sugerir: primero los de la misma categoría, y si son
    pocos se completa con el catálogo general.

    Se filtra por categoría antes de rankear (y no después) porque el IDF se
    calcula sobre el corpus que se le pasa: un corpus acotado al dominio del
    producto hace que las palabras que de verdad distinguen —"pastilla",
    "delantera", "12v"— pesen más que si compitieran contra todo el catálogo.
    """
    categoria = (repuesto.get("categoria") or "").strip()
    candidatos: list[dict] = []

    if categoria:
        candidatos = buscar_en_catalogo(categoria, limit=MAX_CANDIDATOS)

    if len(candidatos) < MIN_CANDIDATOS_UTILES:
        vistos = {c.get("id") for c in candidatos}
        for extra in buscar_en_catalogo("", limit=MAX_CANDIDATOS):
            if extra.get("id") not in vistos:
                candidatos.append(extra)

    # Fuera el propio repuesto: siempre sería el más parecido a sí mismo.
    return [c for c in candidatos if str(c.get("id")) != str(repuesto.get("id"))]


def recomendar_similares(repuesto_id: int | str, limite: int = 5) -> dict:
    """Devuelve los `limite` repuestos más parecidos al indicado.

    @raises BackendNoDisponibleError si el catálogo no se puede consultar —
            el backend PHP lo traduce a "sin sugerencias" sin romper la vista.
    @raises ValueError si el repuesto no existe (es un 404, no una caída).
    """
    repuesto = obtener_repuesto(repuesto_id)
    if not repuesto:
        raise ValueError(f"Repuesto {repuesto_id} no encontrado")

    candidatos = _reunir_candidatos(repuesto)
    if not candidatos:
        return {"repuesto_id": repuesto.get("id"), "recomendaciones": []}

    consulta = _texto_consulta(repuesto)
    rankeados = _estrategia.rankear(consulta, candidatos)

    recomendaciones = [
        {
            "id": r.get("id"),
            "codigo": r.get("codigo"),
            "nombre": r.get("nombre"),
            "categoria": r.get("categoria"),
            "stock": r.get("stock"),
            "precio_venta": r.get("precio_venta"),
            "similitud": round(r["similitud"], 4),
        }
        for r in rankeados
        if r.get("similitud", 0) >= UMBRAL_SIMILITUD
    ][:limite]

    logger.info(
        "Recomendaciones para repuesto %s: %d de %d candidatos superaron el umbral",
        repuesto_id, len(recomendaciones), len(candidatos),
    )
    return {
        "repuesto_id": repuesto.get("id"),
        "nombre": repuesto.get("nombre"),
        "recomendaciones": recomendaciones,
    }

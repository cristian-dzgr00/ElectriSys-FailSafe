"""Orquesta el pipeline completo del asistente:

texto -> intención + entidades -> (según intención) consulta al backend +
ranking por similitud -> respuesta NLG.

Es el único punto de entrada que usa main.py — se mantiene separado de la
capa HTTP (FastAPI) para poder probarlo sin necesidad de un servidor real.
"""
import logging

from app.intent.classifier import predecir_intencion
from app.ner import dictionary
from app.ner.extractor import extraer_entidades
from app.nlg import templates
from app.recommender.client_backend import (
    BackendNoDisponibleError,
    buscar_compatibles,
    buscar_en_catalogo,
    obtener_compatibilidad,
)
from app.recommender.tfidf_cosine import SimilitudTfidfCoseno

logger = logging.getLogger(__name__)

TOP_K = 3
_estrategia_similitud = SimilitudTfidfCoseno()


def _entidades_del_texto(texto: str) -> dict:
    return extraer_entidades(
        texto,
        marcas_conocidas=dictionary.obtener_marcas(),
        modelos_conocidos=dictionary.obtener_modelos(),
        categorias_conocidas=dictionary.obtener_categorias(),
    )


def _buscar_candidatos_por_vehiculo(entidades: dict) -> tuple[list[dict], bool]:
    """Devuelve (candidatos, compatibilidad_exacta)."""
    candidatos = buscar_compatibles(
        marca=entidades["marca"],
        modelo=entidades["modelo"],
        anio=entidades.get("anio"),
        motor=entidades.get("motor"),
        combustible=entidades.get("combustible"),
        categoria=entidades.get("categoria"),
    )
    if candidatos:
        return candidatos, True

    # Sin compatibilidad exacta registrada: si hay categoría, buscar en todo
    # el catálogo por esa categoría (avisando al usuario que no se confirmó
    # compatibilidad exacta — ver templates.recomendar_sustituto).
    if entidades.get("categoria"):
        return buscar_en_catalogo(entidades["categoria"]), False

    return [], True


def _procesar_recomendar_sustituto(texto: str, entidades: dict) -> tuple[list[dict], str]:
    if not entidades.get("marca") or not entidades.get("modelo"):
        return [], templates.sin_vehiculo_identificado()

    try:
        candidatos, compatibilidad_exacta = _buscar_candidatos_por_vehiculo(entidades)
    except BackendNoDisponibleError:
        return [], templates.backend_no_disponible()

    disponibles = [c for c in candidatos if c.get("stock", 0) > 0]
    top = _estrategia_similitud.rankear(texto, disponibles)[:TOP_K]
    return top, templates.recomendar_sustituto(top, entidades, compatibilidad_exacta)


def _procesar_buscar_repuesto(texto: str, entidades: dict) -> tuple[list[dict], str]:
    if not entidades.get("marca") or not entidades.get("modelo"):
        return [], templates.sin_vehiculo_identificado()

    try:
        candidatos, _ = _buscar_candidatos_por_vehiculo(entidades)
    except BackendNoDisponibleError:
        return [], templates.backend_no_disponible()

    rankeados = _estrategia_similitud.rankear(texto, candidatos)
    return rankeados[:TOP_K], templates.buscar_repuesto(rankeados, entidades)


def _procesar_consulta_producto(intencion: str, texto: str, entidades: dict) -> tuple[list[dict], str]:
    termino = entidades.get("codigo") or entidades.get("categoria")
    if not termino:
        if intencion == "consultar_compatibilidad":
            return [], templates.consultar_compatibilidad([], texto)
        if intencion == "consultar_stock":
            return [], templates.consultar_stock(None, texto)
        return [], templates.consultar_precio(None, texto)

    try:
        candidatos = buscar_en_catalogo(termino)
    except BackendNoDisponibleError:
        return [], templates.backend_no_disponible()

    rankeados = _estrategia_similitud.rankear(texto, candidatos)
    producto = rankeados[0] if rankeados else None

    if intencion == "consultar_stock":
        return ([producto] if producto else []), templates.consultar_stock(producto, termino)
    if intencion == "consultar_precio":
        return ([producto] if producto else []), templates.consultar_precio(producto, termino)

    # consultar_compatibilidad: necesita los vehículos compatibles del
    # producto encontrado, no el producto en sí.
    if not producto:
        return [], templates.consultar_compatibilidad([], termino)
    try:
        vehiculos = obtener_compatibilidad(producto["id"])
    except BackendNoDisponibleError:
        return [producto], templates.backend_no_disponible()
    return [producto], templates.consultar_compatibilidad(vehiculos, producto.get("nombre", termino))


def procesar_consulta(texto: str) -> dict:
    intencion, confianza = predecir_intencion(texto)
    entidades = _entidades_del_texto(texto)

    if intencion in ("saludo_despedida", "fuera_de_dominio"):
        sugerencias, respuesta = [], templates.responder_fijo(intencion)
    elif intencion == "recomendar_sustituto":
        sugerencias, respuesta = _procesar_recomendar_sustituto(texto, entidades)
    elif intencion == "buscar_repuesto":
        sugerencias, respuesta = _procesar_buscar_repuesto(texto, entidades)
    elif intencion in ("consultar_stock", "consultar_precio", "consultar_compatibilidad"):
        sugerencias, respuesta = _procesar_consulta_producto(intencion, texto, entidades)
    else:  # pragma: no cover - no debería ocurrir, las 7 intenciones están cubiertas arriba
        sugerencias, respuesta = [], templates.responder_fijo("fuera_de_dominio")

    return {
        "intencion": intencion,
        "confianza": round(confianza, 4),
        "entidades": entidades,
        "sugerencias": sugerencias,
        "respuesta_texto": respuesta,
    }

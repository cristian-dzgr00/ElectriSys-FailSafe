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


def _marcar_compatibilidad(candidatos: list[dict], confirmada: bool) -> list[dict]:
    """Copia cada candidato con la bandera `compatibilidad_confirmada`.

    La bandera viaja con cada sugerencia (y no solo en la respuesta) para que
    la interfaz pueda rotular una por una sin adivinar de dónde salió.
    """
    return [{**c, "compatibilidad_confirmada": confirmada} for c in candidatos]


def _respaldo_por_categoria(texto: str, entidades: dict) -> list[dict]:
    """Hasta TOP_K repuestos CON stock de la categoría detectada, marcados como
    compatibilidad NO confirmada. Lista vacía si no hay categoría o si el
    catálogo no responde: es un extra, nunca debe romper la respuesta."""
    categoria = entidades.get("categoria")
    if not categoria:
        return []
    try:
        candidatos = buscar_en_catalogo(categoria)
    except BackendNoDisponibleError:
        return []
    disponibles = [c for c in candidatos if c.get("stock", 0) > 0]
    top = _estrategia_similitud.rankear(texto, disponibles)[:TOP_K]
    return _marcar_compatibilidad(top, False)


AVISO_NO_CONFIRMADA = "Compatibilidad no confirmada: verifica con el vehículo antes de vender."


def _opciones_de_categoria(opciones: list[dict]) -> str:
    return " o ".join(
        f"\"{c.get('codigo', '?')}\" de {c.get('proveedor') or 'catálogo'}" for c in opciones
    )


def _pregunta_aclaracion(entidades: dict) -> tuple[str, list[str]]:
    """Pregunta corta según lo que falta, y la lista de campos faltantes."""
    marca, modelo = entidades.get("marca"), entidades.get("modelo")
    categoria = entidades.get("categoria")
    if marca and not modelo:
        return f"¿Qué modelo de {marca}?", ["modelo"]
    if modelo and not marca:
        return f"¿De qué marca es el {modelo}?", ["marca"]
    if categoria:
        return f"Para buscar en {categoria}, ¿para qué marca y modelo de vehículo?", ["marca", "modelo"]
    return "¿Para qué marca y modelo de vehículo?", ["marca", "modelo"]


def _responder_sin_vehiculo(texto: str, entidades: dict) -> tuple[list[dict], str]:
    """Falta marca y/o modelo: se pregunta, y si ya se sabe la categoría se
    muestran hasta 3 opciones en stock rotuladas como NO confirmadas."""
    pregunta, _ = _pregunta_aclaracion(entidades)
    respaldo = _respaldo_por_categoria(texto, entidades)
    if not respaldo:
        return [], pregunta
    return respaldo, (
        f"{pregunta} Mientras tanto, en {entidades['categoria']} hay con stock "
        f"{_opciones_de_categoria(respaldo)}. {AVISO_NO_CONFIRMADA}"
    )


def _procesar_recomendar_sustituto(texto: str, entidades: dict) -> tuple[list[dict], str]:
    if not entidades.get("marca") or not entidades.get("modelo"):
        return _responder_sin_vehiculo(texto, entidades)

    try:
        candidatos, compatibilidad_exacta = _buscar_candidatos_por_vehiculo(entidades)
    except BackendNoDisponibleError:
        return [], templates.backend_no_disponible()

    disponibles = [c for c in candidatos if c.get("stock", 0) > 0]
    top = _marcar_compatibilidad(
        _estrategia_similitud.rankear(texto, disponibles)[:TOP_K], compatibilidad_exacta
    )
    return top, templates.recomendar_sustituto(top, entidades, compatibilidad_exacta)


def _procesar_buscar_repuesto(texto: str, entidades: dict) -> tuple[list[dict], str]:
    if not entidades.get("marca") or not entidades.get("modelo"):
        return _responder_sin_vehiculo(texto, entidades)

    try:
        candidatos, compatibilidad_exacta = _buscar_candidatos_por_vehiculo(entidades)
    except BackendNoDisponibleError:
        return [], templates.backend_no_disponible()

    if not compatibilidad_exacta:
        # Lo que llegó es la categoría completa, no repuestos registrados
        # para el vehículo: decir "sí, hay disponible … para <vehículo>" sería
        # afirmar una compatibilidad que nadie verificó.
        disponibles = [c for c in candidatos if c.get("stock", 0) > 0]
        top = _marcar_compatibilidad(_estrategia_similitud.rankear(texto, disponibles)[:TOP_K], False)
        vehiculo = templates._describir_vehiculo(entidades)
        if not top:
            return [], f"No encontré ese repuesto registrado para {vehiculo}."
        return top, (
            f"No encontré ese repuesto registrado para {vehiculo}, pero en la misma categoría hay con stock "
            f"{_opciones_de_categoria(top)}. {AVISO_NO_CONFIRMADA}"
        )

    rankeados = _estrategia_similitud.rankear(texto, candidatos)
    return _marcar_compatibilidad(rankeados[:TOP_K], True), templates.buscar_repuesto(rankeados, entidades)


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


def _fusionar_entidades(entidades_nuevas: dict, contexto_previo: dict | None) -> dict:
    """Completa los campos que el texto actual no mencionó con los del turno
    anterior — memoria de una sola ranura de contexto (ver docs/asistente-nlp.md),
    no un gestor de diálogo con estado conversacional completo.

    Las entidades del texto actual ganan siempre que estén presentes: si el
    usuario corrige algo ("no, el Corolla es del 2019"), el turno nuevo debe
    prevalecer sobre el contexto viejo.
    """
    contexto_previo = contexto_previo or {}
    return {
        campo: entidades_nuevas.get(campo) or contexto_previo.get(campo)
        for campo in entidades_nuevas
    }


def _falta_vehiculo(intencion: str, entidades: dict) -> bool:
    """True si la intención necesita marca+modelo para resolver y todavía
    faltan después de fusionar con el contexto previo — dispara el diálogo
    multi-turno (ver procesar_consulta)."""
    return intencion in ("recomendar_sustituto", "buscar_repuesto") and not (
        entidades.get("marca") and entidades.get("modelo")
    )


# Con confianza por debajo de esto, un texto que solo aporta marca/modelo se
# considera la respuesta a la pregunta pendiente y no un tema nuevo.
CONFIANZA_CAMBIO_DE_TEMA = 0.5


def _compatibilidad_de(sugerencias: list[dict]) -> bool | None:
    """True si todo lo sugerido tiene compatibilidad confirmada, False si hay
    algo sin confirmar, None si no se sugirió nada (o no aplica)."""
    banderas = [s["compatibilidad_confirmada"] for s in sugerencias if "compatibilidad_confirmada" in s]
    if not banderas:
        return None
    return all(banderas)


def _intencion_con_pendiente(intencion: str, confianza: float, entidades_nuevas: dict,
                             contexto_previo: dict | None) -> str:
    """Si el turno anterior quedó esperando marca/modelo y el texto nuevo solo
    los aporta ("toyota hilux"), el clasificador puede verlo como fuera de
    dominio porque ya no menciona el repuesto. La intención pendiente viaja en
    el contexto (`_intencion_pendiente`) y se retoma solo en ese caso."""
    pendiente = (contexto_previo or {}).get("_intencion_pendiente")
    if pendiente not in ("recomendar_sustituto", "buscar_repuesto"):
        return intencion
    if intencion in ("recomendar_sustituto", "buscar_repuesto"):
        return intencion
    if intencion != "fuera_de_dominio" and confianza >= CONFIANZA_CAMBIO_DE_TEMA:
        return intencion
    if entidades_nuevas.get("marca") or entidades_nuevas.get("modelo"):
        return pendiente
    return intencion


def procesar_consulta(texto: str, contexto_previo: dict | None = None) -> dict:
    intencion, confianza = predecir_intencion(texto)
    entidades_nuevas = _entidades_del_texto(texto)
    intencion = _intencion_con_pendiente(intencion, confianza, entidades_nuevas, contexto_previo)
    entidades = _fusionar_entidades(entidades_nuevas, contexto_previo)

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

    esperando = _falta_vehiculo(intencion, entidades)
    faltan = _pregunta_aclaracion(entidades)[1] if esperando else []
    return {
        "intencion": intencion,
        "confianza": round(confianza, 4),
        "entidades": entidades,
        "sugerencias": sugerencias,
        "respuesta_texto": respuesta,
        "esperando_datos": esperando,
        # Campos nuevos (aditivos): permiten a la interfaz resaltar la pregunta
        # de aclaración y retomar la intención en el turno siguiente.
        "faltan_datos": faltan,
        "intencion_pendiente": intencion if esperando else None,
        "compatibilidad_confirmada": _compatibilidad_de(sugerencias),
    }

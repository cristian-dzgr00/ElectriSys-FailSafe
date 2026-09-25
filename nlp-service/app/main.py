"""ElectriSys - Microservicio de NLP para recomendación de repuestos.

Sprint 5: /nlp/consultar exige el header X-Internal-Key cuando
NLP_INTERNAL_KEY está configurado — evita que cualquiera dentro de la
red de Docker pueda usar el microservicio; solo el backend PHP conoce
la clave (ver backend/src/patterns/observer/GestorAsistente.php).
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from app import config
from app.demanda.forecast import predecir_demanda, predecir_demanda_lote
from app.demanda.reabastecimiento import DIAS_COBERTURA, DIAS_ENTREGA, sugerir_pedido
from app.intent.train import MODEL_PATH, entrenar
from app.pipeline import procesar_consulta
from app.asociacion.reglas import recomendar_complementos
from app.busqueda.corrector import corregir
from app.recommender.client_backend import (
    BackendNoDisponibleError,
    buscar_en_catalogo,
    obtener_canastas,
)
from app.recommender.similares import recomendar_similares


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not Path(MODEL_PATH).exists():
        entrenar()
    yield


app = FastAPI(title="ElectriSys NLP Service", version="0.5.0", lifespan=lifespan)


class ConsultaRequest(BaseModel):
    texto: str = Field(..., min_length=1, max_length=1000)
    contexto_previo: dict | None = None


class SugerenciaPedidoRequest(BaseModel):
    repuesto_ids: list[int] = Field(default_factory=list)
    # Los dos parámetros del modelo de reorden. Se acotan acá y no solo en el
    # frontend: un dias_cobertura absurdo generaría un pedido gigante.
    dias_entrega: int = Field(default=DIAS_ENTREGA, ge=1, le=90)
    dias_cobertura: int = Field(default=DIAS_COBERTURA, ge=7, le=180)
    # {repuesto_id (str): unidades ya pedidas y no recibidas}
    en_transito: dict[str, float] | None = None


def _verificar_clave_interna(x_internal_key: str = Header(default="")) -> None:
    if config.NLP_INTERNAL_KEY and x_internal_key != config.NLP_INTERNAL_KEY:
        raise HTTPException(status_code=401, detail="Clave interna inválida o ausente")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/nlp/consultar", dependencies=[Depends(_verificar_clave_interna)])
def consultar(payload: ConsultaRequest):
    return procesar_consulta(payload.texto, payload.contexto_previo)


@app.get("/recomendaciones/{repuesto_id}", dependencies=[Depends(_verificar_clave_interna)])
def recomendaciones(repuesto_id: int, limite: int = 5):
    """Productos relacionados / sustitutos sugeridos para un repuesto.

    Mismo motor TF-IDF + coseno del asistente, sin LLM externo.
    Lo consume la sección "Sugerencias" de Repuestos.jsx a través del proxy
    GET /api/repuestos/{id}/recomendaciones del backend PHP.
    """
    try:
        return recomendar_similares(repuesto_id, limite=min(10, max(1, limite)))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except BackendNoDisponibleError as e:
        # 503 y no 500: el microservicio esta sano, quien no responde es el
        # catalogo. El backend PHP lo traduce a "sin sugerencias".
        raise HTTPException(status_code=503, detail=str(e)) from e


@app.get("/corregir-busqueda", dependencies=[Depends(_verificar_clave_interna)])
def corregir_busqueda(q: str = ""):
    """Corrige una búsqueda que no dio resultados: "filtro acite" -> "filtro de aceite".

    El backend solo llama acá cuando la búsqueda normal devolvió cero
    resultados, así que el costo extra lo paga únicamente quien se equivocó
    al escribir, no cada búsqueda del día.
    """
    consulta = (q or "").strip()
    if len(consulta) < 3:
        return {"original": consulta, "corregida": None, "cambios": []}
    try:
        # El catálogo completo como vocabulario: se corrige contra los
        # productos que existen, no contra un diccionario del español.
        return corregir(consulta, buscar_en_catalogo("", limit=100))
    except BackendNoDisponibleError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


@app.get("/complementos", dependencies=[Depends(_verificar_clave_interna)])
def complementos(ids: str = "", limite: int = 5, dias: int = 180):
    """Productos que suelen venderse junto a los de la venta en curso.

    Distinto de /recomendaciones, que busca productos PARECIDOS (sustitutos).
    Esto busca COMPLEMENTARIOS a partir de lo que la gente realmente compró
    junto: pastillas de freno -> líquido de frenos, no -> otras pastillas.
    """
    en_canasta = [int(x) for x in ids.split(",") if x.strip().isdigit()]
    if not en_canasta:
        return {"data": []}
    try:
        canastas = obtener_canastas(dias=dias)
        return {
            "data": recomendar_complementos(canastas, en_canasta, limite=min(10, max(1, limite))),
            "canastas_analizadas": len(canastas),
        }
    except BackendNoDisponibleError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


@app.post("/sugerencia-pedido", dependencies=[Depends(_verificar_clave_interna)])
def sugerencia_pedido(payload: SugerenciaPedidoRequest):
    """Cuántas unidades pedirle al proveedor de cada repuesto.

    Es POST y no GET porque recibe el mapa de unidades en tránsito, que
    puede ser largo y lo calcula el backend (es quien conoce los pedidos
    abiertos). Devuelve TODOS los repuestos consultados, con la bandera
    necesita_reabastecer: así la vista puede mostrar también los que están
    bien, en vez de dejar al usuario preguntándose si se omitió algo.
    """
    ids = payload.repuesto_ids[:200]
    if not ids:
        return {"data": []}
    try:
        return {
            "data": sugerir_pedido(
                ids,
                dias_entrega=payload.dias_entrega,
                dias_cobertura=payload.dias_cobertura,
                en_transito=payload.en_transito or {},
            ),
            "dias_entrega": payload.dias_entrega,
            "dias_cobertura": payload.dias_cobertura,
        }
    except BackendNoDisponibleError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


@app.get("/prediccion-demanda", dependencies=[Depends(_verificar_clave_interna)])
def prediccion_demanda_lote(ids: str = ""):
    """Señales de reabastecimiento de varios repuestos a la vez.

    `ids` es una lista separada por comas (los ids de la página que el
    usuario está viendo). Se ignoran silenciosamente los valores que no
    sean numéricos en vez de responder 422: esto alimenta un adorno de la
    tabla, y un id mal formado no debe tumbar la vista entera.
    """
    numericos = [int(x) for x in ids.split(",") if x.strip().isdigit()]
    if not numericos:
        return {"data": []}
    # Tope defensivo: la tabla pide 15 por página; un ids= gigante haría
    # que Oracle arme un IN (...) enorme desde una ruta sin rate limit.
    numericos = numericos[:100]
    try:
        return {"data": predecir_demanda_lote(numericos)}
    except BackendNoDisponibleError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


@app.get("/prediccion-demanda/{repuesto_id}", dependencies=[Depends(_verificar_clave_interna)])
def prediccion_demanda(repuesto_id: int):
    """Señal de reabastecimiento por promedio móvil sobre ventas reales."""
    try:
        return predecir_demanda(repuesto_id)
    except BackendNoDisponibleError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

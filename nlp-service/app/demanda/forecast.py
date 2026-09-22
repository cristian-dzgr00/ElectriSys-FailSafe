"""Estimación de demanda por promedio móvil ponderado.

Deliberadamente simple: promedio móvil sobre las ventas semanales reales del
repuesto, con más peso en las semanas recientes. Nada de redes neuronales ni
librerías de deep learning — el requisito del curso es un modelo propio, y
para una serie de 12 puntos un modelo más pesado no predeciría mejor, solo
sería más difícil de justificar en la sustentación.

Lo que responde: "¿en cuántos días se acaba el stock si se sigue vendiendo
como en las últimas semanas?". Con eso el frontend decide si mostrar
"Reabastecer pronto" o "Rotación baja".
"""
import logging
from datetime import date, datetime

from app.recommender.client_backend import obtener_demanda, obtener_demanda_lote

logger = logging.getLogger(__name__)

DIAS_HISTORIAL = 90           # ~13 semanas: suficiente para ver estacionalidad corta
DIAS_POR_SEMANA = 7

# Umbrales de la señal. Están acá y no en el frontend para que la regla sea
# una sola y quede versionada junto al modelo que la alimenta.
DIAS_COBERTURA_CRITICA = 14   # menos de dos semanas de inventario -> reabastecer
DIAS_COBERTURA_EXCESO = 120   # más de cuatro meses parado -> rotación baja


def _a_fecha(valor) -> date | None:
    """Las fechas llegan como ISO desde Oracle vía PHP; se toleran ambos
    formatos (con y sin hora) porque el driver oci8 no siempre las serializa
    igual según el tipo de columna."""
    if isinstance(valor, str):
        try:
            return datetime.fromisoformat(valor.replace("Z", "+00:00")).date()
        except ValueError:
            try:
                return datetime.strptime(valor[:10], "%Y-%m-%d").date()
            except ValueError:
                return None
    return None


def _unidades_por_semana(serie: list[dict], hoy: date) -> list[float]:
    """Agrupa la serie diaria en semanas hacia atrás desde hoy.

    Índice 0 = semana más antigua, último = semana en curso. Las semanas sin
    ventas quedan en 0 a propósito: son información (no se vendió nada), no
    huecos que haya que ignorar.
    """
    total_semanas = DIAS_HISTORIAL // DIAS_POR_SEMANA
    semanas = [0.0] * total_semanas

    for fila in serie:
        fecha = _a_fecha(fila.get("fecha"))
        if fecha is None:
            continue
        dias_atras = (hoy - fecha).days
        if dias_atras < 0 or dias_atras >= DIAS_HISTORIAL:
            continue
        indice = total_semanas - 1 - (dias_atras // DIAS_POR_SEMANA)
        if 0 <= indice < total_semanas:
            semanas[indice] += float(fila.get("unidades") or 0)

    return semanas


def _promedio_movil_ponderado(semanas: list[float]) -> float:
    """Promedio con pesos linealmente crecientes: la semana más reciente pesa
    tanto como la cantidad de semanas consideradas, la más vieja pesa 1.

    Frente al promedio simple, esto reacciona a un cambio de tendencia sin
    depender de una sola semana (que puede ser un pico puntual de una venta
    grande a un taller)."""
    if not semanas:
        return 0.0
    pesos = list(range(1, len(semanas) + 1))
    total_peso = sum(pesos)
    return sum(v * p for v, p in zip(semanas, pesos)) / total_peso


def predecir_demanda(repuesto_id: int | str) -> dict:
    """Estima la demanda semanal del repuesto y cuánto le dura el stock.

    @raises BackendNoDisponibleError si no se puede leer el historial.
    """
    return _calcular(obtener_demanda(repuesto_id, dias=DIAS_HISTORIAL), repuesto_id)


def predecir_demanda_lote(repuesto_ids: list) -> list[dict]:
    """Igual que predecir_demanda pero para varios repuestos de una vez.

    Lo usa la TABLA de repuestos, que necesita la señal de las 15 filas de
    la página. Pedirlas de a una serían 15 idas y vueltas HTTP y 15
    consultas a Oracle por cada cambio de página; el backend las resuelve
    con una sola consulta agrupada y acá solo se hace la aritmética, que es
    en memoria y sobre 12 números por repuesto.

    Los repuestos sin ventas en el período igual vienen en la respuesta del
    backend (con serie vacía), así que ninguno se pierde en silencio.

    @raises BackendNoDisponibleError si no se puede leer el historial.
    """
    if not repuesto_ids:
        return []
    datos = obtener_demanda_lote(repuesto_ids, dias=DIAS_HISTORIAL)
    return [_calcular(fila, fila.get("repuesto_id")) for fila in datos.get("repuestos", [])]


def _calcular(datos: dict, repuesto_id) -> dict:
    """Aritmética de la predicción, sin nada de E/S: recibe {serie, stock,
    stock_minimo} y devuelve la señal. Separado de la obtención de datos
    para que la versión individual y la de lote no puedan divergir."""
    serie = datos.get("serie", [])
    stock = float(datos.get("stock") or 0)
    stock_minimo = float(datos.get("stock_minimo") or 0)

    hoy = date.today()
    semanas = _unidades_por_semana(serie, hoy)
    demanda_semanal = _promedio_movil_ponderado(semanas)
    demanda_diaria = demanda_semanal / DIAS_POR_SEMANA

    unidades_periodo = sum(semanas)

    # Sin demanda medible no se puede dividir: la cobertura es "infinita",
    # que para el negocio significa capital parado, no inventario sano.
    if demanda_diaria <= 0:
        dias_cobertura = None
        senal = "rotacion_baja" if stock > 0 else "sin_datos"
    else:
        dias_cobertura = round(stock / demanda_diaria, 1)
        if stock <= stock_minimo or dias_cobertura <= DIAS_COBERTURA_CRITICA:
            senal = "reabastecer"
        elif dias_cobertura >= DIAS_COBERTURA_EXCESO:
            senal = "rotacion_baja"
        else:
            senal = "normal"

    return {
        "repuesto_id": datos.get("repuesto_id", repuesto_id),
        "senal": senal,
        "stock": stock,
        "stock_minimo": stock_minimo,
        "unidades_periodo": unidades_periodo,
        "dias_historial": DIAS_HISTORIAL,
        "demanda_semanal_estimada": round(demanda_semanal, 2),
        "dias_cobertura": dias_cobertura,
        # Se devuelve la serie semanal para que la vista pueda dibujarla si
        # algún día se quiere, y para que la señal sea auditable a ojo.
        "semanas": [round(v, 2) for v in semanas],
    }

"""Cuánto pedirle al proveedor, a partir de la demanda estimada.

forecast.py responde "¿hace falta reponer?"; este módulo responde la
pregunta que viene después, que es la que de verdad cuesta: "¿cuántas
unidades pido?".

El modelo es el punto de reorden clásico de gestión de inventarios:

    punto_reorden   = demanda_diaria × dias_entrega + stock_seguridad
    stock_seguridad = demanda_diaria × dias_entrega × FACTOR_SEGURIDAD
    cantidad        = demanda_diaria × (dias_entrega + dias_cobertura)
                      − stock_actual − lo que ya viene en camino

Se pide cuando el stock cae por debajo del punto de reorden, y se pide lo
suficiente para cubrir el tiempo de entrega MÁS el período que se quiere
tener cubierto. Pedir solo hasta el punto de reorden obligaría a pedir de
nuevo casi enseguida.

Deliberadamente no se usa EOQ (cantidad económica de pedido): exige conocer
el costo de emitir una orden y el costo de mantener inventario, dos números
que el negocio no tiene medidos. Un modelo que pide datos inventados no es
más inteligente, solo más difícil de justificar.
"""
import math

from app.demanda.forecast import DIAS_POR_SEMANA, predecir_demanda_lote

# Días que tarda el proveedor en entregar. Es el parámetro que más mueve el
# resultado, así que se puede pasar por request; este es el valor por defecto.
DIAS_ENTREGA = 7

# Cuántos días de venta se quieren tener cubiertos además del tiempo de
# entrega. Un mes es el ciclo natural de compras del negocio.
DIAS_COBERTURA = 30

# Colchón sobre el consumo esperado durante la entrega, para absorber un pico
# de demanda o un proveedor que se atrasa. 0.5 = medio tiempo de entrega extra.
FACTOR_SEGURIDAD = 0.5


def _redondear_pedido(cantidad: float) -> int:
    """Siempre hacia arriba: quedarse corto significa perder una venta, y
    sobrar una unidad solo cuesta el espacio en el estante."""
    return max(0, math.ceil(cantidad))


def calcular_sugerencia(prediccion: dict, dias_entrega: int, dias_cobertura: int,
                        en_transito: float = 0.0) -> dict:
    """Traduce una predicción de demanda en una sugerencia de compra.

    `en_transito` son las unidades ya pedidas al proveedor y todavía no
    recibidas: sin descontarlas, el sistema sugeriría pedir de nuevo lo que
    ya viene en camino cada vez que alguien abre la pantalla.
    """
    demanda_semanal = float(prediccion.get("demanda_semanal_estimada") or 0)
    demanda_diaria = demanda_semanal / DIAS_POR_SEMANA
    stock = float(prediccion.get("stock") or 0)
    stock_minimo = float(prediccion.get("stock_minimo") or 0)

    consumo_entrega = demanda_diaria * dias_entrega
    stock_seguridad = consumo_entrega * FACTOR_SEGURIDAD
    punto_reorden = consumo_entrega + stock_seguridad

    disponible = stock + en_transito

    # El stock_minimo que el negocio configuró a mano se respeta como piso:
    # si alguien lo puso alto por experiencia, el modelo no lo contradice.
    punto_reorden_efectivo = max(punto_reorden, stock_minimo)

    necesita = disponible < punto_reorden_efectivo

    objetivo = demanda_diaria * (dias_entrega + dias_cobertura) + stock_seguridad
    # Aunque no haya demanda medible, si está por debajo del mínimo configurado
    # hay que llevarlo al menos hasta ahí.
    objetivo = max(objetivo, stock_minimo)
    cantidad = _redondear_pedido(objetivo - disponible) if necesita else 0

    return {
        "repuesto_id": prediccion.get("repuesto_id"),
        "necesita_reabastecer": bool(necesita and cantidad > 0),
        "cantidad_sugerida": cantidad,
        "stock_actual": stock,
        "en_transito": en_transito,
        "punto_reorden": round(punto_reorden_efectivo, 1),
        "demanda_semanal_estimada": round(demanda_semanal, 2),
        "dias_cobertura_actual": prediccion.get("dias_cobertura"),
        "senal": prediccion.get("senal"),
        # Para que la vista pueda explicar POR QUÉ sugiere esa cantidad, en
        # vez de mostrar un número que el usuario tiene que creer.
        "motivo": _motivo(necesita, cantidad, demanda_semanal, stock, stock_minimo),
    }


def _motivo(necesita: bool, cantidad: int, demanda_semanal: float,
            stock: float, stock_minimo: float) -> str:
    if not necesita or cantidad <= 0:
        return "Stock suficiente para el período de cobertura."
    if demanda_semanal <= 0:
        return f"Sin ventas recientes, pero el stock ({stock:.0f}) está por debajo del mínimo ({stock_minimo:.0f})."
    return (f"Se venden ~{demanda_semanal:.1f} u./semana y quedan {stock:.0f}: "
            f"no alcanzan para cubrir la entrega más el período de cobertura.")


def sugerir_pedido(repuesto_ids: list, dias_entrega: int = DIAS_ENTREGA,
                   dias_cobertura: int = DIAS_COBERTURA,
                   en_transito: dict | None = None) -> list[dict]:
    """Sugerencia de compra para varios repuestos de una vez.

    @raises BackendNoDisponibleError si no se puede leer el historial.
    """
    if not repuesto_ids:
        return []
    en_transito = en_transito or {}
    predicciones = predecir_demanda_lote(repuesto_ids)
    return [
        calcular_sugerencia(
            p, dias_entrega, dias_cobertura,
            en_transito=float(en_transito.get(str(p.get("repuesto_id")), 0) or 0),
        )
        for p in predicciones
    ]

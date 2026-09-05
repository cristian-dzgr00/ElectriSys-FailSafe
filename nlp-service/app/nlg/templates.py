"""Generación de respuesta por plantillas (NLG) — sin LLM externo.

Los textos usan un tono de "posible sustituto según catálogo" en vez de
afirmarlo como garantía: el motor de recomendación rankea por similitud
textual, no por especificación técnica exacta de intercambiabilidad.
"""

RESPUESTAS_FIJAS = {
    "saludo_despedida": (
        "¡Hola! Puedo ayudarte a buscar repuestos, consultar precio o stock, "
        "verificar compatibilidad con un vehículo, o recomendar un sustituto "
        "si algo está agotado. ¿Qué necesitas?"
    ),
    "fuera_de_dominio": (
        "No tengo información sobre eso. Puedo ayudarte con repuestos: "
        "buscar disponibilidad, precio, stock, compatibilidad o sustitutos."
    ),
}


def responder_fijo(intencion: str) -> str:
    return RESPUESTAS_FIJAS.get(intencion, RESPUESTAS_FIJAS["fuera_de_dominio"])


def _describir_vehiculo(entidades: dict) -> str:
    partes = [
        entidades.get("marca"),
        entidades.get("modelo"),
        entidades.get("motor"),
        entidades.get("combustible"),
        str(entidades["anio"]) if entidades.get("anio") else None,
    ]
    partes = [p for p in partes if p]
    return " ".join(partes) if partes else "ese vehículo"


def sin_vehiculo_identificado() -> str:
    return (
        "No logré identificar la marca y el modelo del vehículo en tu mensaje. "
        "¿Puedes indicarme marca, modelo y, si aplica, año/motor/combustible?"
    )


def backend_no_disponible() -> str:
    return "No pude consultar el catálogo en este momento, intenta de nuevo en unos segundos."


def recomendar_sustituto(candidatos: list[dict], entidades: dict, compatibilidad_exacta: bool) -> str:
    vehiculo = _describir_vehiculo(entidades)
    if not candidatos:
        return (
            f"No encontré sustitutos con stock disponible registrados para {vehiculo}. "
            "Te recomiendo verificar con el proveedor o ampliar la búsqueda."
        )

    aviso = "" if compatibilidad_exacta else (
        " (no encontré compatibilidad exacta registrada para ese vehículo; son resultados "
        "de la misma categoría, verifica antes de ofrecerlos)"
    )

    if len(candidatos) == 1:
        c = candidatos[0]
        return (
            f"Puedes recomendar el repuesto \"{c.get('codigo', '?')}\" de {c.get('proveedor') or 'catálogo'} "
            f"— posible sustituto para {vehiculo}. Stock disponible: {c.get('stock', 0)} unidades{aviso}."
        )

    nombres = " o ".join(
        f"\"{c.get('codigo', '?')}\" de {c.get('proveedor') or 'catálogo'}" for c in candidatos
    )
    return f"Puedes recomendar el repuesto {nombres} — posibles sustitutos para {vehiculo}{aviso}."


def buscar_repuesto(candidatos_rankeados: list[dict], entidades: dict) -> str:
    vehiculo = _describir_vehiculo(entidades)
    disponibles = [c for c in candidatos_rankeados if c.get("stock", 0) > 0]

    if disponibles:
        c = disponibles[0]
        return (
            f"Sí, hay disponible \"{c.get('nombre', '?')}\" (código {c.get('codigo', '?')}) para {vehiculo}. "
            f"Stock: {c.get('stock', 0)} unidades, precio: ${c.get('precio_venta', '?')}."
        )
    if candidatos_rankeados:
        return (
            f"Ese repuesto está registrado para {vehiculo} pero no tiene stock disponible "
            "en este momento. ¿Quieres que te sugiera un sustituto?"
        )
    return f"No encontré ese repuesto registrado para {vehiculo}."


def consultar_stock(producto: dict | None, termino_buscado: str) -> str:
    if not producto:
        return f"No encontré un repuesto que coincida con \"{termino_buscado}\" en el catálogo."
    return (
        f"\"{producto.get('nombre', '?')}\" (código {producto.get('codigo', '?')}) "
        f"tiene {producto.get('stock', 0)} unidades en stock."
    )


def consultar_precio(producto: dict | None, termino_buscado: str) -> str:
    if not producto:
        return f"No encontré un repuesto que coincida con \"{termino_buscado}\" en el catálogo."
    return (
        f"\"{producto.get('nombre', '?')}\" (código {producto.get('codigo', '?')}) "
        f"tiene un precio de venta de ${producto.get('precio_venta', '?')}."
    )


def consultar_compatibilidad(vehiculos_compatibles: list[dict], nombre_producto: str) -> str:
    if not vehiculos_compatibles:
        return f"No encontré compatibilidades registradas para \"{nombre_producto}\"."
    descripciones = [
        f"{v.get('marca')} {v.get('modelo')} ({v.get('anio_desde')}-{v.get('anio_hasta')})"
        for v in vehiculos_compatibles[:5]
    ]
    extra = "" if len(vehiculos_compatibles) <= 5 else f" y {len(vehiculos_compatibles) - 5} más"
    return f"\"{nombre_producto}\" es compatible con: " + ", ".join(descripciones) + f"{extra}."

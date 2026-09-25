"""Productos que se venden juntos — reglas de asociación sobre las ventas.

Responde "quien se llevó X también se llevó Y" a partir del histórico real
de ventas, no del parecido entre descripciones. Es información distinta a la
del recomendador TF-IDF de recommender/similares.py, y por eso conviven:

  - TF-IDF encuentra productos PARECIDOS (dos pastillas de freno). Sirve
    para sustituir: si no hay stock de una, ofrecé la otra.
  - Las reglas de asociación encuentran productos COMPLEMENTARIOS (pastillas
    y líquido de frenos). Sirven para sumar a la venta.

Un recomendador que las mezclara ofrecería "otra pastilla de freno" a quien
acaba de comprar una, que es justo lo que no necesita.

Método: co-ocurrencia con soporte, confianza y lift — el núcleo de Apriori,
sin la generación de itemsets de tamaño arbitrario. Con canastas de pocos
productos, los pares explican casi todo y el algoritmo completo solo agrega
costo. Sin librerías externas: son diccionarios y aritmética.
"""
import logging
from collections import Counter, defaultdict
from itertools import combinations

logger = logging.getLogger(__name__)

# Mínimo de ventas que deben contener el par para tenerlo en cuenta. Con 2,
# una sola coincidencia no genera una "regla": haría falta que se repita.
SOPORTE_MINIMO = 2

# Solo interesan asociaciones que ocurran de verdad: si de 10 ventas del
# producto A, en 2 apareció B, la confianza es 0.2.
CONFIANZA_MINIMA = 0.15

# lift > 1 significa que aparecen juntos MÁS de lo que el azar explicaría.
# Con lift <= 1 la "asociación" es una coincidencia de productos populares:
# sugerir el más vendido a todo el mundo no es una recomendación.
LIFT_MINIMO = 1.0


def _contar(canastas: list[list]) -> tuple[Counter, Counter, int]:
    """Cuenta apariciones individuales y de pares. Una pasada sobre los datos."""
    individual = Counter()
    pares = Counter()
    total = 0

    for canasta in canastas:
        # Un producto repetido en la misma venta no es una co-ocurrencia.
        items = sorted(set(int(i) for i in canasta if i is not None))
        if len(items) < 1:
            continue
        total += 1
        individual.update(items)
        # Las canastas de un solo producto cuentan para el soporte individual
        # (son el denominador de la confianza) pero no generan pares.
        for a, b in combinations(items, 2):
            pares[(a, b)] += 1

    return individual, pares, total


def calcular_reglas(canastas: list[list]) -> dict:
    """Construye el índice de reglas a partir de las canastas de venta.

    Devuelve {producto: [reglas ordenadas por lift]}, listo para consultar.
    """
    individual, pares, total = _contar(canastas)
    if total == 0:
        return {"total_canastas": 0, "reglas": {}}

    reglas = defaultdict(list)

    for (a, b), juntas in pares.items():
        if juntas < SOPORTE_MINIMO:
            continue

        soporte = juntas / total
        # La regla se evalúa en las dos direcciones: que A lleve a B no
        # implica que B lleve a A (B puede ser un producto muy vendido).
        for origen, destino in ((a, b), (b, a)):
            apariciones_origen = individual[origen]
            if apariciones_origen == 0:
                continue
            confianza = juntas / apariciones_origen
            if confianza < CONFIANZA_MINIMA:
                continue
            prob_destino = individual[destino] / total
            lift = confianza / prob_destino if prob_destino > 0 else 0
            if lift <= LIFT_MINIMO:
                continue

            reglas[origen].append({
                "repuesto_id": destino,
                "veces_juntos": juntas,
                "soporte": round(soporte, 4),
                "confianza": round(confianza, 4),
                "lift": round(lift, 3),
            })

    # Por lift: primero lo que menos se explica por azar.
    for origen in reglas:
        reglas[origen].sort(key=lambda r: (r["lift"], r["confianza"]), reverse=True)

    logger.info("Reglas de asociación: %d canastas, %d productos con reglas",
                total, len(reglas))
    return {"total_canastas": total, "reglas": dict(reglas)}


def recomendar_complementos(canastas: list[list], repuesto_ids: list,
                            limite: int = 5) -> list[dict]:
    """Productos que suelen acompañar a los que ya están en la venta.

    Recibe la venta en curso (puede tener varios productos) y devuelve lo
    que conviene ofrecer, sin repetir lo que ya está en la canasta.
    """
    modelo = calcular_reglas(canastas)
    if not modelo["reglas"]:
        return []

    en_canasta = {int(i) for i in repuesto_ids}
    candidatos = {}

    for origen in en_canasta:
        for regla in modelo["reglas"].get(origen, []):
            destino = regla["repuesto_id"]
            if destino in en_canasta:
                continue   # ya lo está llevando
            # Si dos productos de la canasta apuntan al mismo complemento,
            # se conserva la señal más fuerte en vez de sumarlas: el lift no
            # es aditivo y sumarlo inventaría una confianza que no existe.
            previo = candidatos.get(destino)
            if previo is None or regla["lift"] > previo["lift"]:
                candidatos[destino] = {**regla, "sugerido_por": origen}

    return sorted(candidatos.values(),
                  key=lambda r: (r["lift"], r["confianza"]),
                  reverse=True)[:limite]

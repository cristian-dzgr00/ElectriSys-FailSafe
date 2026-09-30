"""Tests de los tres modelos nuevos: reabastecimiento, reglas de asociación
y corrección de búsquedas.

Ninguno toca el backend: se sustituyen las funciones del cliente HTTP.
"""
import pytest

from app.asociacion import reglas
from app.busqueda.corrector import corregir
from app.demanda import reabastecimiento as reab


# ── Sugerencia de reabastecimiento ───────────────────────────────────

def _prediccion(**kw):
    base = {"repuesto_id": 1, "stock": 10, "stock_minimo": 5,
            "demanda_semanal_estimada": 7.0, "dias_cobertura": 10, "senal": "normal"}
    base.update(kw)
    return base


def test_pide_cuando_el_stock_no_cubre_la_entrega():
    # 7 u./semana = 1 u./día. Con 3 unidades no se cubren ni los 7 días
    # que tarda el proveedor.
    r = reab.calcular_sugerencia(_prediccion(stock=3), dias_entrega=7, dias_cobertura=30)
    assert r["necesita_reabastecer"] is True
    assert r["cantidad_sugerida"] > 0


def test_no_pide_cuando_hay_stock_de_sobra():
    r = reab.calcular_sugerencia(_prediccion(stock=500), dias_entrega=7, dias_cobertura=30)
    assert r["necesita_reabastecer"] is False
    assert r["cantidad_sugerida"] == 0


def test_descuenta_lo_que_ya_viene_en_camino():
    """Sin esto se sugeriría pedir de nuevo lo ya pedido cada vez que se
    abre la pantalla, y el inventario terminaría duplicado."""
    sin_transito = reab.calcular_sugerencia(_prediccion(stock=3), 7, 30, en_transito=0)
    con_transito = reab.calcular_sugerencia(_prediccion(stock=3), 7, 30, en_transito=50)
    assert sin_transito["cantidad_sugerida"] > 0
    assert con_transito["necesita_reabastecer"] is False


def test_respeta_el_stock_minimo_configurado_a_mano():
    """Sin ventas no hay demanda que proyectar, pero si el negocio fijó un
    mínimo hay que llegar a él igual."""
    r = reab.calcular_sugerencia(
        _prediccion(stock=1, stock_minimo=20, demanda_semanal_estimada=0), 7, 30)
    assert r["necesita_reabastecer"] is True
    assert r["cantidad_sugerida"] >= 19


def test_la_cantidad_cubre_entrega_mas_cobertura():
    """Pedir solo hasta el punto de reorden obligaría a pedir otra vez casi
    enseguida: la cantidad tiene que cubrir el período completo."""
    r = reab.calcular_sugerencia(
        _prediccion(stock=0, demanda_semanal_estimada=7.0), dias_entrega=7, dias_cobertura=30)
    # 1 u./día × (7 + 30) = 37, más el colchón de seguridad
    assert r["cantidad_sugerida"] >= 37


def test_explica_el_motivo():
    r = reab.calcular_sugerencia(_prediccion(stock=1), 7, 30)
    assert r["motivo"]          # la vista muestra por qué sugiere esa cantidad


# ── Reglas de asociación ─────────────────────────────────────────────

def test_detecta_productos_que_se_venden_juntos():
    canastas = [[1, 2], [1, 2], [1, 2], [3, 4], [1, 5]]
    recomendado = reglas.recomendar_complementos(canastas, [1])
    assert recomendado, "deberia sugerir algo para el producto 1"
    assert recomendado[0]["repuesto_id"] == 2


def test_no_sugiere_lo_que_ya_esta_en_la_canasta():
    canastas = [[1, 2], [1, 2], [1, 2]]
    assert reglas.recomendar_complementos(canastas, [1, 2]) == []


def test_ignora_coincidencias_de_una_sola_vez():
    """Un par que apareció una vez no es una regla, es una casualidad."""
    canastas = [[1, 9], [1, 2], [1, 2], [1, 2]]
    ids = [r["repuesto_id"] for r in reglas.recomendar_complementos(canastas, [1])]
    assert 9 not in ids


def test_descarta_lo_popular_sin_asociacion_real():
    """El producto 99 está en TODAS las ventas: acompañar al 1 no dice nada
    de él. Con lift <= 1 no debe sugerirse, o estaríamos recomendando el más
    vendido a todo el mundo y llamándolo inteligencia."""
    canastas = [[1, 99], [2, 99], [3, 99], [4, 99], [1, 99]]
    ids = [r["repuesto_id"] for r in reglas.recomendar_complementos(canastas, [1])]
    assert 99 not in ids


def test_sin_ventas_no_inventa_reglas():
    assert reglas.recomendar_complementos([], [1]) == []


def test_metricas_presentes():
    # Con 2 en TODAS las ventas el lift sería 1.0 y la regla se descarta a
    # propósito (ver test anterior); las ventas [3] y [4] lo vuelven > 1.
    canastas = [[1, 2], [1, 2], [1, 2], [3], [4]]
    r = reglas.recomendar_complementos(canastas, [1])[0]
    for campo in ("veces_juntos", "soporte", "confianza", "lift"):
        assert campo in r


# ── Corrección de búsquedas ──────────────────────────────────────────

CATALOGO = [
    {"nombre": "Filtro de aceite Mobil 1 M1-102", "categoria": "Lubricantes", "codigo": "FA-001"},
    {"nombre": "Cable THHN 12 AWG", "categoria": "Materiales electricos", "codigo": "CB-012"},
    {"nombre": "Bateria 12v 60ah", "categoria": "Electrico", "codigo": "BT-060"},
]


@pytest.mark.parametrize("entrada,esperado", [
    ("filtro acite", "aceite"),
    ("cabel thhn", "cable"),
    ("bateria 12v", None),      # ya está bien escrito
])
def test_corrige_solo_lo_que_hace_falta(entrada, esperado):
    r = corregir(entrada, CATALOGO)
    if esperado is None:
        assert r["corregida"] is None
    else:
        assert esperado in r["corregida"]


def test_no_inventa_cuando_no_hay_nada_parecido():
    assert corregir("xyzabc qwerty", CATALOGO)["corregida"] is None


def test_no_toca_palabras_cortas():
    """En 2-3 letras cualquier cambio da puntaje alto contra cualquier cosa."""
    assert corregir("kit", CATALOGO)["corregida"] is None


def test_catalogo_vacio_no_rompe():
    assert corregir("filtro", [])["corregida"] is None


def test_reporta_los_cambios_hechos():
    """La vista necesita poder decir 'mostrando resultados para X'."""
    r = corregir("filtro acite", CATALOGO)
    assert r["cambios"] and r["cambios"][0]["de"] == "acite"

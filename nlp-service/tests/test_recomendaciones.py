"""Tests de los dos modelos que alimentan la vista de repuestos:
recomendación de productos relacionados y señal de reabastecimiento.

Ninguno toca el backend real: se sustituyen las funciones del cliente HTTP,
que es lo único que sale de este proceso.
"""
from datetime import date, timedelta

import pytest

from app.demanda import forecast
from app.recommender import similares

CATALOGO = [
    {"id": 1, "codigo": "FR-01", "nombre": "Pastilla de freno delantera",
     "descripcion": "Juego de pastillas cerámicas", "categoria": "Frenos",
     "stock": 4, "precio_venta": 95000},
    {"id": 2, "codigo": "FR-02", "nombre": "Pastilla de freno trasera",
     "descripcion": "Juego de pastillas cerámicas traseras", "categoria": "Frenos",
     "stock": 6, "precio_venta": 90000},
    {"id": 3, "codigo": "FR-03", "nombre": "Disco de freno ventilado",
     "descripcion": "Disco delantero ventilado", "categoria": "Frenos",
     "stock": 2, "precio_venta": 210000},
    {"id": 4, "codigo": "EL-01", "nombre": "Batería 12v 60ah",
     "descripcion": "Batería libre mantenimiento", "categoria": "Eléctrico",
     "stock": 9, "precio_venta": 380000},
]


@pytest.fixture
def catalogo_falso(monkeypatch):
    monkeypatch.setattr(similares, "obtener_repuesto", lambda i: CATALOGO[0])
    monkeypatch.setattr(similares, "buscar_en_catalogo", lambda t, limit=100: CATALOGO)


def test_recomienda_el_producto_mas_parecido_primero(catalogo_falso):
    resultado = similares.recomendar_similares(1)
    nombres = [r["nombre"] for r in resultado["recomendaciones"]]
    assert nombres[0] == "Pastilla de freno trasera"


def test_no_se_recomienda_a_si_mismo(catalogo_falso):
    resultado = similares.recomendar_similares(1)
    assert all(r["id"] != 1 for r in resultado["recomendaciones"])


def test_descarta_lo_que_no_supera_el_umbral(catalogo_falso):
    # La batería no comparte vocabulario con una pastilla de freno.
    resultado = similares.recomendar_similares(1)
    assert all("Batería" not in r["nombre"] for r in resultado["recomendaciones"])


def test_repuesto_inexistente_es_error_de_dominio(monkeypatch):
    monkeypatch.setattr(similares, "obtener_repuesto", lambda i: {})
    with pytest.raises(ValueError):
        similares.recomendar_similares(999)


# ── Predicción de demanda ────────────────────────────────────────────

def _serie(dias_atras_y_unidades):
    hoy = date.today()
    return [
        {"fecha": (hoy - timedelta(days=d)).isoformat(), "unidades": u}
        for d, u in dias_atras_y_unidades
    ]


def test_agrupa_por_semana_y_descarta_lo_viejo():
    hoy = date.today()
    semanas = forecast._unidades_por_semana(_serie([(1, 3), (200, 50)]), hoy)
    assert len(semanas) == forecast.DIAS_HISTORIAL // 7
    assert sum(semanas) == 3          # la venta de hace 200 días queda fuera
    assert semanas[-1] == 3           # la reciente cae en la última semana


def test_promedio_ponderado_pesa_mas_lo_reciente():
    creciente = forecast._promedio_movil_ponderado([0, 0, 10])
    decreciente = forecast._promedio_movil_ponderado([10, 0, 0])
    assert creciente > decreciente


def test_senal_reabastecer_con_stock_bajo(monkeypatch):
    monkeypatch.setattr(forecast, "obtener_demanda", lambda i, dias=90: {
        "repuesto_id": i, "stock": 2, "stock_minimo": 5,
        "serie": _serie([(1, 5), (8, 5), (15, 5)]),
    })
    assert forecast.predecir_demanda(1)["senal"] == "reabastecer"


def test_senal_rotacion_baja_sin_ventas(monkeypatch):
    monkeypatch.setattr(forecast, "obtener_demanda", lambda i, dias=90: {
        "repuesto_id": i, "stock": 40, "stock_minimo": 5, "serie": [],
    })
    resultado = forecast.predecir_demanda(1)
    assert resultado["senal"] == "rotacion_baja"
    # Sin demanda no se puede dividir: la cobertura queda explícitamente nula.
    assert resultado["dias_cobertura"] is None


def test_sin_stock_ni_ventas_no_finge_una_senal(monkeypatch):
    monkeypatch.setattr(forecast, "obtener_demanda", lambda i, dias=90: {
        "repuesto_id": i, "stock": 0, "stock_minimo": 5, "serie": [],
    })
    assert forecast.predecir_demanda(1)["senal"] == "sin_datos"


# ── Predicción en lote (la que alimenta los badges de la tabla) ───────

def test_lote_devuelve_una_senal_por_repuesto(monkeypatch):
    monkeypatch.setattr(forecast, "obtener_demanda_lote", lambda ids, dias=90: {
        "dias": dias,
        "repuestos": [
            # se vende seguido y queda poco stock
            {"repuesto_id": 1, "stock": 2, "stock_minimo": 5,
             "serie": _serie([(1, 5), (8, 5), (15, 5)])},
            # stock alto y ninguna venta
            {"repuesto_id": 2, "stock": 40, "stock_minimo": 5, "serie": []},
        ],
    })
    resultado = forecast.predecir_demanda_lote([1, 2])
    senales = {r["repuesto_id"]: r["senal"] for r in resultado}
    assert senales == {1: "reabastecer", 2: "rotacion_baja"}


def test_lote_vacio_no_llama_al_backend(monkeypatch):
    def explotar(*a, **k):
        raise AssertionError("no debería consultarse el backend sin ids")
    monkeypatch.setattr(forecast, "obtener_demanda_lote", explotar)
    assert forecast.predecir_demanda_lote([]) == []


def test_lote_y_individual_dan_el_mismo_resultado(monkeypatch):
    """Las dos rutas comparten _calcular(): si alguien las hiciera divergir,
    la tabla y el modal mostrarían señales distintas para el mismo producto."""
    datos = {"repuesto_id": 7, "stock": 3, "stock_minimo": 5,
             "serie": _serie([(2, 4), (10, 4)])}
    monkeypatch.setattr(forecast, "obtener_demanda", lambda i, dias=90: datos)
    monkeypatch.setattr(forecast, "obtener_demanda_lote",
                        lambda ids, dias=90: {"repuestos": [datos]})

    individual = forecast.predecir_demanda(7)
    lote = forecast.predecir_demanda_lote([7])[0]
    assert individual == lote

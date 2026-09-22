"""Tests HTTP de los endpoints que alimentan la vista de repuestos.

A diferencia de test_recomendaciones.py —que prueba los modelos— acá se
ejercita la capa FastAPI: rutas, códigos de estado, validación de
parámetros y forma de la respuesta. Es lo más cerca del flujo real que se
puede llegar sin levantar el backend PHP: solo se sustituye el cliente
HTTP hacia el backend, todo lo demás es el microservicio de verdad.
"""
import pytest
from fastapi.testclient import TestClient

from app import config, main
from app.demanda import forecast
from app.recommender import client_backend, similares

client = TestClient(main.app)

REPUESTO = {
    "id": 1, "codigo": "FR-01", "nombre": "Pastilla de freno delantera",
    "descripcion": "Juego de pastillas cerámicas", "categoria": "Frenos",
    "stock": 4, "precio_venta": 95000,
}
CATALOGO = [
    REPUESTO,
    {"id": 2, "codigo": "FR-02", "nombre": "Pastilla de freno trasera",
     "descripcion": "Juego de pastillas cerámicas traseras", "categoria": "Frenos",
     "stock": 6, "precio_venta": 90000},
    {"id": 3, "codigo": "EL-01", "nombre": "Batería 12v 60ah",
     "descripcion": "Batería libre mantenimiento", "categoria": "Eléctrico",
     "stock": 9, "precio_venta": 380000},
]


@pytest.fixture(autouse=True)
def sin_clave_interna(monkeypatch):
    """Los endpoints exigen X-Internal-Key solo si está configurada; acá se
    prueba la lógica, no la autenticación (eso ya lo cubre test_main.py)."""
    monkeypatch.setattr(config, "NLP_INTERNAL_KEY", "")


@pytest.fixture
def backend_falso(monkeypatch):
    monkeypatch.setattr(similares, "obtener_repuesto", lambda i: REPUESTO)
    monkeypatch.setattr(similares, "buscar_en_catalogo", lambda t, limit=100: CATALOGO)


# ── /recomendaciones/{id} ────────────────────────────────────────────

def test_recomendaciones_responde_la_forma_que_espera_el_frontend(backend_falso):
    resp = client.get("/recomendaciones/1")
    assert resp.status_code == 200
    cuerpo = resp.json()
    assert "recomendaciones" in cuerpo
    # El proxy PHP lee exactamente estas claves para armar la tarjeta.
    primera = cuerpo["recomendaciones"][0]
    for campo in ("id", "codigo", "nombre", "categoria", "stock", "precio_venta", "similitud"):
        assert campo in primera


def test_recomendaciones_respeta_el_limite(backend_falso):
    resp = client.get("/recomendaciones/1", params={"limite": 1})
    assert len(resp.json()["recomendaciones"]) <= 1


def test_recomendaciones_de_repuesto_inexistente_da_404(monkeypatch):
    monkeypatch.setattr(similares, "obtener_repuesto", lambda i: {})
    assert client.get("/recomendaciones/999").status_code == 404


def test_recomendaciones_con_backend_caido_da_503(monkeypatch):
    def caido(*a, **k):
        raise client_backend.BackendNoDisponibleError("conexión rechazada")
    monkeypatch.setattr(similares, "obtener_repuesto", caido)
    # 503 y no 500: el microservicio está sano, el catálogo no responde.
    # El proxy PHP lo traduce a "sin sugerencias" y la vista sigue viva.
    assert client.get("/recomendaciones/1").status_code == 503


# ── /prediccion-demanda ──────────────────────────────────────────────

def test_prediccion_individual(monkeypatch):
    monkeypatch.setattr(forecast, "obtener_demanda", lambda i, dias=90: {
        "repuesto_id": i, "stock": 2, "stock_minimo": 5, "serie": [],
    })
    cuerpo = client.get("/prediccion-demanda/1").json()
    assert cuerpo["senal"] in ("reabastecer", "rotacion_baja", "normal", "sin_datos")


def test_prediccion_lote_devuelve_data(monkeypatch):
    monkeypatch.setattr(forecast, "obtener_demanda_lote", lambda ids, dias=90: {
        "repuestos": [{"repuesto_id": i, "stock": 1, "stock_minimo": 5, "serie": []}
                      for i in ids],
    })
    cuerpo = client.get("/prediccion-demanda", params={"ids": "1,2,3"}).json()
    assert len(cuerpo["data"]) == 3


def test_prediccion_lote_ignora_ids_no_numericos(monkeypatch):
    """Un id basura no debe tumbar la tabla entera: se filtra y se sigue."""
    monkeypatch.setattr(forecast, "obtener_demanda_lote", lambda ids, dias=90: {
        "repuestos": [{"repuesto_id": i, "stock": 1, "stock_minimo": 5, "serie": []}
                      for i in ids],
    })
    resp = client.get("/prediccion-demanda", params={"ids": "1,abc,,3"})
    assert resp.status_code == 200
    assert [r["repuesto_id"] for r in resp.json()["data"]] == [1, 3]


def test_prediccion_lote_sin_ids_no_falla():
    resp = client.get("/prediccion-demanda", params={"ids": ""})
    assert resp.status_code == 200
    assert resp.json()["data"] == []


def test_prediccion_lote_topea_la_cantidad(monkeypatch):
    """Tope defensivo: es una ruta sin rate limit que termina en un IN (...)."""
    recibidos = {}

    def espia(ids, dias=90):
        recibidos["n"] = len(ids)
        return {"repuestos": []}

    monkeypatch.setattr(forecast, "obtener_demanda_lote", espia)
    client.get("/prediccion-demanda", params={"ids": ",".join(str(i) for i in range(1, 300))})
    assert recibidos["n"] == 100


def test_prediccion_lote_con_backend_caido_da_503(monkeypatch):
    def caido(*a, **k):
        raise client_backend.BackendNoDisponibleError("timeout")
    monkeypatch.setattr(forecast, "obtener_demanda_lote", caido)
    assert client.get("/prediccion-demanda", params={"ids": "1"}).status_code == 503

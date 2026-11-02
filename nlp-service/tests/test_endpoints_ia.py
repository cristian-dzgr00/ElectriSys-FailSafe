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


# ── /sugerencia-pedido: casos límite ─────────────────────────────────

def _lote_falso(filas):
    """Sustituye la lectura del historial; `filas` es lo que 'existe' en la BD."""
    def _lote(ids, dias=90):
        return {"repuestos": [f for f in filas if f["repuesto_id"] in ids]}
    return _lote


def test_sugerencia_pedido_sin_ids_devuelve_lista_vacia():
    resp = client.post("/sugerencia-pedido", json={"repuesto_ids": []})
    assert resp.status_code == 200
    assert resp.json() == {"data": []}


def test_sugerencia_pedido_con_ids_inexistentes_no_inventa_filas(monkeypatch):
    monkeypatch.setattr(forecast, "obtener_demanda_lote", _lote_falso([]))
    resp = client.post("/sugerencia-pedido", json={"repuesto_ids": [9999, 8888]})
    assert resp.status_code == 200
    assert resp.json()["data"] == []


def test_sugerencia_pedido_sin_historial_usa_el_stock_minimo(monkeypatch):
    """Cero ventas: no hay demanda que dividir, pero si el stock está bajo el
    mínimo igual se sugiere llegar al mínimo (y nada de NaN ni división por 0)."""
    monkeypatch.setattr(forecast, "obtener_demanda_lote", _lote_falso([
        {"repuesto_id": 7, "stock": 1, "stock_minimo": 6, "serie": []},
        {"repuesto_id": 8, "stock": 50, "stock_minimo": 5, "serie": []},
    ]))
    filas = {f["repuesto_id"]: f for f in client.post(
        "/sugerencia-pedido", json={"repuesto_ids": [7, 8]}).json()["data"]}
    assert filas[7]["necesita_reabastecer"] is True
    assert filas[7]["cantidad_sugerida"] == 5          # 6 (mínimo) - 1 (stock)
    assert filas[7]["demanda_semanal_estimada"] == 0
    assert filas[8]["necesita_reabastecer"] is False
    assert filas[8]["cantidad_sugerida"] == 0
    assert filas[8]["senal"] == "rotacion_baja"        # stock parado, sin ventas


def test_sugerencia_pedido_descuenta_lo_que_ya_viene_en_camino(monkeypatch):
    monkeypatch.setattr(forecast, "obtener_demanda_lote", _lote_falso([
        {"repuesto_id": 7, "stock": 1, "stock_minimo": 6, "serie": []},
    ]))
    resp = client.post("/sugerencia-pedido", json={"repuesto_ids": [7], "en_transito": {"7": 10}})
    fila = resp.json()["data"][0]
    assert fila["necesita_reabastecer"] is False
    assert fila["en_transito"] == 10


@pytest.mark.parametrize("cuerpo", [
    {"repuesto_ids": [1], "dias_entrega": 0},
    {"repuesto_ids": [1], "dias_entrega": 91},
    {"repuesto_ids": [1], "dias_cobertura": 6},
    {"repuesto_ids": [1], "dias_cobertura": 181},
    {"repuesto_ids": ["no-es-un-id"]},
])
def test_sugerencia_pedido_rechaza_parametros_absurdos(cuerpo):
    assert client.post("/sugerencia-pedido", json=cuerpo).status_code == 422


def test_sugerencia_pedido_topea_la_cantidad_de_ids(monkeypatch):
    recibidos = {}

    def espia(ids, dias=90):
        recibidos["n"] = len(ids)
        return {"repuestos": []}

    monkeypatch.setattr(forecast, "obtener_demanda_lote", espia)
    client.post("/sugerencia-pedido", json={"repuesto_ids": list(range(1, 500))})
    assert recibidos["n"] == 200


def test_sugerencia_pedido_con_backend_caido_da_503(monkeypatch):
    def caido(*a, **k):
        raise client_backend.BackendNoDisponibleError("timeout")
    monkeypatch.setattr(forecast, "obtener_demanda_lote", caido)
    assert client.post("/sugerencia-pedido", json={"repuesto_ids": [1]}).status_code == 503


# ── /complementos: casos límite ──────────────────────────────────────

CANASTAS = [[1, 2], [1, 2], [1, 2, 3], [4, 5]]


def test_complementos_sin_ids_devuelve_vacio_sin_llamar_al_backend(monkeypatch):
    def no_debe_llamarse(*a, **k):
        raise AssertionError("no hace falta leer ventas si no hay productos en la venta")
    monkeypatch.setattr(main, "obtener_canastas", no_debe_llamarse)
    for ids in ("", " ", "abc", ",,"):
        resp = client.get("/complementos", params={"ids": ids})
        assert resp.status_code == 200
        assert resp.json() == {"data": []}


def test_complementos_devuelve_los_que_se_venden_juntos(monkeypatch):
    monkeypatch.setattr(main, "obtener_canastas", lambda dias=180: CANASTAS)
    cuerpo = client.get("/complementos", params={"ids": "1"}).json()
    assert [d["repuesto_id"] for d in cuerpo["data"]][:1] == [2]
    assert cuerpo["canastas_analizadas"] == len(CANASTAS)


def test_complementos_con_producto_sin_historial_no_inventa_reglas(monkeypatch):
    monkeypatch.setattr(main, "obtener_canastas", lambda dias=180: CANASTAS)
    assert client.get("/complementos", params={"ids": "999"}).json()["data"] == []


def test_complementos_sin_ventas_registradas_no_falla(monkeypatch):
    monkeypatch.setattr(main, "obtener_canastas", lambda dias=180: [])
    resp = client.get("/complementos", params={"ids": "1"})
    assert resp.status_code == 200
    assert resp.json()["data"] == []


def test_complementos_acota_el_limite(monkeypatch):
    monkeypatch.setattr(main, "obtener_canastas", lambda dias=180: CANASTAS)
    assert client.get("/complementos", params={"ids": "1", "limite": 0}).status_code == 200
    assert client.get("/complementos", params={"ids": "1", "limite": 10_000}).status_code == 200


def test_complementos_con_backend_caido_da_503(monkeypatch):
    def caido(*a, **k):
        raise client_backend.BackendNoDisponibleError("timeout")
    monkeypatch.setattr(main, "obtener_canastas", caido)
    assert client.get("/complementos", params={"ids": "1"}).status_code == 503


# ── /corregir-busqueda: casos límite ─────────────────────────────────

def test_corregir_busqueda_vacia_o_muy_corta_no_consulta_el_catalogo(monkeypatch):
    def no_debe_llamarse(*a, **k):
        raise AssertionError("con menos de 3 letras no hay nada que corregir")
    monkeypatch.setattr(main, "buscar_en_catalogo", no_debe_llamarse)
    for q in ("", "   ", "ab"):
        cuerpo = client.get("/corregir-busqueda", params={"q": q}).json()
        assert cuerpo["corregida"] is None
        assert cuerpo["cambios"] == []


def test_corregir_busqueda_corrige_contra_el_catalogo(monkeypatch):
    monkeypatch.setattr(main, "buscar_en_catalogo", lambda t, limit=100: CATALOGO)
    cuerpo = client.get("/corregir-busqueda", params={"q": "pastila de frenno"}).json()
    assert cuerpo["corregida"] == "pastilla de freno"


def test_corregir_busqueda_muy_larga_no_rompe_ni_inventa(monkeypatch):
    monkeypatch.setattr(main, "buscar_en_catalogo", lambda t, limit=100: CATALOGO)
    resp = client.get("/corregir-busqueda", params={"q": "zzzz " * 2000})
    assert resp.status_code == 200
    assert resp.json()["corregida"] is None


def test_corregir_busqueda_con_backend_caido_da_503(monkeypatch):
    def caido(*a, **k):
        raise client_backend.BackendNoDisponibleError("timeout")
    monkeypatch.setattr(main, "buscar_en_catalogo", caido)
    assert client.get("/corregir-busqueda", params={"q": "pastila"}).status_code == 503


# ── /nlp/consultar: límites de entrada ───────────────────────────────

def test_consultar_rechaza_texto_vacio_y_demasiado_largo():
    assert client.post("/nlp/consultar", json={"texto": ""}).status_code == 422
    assert client.post("/nlp/consultar", json={"texto": "a" * 1001}).status_code == 422
    assert client.post("/nlp/consultar", json={}).status_code == 422


def test_consultar_con_contexto_previo_que_no_es_objeto_da_422():
    resp = client.post("/nlp/consultar", json={"texto": "hola", "contexto_previo": "texto"})
    assert resp.status_code == 422

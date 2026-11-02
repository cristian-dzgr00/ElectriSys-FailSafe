"""Respaldo por categoría con aviso honesto de compatibilidad no confirmada."""
import app.pipeline as pipeline
from app.recommender.client_backend import BackendNoDisponibleError


def _prod(i, stock=5, categoria="Filtros", nombre=None):
    return {"id": i, "codigo": f"F-{i}", "nombre": nombre or f"Filtro de aceite {i}",
            "descripcion": "filtro de aceite", "categoria": categoria, "stock": stock,
            "proveedor": "Proveedor", "precio_venta": 30000 + i}


def _entorno(monkeypatch, intencion, compatibles=(), catalogo=(), marcas=("Toyota",), modelos=("Hilux",)):
    monkeypatch.setattr(pipeline, "predecir_intencion", lambda texto: (intencion, 0.9))
    monkeypatch.setattr(pipeline.dictionary, "obtener_marcas", lambda: list(marcas))
    monkeypatch.setattr(pipeline.dictionary, "obtener_modelos", lambda marca=None: list(modelos))
    monkeypatch.setattr(pipeline.dictionary, "obtener_categorias", lambda: ["Filtros"])
    monkeypatch.setattr(pipeline, "buscar_compatibles", lambda **kw: list(compatibles))
    monkeypatch.setattr(pipeline, "buscar_en_catalogo", lambda termino, **kw: list(catalogo))


TEXTO = "filtro de aceite para toyota hilux"


def test_con_compatibilidad_confirmada_todo_queda_marcado_true_y_sin_aviso(monkeypatch):
    _entorno(monkeypatch, "recomendar_sustituto", compatibles=[_prod(1), _prod(2)])
    r = pipeline.procesar_consulta(TEXTO)
    assert r["compatibilidad_confirmada"] is True
    assert all(s["compatibilidad_confirmada"] is True for s in r["sugerencias"])
    assert "no confirmada" not in r["respuesta_texto"].lower()


def test_sin_compatibles_respalda_con_hasta_3_en_stock_marcados_false(monkeypatch):
    catalogo = [_prod(1), _prod(2), _prod(3), _prod(4), _prod(5, stock=0)]
    _entorno(monkeypatch, "recomendar_sustituto", catalogo=catalogo)
    r = pipeline.procesar_consulta(TEXTO)
    assert len(r["sugerencias"]) == 3
    assert all(s["compatibilidad_confirmada"] is False for s in r["sugerencias"])
    assert all(s["stock"] > 0 for s in r["sugerencias"])
    assert r["compatibilidad_confirmada"] is False
    assert "compatibilidad exacta" in r["respuesta_texto"].lower()


def test_buscar_repuesto_con_respaldo_no_afirma_disponibilidad_para_el_vehiculo(monkeypatch):
    _entorno(monkeypatch, "buscar_repuesto", catalogo=[_prod(1), _prod(2)])
    r = pipeline.procesar_consulta(TEXTO)
    texto = r["respuesta_texto"]
    assert not texto.lower().startswith("sí, hay disponible")
    assert "Compatibilidad no confirmada: verifica con el vehículo antes de vender." in texto
    assert all(s["compatibilidad_confirmada"] is False for s in r["sugerencias"])


def test_buscar_repuesto_con_compatibles_conserva_el_mensaje_original(monkeypatch):
    _entorno(monkeypatch, "buscar_repuesto", compatibles=[_prod(1)])
    r = pipeline.procesar_consulta(TEXTO)
    assert r["respuesta_texto"].lower().startswith("sí, hay disponible")
    assert r["compatibilidad_confirmada"] is True


def test_el_respaldo_excluye_lo_que_no_tiene_stock(monkeypatch):
    _entorno(monkeypatch, "buscar_repuesto", catalogo=[_prod(1, stock=0), _prod(2, stock=0)])
    r = pipeline.procesar_consulta(TEXTO)
    assert r["sugerencias"] == []
    assert r["compatibilidad_confirmada"] is None
    assert "no encontré" in r["respuesta_texto"].lower()


def test_vehiculo_desconocido_con_categoria_pregunta_y_ofrece_respaldo_no_confirmado(monkeypatch):
    _entorno(monkeypatch, "recomendar_sustituto", catalogo=[_prod(1), _prod(2)], marcas=(), modelos=())
    r = pipeline.procesar_consulta("no hay filtro de aceite, que recomiendo")
    assert r["esperando_datos"] is True
    assert r["respuesta_texto"].startswith("Para buscar en Filtros, ¿para qué marca y modelo de vehículo?")
    assert "Compatibilidad no confirmada" in r["respuesta_texto"]
    assert len(r["sugerencias"]) == 2
    assert all(s["compatibilidad_confirmada"] is False for s in r["sugerencias"])


def test_vehiculo_desconocido_sin_categoria_solo_pregunta(monkeypatch):
    _entorno(monkeypatch, "buscar_repuesto", catalogo=[_prod(1)], marcas=(), modelos=())
    monkeypatch.setattr(pipeline.dictionary, "obtener_categorias", lambda: [])
    r = pipeline.procesar_consulta("tienen algo")
    assert r["sugerencias"] == []
    assert r["respuesta_texto"] == "¿Para qué marca y modelo de vehículo?"


def test_si_el_catalogo_cae_durante_el_respaldo_solo_se_pregunta(monkeypatch):
    _entorno(monkeypatch, "recomendar_sustituto", marcas=(), modelos=())

    def _cae(termino, **kw):
        raise BackendNoDisponibleError("caido")

    monkeypatch.setattr(pipeline, "buscar_en_catalogo", _cae)
    r = pipeline.procesar_consulta("no hay filtro de aceite, que recomiendo")
    assert r["sugerencias"] == []
    assert r["esperando_datos"] is True
    assert "marca y modelo" in r["respuesta_texto"]


def test_los_resultados_confirmados_no_se_mezclan_con_el_respaldo(monkeypatch):
    # Hay compatibles: el catálogo general ni siquiera se consulta.
    _entorno(monkeypatch, "recomendar_sustituto", compatibles=[_prod(1)])

    def _no_debe_llamarse(termino, **kw):
        raise AssertionError("no debería consultar el catálogo con compatibles confirmados")

    monkeypatch.setattr(pipeline, "buscar_en_catalogo", _no_debe_llamarse)
    r = pipeline.procesar_consulta(TEXTO)
    assert [s["id"] for s in r["sugerencias"]] == [1]

"""Pruebas de orquestación del pipeline.

Mockean predecir_intencion y las llamadas al backend para probar la lógica
de ruteo/armado de respuesta de forma aislada y determinista, sin depender
de la exactitud del clasificador real (eso ya se prueba en test_intent.py)
ni de un backend vivo (eso se prueba en client_backend/en Sprint 5).
"""
import app.pipeline as pipeline
from app.recommender.client_backend import BackendNoDisponibleError


def _sin_diccionarios(monkeypatch, marcas=None, modelos=None, categorias=None):
    monkeypatch.setattr(pipeline.dictionary, "obtener_marcas", lambda: marcas or [])
    monkeypatch.setattr(pipeline.dictionary, "obtener_modelos", lambda marca=None: modelos or [])
    monkeypatch.setattr(pipeline.dictionary, "obtener_categorias", lambda: categorias or [])


def test_saludo_no_llama_al_backend(monkeypatch):
    def _falla(**kw):
        raise AssertionError("no debería llamar al backend para un saludo")

    monkeypatch.setattr(pipeline, "predecir_intencion", lambda texto: ("saludo_despedida", 0.9))
    monkeypatch.setattr(pipeline, "buscar_compatibles", _falla)
    _sin_diccionarios(monkeypatch)

    resultado = pipeline.procesar_consulta("hola buenos dias")
    assert resultado["intencion"] == "saludo_despedida"
    assert resultado["sugerencias"] == []


def test_recomendar_sustituto_caso_completo_del_enunciado(monkeypatch):
    candidatos_fake = [
        {"id": 9, "codigo": "HP-1002", "nombre": "Filtro de aceite K&N", "descripcion": "filtro de aceite",
         "categoria": "Filtros", "proveedor": "K&N Filtros", "stock": 12, "precio_venta": 35000},
        {"id": 10, "codigo": "M1-102", "nombre": "Filtro de aceite Mobil 1", "descripcion": "filtro sintetico",
         "categoria": "Filtros", "proveedor": "Mobil 1", "stock": 8, "precio_venta": 38000},
        {"id": 8, "codigo": "90915-YZZD4", "nombre": "Filtro de aceite original Toyota",
         "descripcion": "filtro original", "categoria": "Filtros", "proveedor": "Toyota Original Parts",
         "stock": 0, "precio_venta": 42000},
    ]
    monkeypatch.setattr(pipeline, "predecir_intencion", lambda texto: ("recomendar_sustituto", 0.9))
    monkeypatch.setattr(pipeline, "buscar_compatibles", lambda **kw: candidatos_fake)
    _sin_diccionarios(monkeypatch, marcas=["Toyota"], modelos=["Hilux"], categorias=["Filtros"])

    texto = "No hay filtro de aceite original de Toyota para Hilux 2.7 gasolina 2024, que recomiendo"
    resultado = pipeline.procesar_consulta(texto)

    codigos_sugeridos = [s["codigo"] for s in resultado["sugerencias"]]
    assert "90915-YZZD4" not in codigos_sugeridos  # sin stock, no se sugiere
    assert "HP-1002" in codigos_sugeridos
    assert "M1-102" in codigos_sugeridos
    assert "HP-1002" in resultado["respuesta_texto"]


def test_recomendar_sustituto_sin_vehiculo_identificado(monkeypatch):
    monkeypatch.setattr(pipeline, "predecir_intencion", lambda texto: ("recomendar_sustituto", 0.9))
    _sin_diccionarios(monkeypatch)  # ningún diccionario reconoce nada

    resultado = pipeline.procesar_consulta("no hay filtro de aceite, que recomiendo")
    assert resultado["sugerencias"] == []
    assert "identificar" in resultado["respuesta_texto"].lower()


def test_recomendar_sustituto_backend_caido_responde_controlado(monkeypatch):
    def _falla(**kw):
        raise BackendNoDisponibleError("caido")

    monkeypatch.setattr(pipeline, "predecir_intencion", lambda texto: ("recomendar_sustituto", 0.9))
    monkeypatch.setattr(pipeline, "buscar_compatibles", _falla)
    _sin_diccionarios(monkeypatch, marcas=["Toyota"], modelos=["Hilux"])

    resultado = pipeline.procesar_consulta("no hay filtro para toyota hilux 2024, que recomiendo")
    assert resultado["sugerencias"] == []
    assert "no pude consultar" in resultado["respuesta_texto"].lower()


def test_recomendar_sustituto_sin_compatibilidad_exacta_usa_fallback_categoria(monkeypatch):
    fallback_fake = [
        {"id": 1, "codigo": "GEN-1", "nombre": "Filtro genérico", "descripcion": "filtro de aceite",
         "categoria": "Filtros", "stock": 4, "precio_venta": 20000},
    ]
    monkeypatch.setattr(pipeline, "predecir_intencion", lambda texto: ("recomendar_sustituto", 0.9))
    monkeypatch.setattr(pipeline, "buscar_compatibles", lambda **kw: [])  # sin compatibilidad exacta
    monkeypatch.setattr(pipeline, "buscar_en_catalogo", lambda termino, **kw: fallback_fake)
    _sin_diccionarios(monkeypatch, marcas=["Toyota"], modelos=["Hilux"], categorias=["Filtros"])

    resultado = pipeline.procesar_consulta("no hay filtro de aceite para toyota hilux, que recomiendo")
    assert len(resultado["sugerencias"]) == 1
    assert "no encontré compatibilidad exacta" in resultado["respuesta_texto"].lower()


def test_buscar_repuesto_caso_disponible(monkeypatch):
    candidatos_fake = [
        {"id": 1, "codigo": "F-1", "nombre": "Filtro X", "descripcion": "filtro", "categoria": "Filtros",
         "stock": 5, "precio_venta": 30000},
    ]
    monkeypatch.setattr(pipeline, "predecir_intencion", lambda texto: ("buscar_repuesto", 0.9))
    monkeypatch.setattr(pipeline, "buscar_compatibles", lambda **kw: candidatos_fake)
    _sin_diccionarios(monkeypatch, marcas=["Toyota"], modelos=["Hilux"])

    resultado = pipeline.procesar_consulta("tienen filtro de aceite para toyota hilux 2024")
    assert "sí, hay disponible" in resultado["respuesta_texto"].lower()


def test_consultar_stock_por_codigo(monkeypatch):
    productos_fake = [
        {"id": 5, "codigo": "90915-YZZD4", "nombre": "Filtro original", "stock": 3, "precio_venta": 42000,
         "descripcion": "", "categoria": "Filtros"},
    ]
    monkeypatch.setattr(pipeline, "predecir_intencion", lambda texto: ("consultar_stock", 0.9))
    monkeypatch.setattr(pipeline, "buscar_en_catalogo", lambda termino, **kw: productos_fake)
    _sin_diccionarios(monkeypatch)

    resultado = pipeline.procesar_consulta("cuantas unidades hay del filtro 90915-YZZD4")
    assert "3" in resultado["respuesta_texto"]
    assert resultado["sugerencias"][0]["codigo"] == "90915-YZZD4"


def test_consultar_precio_sin_termino_identificado(monkeypatch):
    monkeypatch.setattr(pipeline, "predecir_intencion", lambda texto: ("consultar_precio", 0.9))
    _sin_diccionarios(monkeypatch)

    resultado = pipeline.procesar_consulta("cuanto cuesta")
    assert resultado["sugerencias"] == []
    assert "no encontré" in resultado["respuesta_texto"].lower()


def test_consultar_compatibilidad_completo(monkeypatch):
    productos_fake = [
        {"id": 5, "codigo": "F-1", "nombre": "Filtro X", "stock": 3, "precio_venta": 1000,
         "descripcion": "filtro", "categoria": "Filtros"},
    ]
    vehiculos_fake = [{"marca": "Toyota", "modelo": "Hilux", "anio_desde": 2020, "anio_hasta": 2025}]
    monkeypatch.setattr(pipeline, "predecir_intencion", lambda texto: ("consultar_compatibilidad", 0.9))
    monkeypatch.setattr(pipeline, "buscar_en_catalogo", lambda termino, **kw: productos_fake)
    monkeypatch.setattr(pipeline, "obtener_compatibilidad", lambda repuesto_id: vehiculos_fake)
    _sin_diccionarios(monkeypatch, categorias=["Filtros"])

    resultado = pipeline.procesar_consulta("el filtro F-1 es compatible con otros vehiculos")
    assert "Toyota Hilux" in resultado["respuesta_texto"]


def test_fuera_de_dominio_no_llama_al_backend(monkeypatch):
    def _falla(**kw):
        raise AssertionError("no debería llamar al backend")

    monkeypatch.setattr(pipeline, "predecir_intencion", lambda texto: ("fuera_de_dominio", 0.9))
    monkeypatch.setattr(pipeline, "buscar_compatibles", _falla)
    monkeypatch.setattr(pipeline, "buscar_en_catalogo", _falla)
    _sin_diccionarios(monkeypatch)

    resultado = pipeline.procesar_consulta("cual es la capital de francia")
    assert resultado["sugerencias"] == []

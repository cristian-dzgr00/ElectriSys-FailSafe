"""El pipeline ya no exige que se escriba la marca cuando el modelo es único en el catálogo.

Mockean el clasificador y el backend igual que test_clarificacion.py: se prueba la lógica del
pipeline (construcción de la tabla modelo -> marca y su efecto en el diálogo).
"""
import app.pipeline as pipeline

MODELOS_POR_MARCA = {"Toyota": ["Hilux", "Corolla"], "Chevrolet": ["Spark", "Rio"], "Kia": ["Rio", "Sportage"]}


def _producto(i=1):
    return {"id": i, "codigo": f"F-{i}", "nombre": "Filtro de aceite", "descripcion": "filtro de aceite",
            "categoria": "Filtros", "stock": 5, "proveedor": "P", "precio_venta": 30000}


def _entorno(monkeypatch, intencion="buscar_repuesto", compatibles=(), por_marca=None):
    por_marca = MODELOS_POR_MARCA if por_marca is None else por_marca
    todos = sorted({m for v in por_marca.values() for m in v})
    monkeypatch.setattr(pipeline, "predecir_intencion", lambda texto: (intencion, 0.9))
    monkeypatch.setattr(pipeline.dictionary, "obtener_marcas", lambda: list(por_marca))
    monkeypatch.setattr(pipeline.dictionary, "obtener_modelos",
                        lambda marca=None: list(por_marca[marca]) if marca else todos)
    monkeypatch.setattr(pipeline.dictionary, "obtener_categorias", lambda: ["Filtros"])
    monkeypatch.setattr(pipeline, "buscar_en_catalogo", lambda termino, **kw: [])
    llamadas = []
    monkeypatch.setattr(pipeline, "buscar_compatibles", lambda **kw: llamadas.append(kw) or list(compatibles))
    return llamadas


def test_modelo_unico_completa_la_marca_y_busca_sin_preguntar(monkeypatch):
    llamadas = _entorno(monkeypatch, compatibles=[_producto()])
    r = pipeline.procesar_consulta("tienen filtro de aceite para la hilux")
    assert r["entidades"]["marca"] == "Toyota" and r["entidades"]["modelo"] == "Hilux"
    assert r["esperando_datos"] is False
    assert llamadas and llamadas[0]["marca"] == "Toyota" and llamadas[0]["modelo"] == "Hilux"
    assert len(r["sugerencias"]) == 1


def test_modelo_repetido_en_dos_marcas_sigue_preguntando_la_marca(monkeypatch):
    _entorno(monkeypatch)
    r = pipeline.procesar_consulta("filtro para el rio")
    assert r["entidades"]["marca"] is None
    assert r["esperando_datos"] is True
    assert r["faltan_datos"] == ["marca"]
    assert r["respuesta_texto"].startswith("¿De qué marca es el Rio?")


def test_la_marca_escrita_no_se_pisa_con_la_inferida(monkeypatch):
    _entorno(monkeypatch)
    r = pipeline.procesar_consulta("filtro para kia rio")
    assert r["entidades"]["marca"] == "Kia"


def test_sin_marcas_en_el_catalogo_no_se_infiere_nada(monkeypatch):
    _entorno(monkeypatch, por_marca={})
    r = pipeline.procesar_consulta("filtro para hilux")
    assert r["entidades"]["marca"] is None


def test_la_tabla_modelo_a_marca_se_arma_con_las_consultas_del_diccionario(monkeypatch):
    _entorno(monkeypatch)
    assert pipeline._marca_de_modelo() == {
        "Hilux": ["Toyota"], "Corolla": ["Toyota"], "Spark": ["Chevrolet"], "Rio": ["Chevrolet", "Kia"],
        "Sportage": ["Kia"],
    }

"""Pedido de aclaración cuando falta la marca o el modelo del vehículo.

Mockean el clasificador y el backend (igual que test_pipeline.py): lo que se
prueba acá es la lógica de diálogo del pipeline, no la exactitud del NER ni
del clasificador de intención.
"""
import app.pipeline as pipeline


def _entorno(monkeypatch, intencion="buscar_repuesto", confianza=0.9, marcas=("Toyota",),
             modelos=("Hilux",), categorias=("Filtros",), catalogo=None):
    monkeypatch.setattr(pipeline, "predecir_intencion", lambda texto: (intencion, confianza))
    monkeypatch.setattr(pipeline.dictionary, "obtener_marcas", lambda: list(marcas))
    monkeypatch.setattr(pipeline.dictionary, "obtener_modelos", lambda marca=None: list(modelos))
    monkeypatch.setattr(pipeline.dictionary, "obtener_categorias", lambda: list(categorias))
    monkeypatch.setattr(pipeline, "buscar_en_catalogo", lambda termino, **kw: list(catalogo or []))
    monkeypatch.setattr(pipeline, "buscar_compatibles", lambda **kw: [])


def test_sin_marca_ni_modelo_pregunta_corto_y_marca_esperando_datos(monkeypatch):
    _entorno(monkeypatch, categorias=())
    r = pipeline.procesar_consulta("tienen un repuesto")
    assert r["respuesta_texto"] == "¿Para qué marca y modelo de vehículo?"
    assert r["esperando_datos"] is True
    assert r["faltan_datos"] == ["marca", "modelo"]
    assert r["intencion_pendiente"] == "buscar_repuesto"
    assert r["sugerencias"] == []


def test_con_categoria_la_pregunta_nombra_la_categoria(monkeypatch):
    _entorno(monkeypatch)
    r = pipeline.procesar_consulta("necesito un filtro de aceite")
    assert r["respuesta_texto"].startswith("Para buscar en Filtros, ¿para qué marca y modelo de vehículo?")


def test_solo_marca_pregunta_por_el_modelo(monkeypatch):
    _entorno(monkeypatch, modelos=(), categorias=())
    r = pipeline.procesar_consulta("filtro para toyota")
    assert r["respuesta_texto"] == "¿Qué modelo de Toyota?"
    assert r["faltan_datos"] == ["modelo"]
    assert r["esperando_datos"] is True


def test_solo_modelo_pregunta_por_la_marca(monkeypatch):
    _entorno(monkeypatch, marcas=(), categorias=())
    r = pipeline.procesar_consulta("filtro para hilux")
    assert r["respuesta_texto"] == "¿De qué marca es el Hilux?"
    assert r["faltan_datos"] == ["marca"]


def test_respuesta_completa_no_pregunta_nada(monkeypatch):
    _entorno(monkeypatch, categorias=())
    r = pipeline.procesar_consulta("filtro para toyota hilux")
    assert r["esperando_datos"] is False
    assert r["faltan_datos"] == []
    assert r["intencion_pendiente"] is None


def test_segundo_turno_retoma_la_intencion_aunque_el_clasificador_diga_fuera_de_dominio(monkeypatch):
    """"toyota hilux" a secas no menciona ningún repuesto: el clasificador real
    puede verlo como fuera de dominio. La intención pendiente evita perder el hilo."""
    _entorno(monkeypatch, categorias=("Filtros",))
    turno1 = pipeline.procesar_consulta("necesito un filtro de aceite")
    assert turno1["intencion_pendiente"] == "buscar_repuesto"

    candidatos = [{"id": 1, "codigo": "F-1", "nombre": "Filtro X", "descripcion": "filtro",
                   "categoria": "Filtros", "stock": 5, "precio_venta": 30000}]
    monkeypatch.setattr(pipeline, "predecir_intencion", lambda texto: ("fuera_de_dominio", 0.4))
    monkeypatch.setattr(pipeline, "buscar_compatibles", lambda **kw: candidatos)

    contexto = {**turno1["entidades"], "_intencion_pendiente": turno1["intencion_pendiente"]}
    turno2 = pipeline.procesar_consulta("toyota hilux", contexto_previo=contexto)

    assert turno2["intencion"] == "buscar_repuesto"
    assert turno2["esperando_datos"] is False
    assert turno2["entidades"]["categoria"] == "Filtros"
    assert turno2["sugerencias"][0]["codigo"] == "F-1"
    # La clave de control no se filtra a las entidades que ve el frontend.
    assert "_intencion_pendiente" not in turno2["entidades"]


def test_sin_intencion_pendiente_fuera_de_dominio_sigue_siendo_fuera_de_dominio(monkeypatch):
    _entorno(monkeypatch, intencion="fuera_de_dominio", confianza=0.4)
    r = pipeline.procesar_consulta("toyota hilux")
    assert r["intencion"] == "fuera_de_dominio"


def test_un_tema_nuevo_con_buena_confianza_no_se_pisa_con_la_intencion_pendiente(monkeypatch):
    _entorno(monkeypatch, intencion="consultar_precio", confianza=0.95)
    r = pipeline.procesar_consulta(
        "cuanto cuesta el filtro para toyota hilux",
        contexto_previo={"_intencion_pendiente": "buscar_repuesto"},
    )
    assert r["intencion"] == "consultar_precio"


def test_un_contexto_previo_con_intencion_invalida_se_ignora(monkeypatch):
    _entorno(monkeypatch, intencion="fuera_de_dominio", confianza=0.3)
    r = pipeline.procesar_consulta("toyota hilux", contexto_previo={"_intencion_pendiente": "hackeame"})
    assert r["intencion"] == "fuera_de_dominio"

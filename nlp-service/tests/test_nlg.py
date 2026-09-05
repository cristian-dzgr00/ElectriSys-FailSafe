from app.nlg import templates


def test_responder_fijo_saludo():
    assert "ayudarte" in templates.responder_fijo("saludo_despedida").lower()


def test_responder_fijo_desconocido_cae_a_fuera_de_dominio():
    assert templates.responder_fijo("algo_no_registrado") == templates.RESPUESTAS_FIJAS["fuera_de_dominio"]


def test_recomendar_sustituto_sin_candidatos():
    texto = templates.recomendar_sustituto([], {"marca": "Toyota", "modelo": "Hilux"}, True)
    assert "no encontré" in texto.lower()


def test_recomendar_sustituto_con_candidatos():
    candidatos = [{"codigo": "HP-1002", "proveedor": "K&N Filtros", "stock": 12}]
    texto = templates.recomendar_sustituto(candidatos, {"marca": "Toyota", "modelo": "Hilux"}, True)
    assert "HP-1002" in texto
    assert "K&N Filtros" in texto
    assert "12" in texto


def test_recomendar_sustituto_avisa_si_no_es_compatibilidad_exacta():
    candidatos = [{"codigo": "HP-1002", "proveedor": "K&N Filtros", "stock": 12}]
    texto = templates.recomendar_sustituto(candidatos, {"marca": "Toyota", "modelo": "Hilux"}, False)
    assert "no encontré compatibilidad exacta" in texto.lower()


def test_recomendar_sustituto_con_varios_candidatos_los_menciona_todos():
    candidatos = [
        {"codigo": "HP-1002", "proveedor": "K&N Filtros", "stock": 12},
        {"codigo": "M1-102", "proveedor": "Mobil 1", "stock": 8},
    ]
    texto = templates.recomendar_sustituto(candidatos, {"marca": "Toyota", "modelo": "Hilux"}, True)
    assert "HP-1002" in texto
    assert "M1-102" in texto


def test_buscar_repuesto_disponible():
    candidatos = [{"nombre": "Filtro X", "codigo": "F-1", "stock": 5, "precio_venta": 35000}]
    texto = templates.buscar_repuesto(candidatos, {"marca": "Toyota", "modelo": "Hilux"})
    assert "sí, hay disponible" in texto.lower()
    assert "F-1" in texto


def test_buscar_repuesto_sin_stock():
    candidatos = [{"nombre": "Filtro X", "codigo": "F-1", "stock": 0}]
    texto = templates.buscar_repuesto(candidatos, {"marca": "Toyota", "modelo": "Hilux"})
    assert "no tiene stock" in texto.lower()


def test_buscar_repuesto_no_encontrado():
    texto = templates.buscar_repuesto([], {"marca": "Toyota", "modelo": "Hilux"})
    assert "no encontré ese repuesto" in texto.lower()


def test_consultar_stock_encontrado():
    producto = {"nombre": "Filtro X", "codigo": "F-1", "stock": 7}
    assert "7" in templates.consultar_stock(producto, "filtro")


def test_consultar_stock_no_encontrado():
    assert "no encontré" in templates.consultar_stock(None, "repuesto raro").lower()


def test_consultar_precio_encontrado():
    producto = {"nombre": "Filtro X", "codigo": "F-1", "precio_venta": 35000}
    assert "35000" in templates.consultar_precio(producto, "filtro")


def test_consultar_precio_no_encontrado():
    assert "no encontré" in templates.consultar_precio(None, "repuesto raro").lower()


def test_consultar_compatibilidad_con_resultados():
    vehiculos = [{"marca": "Toyota", "modelo": "Hilux", "anio_desde": 2020, "anio_hasta": 2025}]
    texto = templates.consultar_compatibilidad(vehiculos, "Filtro X")
    assert "Toyota Hilux" in texto


def test_consultar_compatibilidad_sin_resultados():
    assert "no encontré" in templates.consultar_compatibilidad([], "Filtro X").lower()

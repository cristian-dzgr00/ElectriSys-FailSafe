from app.ner import dictionary


def test_obtener_marcas_degrada_a_vacio_si_backend_no_disponible():
    dictionary.invalidar_cache()
    resultado = dictionary._obtener_con_cache(
        "marcas_test_falla", lambda: (_ for _ in ()).throw(RuntimeError("backend caído"))
    )
    assert resultado == []


def test_obtener_con_cache_no_llama_dos_veces_si_el_valor_sigue_vigente():
    dictionary.invalidar_cache()
    llamadas = {"n": 0}

    def _cargar():
        llamadas["n"] += 1
        return ["Toyota", "Mazda"]

    primero = dictionary._obtener_con_cache("marcas_test_cache", _cargar)
    segundo = dictionary._obtener_con_cache("marcas_test_cache", _cargar)

    assert primero == ["Toyota", "Mazda"]
    assert segundo == ["Toyota", "Mazda"]
    assert llamadas["n"] == 1


def test_obtener_con_cache_usa_valor_viejo_si_falla_el_refresco():
    dictionary.invalidar_cache()
    clave = "marcas_test_stale"

    dictionary._obtener_con_cache(clave, lambda: ["Toyota"])
    # Forzar que el TTL ya haya expirado
    _, valores = dictionary._cache[clave]
    dictionary._cache[clave] = (0.0, valores)

    def _falla():
        raise RuntimeError("backend caído")

    resultado = dictionary._obtener_con_cache(clave, _falla)
    assert resultado == ["Toyota"]


def test_obtener_marcas_usa_backend_url_configurable(monkeypatch):
    dictionary.invalidar_cache()
    capturado = {}

    def _fake_get_json(path):
        capturado["path"] = path
        return {"data": ["Renault"]}

    monkeypatch.setattr(dictionary, "_get_json", _fake_get_json)
    resultado = dictionary.obtener_marcas()
    assert resultado == ["Renault"]
    assert capturado["path"] == "/api/vehiculos/marcas"

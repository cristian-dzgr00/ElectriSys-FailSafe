import csv
import threading

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.ner import agente_errores, dictionary, extractor
from app.ner.extractor import extraer_entidades

MARCAS = ["Toyota", "Kia"]
MODELOS = ["Hilux", "Rio"]
CATEGORIAS = ["Filtros"]
CATALOGO_MINIMO = {"marca": MARCAS, "modelo": MODELOS, "categoria": CATEGORIAS}


@pytest.fixture
def agente(tmp_path, monkeypatch):
    """Agente con una tabla pequeña en una carpeta temporal.

    Restaura la tabla en memoria del extractor al terminar, para no
    contaminar los demás tests.
    """
    monkeypatch.setattr(agente_errores, "RUTA_TABLA", tmp_path / "posibles_errores.csv")
    monkeypatch.setattr(agente_errores, "RUTA_AVISOS", tmp_path / "posibles_errores_avisos.csv")
    monkeypatch.setattr(extractor, "_tabla_en_memoria", extractor._tabla_en_memoria)
    agente_errores._reiniciar_estado()
    agente_errores.regenerar_tabla(CATALOGO_MINIMO)
    yield agente_errores
    agente_errores._reiniciar_estado()
    extractor._indices_fuzzy.clear()


def _extraer(texto, marcas=None, modelos=None):
    return extraer_entidades(texto, marcas or MARCAS, modelos or MODELOS, CATEGORIAS)


def _filas(ruta):
    with ruta.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_registrar_marca_nueva_la_hace_buscable_de_inmediato(agente):
    marcas = MARCAS + ["Geely"]
    assert _extraer("necesito filtro para un yili 2024", marcas)["marca"] is None

    resumen = agente.registrar_nombre("marca", "Geely")

    assert resumen["agregadas"] > 0 and resumen["ya_registrado"] is False
    assert _extraer("necesito filtro para un yili 2024", marcas)["marca"] == "Geely"
    assert _extraer("bujias para jilli", marcas)["marca"] == "Geely"


def test_registrar_modelo_nuevo_la_hace_buscable_de_inmediato(agente):
    modelos = MODELOS + ["Coolray"]
    assert _extraer("pastillas para culrei", modelos=modelos)["modelo"] is None

    agente.registrar_nombre("modelo", "Coolray", marca="Geely")

    assert _extraer("pastillas para culrei", modelos=modelos)["modelo"] == "Coolray"


def test_registrar_es_idempotente(agente):
    primero = agente.registrar_nombre("marca", "Geely")
    filas_despues_del_primero = _filas(agente.RUTA_TABLA)

    segundo = agente.registrar_nombre("marca", "geely")

    assert primero["agregadas"] > 0
    assert segundo["ya_registrado"] is True and segundo["agregadas"] == 0
    assert _filas(agente.RUTA_TABLA) == filas_despues_del_primero


def test_registrar_un_nombre_existente_no_agrega_nada(agente):
    assert agente.registrar_nombre("modelo", "Hilux")["ya_registrado"] is True


def test_registrar_rechaza_tipo_invalido_y_nombre_vacio(agente):
    with pytest.raises(ValueError):
        agente.registrar_nombre("motor", "Geely")
    with pytest.raises(ValueError):
        agente.registrar_nombre("marca", "   ")


def test_dos_hilos_registrando_a_la_vez(agente):
    errores = []

    def registrar(tipo, nombre):
        try:
            agente.registrar_nombre(tipo, nombre)
        except Exception as e:  # pragma: no cover - solo si falla
            errores.append(e)

    hilos = [threading.Thread(target=registrar, args=a) for a in (("marca", "Geely"), ("modelo", "Coolray"))]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    assert errores == []
    filas = _filas(agente.RUTA_TABLA)
    correctos = {f["correcto"] for f in filas}
    assert {"Geely", "Coolray"} <= correctos
    assert len({f["error"] for f in filas}) == len(filas)
    # Lo que quedó en disco es lo mismo que quedó en memoria.
    en_memoria = extractor.obtener_tabla_errores()
    assert sum(len(v) for v in en_memoria.values()) == len(filas)


def test_escritura_atomica_no_deja_el_archivo_a_medias(agente, monkeypatch):
    antes = agente.RUTA_TABLA.read_bytes()
    replace_original = agente_errores.os.replace

    def falla(*_):
        raise OSError("disco lleno")

    monkeypatch.setattr(agente_errores.os, "replace", falla)
    with pytest.raises(OSError):
        agente.registrar_nombre("marca", "Geely")

    assert agente.RUTA_TABLA.read_bytes() == antes
    assert list(agente.RUTA_TABLA.parent.glob("*.tmp")) == []
    # La memoria se deshizo: al reintentar, se registra de verdad.
    monkeypatch.setattr(agente_errores.os, "replace", replace_original)
    assert agente.registrar_nombre("marca", "Geely")["ya_registrado"] is False


def test_una_colision_se_descarta_y_se_registra_en_avisos(agente):
    # "Hilus" es un paso de "hilux": al volverse nombre oficial, los errores de
    # Hilux que chocan con él salen de la tabla y quedan en los avisos.
    assert "hilus" in extractor.obtener_tabla_errores()["modelo"]

    agente.registrar_nombre("modelo", "Hilus")

    tabla = extractor.obtener_tabla_errores()
    assert tabla["modelo"].get("hilus") is None
    motivos = {a["motivo"] for a in _filas(agente.RUTA_AVISOS) if a["correcto"] == "Hilux"}
    assert any("Hilus" in m for m in motivos)


def test_sincronizar_catalogo_registra_solo_lo_que_falta(agente):
    catalogo = {"marca": MARCAS + ["Geely"], "modelo": MODELOS, "categoria": CATEGORIAS}

    primero = agente.sincronizar_catalogo(catalogo)
    segundo = agente.sincronizar_catalogo(catalogo)

    assert primero["registrados"] == ["marca:Geely"]
    assert segundo["registrados"] == []


def test_dictionary_avisa_al_agente_al_refrescar_la_cache(monkeypatch):
    avisos = []
    listo = threading.Event()

    def falso_sincronizar(catalogo):
        avisos.append(catalogo)
        listo.set()

    monkeypatch.setattr(agente_errores, "sincronizar_catalogo", falso_sincronizar)
    dictionary.invalidar_cache()
    dictionary._obtener_con_cache("marcas", lambda: ["Toyota", "Geely"])

    assert listo.wait(timeout=5)
    assert avisos == [{"marca": ["Toyota", "Geely"]}]
    dictionary.invalidar_cache()


# ---------------------------------------------------------------- endpoint


@pytest.fixture
def cliente(agente, monkeypatch):
    monkeypatch.setattr(config, "NLP_INTERNAL_KEY", "clave-de-prueba")
    return TestClient(app)


def test_endpoint_exige_la_clave_interna(cliente):
    r = cliente.post("/nlp/errores/registrar", json={"tipo": "marca", "nombre": "Geely"})
    assert r.status_code == 401


def test_endpoint_rechaza_tipos_invalidos(cliente):
    headers = {"X-Internal-Key": "clave-de-prueba"}
    for tipo in ("categoria", "motor", ""):
        r = cliente.post("/nlp/errores/registrar", json={"tipo": tipo, "nombre": "Geely"}, headers=headers)
        assert r.status_code == 422, tipo


def test_endpoint_registra_y_responde_el_resumen(cliente):
    headers = {"X-Internal-Key": "clave-de-prueba"}
    r = cliente.post(
        "/nlp/errores/registrar",
        json={"tipo": "modelo", "nombre": "Coolray", "marca": "Geely"},
        headers=headers,
    )
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["nombre"] == "Coolray" and cuerpo["agregadas"] > 0
    assert {"descartadas", "ms"} <= cuerpo.keys()
    assert _extraer("pastillas para culrei", modelos=MODELOS + ["Coolray"])["modelo"] == "Coolray"


def test_registrar_modelo_con_marca_agrega_errores_con_contexto(agente):
    modelos = MODELOS + ["Kx3"]
    agente.registrar_nombre("modelo", "Kx3", marca="Kia")
    assert _extraer("filtro para kia kx4", modelos=modelos)["modelo"] == "Kx3"
    # El modelo corto solo no se reconoce: sin "kia" al lado, "kx4" es ruido.
    assert _extraer("filtro para kx4", modelos=modelos)["modelo"] is None
    # Y la marca corta mal escrita junto al modelo nuevo también.
    assert _extraer("filtro para kua kx3", modelos=modelos)["marca"] == "Kia"

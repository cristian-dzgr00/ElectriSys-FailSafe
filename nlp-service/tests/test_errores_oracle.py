"""Tabla de posibles errores en Oracle: lectura con respaldo al CSV y MERGE del agente.

Los tests unitarios usan un repositorio falso (no necesitan Oracle). Los de
integración corren contra una base real solo si se definen las variables
NLP_TEST_DB_HOST, NLP_TEST_DB_PORT, NLP_TEST_DB_USER y NLP_TEST_DB_PASS
(esquema con oracle/13 y 14 ya cargados); si no, se saltan.
"""
import os

import pytest

from app.ner import agente_errores, extractor, repositorio_oracle
from app.ner.extractor import extraer_entidades

MARCAS = ["Toyota", "Chevrolet", "Kia"]
MODELOS = ["Hilux", "Corolla", "Rio", "Spark"]
CATEGORIAS = ["Filtros"]


def _extraer(texto, tabla=None):
    return extraer_entidades(texto, MARCAS, MODELOS, CATEGORIAS, tabla_errores=tabla)


@pytest.fixture
def tabla_limpia(monkeypatch):
    """La tabla en memoria se vuelve a cargar en cada test y se restaura al final."""
    monkeypatch.setattr(extractor, "_tabla_en_memoria", None)
    monkeypatch.setattr(extractor, "_origen_tabla", None)
    yield
    extractor._indices_fuzzy.clear()


# ---------------------------------------------------------------- lectura


def test_sin_oracle_configurado_se_usa_el_csv(tabla_limpia, monkeypatch):
    monkeypatch.delenv("DB_HOST", raising=False)
    extractor.obtener_tabla_errores()
    assert extractor.origen_tabla_errores() == "csv"


def test_lee_la_tabla_desde_oracle(tabla_limpia, monkeypatch):
    monkeypatch.setattr(repositorio_oracle, "configurado", lambda: True)
    monkeypatch.setattr(repositorio_oracle, "cargar", lambda: {"modelo": {"jilus": "Hilux"}})

    assert _extraer("necesito filtro para jilus 2020")["modelo"] == "Hilux"
    assert extractor.origen_tabla_errores() == "oracle"


def test_si_oracle_no_responde_se_usa_el_csv(tabla_limpia, monkeypatch):
    def falla():
        raise ConnectionError("ORA-12541: no hay listener")

    monkeypatch.setattr(repositorio_oracle, "configurado", lambda: True)
    monkeypatch.setattr(repositorio_oracle, "cargar", falla)

    ent = _extraer("toyta jilus 2020")
    assert (ent["marca"], ent["modelo"]) == ("Toyota", "Hilux")
    assert extractor.origen_tabla_errores() == "csv"


def test_si_la_tabla_de_oracle_esta_vacia_se_usa_el_csv(tabla_limpia, monkeypatch):
    monkeypatch.setattr(repositorio_oracle, "configurado", lambda: True)
    monkeypatch.setattr(repositorio_oracle, "cargar", lambda: {})
    extractor.obtener_tabla_errores()
    assert extractor.origen_tabla_errores() == "csv"


def test_toyta_jilus_2020_sigue_funcionando():
    ent = _extraer("toyta jilus 2020")
    assert (ent["marca"], ent["modelo"], ent["anio"]) == ("Toyota", "Hilux", 2020)


# ---------------------------------------------------------------- escritura del agente


class RepositorioFalso:
    def __init__(self, falla=False):
        self.falla = falla
        self.guardadas: list[dict] = []
        self.borradas: list[tuple[str, str]] = []

    def guardar(self, filas, borrar=None):
        if self.falla:
            raise ConnectionError("ORA-03113: fin de archivo en el canal de comunicación")
        self.guardadas += filas
        self.borradas += borrar or []

    def contar(self):
        return len({(f["tipo"], f["error"]) for f in self.guardadas})


@pytest.fixture
def agente_con_oracle_falso(tmp_path, monkeypatch):
    monkeypatch.setattr(agente_errores, "RUTA_TABLA", tmp_path / "posibles_errores.csv")
    monkeypatch.setattr(agente_errores, "RUTA_AVISOS", tmp_path / "posibles_errores_avisos.csv")
    monkeypatch.setattr(extractor, "_tabla_en_memoria", extractor._tabla_en_memoria)
    agente_errores._reiniciar_estado()
    agente_errores.regenerar_tabla({"marca": ["Toyota", "Kia"], "modelo": ["Hilux"], "categoria": []})

    repo = RepositorioFalso()
    monkeypatch.setattr(repositorio_oracle, "configurado", lambda: True)
    monkeypatch.setattr(repositorio_oracle, "guardar", repo.guardar)
    monkeypatch.setattr(repositorio_oracle, "contar", repo.contar)
    yield repo
    agente_errores._reiniciar_estado()
    extractor._indices_fuzzy.clear()


def test_registrar_hace_merge_en_oracle_de_las_filas_nuevas(agente_con_oracle_falso):
    repo = agente_con_oracle_falso
    resumen = agente_errores.registrar_nombre("marca", "Geely")

    assert resumen["agregadas"] > 0
    assert len(repo.guardadas) == resumen["agregadas"]
    assert {f["correcto"] for f in repo.guardadas} == {"Geely"}


def test_registrar_dos_veces_no_vuelve_a_escribir_en_oracle(agente_con_oracle_falso):
    repo = agente_con_oracle_falso
    agente_errores.registrar_nombre("marca", "Geely")
    escritas = len(repo.guardadas)

    agente_errores.registrar_nombre("marca", "Geely")

    assert len(repo.guardadas) == escritas


def test_nombre_oficial_nuevo_borra_en_oracle_los_errores_que_invalida(agente_con_oracle_falso):
    repo = agente_con_oracle_falso
    agente_errores.registrar_nombre("modelo", "Hilus")
    assert ("modelo", "hilus") in repo.borradas


def test_si_oracle_falla_el_registro_sigue_y_queda_pendiente(agente_con_oracle_falso, monkeypatch):
    repo = agente_con_oracle_falso
    repo.falla = True

    resumen = agente_errores.registrar_nombre("marca", "Geely")

    # El registro no falló: el nombre ya es buscable desde la memoria y el CSV.
    assert resumen["agregadas"] > 0
    assert _extraer("filtro para yili", None)["marca"] is None  # Geely no está en MARCAS
    assert extraer_entidades("filtro para yili", MARCAS + ["Geely"], MODELOS, CATEGORIAS)["marca"] == "Geely"
    assert agente_errores._oracle_pendiente is True

    # Cuando Oracle vuelve, la sincronización reconcilia todo lo pendiente.
    repo.falla = False
    r = agente_errores.reconciliar_oracle()
    assert r["oracle"] == "reconciliado"
    assert "Geely" in {f["correcto"] for f in repo.guardadas}
    assert agente_errores._oracle_pendiente is False


# ---------------------------------------------------------------- integración (Oracle real)

_CONFIG_PRUEBA = {
    "DB_HOST": os.getenv("NLP_TEST_DB_HOST"),
    "DB_PORT": os.getenv("NLP_TEST_DB_PORT", "1521"),
    "DB_SERVICE_NAME": os.getenv("NLP_TEST_DB_SERVICE", "FREEPDB1"),
    "DB_USER": os.getenv("NLP_TEST_DB_USER"),
    "DB_PASS": os.getenv("NLP_TEST_DB_PASS"),
}
requiere_oracle = pytest.mark.skipif(
    not (_CONFIG_PRUEBA["DB_HOST"] and _CONFIG_PRUEBA["DB_USER"]),
    reason="sin NLP_TEST_DB_*: no hay Oracle de prueba",
)


@pytest.fixture
def oracle_real(monkeypatch):
    for clave, valor in _CONFIG_PRUEBA.items():
        monkeypatch.setenv(clave, valor or "")


@requiere_oracle
def test_integracion_buscar_por_tipo_y_error(oracle_real):
    assert repositorio_oracle.buscar("modelo", "jilus") == "Hilux"
    assert repositorio_oracle.buscar("marca", "jilus") is None  # un error de modelo no es de marca


@requiere_oracle
def test_integracion_toyta_jilus_2020_con_la_tabla_de_oracle(oracle_real, tabla_limpia):
    ent = _extraer("toyta jilus 2020")
    assert (ent["marca"], ent["modelo"]) == ("Toyota", "Hilux")
    assert extractor.origen_tabla_errores() == "oracle"


@requiere_oracle
def test_integracion_merge_no_duplica(oracle_real):
    fila = {"tipo": "marca", "error": "zzprueba", "correcto": "Toyota", "nivel": 1,
            "origen": "manual", "nota": "test de integración"}
    try:
        repositorio_oracle.guardar([fila])
        antes = repositorio_oracle.contar()
        repositorio_oracle.guardar([fila])
        assert repositorio_oracle.contar() == antes
        assert repositorio_oracle.buscar("marca", "zzprueba") == "Toyota"
    finally:
        repositorio_oracle.guardar([], borrar=[("marca", "zzprueba")])

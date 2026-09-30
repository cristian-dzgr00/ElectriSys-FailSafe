import csv
import time

import numpy as np
import pandas as pd
import pytest
from rapidfuzz import process
from rapidfuzz.distance import DamerauLevenshtein

from app.ner import agente_errores, extractor
from app.ner.extractor import cargar_tabla_errores, extraer_entidades
from app.ner.generador_errores import (
    COLUMNAS,
    COLUMNAS_AVISOS,
    ediciones_una_letra,
    formas_de,
    generar_errores,
)
from app.preprocessing import normalizar

MARCAS = ["Toyota", "Chevrolet", "Mazda", "Nissan", "Hyundai", "Kia", "Renault", "Ford", "Suzuki"]
MODELOS = [
    "Hilux", "Corolla", "Fortuner", "Spark", "Spark GT", "Aveo", "3", "CX-5",
    "Sentra", "Frontier", "Tucson", "Accent", "Rio", "Sportage", "Logan",
    "Duster", "Escape", "Fiesta", "Swift",
]
CATEGORIAS = [
    "Filtros", "Frenos", "Baterías", "Suspensión", "Motor", "Transmisión",
    "Encendido", "Correas y Bandas",
]

RUTA_TABLA = extractor.TABLA_ERRORES_PATH
RUTA_AVISOS = RUTA_TABLA.with_name("posibles_errores_avisos.csv")

# Un error por nombre del catálogo ("3" no tiene: un número suelto no se
# puede distinguir de una cantidad o un año).
ERRORES_MARCA = {
    "Toyota": "toytoa", "Chevrolet": "chebrolet", "Mazda": "masda", "Nissan": "nisan",
    "Hyundai": "yundai", "Kia": "kya", "Renault": "reno", "Ford": "frod", "Suzuki": "susuki",
}
ERRORES_MODELO = {
    "Hilux": "jilus", "Corolla": "corola", "Fortuner": "fortunr", "Spark": "sprak",
    "Spark GT": "sprak gt", "Aveo": "abeo", "CX-5": "cx5", "Sentra": "sentrq",
    "Frontier": "fronteir", "Tucson": "tucsn", "Accent": "acsent", "Rio": "ryo",
    "Sportage": "sportaje", "Logan": "logna", "Duster": "dusrer", "Escape": "escpae",
    "Fiesta": "fiezta", "Swift": "suift",
}
ERRORES_CATEGORIA = {
    "Filtros": "filtors", "Frenos": "frenoz", "Baterías": "baterais", "Suspensión": "suspencion",
    "Motor": "motro", "Transmisión": "trasmision", "Encendido": "ensendido",
    "Correas y Bandas": "coreas y bandas",
}


def _extraer(texto, **kwargs):
    return extraer_entidades(texto, MARCAS, MODELOS, CATEGORIAS, **kwargs)


def _leer(ruta):
    with ruta.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _frases_reales():
    base = RUTA_TABLA.parents[2]
    return list(pd.read_csv(base / "data" / "intents_dataset.csv").texto) + list(
        pd.read_csv(base / "eval" / "holdout_intent.csv").texto
    )


# ---------------------------------------------------------------- búsqueda


def test_jilus_se_reconoce_como_hilux():
    assert _extraer("necesito filtro para jilus 2020")["modelo"] == "Hilux"


def test_jilus_no_se_reconocia_sin_tabla():
    assert _extraer("necesito filtro para jilus 2020", tabla_errores={})["modelo"] is None


@pytest.mark.parametrize("correcto,error", ERRORES_MARCA.items())
def test_error_de_marca_se_reconoce(correcto, error):
    assert _extraer(f"necesito un repuesto para {error}")["marca"] == correcto


@pytest.mark.parametrize("correcto,error", ERRORES_MODELO.items())
def test_error_de_modelo_se_reconoce(correcto, error):
    assert _extraer(f"necesito un repuesto para {error}")["modelo"] == correcto


@pytest.mark.parametrize("correcto,error", ERRORES_CATEGORIA.items())
def test_error_de_categoria_se_reconoce(correcto, error):
    assert _extraer(f"necesito un repuesto de {error}")["categoria"] == correcto


def test_error_que_no_esta_en_la_tabla_pero_se_parece_a_una_clave():
    tabla = {"modelo": {"jilusito": "Hilux"}}
    assert "jilusitoo" not in tabla["modelo"]
    assert _extraer("filtro para jilusitoo", tabla_errores=tabla)["modelo"] == "Hilux"


def test_error_de_dos_letras_fuera_de_la_tabla_lo_cubre_el_respaldo():
    tabla = cargar_tabla_errores()
    assert "sporrtajee" not in tabla["modelo"]
    assert _extraer("necesito filtro para sporrtajee")["modelo"] == "Sportage"


def test_grupo_de_mas_palabras_gana_sprak_gt_sobre_sprak():
    assert _extraer("pastillas para un sprak gt 2019")["modelo"] == "Spark GT"


@pytest.mark.parametrize("frase", [
    "hola buenas tardes",
    "cuanto cuesta el envio a la ciudad",
    "filtro de aceite para el centro de la ciudad",
    "necesito algo que no tenga nada que ver",
])
def test_frase_sin_entidades_devuelve_none(frase):
    ent = _extraer(frase)
    assert (ent["marca"], ent["modelo"]) == (None, None)


def test_frases_reales_sin_falsos_positivos_nuevos():
    """En el dataset y el holdout la tabla no cambia ningún resultado: no
    agrega detecciones que la lógica de siempre no hacía."""
    for frase in _frases_reales():
        con_tabla, sin_tabla = _extraer(frase), _extraer(frase, tabla_errores={})
        for campo in ("marca", "modelo", "categoria"):
            assert con_tabla[campo] == sin_tabla[campo], (frase, campo)


def test_frases_reales_sin_ninguna_entidad_devuelven_none_en_los_tres():
    revisadas = 0
    for frase in _frases_reales():
        sin_tabla = _extraer(frase, tabla_errores={})
        if (sin_tabla["marca"], sin_tabla["modelo"], sin_tabla["categoria"]) == (None, None, None):
            ent = _extraer(frase)
            assert (ent["marca"], ent["modelo"], ent["categoria"]) == (None, None, None), frase
            revisadas += 1
    assert revisadas > 0


def test_con_tabla_vacia_el_resultado_es_igual_que_hoy():
    for frase in ["necesito filtro para jilus 2020", "pastillas para chebrolet sprak", "toyta corolla 2017"]:
        vacia = _extraer(frase, tabla_errores={})
        assert vacia["marca"] == extractor._mejor_match(normalizar(frase), MARCAS)
        assert vacia["modelo"] == extractor._mejor_match(normalizar(frase), MODELOS)


def test_tabla_inexistente_devuelve_vacio_sin_error(tmp_path):
    assert cargar_tabla_errores(tmp_path / "no_existe.csv") == {}
    vacio = tmp_path / "vacio.csv"
    vacio.write_text("", encoding="utf-8")
    assert cargar_tabla_errores(vacio) == {}


def test_la_tabla_no_inventa_modelos_fuera_del_catalogo():
    sin_hilux = [m for m in MODELOS if m != "Hilux"]
    ent = extraer_entidades("necesito filtro para jilus 2020", MARCAS, sin_hilux, CATEGORIAS)
    assert ent["modelo"] is None


def test_un_error_de_modelo_no_se_activa_como_marca():
    assert _extraer("filtro para jilus")["marca"] is None


def test_busqueda_con_tabla_completa_tarda_menos_de_20_ms():
    frases = _frases_reales()[:100] + ["necesito filtro para jilus 2020"] * 20
    _extraer(frases[0])  # carga la tabla y arma el índice
    inicio = time.perf_counter()
    for frase in frases:
        _extraer(frase)
    promedio_ms = (time.perf_counter() - inicio) * 1000 / len(frases)
    assert promedio_ms < 20


# ---------------------------------------------------------------- generador


def test_generador_es_determinista():
    assert generar_errores("Chevrolet", "marca") == generar_errores("Chevrolet", "marca")


def test_nivel_1_enumera_todas_las_ediciones_de_una_letra():
    # "hilux" (5 letras distintas): 5 borrados + 4 intercambios + 5*35 cambios
    # + 6*36 inserciones, menos 5 inserciones que repiten la misma cadena.
    assert len(ediciones_una_letra("hilux")) == 5 + 4 + 175 + 216 - 5
    filas = generar_errores("Hilux", "modelo")
    nivel_1 = [f for f in filas if f["nivel"] == 1]
    assert len(nivel_1) == 395 + 2  # + "hi lux" y "hil ux"


def test_generador_produce_los_tres_niveles_con_ejemplos_esperados():
    por_error = {f["error"]: f["nivel"] for f in generar_errores("Hilux", "modelo")}
    assert por_error["hlux"] == 1
    assert por_error["jilus"] == 2
    assert por_error["hlixu"] == 3
    assert {f["nivel"] for f in generar_errores("Hilux", "modelo")} == {1, 2, 3}


def test_generador_transliteracion_y_apodos():
    marca = {f["error"] for f in generar_errores("Geely", "marca")}
    assert {"yili", "jili", "jilli"} <= marca
    modelo = {f["error"] for f in generar_errores("Coolray", "modelo")}
    assert {"culrei", "coolrei"} <= modelo
    assert "chevy" in {f["error"] for f in generar_errores("Chevrolet", "marca")}


def test_generador_respeta_minimos_de_longitud():
    assert generar_errores("3", "modelo") == []
    assert {f["nivel"] for f in generar_errores("Kia", "marca")} == {1}
    assert {f["nota"] for f in generar_errores("Kia", "marca")} == {"letra repetida"}
    assert 3 not in {f["nivel"] for f in generar_errores("Ford", "marca")}
    assert "cx5" in {f["error"] for f in generar_errores("CX-5", "modelo")}


def test_generador_devuelve_el_nombre_original_del_catalogo():
    assert {f["correcto"] for f in generar_errores("Baterías", "categoria")} == {"Baterías"}


# ---------------------------------------------------------------- validación del CSV


def test_csv_tiene_las_columnas_correctas_y_sin_bom():
    assert not RUTA_TABLA.read_bytes().startswith(b"\xef\xbb\xbf")
    with RUTA_TABLA.open(encoding="utf-8", newline="") as f:
        assert next(csv.reader(f)) == COLUMNAS
    with RUTA_AVISOS.open(encoding="utf-8", newline="") as f:
        assert next(csv.reader(f)) == COLUMNAS_AVISOS


def test_csv_sin_duplicados_ni_errores_iguales_al_correcto():
    filas = _leer(RUTA_TABLA)
    errores = [f["error"] for f in filas]
    assert len(errores) == len(set(errores))
    for f in filas:
        assert f["error"] != normalizar(f["correcto"])
        assert f["error"] == normalizar(f["error"])  # ya normalizado
        assert f["nivel"] in {"1", "2", "3", "4"}
        assert f["origen"] in {"manual", "auto"}


def test_todo_correcto_pertenece_al_catalogo():
    catalogo = {(t, n) for t, nombres in agente_errores.CATALOGO_SEMILLA.items() for n in nombres}
    for f in _leer(RUTA_TABLA):
        assert (f["tipo"], f["correcto"]) in catalogo, f


def test_csv_sin_colisiones_con_otros_nombres_del_catalogo():
    oficiales = [n for nombres in agente_errores.CATALOGO_SEMILLA.values() for n in nombres]
    formas = [(forma, n) for n in oficiales for forma in sorted(formas_de(n))]
    filas = _leer(RUTA_TABLA)
    distancias = process.cdist([f["error"] for f in filas], [forma for forma, _ in formas],
                               scorer=DamerauLevenshtein.distance, score_cutoff=1, workers=-1)
    for i, j in zip(*np.nonzero(distancias <= 1)):
        assert normalizar(formas[j][1]) == normalizar(filas[i]["correcto"]), (filas[i], formas[j][1])


def test_palabras_comunes_no_son_errores():
    errores = {f["error"] for f in _leer(RUTA_TABLA)}
    assert not {"centra", "rotor", "aves", "buster", "cuesta", "motos"} & errores


# ---------------------------------------------------------------- contexto y ambigüedad


@pytest.mark.parametrize("frase,campo,esperado", [
    ("bujias para kiu rio 2017", "marca", "Kia"),
    ("bujias para kia roi 2017", "modelo", "Rio"),
    ("amortiguador para fprdd escape", "marca", "Ford"),
    ("embrague de chevrolet aov 2016", "modelo", "Aveo"),
    ("radiador para mazda x 5 2019", "modelo", "CX-5"),
])
def test_nombre_corto_mal_escrito_se_reconoce_junto_a_su_pareja(frase, campo, esperado):
    assert _extraer(frase)[campo] == esperado


def test_nombre_corto_mal_escrito_solo_no_se_reconoce():
    """Sin la pareja al lado, "kiu" o "roi" no bastan: serían falsos positivos."""
    ent = _extraer("bujias para kiu 2017")
    assert ent["marca"] is None
    assert _extraer("el roi del negocio")["modelo"] is None


def test_error_ambiguo_entre_dos_modelos_no_adivina():
    # "frotuer" está igual de cerca de Fortuner que de Frontier.
    assert _extraer("bomba de agua para un nissan frotuer 2018")["modelo"] is None

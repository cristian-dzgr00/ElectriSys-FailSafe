"""Propiedades estables del dataset de intenciones y de la tabla de errores tras la ampliación.

No lee los conjuntos congelados (eval/holdout_*_v2.*): el solapamiento con ellos lo verifica el
programa eval/verificar_solapamiento.py, que aquí solo se prueba con archivos temporales.
"""
import csv
import re
from collections import Counter
from pathlib import Path

import numpy as np
import pytest
from rapidfuzz import process
from rapidfuzz.distance import DamerauLevenshtein

from app.ner import agente_errores
from app.ner.generador_errores import COLUMNAS, COLUMNAS_AVISOS, formas_de
from app.preprocessing import normalizar

RAIZ = Path(__file__).resolve().parent.parent
DATASET = RAIZ / "data" / "intents_dataset.csv"
TABLA = RAIZ / "data" / "errores" / "posibles_errores.csv"
AVISOS = RAIZ / "data" / "errores" / "posibles_errores_avisos.csv"
MANUALES = RAIZ / "data" / "posibles_errores_manuales.csv"
DEMO = RAIZ / "eval" / "datos_demo"

INTENCIONES = {
    "buscar_repuesto", "recomendar_sustituto", "consultar_stock", "consultar_precio",
    "consultar_compatibilidad", "saludo_despedida", "fuera_de_dominio",
}
# El archivo original tenía 374 filas; la ampliación solo agrega al final (nunca reordena ni edita).
FILAS_ORIGINALES = 374
ORIGINAL_POR_INTENCION = {
    "recomendar_sustituto": 56, "buscar_repuesto": 56, "consultar_stock": 56, "consultar_precio": 56,
    "consultar_compatibilidad": 50, "saludo_despedida": 50, "fuera_de_dominio": 50,
}
MINIMO_NUEVAS_POR_INTENCION = 250
MINIMO_VARIANTES_POR_NOMBRE = 15
MAX_SEGUIMIENTOS = 0.03
# Filas de la tabla original que ya estaban a un paso de "Sail" (modelo nuevo en la tabla). Se
# conservan a propósito: la tabla original no se modifica, solo se amplía.
EXCEPCIONES_PREEXISTENTES_CERCA_DE_NOMBRE_NUEVO = {"sarl", "saif", "sait"}


def _leer(ruta: Path) -> list[dict]:
    with ruta.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _vocabulario() -> dict[str, list[str]]:
    def nombres(archivo):
        with (DEMO / archivo).open(encoding="utf-8-sig", newline="") as f:
            return [r["NOMBRE"] for r in csv.DictReader(f)]

    return {"marca": nombres("marcas.csv"), "modelo": nombres("modelos.csv"), "categoria": nombres("categorias.csv")}


def _nuevas() -> list[dict]:
    return _leer(DATASET)[FILAS_ORIGINALES:]


# ------------------------------------------------------------------ dataset de intenciones


def test_las_filas_originales_siguen_al_inicio_y_sin_cambios():
    filas = _leer(DATASET)
    original = filas[:FILAS_ORIGINALES]
    assert Counter(f["intencion"] for f in original) == ORIGINAL_POR_INTENCION
    assert original[0]["texto"].startswith("No hay filtro de aceite original de Toyota para una Hilux 2.7")
    assert original[-1]["texto"] == "¿y cuántas unidades del otro código?"
    assert original[-1]["intencion"] == "consultar_stock"


def test_minimo_de_frases_nuevas_por_intencion():
    conteo = Counter(f["intencion"] for f in _nuevas())
    assert set(conteo) == INTENCIONES
    pocas = {i: n for i, n in conteo.items() if n < MINIMO_NUEVAS_POR_INTENCION}
    assert not pocas, pocas


def test_total_por_intencion_supera_el_original_mas_el_minimo():
    total = Counter(f["intencion"] for f in _leer(DATASET))
    for intencion, antes in ORIGINAL_POR_INTENCION.items():
        assert total[intencion] >= antes + MINIMO_NUEVAS_POR_INTENCION, intencion
    assert sum(total.values()) >= 2100


def test_frases_nuevas_sin_duplicados_crudos_ni_normalizados():
    filas = _leer(DATASET)
    originales = {normalizar(f["texto"]) for f in filas[:FILAS_ORIGINALES]}
    nuevas = filas[FILAS_ORIGINALES:]
    crudos = [f["texto"] for f in nuevas]
    assert len(crudos) == len(set(crudos))
    normalizadas = [normalizar(t) for t in crudos]
    assert len(normalizadas) == len(set(normalizadas)), "hay frases nuevas iguales tras normalizar"
    assert not set(normalizadas) & originales, "una frase nueva repite una original tras normalizar"


def test_sin_textos_vacios_ni_etiquetas_invalidas_en_las_nuevas():
    for f in _nuevas():
        assert f["texto"].strip() and normalizar(f["texto"]), f
        assert f["intencion"] in INTENCIONES, f
        assert f["texto"] == f["texto"].strip()


def test_dataset_utf8_sin_bom_lf_y_texto_entrecomillado():
    crudo = DATASET.read_bytes()
    assert not crudo.startswith(b"\xef\xbb\xbf")
    assert b"\r" not in crudo and crudo.endswith(b"\n")
    crudo.decode("utf-8")
    lineas = crudo.decode("utf-8").split("\n")
    assert lineas[0] == "texto,intencion"
    assert all(l.startswith('"') for l in lineas[1:] if l)


def test_longitud_variada_y_razonable_en_las_nuevas():
    nuevas = _nuevas()
    largos = [len(f["texto"].split()) for f in nuevas]
    assert min(largos) >= 1 and max(largos) <= 20
    por_intencion: dict[str, list[int]] = {}
    for f in nuevas:
        por_intencion.setdefault(f["intencion"], []).append(len(f["texto"].split()))
    for intencion, ls in por_intencion.items():
        assert len(set(ls)) >= 5, f"{intencion}: poca variedad de longitudes"
    assert sum(1 for n in largos if n <= 3) / len(largos) < 0.5
    assert sum(1 for n in largos if n >= 6) / len(largos) > 0.25


def test_pocas_frases_de_seguimiento_que_dependen_del_turno_anterior():
    nuevas = _nuevas()
    seguimientos = [f for f in nuevas
                    if re.match(r"^(y |tambien |ademas |ese mismo|el mismo)", normalizar(f["texto"]))]
    assert len(seguimientos) / len(nuevas) <= MAX_SEGUIMIENTOS, [f["texto"] for f in seguimientos]


def test_hay_modelos_sin_marca_codigos_y_combustibles():
    nuevas = _nuevas()
    modelos = {normalizar(m) for m in _vocabulario()["modelo"] if not m.isdigit() and len(m) > 3}
    marcas = {normalizar(m) for m in _vocabulario()["marca"]}
    sin_marca = [f for f in nuevas
                 if modelos & set(normalizar(f["texto"]).split()) and not marcas & set(normalizar(f["texto"]).split())]
    assert len(sin_marca) >= 100
    textos = " ".join(normalizar(f["texto"]) for f in nuevas)
    assert re.search(r"\b5w 30\b", textos) and re.search(r"\b15w 40\b", textos)
    assert "diesel" in textos and "gasolina" in textos and "acpm" in textos
    assert re.search(r"\b(john deere|massey|new holland|case)\b", textos)
    assert re.search(r"\b\d\s\d\s?l?\b|\b1 6\b|\b2 7\b", textos)


def test_las_tres_clases_de_negocio_adyacente_estan_en_fuera_de_dominio():
    textos = " ".join(normalizar(f["texto"]) for f in _nuevas() if f["intencion"] == "fuera_de_dominio")
    for palabra in ("domicilio", "garantia", "factura", "horario", "parqueadero", "instalacion", "alineacion"):
        assert palabra in textos, palabra


# ------------------------------------------------------------------ tabla de errores


def test_la_tabla_cubre_todo_el_catalogo_con_variantes_suficientes():
    filas = _leer(TABLA)
    conteo = Counter((f["tipo"], f["correcto"]) for f in filas)
    for tipo, nombres in _vocabulario().items():
        for nombre in nombres:
            if nombre.isdigit():
                continue  # "3", "290", "4707", "6713": un número suelto no se distingue de una cantidad o un año
            assert conteo[(tipo, nombre)] >= MINIMO_VARIANTES_POR_NOMBRE, (tipo, nombre, conteo[(tipo, nombre)])
    assert conteo[("modelo", "3")] >= 5  # variantes con la marca ("mazda tres", "masda tres"...)


def test_la_tabla_incluye_los_ejemplos_de_la_ampliacion():
    esperados = {
        ("marca", "chebrolet", "Chevrolet"), ("marca", "nisan", "Nissan"), ("marca", "mistubishi", "Mitsubishi"),
        ("marca", "niu holland", "New Holland"), ("marca", "johndeer", "John Deere"), ("marca", "caseih", "Case IH"),
        ("modelo", "jailux", "Hilux"), ("modelo", "onicks", "Onix"), ("modelo", "onnix", "Onix"),
        ("categoria", "vaterias", "Baterías"), ("categoria", "neumatico", "Neumáticos"),
    }
    tabla = {(f["tipo"], f["error"], f["correcto"]) for f in _leer(TABLA)}
    faltan = esperados - tabla
    # "chebrolet" y "nisan" ya estaban desde antes; el resto lo agregó la ampliación.
    assert not faltan, faltan


def test_origen_manual_sin_digitos_salvo_nombres_con_digitos():
    for f in _leer(TABLA):
        if f["origen"] == "manual" and not re.search(r"\d", f["correcto"]):
            assert not re.search(r"\d", f["error"]), f


def test_nombres_nuevos_en_la_tabla_sin_digitos_de_ruido():
    semilla = {(t, n) for t, nombres in agente_errores.CATALOGO_SEMILLA.items() for n in nombres}
    for f in _leer(TABLA):
        if (f["tipo"], f["correcto"]) not in semilla and not re.search(r"\d", f["correcto"]):
            assert not re.search(r"\d", f["error"]), f


def test_un_solo_destino_por_error_y_valores_validos():
    filas = _leer(TABLA)
    errores = [f["error"] for f in filas]
    assert len(errores) == len(set(errores))
    for f in filas:
        assert f["tipo"] in {"marca", "modelo", "categoria"}
        assert f["nivel"] in {"1", "2", "3", "4"}, f
        assert f["origen"] in {"manual", "auto"}, f
        assert f["error"] == normalizar(f["error"]) and f["error"] != normalizar(f["correcto"]), f
        assert len(f["error"].replace(" ", "")) >= 3, f


def test_las_filas_manuales_estan_en_la_tabla_o_en_avisos_y_con_un_destino():
    en_tabla = {f["error"]: (f["tipo"], f["correcto"]) for f in _leer(TABLA)}
    avisos = {(a["tipo"], a["error"]) for a in _leer(AVISOS)}
    manuales = _leer(MANUALES)
    assert list(manuales[0].keys()) == COLUMNAS
    errores = [f["error"] for f in manuales]
    assert len(errores) == len(set(errores))
    for f in manuales:
        assert f["origen"] == "manual"
        assert en_tabla.get(f["error"]) == (f["tipo"], f["correcto"]) or (f["tipo"], f["error"]) in avisos, f


def test_la_tabla_sin_colisiones_con_el_catalogo_completo():
    oficiales = [n for nombres in agente_errores.CATALOGO_COMPLETO.values() for n in nombres]
    formas = [(forma, n) for n in oficiales for forma in sorted(formas_de(n))]
    filas = _leer(TABLA)
    distancias = process.cdist([f["error"] for f in filas], [forma for forma, _ in formas],
                               scorer=DamerauLevenshtein.distance, score_cutoff=1, workers=-1)
    for i, j in zip(*np.nonzero(distancias <= 1)):
        if filas[i]["error"] in EXCEPCIONES_PREEXISTENTES_CERCA_DE_NOMBRE_NUEVO:
            continue
        assert normalizar(formas[j][1]) == normalizar(filas[i]["correcto"]), (filas[i], formas[j][1])


def test_formato_de_los_csv_de_errores():
    for ruta, columnas in ((TABLA, COLUMNAS), (MANUALES, COLUMNAS), (AVISOS, COLUMNAS_AVISOS)):
        crudo = ruta.read_bytes()
        assert not crudo.startswith(b"\xef\xbb\xbf"), ruta.name
        crudo.decode("utf-8")
        with ruta.open(encoding="utf-8", newline="") as f:
            assert next(csv.reader(f)) == columnas, ruta.name


def test_los_errores_nuevos_del_catalogo_ampliado_se_encuentran_en_el_extractor():
    from app.ner.extractor import extraer_entidades

    catalogo = agente_errores.CATALOGO_COMPLETO
    casos = [
        ("necesito pastillas para un mistubishi l200", "marca", "Mitsubishi"),
        ("filtro de aire para johndeer 5075e", "marca", "John Deere"),
        ("llantas para un niu holland tl90", "marca", "New Holland"),
        ("bujias para un chebrolet onicks 2020", "modelo", "Onix"),
        ("busco vaterias para tractor", "categoria", "Baterías"),
    ]
    for frase, campo, esperado in casos:
        ent = extraer_entidades(frase, catalogo["marca"], catalogo["modelo"], catalogo["categoria"])
        assert ent[campo] == esperado, (frase, ent)


# ------------------------------------------------------------------ script de carga a Oracle


def test_script_oracle_inserta_cada_frase_nueva_de_forma_idempotente():
    ruta = RAIZ.parent / "oracle" / "18_nlp_frases_ampliadas.sql"
    if not ruta.exists():
        pytest.skip("oracle/ no está montado en este entorno")
    crudo = ruta.read_bytes()
    assert not crudo.startswith(b"\xef\xbb\xbf")
    sql = crudo.decode("utf-8")
    inserts = [l for l in sql.splitlines() if l.startswith("INSERT INTO nlp_frases")]
    nuevas = _nuevas()
    assert len(inserts) == len(nuevas)
    assert all("NOT EXISTS" in l and "'entrenamiento'" in l for l in inserts)
    for f in nuevas[:: max(1, len(nuevas) // 50)]:
        assert "'" + f["texto"].replace("'", "''") + "'" in sql
    assert "DELETE" not in sql.upper() and "UPDATE" not in sql.upper() and "DROP" not in sql.upper()


# ------------------------------------------------------------------ verificar_solapamiento.py (con archivos temporales)


@pytest.fixture
def verificador(tmp_path, monkeypatch):
    from eval import verificar_solapamiento as vs

    def escribir(nombre, filas, cabecera):
        ruta = tmp_path / nombre
        with ruta.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(cabecera)
            w.writerows(filas)
        return ruta

    base = tmp_path / "base"
    base.mkdir()
    monkeypatch.setattr(vs, "_NUEVAS_SOLAPADAS", [0])
    monkeypatch.setattr(vs, "_PREVIAS_ERRORES", [0])
    return vs, escribir, base, tmp_path, monkeypatch


def test_verificador_detecta_frases_nuevas_iguales_o_variantes_del_congelado(verificador):
    vs, escribir, base, tmp_path, monkeypatch = verificador
    escribir("holdout.csv", [["cuanto vale la batería del logan", "consultar_precio"]], ["texto", "intencion"])
    previa = ["¿Hacen domicilios?", "fuera_de_dominio"]
    escribir("base/intents_dataset.csv", [previa], ["texto", "intencion"])
    escribir("dataset.csv", [previa,
                             ["cuanto vale la bateria del logan", "consultar_precio"],        # igual normalizada
                             ["batería logan vale cuanto", "consultar_precio"],              # mismo núcleo
                             ["quiero unas bujias para el spark", "buscar_repuesto"]],        # limpia
             ["texto", "intencion"])
    monkeypatch.setattr(vs, "DATASET", tmp_path / "dataset.csv")
    monkeypatch.setattr(vs, "HOLDOUT_INTENT", tmp_path / "holdout.csv")
    salida = tmp_path / "salida.txt"
    n = vs.verificar_intenciones(base, str(salida))
    assert n == 2
    assert salida.read_text(encoding="utf-8").splitlines() == [
        "cuanto vale la bateria del logan", "batería logan vale cuanto"]


def test_verificador_solo_reporta_filas_nuevas_de_errores(verificador):
    vs, escribir, base, tmp_path, monkeypatch = verificador
    cab = ["tipo", "error", "correcto", "nivel", "origen", "nota"]
    escribir("holdout_e.csv", [["marca", "toyta", "Toyota", "1"], ["marca", "chebrolet", "Chevrolet", "0"]],
             ["tipo", "error", "correcto", "en_tabla"])
    escribir("base/posibles_errores.csv", [["marca", "toyta", "Toyota", 1, "auto", "x"]], cab)
    escribir("tabla.csv", [["marca", "toyta", "Toyota", 1, "auto", "x"],
                           ["marca", "chebrolet", "Chevrolet", 2, "manual", "y"],
                           ["marca", "nisan", "Nissan", 1, "auto", "z"]], cab)
    monkeypatch.setattr(vs, "TABLA", tmp_path / "tabla.csv")
    monkeypatch.setattr(vs, "MANUALES", tmp_path / "no_existe.csv")
    monkeypatch.setattr(vs, "HOLDOUT_ERRORES", tmp_path / "holdout_e.csv")
    salida = tmp_path / "salida_e.txt"
    n = vs.verificar_errores(base, str(salida))
    assert n == 1  # solo la fila nueva; la previa que coincide es informativa
    assert salida.read_text(encoding="utf-8") == "marca\tchebrolet\n"
    assert vs._PREVIAS_ERRORES[0] == 1

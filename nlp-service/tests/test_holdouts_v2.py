"""Verificaciones de formato y de independencia de los holdouts v2 (congelados).

No cargan ningún modelo: solo comprueban que los conjuntos de prueba estén bien
formados, no se solapen con el entrenamiento y sigan siendo los que se congelaron
(hash registrado en eval/CONGELADO.txt).
"""
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import pytest
from rapidfuzz import fuzz

from app.preprocessing import STOPWORDS_ES, normalizar

RAIZ = Path(__file__).resolve().parent.parent
EVAL = RAIZ / "eval"
INTENT_V2 = EVAL / "holdout_intent_v2.csv"
NER_V2 = EVAL / "holdout_ner_v2.json"
REC_V2 = EVAL / "holdout_recomendador_v2.json"
ERR_V2 = EVAL / "holdout_errores_v2.csv"
CONGELADO = EVAL / "CONGELADO.txt"

INTENCIONES = {
    "recomendar_sustituto", "buscar_repuesto", "consultar_stock", "consultar_precio",
    "consultar_compatibilidad", "saludo_despedida", "fuera_de_dominio",
}
MINIMO_POR_CLASE = 24
CAMPOS_NER = ["marca", "modelo", "anio", "motor", "combustible", "categoria", "codigo"]
GRUPOS_NER = {"normal", "sinonimo", "codigo", "trampa", "negativo", "typo"}
# Solapes permitidos entre holdout_intent_v2.csv y el holdout viejo (decisión consciente: ninguno).
SOLAPE_PERMITIDO_CON_HOLDOUT_VIEJO: set[str] = set()
UMBRAL_FUZZY_VARIANTE = 90


def _csv(ruta: Path) -> list[dict]:
    with open(ruta, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _json(ruta: Path):
    return json.loads(ruta.read_text(encoding="utf-8"))


def _nucleo(texto_normalizado: str) -> frozenset:
    """Tokens sin dígitos ni stopwords: dos frases con el mismo núcleo son variantes triviales."""
    sin_digitos = re.sub(r"\d+", " ", texto_normalizado)
    return frozenset(t for t in sin_digitos.split() if t not in STOPWORDS_ES)


@pytest.fixture(scope="module")
def catalogo():
    repuestos = _csv(EVAL / "datos_demo" / "repuestos.csv")
    compat = _csv(EVAL / "datos_demo" / "compatibilidad.csv")
    return {
        "repuestos": repuestos,
        "compat": compat,
        "marcas": {c["MARCA"] for c in compat},
        "modelos": {c["MODELO"] for c in compat},
        "categorias": {r["CATEGORIA"] for r in repuestos},
        "codigos": {r["CODIGO"] for r in repuestos},
        "motores": {c["MOTOR"] for c in compat},
        "combustibles": {c["COMBUSTIBLE"] for c in compat},
    }


# ------------------------------------------------------------------ archivos
@pytest.mark.parametrize("ruta", [INTENT_V2, NER_V2, REC_V2, ERR_V2, CONGELADO])
def test_archivos_utf8_sin_bom_y_lf(ruta):
    datos = ruta.read_bytes()
    assert not datos.startswith(b"\xef\xbb\xbf"), "no debe tener BOM"
    assert b"\r" not in datos, "debe usar finales de línea LF"
    datos.decode("utf-8")


def test_hashes_coinciden_con_congelado():
    texto = CONGELADO.read_text(encoding="utf-8")
    for ruta in (INTENT_V2, NER_V2, REC_V2, ERR_V2):
        esperado = hashlib.sha256(ruta.read_bytes()).hexdigest()
        assert f"{esperado}  {ruta.name}" in texto, f"{ruta.name} cambió respecto de lo congelado"


# ------------------------------------------------------------------ intención
def test_intent_formato_y_tamano():
    filas = _csv(INTENT_V2)
    assert filas and set(filas[0].keys()) == {"texto", "intencion"}
    assert len(filas) >= MINIMO_POR_CLASE * len(INTENCIONES)
    assert all(f["texto"].strip() and f["intencion"].strip() for f in filas)


def test_intent_etiquetas_validas_y_minimo_por_clase():
    conteo = Counter(f["intencion"] for f in _csv(INTENT_V2))
    assert set(conteo) == INTENCIONES
    assert all(n >= MINIMO_POR_CLASE for n in conteo.values()), conteo


def test_intent_sin_duplicados_normalizados():
    normalizados = [normalizar(f["texto"]) for f in _csv(INTENT_V2)]
    repetidos = [t for t, n in Counter(normalizados).items() if n > 1]
    assert not repetidos, repetidos


def test_intent_sin_solape_con_entrenamiento():
    entrenamiento = {normalizar(f["texto"]) for f in _csv(RAIZ / "data" / "intents_dataset.csv")}
    solape = {normalizar(f["texto"]) for f in _csv(INTENT_V2)} & entrenamiento
    assert not solape, solape


def test_intent_sin_variantes_triviales_del_entrenamiento():
    entrenamiento = [normalizar(f["texto"]) for f in _csv(RAIZ / "data" / "intents_dataset.csv")]
    nucleos = {_nucleo(t) for t in entrenamiento}
    problemas = []
    for f in _csv(INTENT_V2):
        n = normalizar(f["texto"])
        if _nucleo(n) in nucleos:
            problemas.append(("mismo núcleo", f["texto"]))
        elif max(fuzz.token_sort_ratio(n, t) for t in entrenamiento) >= UMBRAL_FUZZY_VARIANTE:
            problemas.append(("muy parecida", f["texto"]))
    assert not problemas, problemas


def test_intent_solape_con_holdout_viejo_solo_el_permitido():
    viejo = {normalizar(f["texto"]) for f in _csv(EVAL / "holdout_intent.csv")}
    solape = {normalizar(f["texto"]) for f in _csv(INTENT_V2)} & viejo
    assert solape <= SOLAPE_PERMITIDO_CON_HOLDOUT_VIEJO, solape


def test_intent_fuera_de_dominio_incluye_preguntas_de_negocio():
    # medir_baseline.py separa fuera_de_dominio por posición: las 18 primeras son ajenas
    # al negocio y las siguientes son preguntas de negocio sin intención soportada.
    fuera = [f["texto"] for f in _csv(INTENT_V2) if f["intencion"] == "fuera_de_dominio"]
    assert len(fuera) >= 18 + 10
    assert fuera[17] == "tienes novia o novio"
    assert fuera[18] == "hasta qué hora atienden los sábados"


# ------------------------------------------------------------------ NER
def test_ner_formato_y_tamano():
    casos = _json(NER_V2)
    assert len(casos) >= 80
    for c in casos:
        assert set(c) == {"texto", "grupo", "esperado"}
        assert c["texto"].strip() and c["grupo"] in GRUPOS_NER
        assert list(c["esperado"]) == CAMPOS_NER, "anotación cerrada: los 7 campos, null si no hay"


def test_ner_sin_textos_duplicados():
    normalizados = [normalizar(c["texto"]) for c in _json(NER_V2)]
    assert len(normalizados) == len(set(normalizados))


def test_ner_valores_pertenecen_al_vocabulario(catalogo):
    for c in _json(NER_V2):
        e = c["esperado"]
        assert e["marca"] is None or e["marca"] in catalogo["marcas"], c
        assert e["modelo"] is None or e["modelo"] in catalogo["modelos"], c
        assert e["categoria"] is None or e["categoria"] in catalogo["categorias"], c
        assert e["codigo"] is None or e["codigo"] in catalogo["codigos"], c
        assert e["combustible"] is None or e["combustible"] in catalogo["combustibles"], c
        assert e["anio"] is None or (isinstance(e["anio"], int) and 1950 <= e["anio"] <= 2049), c
        assert e["motor"] is None or e["motor"] in catalogo["motores"] or re.fullmatch(r"\d{3,4}cc", e["motor"]), c


def test_ner_marca_y_modelo_son_coherentes_con_el_catalogo(catalogo):
    pares = {(c["MARCA"], c["MODELO"]) for c in catalogo["compat"]}
    for c in _json(NER_V2):
        e = c["esperado"]
        if e["marca"] and e["modelo"]:
            assert (e["marca"], e["modelo"]) in pares, c


def test_ner_cubre_todo_el_catalogo(catalogo):
    esperados = [c["esperado"] for c in _json(NER_V2)]
    assert {e["marca"] for e in esperados if e["marca"]} == catalogo["marcas"]
    assert {e["modelo"] for e in esperados if e["modelo"]} == catalogo["modelos"]
    assert {e["categoria"] for e in esperados if e["categoria"]} == catalogo["categorias"]


def test_ner_cada_campo_tiene_casos_con_y_sin_valor():
    esperados = [c["esperado"] for c in _json(NER_V2)]
    for campo in CAMPOS_NER:
        con = sum(1 for e in esperados if e[campo] is not None)
        sin = sum(1 for e in esperados if e[campo] is None)
        assert con >= 5 and sin >= 5, (campo, con, sin)


def test_ner_tiene_al_menos_20_casos_con_errores_de_tipeo_y_casos_sin_entidades():
    casos = _json(NER_V2)
    assert sum(1 for c in casos if c["grupo"] == "typo") >= 20
    vacios = [c for c in casos if all(v is None for v in c["esperado"].values())]
    assert len(vacios) >= 5


# ------------------------------------------------------------------ recomendador
def _candidatos(catalogo, marca, modelo, anio):
    por_id = {r["ID"]: r for r in catalogo["repuestos"]}
    salida = {}
    for c in catalogo["compat"]:
        if c["MARCA"] == marca and c["MODELO"] == modelo and int(c["ANIO_DESDE"]) <= anio <= int(c["ANIO_HASTA"]):
            r = por_id[c["REPUESTO_ID"]]
            if r["ACTIVO"] == "1" and int(r["STOCK"]) > 0:
                salida[r["CODIGO"]] = r["CATEGORIA"]
    return salida


def test_recomendador_formato_y_regla():
    casos = _json(REC_V2)
    assert len(casos) >= 30
    assert isinstance(casos[0].get("regla"), str) and "R1" in casos[0]["regla"]
    for c in casos:
        assert {"texto", "codigos_correctos", "marca", "modelo", "anio", "categoria", "n_candidatos"} <= set(c)
        assert c["texto"].strip() and c["codigos_correctos"]
    textos = [normalizar(c["texto"]) for c in casos]
    assert len(textos) == len(set(textos))


def test_recomendador_codigos_correctos_siguen_la_regla_mecanica(catalogo):
    for c in _json(REC_V2):
        cand = _candidatos(catalogo, c["marca"], c["modelo"], c["anio"])
        correctos = sorted(k for k, cat in cand.items() if cat == c["categoria"])
        assert c["codigos_correctos"] == correctos, c["texto"]
        assert c["n_candidatos"] == len(cand) > 3, c["texto"]
        assert 1 <= len(correctos) < len(cand), c["texto"]


# ------------------------------------------------------------------ errores de digitación
def _tabla_errores() -> set:
    with open(RAIZ / "data" / "errores" / "posibles_errores.csv", encoding="utf-8", newline="") as f:
        return {(r["tipo"], r["error"], r["correcto"]) for r in csv.DictReader(f)}


def test_errores_formato_y_tamano():
    filas = _csv(ERR_V2)
    assert filas and list(filas[0].keys()) == ["tipo", "error", "correcto", "en_tabla"]
    assert len(filas) >= 150
    assert {f["tipo"] for f in filas} == {"marca", "modelo", "categoria"}
    assert {f["en_tabla"] for f in filas} <= {"0", "1"}


def test_errores_sin_duplicados_ni_identicos_al_correcto():
    filas = _csv(ERR_V2)
    pares = [(f["tipo"], f["error"]) for f in filas]
    assert len(pares) == len(set(pares))
    assert all(f["error"] != normalizar(f["correcto"]) and f["error"] == f["error"].strip().lower() for f in filas)


def test_errores_correcto_pertenece_al_catalogo_y_sin_digitos_de_ruido(catalogo):
    vocabulario = {"marca": catalogo["marcas"], "modelo": catalogo["modelos"], "categoria": catalogo["categorias"]}
    for f in _csv(ERR_V2):
        assert f["correcto"] in vocabulario[f["tipo"]], f
        if not re.search(r"\d", f["correcto"]):
            assert not re.search(r"\d", f["error"]), f


def test_errores_en_tabla_es_consistente_y_hay_suficientes_fuera_de_tabla():
    tabla = _tabla_errores()
    filas = _csv(ERR_V2)
    for f in filas:
        esperado = "1" if (f["tipo"], f["error"], f["correcto"]) in tabla else "0"
        assert f["en_tabla"] == esperado, f
    fuera = sum(1 for f in filas if f["en_tabla"] == "0")
    assert fuera / len(filas) >= 0.40


def test_errores_cubre_marcas_modelos_y_categorias(catalogo):
    filas = _csv(ERR_V2)
    assert {f["correcto"] for f in filas if f["tipo"] == "marca"} == catalogo["marcas"]
    assert {f["correcto"] for f in filas if f["tipo"] == "categoria"} == catalogo["categorias"]
    assert len({f["correcto"] for f in filas if f["tipo"] == "modelo"}) >= 20

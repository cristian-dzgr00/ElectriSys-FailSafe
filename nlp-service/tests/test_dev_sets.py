"""Conjuntos de DESARROLLO (eval/dev_*): su formato y que el código vigente no retroceda en ellos.

No tocan los conjuntos congelados (eval/holdout_*_v2.*). Los dev_* se escribieron a mano antes de
mejorar el extractor y el recomendador, pero se usaron para iterar: sirven de red de seguridad
contra regresiones, no como evidencia de generalización.
"""
import csv
import json
from pathlib import Path

import pytest

from app.ner import extractor
from app.preprocessing import normalizar
from eval import medir_baseline as mb

EVAL = Path(__file__).resolve().parent.parent / "eval"
CAMPOS = {"marca", "modelo", "anio", "motor", "combustible", "codigo", "categoria"}


@pytest.fixture(scope="module")
def entorno():
    cat = mb.cargar_catalogo()
    return cat, mb.vocab_ner(cat, con_marca_de_modelo=True)


def test_dev_ner_tiene_formato_y_tamano():
    casos = json.loads((EVAL / "dev_ner.json").read_text(encoding="utf-8"))
    assert len(casos) >= 80
    assert all(c["texto"].strip() and c["grupo"] and set(c["esperado"]) <= CAMPOS for c in casos)
    assert len({normalizar(c["texto"]) for c in casos}) == len(casos), "frases repetidas en dev_ner.json"


def test_dev_recomendador_tiene_respuestas_por_regla_y_no_vacias():
    casos = json.loads((EVAL / "dev_recomendador.json").read_text(encoding="utf-8"))
    assert len(casos) >= 30
    assert all(c["codigos_correctos"] and c["n_candidatos"] >= len(c["codigos_correctos"]) and c["regla"] for c in casos)


def test_dev_errores_tiene_formato_y_en_tabla_calculado_con_la_tabla_real():
    with (EVAL / "dev_errores.csv").open(encoding="utf-8", newline="") as f:
        lector = csv.DictReader(f)
        assert lector.fieldnames == ["tipo", "error", "correcto", "en_tabla"]
        filas = list(lector)
    assert len(filas) >= 150
    tabla = extractor.cargar_tabla_errores()
    for f in filas:
        assert f["en_tabla"] == str(int(normalizar(f["error"]) in tabla.get(f["tipo"], {}))), f
    fuera = sum(1 for f in filas if f["en_tabla"] == "0")
    assert fuera >= 40, "hacen falta errores que NO estén en la tabla para medir los respaldos"


def test_ner_en_dev_no_retrocede(entorno):
    cat, vocab = entorno
    r = mb.medir_ner(cat, EVAL / "dev_ner.json", vocab)
    assert r["exactitud_global_campos"]["exactitud"] >= 0.97
    assert r["por_campo"]["categoria"]["exactitud"] >= 0.95
    assert r["por_campo"]["marca"]["exactitud"] >= 0.97


def test_el_pipeline_recomienda_aunque_no_se_escriba_la_marca(entorno):
    cat, vocab = entorno
    r = mb.medir_recomendador(cat, EVAL / "dev_recomendador.json", vocab)
    assert r["pipeline_casos_sin_marca_o_modelo"]["n"] == 0
    assert r["pipeline_completo"]["p1"]["media"] >= 0.9
    assert r["solo_ranking"]["p1"]["media"] >= 0.9


def test_errores_de_digitacion_fuera_de_la_tabla_se_resuelven_en_dev(entorno):
    cat, vocab = entorno
    r = mb.medir_errores(cat, EVAL / "dev_errores.csv", vocab)
    assert r["exactitud"]["global"]["exactitud"] >= 0.95
    assert r["exactitud"]["en_tabla=0"]["exactitud"] >= 0.9
    assert r["control_nombre_correcto"]["resueltos"] == r["control_nombre_correcto"]["total"]

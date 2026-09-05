import csv
from collections import Counter
from pathlib import Path

DATASET_PATH = Path(__file__).resolve().parent.parent / "data" / "intents_dataset.csv"
MINIMO_POR_CLASE = 5


def _leer_dataset() -> list[dict]:
    with open(DATASET_PATH, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_dataset_existe_y_tiene_columnas_correctas():
    filas = _leer_dataset()
    assert len(filas) > 0
    assert set(filas[0].keys()) == {"texto", "intencion"}


def test_dataset_sin_duplicados_exactos():
    filas = _leer_dataset()
    textos = [f["texto"].strip().lower() for f in filas]
    duplicados = [t for t, n in Counter(textos).items() if n > 1]
    assert not duplicados, f"Ejemplos duplicados en el dataset: {duplicados}"


def test_dataset_todas_las_clases_tienen_minimo_de_ejemplos():
    filas = _leer_dataset()
    conteo = Counter(f["intencion"] for f in filas)
    insuficientes = {i: n for i, n in conteo.items() if n < MINIMO_POR_CLASE}
    assert not insuficientes, (
        f"Intenciones con menos de {MINIMO_POR_CLASE} ejemplos: {insuficientes}"
    )


def test_dataset_no_tiene_textos_ni_intenciones_vacias():
    filas = _leer_dataset()
    assert all(f["texto"].strip() for f in filas)
    assert all(f["intencion"].strip() for f in filas)


def test_dataset_intenciones_son_las_7_esperadas():
    filas = _leer_dataset()
    esperadas = {
        "recomendar_sustituto", "buscar_repuesto", "consultar_stock",
        "consultar_precio", "consultar_compatibilidad", "saludo_despedida",
        "fuera_de_dominio",
    }
    encontradas = {f["intencion"] for f in filas}
    assert encontradas == esperadas

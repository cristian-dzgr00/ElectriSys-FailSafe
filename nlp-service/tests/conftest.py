import shutil
from pathlib import Path

import pytest

from app.ner import agente_errores


@pytest.fixture(autouse=True, scope="session")
def _modelo_de_intencion_disponible(tmp_path_factory):
    """Garantiza que exista el modelo entrenado, como hace el servicio al arrancar.

    `models/intent_classifier.pkl` está en .gitignore, así que en un checkout limpio
    (GitHub Actions) no existe. Antes los tests lo creaban por casualidad porque
    test_intent.py entrenaba y sobrescribía el modelo real; ahora ese test entrena en
    una carpeta temporal y esta fixture cubre a los que usan el modelo real (test_main).
    Las métricas se escriben en una carpeta temporal para no tocar models/metrics_intent.json.
    """
    from app.intent import train

    ruta_modelo = Path(train.MODEL_PATH)
    lo_creamos = not ruta_modelo.exists()
    if lo_creamos:
        train.entrenar(metrics_path=tmp_path_factory.mktemp("metricas") / "metrics_intent.json")
    yield
    if lo_creamos and ruta_modelo.exists():
        ruta_modelo.unlink()


@pytest.fixture(autouse=True, scope="session")
def _tabla_errores_en_carpeta_temporal(tmp_path_factory):
    """Ningún test escribe en data/errores/ del repo.

    dictionary.py avisa al agente en un hilo cada vez que refresca su caché
    (también en los tests de dictionary); el agente escribe entonces sobre
    una copia temporal de la tabla, no sobre la versionada. La lectura del
    extractor sigue usando la tabla real.
    """
    destino = tmp_path_factory.mktemp("errores")
    originales = (agente_errores.RUTA_TABLA, agente_errores.RUTA_AVISOS)
    for ruta in originales:
        if ruta.exists():
            shutil.copy(ruta, destino / ruta.name)
    agente_errores.RUTA_TABLA = destino / originales[0].name
    agente_errores.RUTA_AVISOS = destino / originales[1].name
    agente_errores._reiniciar_estado()
    yield
    agente_errores.RUTA_TABLA, agente_errores.RUTA_AVISOS = originales
    agente_errores._reiniciar_estado()

import shutil

import pytest

from app.ner import agente_errores


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

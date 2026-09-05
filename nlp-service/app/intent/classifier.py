"""Clasificador de intención: carga el modelo entrenado y predice.

Si la confianza de la predicción es baja, se prefiere devolver
'fuera_de_dominio' en vez de forzar una clase poco confiable — con un
dataset todavía chico, es mejor admitir incertidumbre que inventar.
"""
from pathlib import Path

import joblib

from app.intent.train import MODEL_PATH

UMBRAL_CONFIANZA = 0.35
INTENCION_FALLBACK = "fuera_de_dominio"

_pipeline_cacheado = None


def _cargar_pipeline():
    global _pipeline_cacheado
    if _pipeline_cacheado is None:
        if not Path(MODEL_PATH).exists():
            raise FileNotFoundError(
                f"No se encontró el modelo entrenado en {MODEL_PATH}. "
                "Corre primero: python -m app.intent.train"
            )
        _pipeline_cacheado = joblib.load(MODEL_PATH)
    return _pipeline_cacheado


def predecir_intencion(texto: str, pipeline=None) -> tuple[str, float]:
    """Devuelve (intencion, confianza) para el texto dado.

    El parámetro `pipeline` es opcional y existe principalmente para poder
    probar la lógica del umbral de confianza con un modelo falso en los
    tests, sin depender del modelo real entrenado.
    """
    pipeline = pipeline if pipeline is not None else _cargar_pipeline()

    probabilidades = pipeline.predict_proba([texto])[0]
    clases = pipeline.classes_
    idx_max = max(range(len(probabilidades)), key=lambda i: probabilidades[i])
    intencion = clases[idx_max]
    confianza = float(probabilidades[idx_max])

    if confianza < UMBRAL_CONFIANZA:
        return INTENCION_FALLBACK, confianza

    return intencion, confianza

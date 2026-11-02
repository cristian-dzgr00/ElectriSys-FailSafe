"""Entrena el clasificador de intención y guarda el modelo + métricas.

Uso: python -m app.intent.train

`entrenar()` sin argumentos escribe en models/ (lo que sirve el servicio). Las
pruebas y los experimentos pasan rutas propias para NO pisar el modelo real
(ver tests/test_intent.py).
"""
import hashlib
import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import Pipeline

from app.intent.modelos import NOMBRE_PRODUCCION, construir

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATASET_PATH = BASE_DIR / "data" / "intents_dataset.csv"
MODEL_PATH = BASE_DIR / "models" / "intent_classifier.pkl"
METRICS_PATH = BASE_DIR / "models" / "metrics_intent.json"

SEMILLA_CV = 42
INTENCION_FALLBACK = "fuera_de_dominio"


def _construir_pipeline() -> Pipeline:
    """El modelo de producción (definido en modelos.py: TF-IDF de unigramas con los
    nombres de vehículo reemplazados por un marcador + regresión logística C=15,
    solver liblinear).

    Por qué esta configuración y no otra: se comparó por validación cruzada
    repetida (normal y agrupada) contra otros C, bigramas, class_weight="balanced",
    Naive Bayes, SVM lineal y un perceptrón de una capa oculta (64/128/256). Ninguno
    superó a la regresión logística C=15; el MLP rindió ~2 puntos de F1 menos.
    El resultado completo, con diferencias pareadas, está en eval/cifras_vigentes.json
    (generado por eval/generar_cifras.py).
    """
    return construir(NOMBRE_PRODUCCION)


def entrenar(dataset_path=None, model_path=None, metrics_path=None) -> dict:
    """Entrena con TODO el dataset, guarda el modelo y las métricas y devuelve las métricas.

    Las tres rutas son opcionales; por defecto son las del servicio (DATASET_PATH,
    MODEL_PATH, METRICS_PATH). Se leen al llamar, no al importar, para poder cambiarlas.
    """
    # Se importa aquí (y no arriba) para que classifier.py, que importa MODEL_PATH de este
    # módulo, no cree un ciclo de importación.
    from app.intent.classifier import UMBRAL_CONFIANZA

    dataset_path = Path(dataset_path) if dataset_path else DATASET_PATH
    model_path = Path(model_path) if model_path else MODEL_PATH
    metrics_path = Path(metrics_path) if metrics_path else METRICS_PATH

    df = pd.read_csv(dataset_path)
    X, y = df["texto"], df["intencion"]

    pipeline = _construir_pipeline()

    # Validación cruzada estratificada de 5 partes con semilla fija: mide qué tan bien
    # generaliza. Es UNA corrida; la comparación con 10 repeticiones y la validación
    # agrupada están en eval/cifras_vigentes.json.
    n_splits = min(5, y.value_counts().min())
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=SEMILLA_CV)
    proba = cross_val_predict(pipeline, X, y, cv=skf, method="predict_proba")
    clases = sorted(set(y))
    y_pred = pd.Series([clases[i] for i in proba.argmax(axis=1)], index=y.index)
    y_umbral = pd.Series(
        [INTENCION_FALLBACK if p.max() < UMBRAL_CONFIANZA else clases[p.argmax()] for p in proba], index=y.index
    )

    reporte = classification_report(y, y_pred, output_dict=True, zero_division=0)
    metricas = {
        "n_splits": int(n_splits),
        "accuracy": float(accuracy_score(y, y_pred)),
        "f1_macro": float(f1_score(y, y_pred, average="macro")),
        "umbral_confianza": UMBRAL_CONFIANZA,
        "accuracy_con_umbral": float(accuracy_score(y, y_umbral)),
        "f1_macro_con_umbral": float(f1_score(y, y_umbral, average="macro")),
        "reporte_por_clase": reporte,
        "n_ejemplos": int(len(df)),
        "modelo": NOMBRE_PRODUCCION,
        "semilla_cv": SEMILLA_CV,
        "dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        "nota": (
            f"Métricas de una corrida de validación cruzada estratificada ({n_splits} partes, "
            f"semilla {SEMILLA_CV}) sobre {len(df)} ejemplos. Las cifras de referencia "
            "(10 repeticiones, validación agrupada, comparación de modelos) están en "
            "eval/cifras_vigentes.json."
        ),
    }

    # El modelo que se sirve en producción se entrena con TODO el dataset
    # (la validación cruzada de arriba es solo para medir qué tan bien
    # generaliza; el modelo final aprovecha todos los ejemplos disponibles).
    pipeline.fit(X, y)

    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, model_path)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(metricas, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

    return metricas


if __name__ == "__main__":
    m = entrenar()
    print(f"Accuracy (CV {m['n_splits']}-fold): {m['accuracy']:.3f}")
    print(f"F1 macro (CV): {m['f1_macro']:.3f}")
    print(f"F1 macro con umbral {m['umbral_confianza']}: {m['f1_macro_con_umbral']:.3f}")
    print(f"Modelo guardado en:   {MODEL_PATH}")
    print(f"Métricas guardadas en: {METRICS_PATH}")

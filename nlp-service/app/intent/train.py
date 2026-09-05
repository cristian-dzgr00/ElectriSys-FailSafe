"""Entrena el clasificador de intención y guarda el modelo + métricas.

Uso: python -m app.intent.train
"""
import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import Pipeline

from app.preprocessing import preprocesar

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATASET_PATH = BASE_DIR / "data" / "intents_dataset.csv"
MODEL_PATH = BASE_DIR / "models" / "intent_classifier.pkl"
METRICS_PATH = BASE_DIR / "models" / "metrics_intent.json"


def _construir_pipeline() -> Pipeline:
    # ngram_range=(1,1) y C=15: se probaron bigramas y class_weight="balanced"
    # (más "estándar" a priori) pero con ~60 ejemplos y 7 clases producían
    # probabilidades demasiado planas (~0.20 para la clase correcta), lo que
    # hacía que el umbral de confianza descartara predicciones correctas.
    # Esta configuración se validó empíricamente: separa con claridad los
    # casos de dominio (confianza ~0.6-0.9) de los realmente ajenos (~0.15-0.2).
    return Pipeline([
        ("tfidf", TfidfVectorizer(
            tokenizer=preprocesar,
            token_pattern=None,  # requerido por sklearn al usar tokenizer propio
            ngram_range=(1, 1),
            min_df=1,
        )),
        # solver="liblinear": además de dar resultados ligeramente mejores
        # que el "lbfgs" por defecto en este dataset, evita un warning de
        # incompatibilidad scipy/sklearn ("Unknown solver options: iprint")
        # que el solver por defecto dispara con esta versión de scipy.
        ("clf", LogisticRegression(max_iter=2000, C=15, solver="liblinear")),
    ])


def entrenar() -> dict:
    df = pd.read_csv(DATASET_PATH)
    X, y = df["texto"], df["intencion"]

    pipeline = _construir_pipeline()

    # Dataset pequeño (~60 ejemplos): un solo split train/test sería muy
    # ruidoso (la métrica dependería demasiado de qué ejemplos caen en el
    # test). Se usa validación cruzada k-fold estratificada en su lugar.
    n_splits = min(5, y.value_counts().min())
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
    y_pred = cross_val_predict(pipeline, X, y, cv=skf)

    reporte = classification_report(y, y_pred, output_dict=True, zero_division=0)
    metricas = {
        "n_splits": int(n_splits),
        "accuracy": float(accuracy_score(y, y_pred)),
        "f1_macro": float(f1_score(y, y_pred, average="macro")),
        "reporte_por_clase": reporte,
        "n_ejemplos": int(len(df)),
        "nota": (
            f"Métricas de validación cruzada ({n_splits}-fold) sobre un dataset de "
            f"{len(df)} ejemplos. Se espera que mejoren y se estabilicen al ampliar "
            "el dataset (ver data/intents_dataset.csv)."
        ),
    }

    # El modelo que se sirve en producción se entrena con TODO el dataset
    # (la validación cruzada de arriba es solo para medir qué tan bien
    # generaliza; el modelo final aprovecha todos los ejemplos disponibles).
    pipeline.fit(X, y)

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, MODEL_PATH)
    METRICS_PATH.write_text(json.dumps(metricas, indent=2, ensure_ascii=False), encoding="utf-8")

    return metricas


if __name__ == "__main__":
    m = entrenar()
    print(f"Accuracy (CV {m['n_splits']}-fold): {m['accuracy']:.3f}")
    print(f"F1 macro (CV): {m['f1_macro']:.3f}")
    print(f"Modelo guardado en:   {MODEL_PATH}")
    print(f"Métricas guardadas en: {METRICS_PATH}")

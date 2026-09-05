"""Evaluación de la clasificación de intención sobre un set de prueba
INDEPENDIENTE (holdout_intent.csv) — no usado en el entrenamiento, con
frases parafraseadas distinto a data/intents_dataset.csv. A diferencia de
la validación cruzada de la Sprint 3 (que reparte el mismo dataset chico
en folds), esto mide generalización real a frases nunca vistas.

Uso: python -m eval.eval_intent
"""
import json
from pathlib import Path

import pandas as pd
from sklearn.metrics import accuracy_score, classification_report, f1_score

from app.intent.classifier import predecir_intencion
from app.intent.train import MODEL_PATH, entrenar

BASE_DIR = Path(__file__).resolve().parent
HOLDOUT_PATH = BASE_DIR / "holdout_intent.csv"
RESULTADOS_PATH = BASE_DIR / "resultados_intent.json"


def evaluar() -> dict:
    if not MODEL_PATH.exists():
        entrenar()

    df = pd.read_csv(HOLDOUT_PATH)
    predicciones = [predecir_intencion(t)[0] for t in df["texto"]]
    confianzas = [predecir_intencion(t)[1] for t in df["texto"]]

    resultado = {
        "n_ejemplos": len(df),
        "accuracy": accuracy_score(df["intencion"], predicciones),
        "f1_macro": f1_score(df["intencion"], predicciones, average="macro"),
        "confianza_promedio": sum(confianzas) / len(confianzas),
        "reporte_por_clase": classification_report(
            df["intencion"], predicciones, output_dict=True, zero_division=0
        ),
        "errores": [
            {"texto": t, "esperado": e, "predicho": p}
            for t, e, p in zip(df["texto"], df["intencion"], predicciones)
            if e != p
        ],
    }
    RESULTADOS_PATH.write_text(json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8")
    return resultado


if __name__ == "__main__":
    r = evaluar()
    print(f"Accuracy (holdout): {r['accuracy']:.3f}")
    print(f"F1 macro (holdout): {r['f1_macro']:.3f}")
    print(f"Confianza promedio: {r['confianza_promedio']:.3f}")
    print(f"Errores: {len(r['errores'])}/{r['n_ejemplos']}")
    for e in r["errores"]:
        print(f"  - \"{e['texto']}\" -> esperado={e['esperado']} predicho={e['predicho']}")

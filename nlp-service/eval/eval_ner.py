"""Evaluación del NER (extractor.py) sobre un set de prueba anotado a mano
(holdout_ner.json), campo por campo.

Usa una foto fija del vocabulario del catálogo semilla (database/seed_vehiculos.sql)
en vez de pedirlo al backend en vivo: esto evalúa la lógica de extracción en
sí misma (reglas + fuzzy matching), no la integración con el backend — eso
ya lo cubren los tests de app/ner/dictionary.py. Así el resultado es
reproducible sin necesitar el backend levantado.

Uso: python -m eval.eval_ner
"""
import json
from pathlib import Path

from app.ner.extractor import extraer_entidades

BASE_DIR = Path(__file__).resolve().parent
HOLDOUT_PATH = BASE_DIR / "holdout_ner.json"
RESULTADOS_PATH = BASE_DIR / "resultados_ner.json"

# Foto fija del catálogo semilla (ver database/seed_vehiculos.sql)
MARCAS = ["Toyota", "Chevrolet", "Mazda", "Nissan", "Hyundai", "Kia", "Renault", "Ford", "Suzuki"]
MODELOS = [
    "Hilux", "Corolla", "Fortuner", "Spark", "Spark GT", "Aveo", "3", "CX-5",
    "Sentra", "Frontier", "Tucson", "Accent", "Rio", "Sportage", "Logan",
    "Duster", "Escape", "Fiesta", "Swift",
]
CATEGORIAS = [
    "Filtros", "Frenos", "Baterías", "Suspensión", "Motor", "Transmisión",
    "Encendido", "Correas y Bandas",
]


def _coincide(esperado, obtenido) -> bool:
    if esperado is None:
        return obtenido is None
    if isinstance(esperado, str) and isinstance(obtenido, str):
        return esperado.strip().lower() == obtenido.strip().lower()
    return esperado == obtenido


def evaluar() -> dict:
    casos = json.loads(HOLDOUT_PATH.read_text(encoding="utf-8"))

    aciertos_por_campo: dict[str, int] = {}
    total_por_campo: dict[str, int] = {}
    errores = []

    for caso in casos:
        entidades = extraer_entidades(
            caso["texto"], marcas_conocidas=MARCAS, modelos_conocidos=MODELOS,
            categorias_conocidas=CATEGORIAS,
        )
        for campo, esperado in caso["esperado"].items():
            obtenido = entidades.get(campo)
            total_por_campo[campo] = total_por_campo.get(campo, 0) + 1
            if _coincide(esperado, obtenido):
                aciertos_por_campo[campo] = aciertos_por_campo.get(campo, 0) + 1
            else:
                errores.append({
                    "texto": caso["texto"], "campo": campo,
                    "esperado": esperado, "obtenido": obtenido,
                })

    precision_por_campo = {
        campo: aciertos_por_campo.get(campo, 0) / total for campo, total in total_por_campo.items()
    }
    total_aciertos = sum(aciertos_por_campo.values())
    total_evaluado = sum(total_por_campo.values())

    resultado = {
        "n_casos": len(casos),
        "precision_global": total_aciertos / total_evaluado,
        "precision_por_campo": precision_por_campo,
        "total_por_campo": total_por_campo,
        "errores": errores,
    }
    RESULTADOS_PATH.write_text(json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8")
    return resultado


if __name__ == "__main__":
    r = evaluar()
    print(f"Precisión global: {r['precision_global']:.3f} ({r['n_casos']} casos)")
    for campo, p in sorted(r["precision_por_campo"].items()):
        print(f"  {campo:12} {p:.3f}  ({r['total_por_campo'][campo]} evaluados)")
    if r["errores"]:
        print(f"\nErrores ({len(r['errores'])}):")
        for e in r["errores"]:
            print(f"  - \"{e['texto']}\" [{e['campo']}] esperado={e['esperado']!r} obtenido={e['obtenido']!r}")

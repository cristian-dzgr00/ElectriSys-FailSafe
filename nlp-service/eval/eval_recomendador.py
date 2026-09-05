"""Evaluación de precisión@k del motor de recomendación (holdout_recomendador.json).

A diferencia de eval_intent/eval_ner, este SÍ necesita el backend PHP
levantado y accesible (BACKEND_URL) con el catálogo semilla cargado
(database/seed_vehiculos.sql) — mide la cadena real NER -> búsqueda de
candidatos -> ranking TF-IDF/coseno, no solo el ranking en aislado, porque
"el repuesto correcto" depende de qué candidatos existen realmente en la
base de datos.

Uso: python -m eval.eval_recomendador
(requiere BACKEND_URL apuntando a un backend con datos, y opcionalmente
JWT_SECRET/BACKEND_SERVICE_TOKEN para autenticarse — ver app/config.py)
"""
import json
from pathlib import Path

from app.ner import dictionary
from app.ner.extractor import extraer_entidades
from app.recommender.client_backend import BackendNoDisponibleError, buscar_compatibles
from app.recommender.tfidf_cosine import SimilitudTfidfCoseno

BASE_DIR = Path(__file__).resolve().parent
HOLDOUT_PATH = BASE_DIR / "holdout_recomendador.json"
RESULTADOS_PATH = BASE_DIR / "resultados_recomendador.json"

_estrategia = SimilitudTfidfCoseno()


def _codigos(candidatos: list[dict]) -> list[str]:
    return [c.get("codigo") for c in candidatos]


def evaluar() -> dict:
    casos = json.loads(HOLDOUT_PATH.read_text(encoding="utf-8"))
    dictionary.invalidar_cache()

    detalle = []
    acierto_top1 = acierto_top3 = 0

    for caso in casos:
        texto = caso["texto"]
        correctos = set(caso["codigos_correctos"])
        entidades = extraer_entidades(
            texto,
            marcas_conocidas=dictionary.obtener_marcas(),
            modelos_conocidos=dictionary.obtener_modelos(),
            categorias_conocidas=dictionary.obtener_categorias(),
        )

        try:
            candidatos = buscar_compatibles(
                marca=entidades["marca"], modelo=entidades["modelo"],
                anio=entidades.get("anio"), motor=entidades.get("motor"),
                combustible=entidades.get("combustible"), categoria=entidades.get("categoria"),
            )
        except BackendNoDisponibleError as e:
            detalle.append({"texto": texto, "error": f"backend no disponible: {e}"})
            continue

        disponibles = [c for c in candidatos if c.get("stock", 0) > 0]
        rankeados = _estrategia.rankear(texto, disponibles)
        codigos_rankeados = _codigos(rankeados)

        top1_ok = len(codigos_rankeados) >= 1 and codigos_rankeados[0] in correctos
        top3_ok = any(c in correctos for c in codigos_rankeados[:3])
        acierto_top1 += int(top1_ok)
        acierto_top3 += int(top3_ok)

        detalle.append({
            "texto": texto,
            "entidades_extraidas": entidades,
            "codigos_correctos": list(correctos),
            "codigos_rankeados": codigos_rankeados,
            "top1_ok": top1_ok,
            "top3_ok": top3_ok,
        })

    n = len(casos)
    resultado = {
        "n_casos": n,
        "precision_top1": acierto_top1 / n,
        "precision_top3": acierto_top3 / n,
        "detalle": detalle,
    }
    RESULTADOS_PATH.write_text(json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8")
    return resultado


if __name__ == "__main__":
    r = evaluar()
    print(f"Precisión@1: {r['precision_top1']:.3f}")
    print(f"Precisión@3: {r['precision_top3']:.3f}")
    for d in r["detalle"]:
        if "error" in d:
            print(f"  ! \"{d['texto']}\" -> {d['error']}")
        else:
            marca_ok = "OK" if d["top1_ok"] else ("top3" if d["top3_ok"] else "FALLO")
            print(f"  [{marca_ok}] \"{d['texto'][:50]}\" -> {d['codigos_rankeados'][:3]} (correctos: {d['codigos_correctos']})")

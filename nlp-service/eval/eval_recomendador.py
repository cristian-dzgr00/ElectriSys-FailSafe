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

Sin backend: python -m eval.eval_recomendador --offline
Usa el catálogo de eval/datos_demo (emulación de buscar-compatibles, como
medir_baseline.py) y evalúa los DOS conjuntos de desarrollo: holdout_recomendador.json
(6 casos, el original) y dev_recomendador.json (36 casos con respuestas por regla).
Es el modo con que se regenera resultados_recomendador.json de forma reproducible.
"""
import argparse
import json
from pathlib import Path

from app.ner import dictionary
from app.ner.extractor import extraer_entidades
from app.recommender.client_backend import BackendNoDisponibleError, buscar_compatibles
from app.recommender.tfidf_cosine import SimilitudTfidfCoseno

BASE_DIR = Path(__file__).resolve().parent
HOLDOUT_PATH = BASE_DIR / "holdout_recomendador.json"
DEV_PATH = BASE_DIR / "dev_recomendador.json"
RESULTADOS_PATH = BASE_DIR / "resultados_recomendador.json"

_estrategia = SimilitudTfidfCoseno()


def _codigos(candidatos: list[dict]) -> list[str]:
    return [c.get("codigo") for c in candidatos]


def _evaluar_offline_conjunto(cat, vocab, ruta: Path) -> dict:
    """Cadena NER -> candidatos (filtro por categoría y respaldo por categoría) -> ranking, sin backend."""
    from eval import medir_baseline as mb

    casos = json.loads(ruta.read_text(encoding="utf-8"))
    detalle, top1, top3, sin_vehiculo = [], 0, 0, 0
    for caso in casos:
        correctos = set(caso["codigos_correctos"])
        ent = extraer_entidades(caso["texto"], **vocab)
        codigos: list[str] = []
        if ent.get("marca") and ent.get("modelo"):
            cand = mb.candidatos_compatibles(cat, ent["marca"], ent["modelo"], ent.get("anio"), ent.get("motor"),
                                             ent.get("combustible"), ent.get("categoria"))
            if not cand and ent.get("categoria"):
                cand = [dict(r) for r in cat["repuestos"].values()
                        if mb.comparable(r["categoria"]) == mb.comparable(ent["categoria"]) and r["activo"]]
            codigos = _codigos(_estrategia.rankear(caso["texto"], [c for c in cand if c["stock"] > 0]))
        else:
            sin_vehiculo += 1
        ok1 = bool(codigos) and codigos[0] in correctos
        ok3 = any(c in correctos for c in codigos[:3])
        top1, top3 = top1 + int(ok1), top3 + int(ok3)
        detalle.append({"texto": caso["texto"], "entidades_extraidas": {k: ent.get(k) for k in ("marca", "modelo", "anio", "categoria")},
                        "codigos_correctos": sorted(correctos), "codigos_rankeados": codigos[:5], "top1_ok": ok1, "top3_ok": ok3})
    n = len(casos)
    return {"n_casos": n, "precision_top1": top1 / n, "precision_top3": top3 / n,
            "casos_sin_marca_o_modelo": sin_vehiculo, "detalle": detalle}


def evaluar_offline() -> dict:
    from eval import medir_baseline as mb

    cat = mb.cargar_catalogo()
    vocab = mb.vocab_ner(cat, con_marca_de_modelo=True)
    conjuntos = {
        "holdout_recomendador.json (desarrollo, 6 casos)": _evaluar_offline_conjunto(cat, vocab, HOLDOUT_PATH),
        "dev_recomendador.json (desarrollo, respuestas por regla)": _evaluar_offline_conjunto(cat, vocab, DEV_PATH),
    }
    resultado = {
        "modo": "offline: catálogo de eval/datos_demo (sin backend), conjuntos de DESARROLLO",
        "nota": "Reemplaza los resultados del 2026-09-05 contra Oracle, que además no discriminaban (<= 3 candidatos). "
                "Las cifras con conjuntos congelados están en resultados_despues.json.",
        "conjuntos": conjuntos,
    }
    RESULTADOS_PATH.write_text(json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8")
    return resultado


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
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="usar eval/datos_demo en vez del backend")
    if ap.parse_args().offline:
        for nombre, c in evaluar_offline()["conjuntos"].items():
            print(f"{nombre}: n={c['n_casos']}  P@1={c['precision_top1']:.3f}  P@3(hit)={c['precision_top3']:.3f}  "
                  f"sin marca/modelo={c['casos_sin_marca_o_modelo']}")
        raise SystemExit(0)
    r = evaluar()
    print(f"Precisión@1: {r['precision_top1']:.3f}")
    print(f"Precisión@3: {r['precision_top3']:.3f}")
    for d in r["detalle"]:
        if "error" in d:
            print(f"  ! \"{d['texto']}\" -> {d['error']}")
        else:
            marca_ok = "OK" if d["top1_ok"] else ("top3" if d["top3_ok"] else "FALLO")
            print(f"  [{marca_ok}] \"{d['texto'][:50]}\" -> {d['codigos_rankeados'][:3]} (correctos: {d['codigos_correctos']})")

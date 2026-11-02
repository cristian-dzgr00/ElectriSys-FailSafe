"""Mide la línea base "antes de mejoras" del asistente NLP sobre los holdouts v2.

Evalúa, con el código y el modelo ACTUALES, los cuatro conjuntos congelados:
  - holdout_intent_v2.csv         -> clasificador de intención
  - holdout_ner_v2.json           -> NER híbrido, campo por campo
  - holdout_recomendador_v2.json  -> ranking TF-IDF + coseno de sustitutos
  - holdout_errores_v2.csv        -> resolución de errores de digitación

y escribe eval/baseline_antes.json. No modifica el modelo, los datasets ni los
holdouts: solo lee, y al final verifica que los SHA-256 no cambiaron. Es
determinista (semillas fijas, sin fechas ni tiempos en el resultado).

Decisiones de diseño (ver también la sección "notas" del JSON de salida):
  * El modelo de intención se carga de models/intent_classifier.pkl igual que
    lo hace el servicio; si no existe, se entrena EN MEMORIA (sin escribir).
  * No hay backend: el vocabulario del NER (marcas, modelos, categorías) y los
    candidatos del recomendador salen de los CSV de eval/datos_demo/. El filtro
    de candidatos es una emulación de /api/repuestos/buscar-compatibles
    (marca, modelo, año dentro de [ANIO_DESDE, ANIO_HASTA], stock > 0).

Uso (desde nlp-service/):  python eval/medir_baseline.py

Con ``--salida eval/resultados_despues.json`` se mide el estado ACTUAL del código
sobre los mismos conjuntos y se escribe en otro archivo (la medición "después de
mejoras"). Esa variante además le pasa al NER la tabla modelo -> marca del
catálogo (para inferir la marca cuando el texto nombra un modelo único) y numera
la ejecución, porque los conjuntos congelados no deben usarse más de lo necesario.
SIN ``--salida`` el comportamiento es el de siempre y reescribe baseline_antes.json:
no se debe volver a correr así (el "antes" ya está medido y congelado).
"""
import argparse
import csv
import hashlib
import json
import math
import platform
import sys
from collections import Counter, defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import joblib  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import sklearn  # noqa: E402
from sklearn.metrics import (  # noqa: E402
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
)

from app.intent.classifier import UMBRAL_CONFIANZA, predecir_intencion  # noqa: E402
from app.intent.train import DATASET_PATH, MODEL_PATH, _construir_pipeline  # noqa: E402
from app.ner.extractor import TABLA_ERRORES_PATH, extraer_entidades  # noqa: E402
from app.preprocessing import normalizar  # noqa: E402
from app.recommender.tfidf_cosine import SimilitudTfidfCoseno  # noqa: E402

EVAL = RAIZ / "eval"
DATOS_DEMO = EVAL / "datos_demo"
HOLDOUTS = {
    "intent": EVAL / "holdout_intent_v2.csv",
    "ner": EVAL / "holdout_ner_v2.json",
    "recomendador": EVAL / "holdout_recomendador_v2.json",
    "errores": EVAL / "holdout_errores_v2.csv",
}
SALIDA = EVAL / "baseline_antes.json"

SEMILLA = 20260102
REMUESTREOS = 1000
Z95 = 1.959963984540054
CAMPOS_NER = ["marca", "modelo", "categoria", "anio", "motor", "combustible", "codigo"]
# En holdout_intent_v2.csv las primeras 18 frases de fuera_de_dominio son ajenas
# al negocio y las 16 restantes son preguntas de negocio sin intención soportada.
N_FUERA_AJENO = 18


# ---------------------------------------------------------------- utilidades
def sha256(ruta: Path) -> str:
    return hashlib.sha256(Path(ruta).read_bytes()).hexdigest()


def wilson(aciertos: int, n: int) -> dict:
    """Intervalo de Wilson al 95 % para una proporción."""
    if n == 0:
        return {"n": 0, "correctos": 0, "exactitud": None, "ic95": [None, None]}
    p = aciertos / n
    denom = 1 + Z95**2 / n
    centro = (p + Z95**2 / (2 * n)) / denom
    mitad = Z95 * math.sqrt(p * (1 - p) / n + Z95**2 / (4 * n * n)) / denom
    return {
        "n": n,
        "correctos": aciertos,
        "exactitud": round(p, 4),
        "ic95": [round(max(0.0, centro - mitad), 4), round(min(1.0, centro + mitad), 4)],
    }


def ic_bootstrap(valores, semilla: int = SEMILLA) -> dict:
    """Media e IC95 percentil por bootstrap de una métrica por caso."""
    v = np.asarray(valores, dtype=float)
    rng = np.random.default_rng(semilla)
    idx = rng.integers(0, len(v), size=(REMUESTREOS, len(v)))
    medias = v[idx].mean(axis=1)
    return {
        "n": int(len(v)),
        "media": round(float(v.mean()), 4),
        "ic95": [round(float(np.percentile(medias, 2.5)), 4), round(float(np.percentile(medias, 97.5)), 4)],
    }


def comparable(valor):
    """Normaliza un valor de entidad para compararlo (texto sin tildes/espacios)."""
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        return int(valor)
    return normalizar(str(valor)).replace(" ", "")


def leer_csv(ruta: Path) -> list[dict]:
    with open(ruta, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------- catálogo
def cargar_catalogo() -> dict:
    repuestos = leer_csv(DATOS_DEMO / "repuestos.csv")
    compat = leer_csv(DATOS_DEMO / "compatibilidad.csv")
    por_id = {
        r["ID"]: {
            "id": int(r["ID"]), "codigo": r["CODIGO"], "nombre": r["NOMBRE"],
            "descripcion": r["DESCRIPCION"], "categoria": r["CATEGORIA"],
            "stock": int(r["STOCK"]), "activo": r["ACTIVO"] == "1",
        }
        for r in repuestos
    }
    marcas = sorted({c["MARCA"] for c in compat})
    modelos = sorted({c["MODELO"] for c in compat})
    categorias = sorted({r["CATEGORIA"] for r in repuestos})
    marca_de_modelo = {}
    marcas_de_modelo: dict[str, list[str]] = {}
    for c in compat:
        marca_de_modelo.setdefault(c["MODELO"], c["MARCA"])
        if c["MARCA"] not in marcas_de_modelo.setdefault(c["MODELO"], []):
            marcas_de_modelo[c["MODELO"]].append(c["MARCA"])
    return {
        "repuestos": por_id, "compat": compat, "marcas": marcas, "modelos": modelos,
        "categorias": categorias, "marca_de_modelo": marca_de_modelo,
        "marcas_de_modelo": marcas_de_modelo,
    }


def vocab_ner(cat: dict, con_marca_de_modelo: bool = False) -> dict:
    vocab = {
        "marcas_conocidas": cat["marcas"],
        "modelos_conocidos": cat["modelos"],
        "categorias_conocidas": cat["categorias"],
    }
    if con_marca_de_modelo:
        vocab["marca_de_modelo"] = cat["marcas_de_modelo"]
    return vocab


def candidatos_compatibles(cat: dict, marca, modelo, anio=None, motor=None, combustible=None, categoria=None):
    """Emulación offline de /api/repuestos/buscar-compatibles (sin filtrar stock)."""
    vistos, salida = set(), []
    for c in cat["compat"]:
        if comparable(c["MARCA"]) != comparable(marca) or comparable(c["MODELO"]) != comparable(modelo):
            continue
        if anio and not (int(c["ANIO_DESDE"]) <= int(anio) <= int(c["ANIO_HASTA"])):
            continue
        if motor and comparable(c["MOTOR"]) != comparable(motor):
            continue
        if combustible and comparable(c["COMBUSTIBLE"]) != comparable(combustible):
            continue
        r = cat["repuestos"][c["REPUESTO_ID"]]
        if not r["activo"] or r["id"] in vistos:
            continue
        if categoria and comparable(r["categoria"]) != comparable(categoria):
            continue
        vistos.add(r["id"])
        salida.append(dict(r))
    return sorted(salida, key=lambda x: x["id"])


# ---------------------------------------------------------------- intención
def cargar_modelo_intencion() -> tuple[object, dict]:
    df = pd.read_csv(DATASET_PATH)
    info = {"dataset_entrenamiento": str(DATASET_PATH.relative_to(RAIZ)).replace("\\", "/"),
            "dataset_sha256": sha256(DATASET_PATH), "n_entrenamiento": int(len(df))}
    reentrenado = _construir_pipeline().fit(df["texto"], df["intencion"])
    if Path(MODEL_PATH).exists():
        info.update({"origen": "cargado de models/intent_classifier.pkl (igual que el servicio)",
                     "modelo_sha256": sha256(MODEL_PATH)})
        return joblib.load(MODEL_PATH), info | {"_reentrenado": reentrenado}
    info.update({"origen": "entrenado en memoria con el dataset actual (no existía el .pkl)", "modelo_sha256": None})
    return reentrenado, info | {"_reentrenado": reentrenado}


def medir_intencion(ruta: Path | None = None) -> dict:
    pipeline, info = cargar_modelo_intencion()
    reentrenado = info.pop("_reentrenado")
    df = pd.read_csv(ruta or HOLDOUTS["intent"])
    etiquetas = sorted(set(pd.read_csv(DATASET_PATH)["intencion"]) | set(df["intencion"]))

    y_true = df["intencion"].to_numpy()
    preds, confs, crudas = [], [], []
    for texto in df["texto"]:
        intencion, conf = predecir_intencion(texto, pipeline=pipeline)
        preds.append(intencion)
        confs.append(conf)
        crudas.append(pipeline.classes_[int(np.argmax(pipeline.predict_proba([texto])[0]))])
    y_pred = np.array(preds)
    reent = np.array([predecir_intencion(t, pipeline=reentrenado)[0] for t in df["texto"]])

    p, r, f, soporte = precision_recall_fscore_support(y_true, y_pred, labels=etiquetas, zero_division=0)
    por_clase = {
        e: {"precision": round(float(p[i]), 4), "recall": round(float(r[i]), 4),
            "f1": round(float(f[i]), 4), "soporte": int(soporte[i])}
        for i, e in enumerate(etiquetas)
    }
    matriz = confusion_matrix(y_true, y_pred, labels=etiquetas)

    rng = np.random.default_rng(SEMILLA)
    idx = rng.integers(0, len(df), size=(REMUESTREOS, len(df)))
    accs = np.empty(REMUESTREOS)
    f1s = np.empty(REMUESTREOS)
    for b in range(REMUESTREOS):
        yt, yp = y_true[idx[b]], y_pred[idx[b]]
        accs[b] = (yt == yp).mean()
        f1s[b] = f1_score(yt, yp, labels=etiquetas, average="macro", zero_division=0)
    acc = float(accuracy_score(y_true, y_pred))
    f1m = float(f1_score(y_true, y_pred, labels=etiquetas, average="macro", zero_division=0))

    errores = [
        {"texto": t, "esperado": e, "predicho": pr, "confianza": round(float(c), 4),
         "por_umbral": bool(pr == "fuera_de_dominio" and cr != "fuera_de_dominio"), "clase_sin_umbral": str(cr)}
        for t, e, pr, c, cr in zip(df["texto"], y_true, y_pred, confs, crudas) if e != pr
    ]
    fuera = [i for i, e in enumerate(y_true) if e == "fuera_de_dominio"]
    fuera_ajeno, fuera_negocio = fuera[:N_FUERA_AJENO], fuera[N_FUERA_AJENO:]
    correctos = y_true == y_pred
    return {
        "n": int(len(df)),
        "modelo": info,
        "umbral_confianza": UMBRAL_CONFIANZA,
        "accuracy": round(acc, 4),
        "accuracy_ic95_bootstrap": [round(float(np.percentile(accs, 2.5)), 4), round(float(np.percentile(accs, 97.5)), 4)],
        "f1_macro": round(f1m, 4),
        "f1_macro_ic95_bootstrap": [round(float(np.percentile(f1s, 2.5)), 4), round(float(np.percentile(f1s, 97.5)), 4)],
        "bootstrap": {"remuestreos": REMUESTREOS, "semilla": SEMILLA, "tipo": "percentil, remuestreo de frases"},
        "por_clase": por_clase,
        "matriz_confusion": {"etiquetas": etiquetas, "filas": "esperado", "columnas": "predicho",
                             "matriz": matriz.tolist()},
        "fuera_de_dominio_por_subgrupo": {
            "ajeno_al_negocio": wilson(int(correctos[fuera_ajeno].sum()), len(fuera_ajeno)),
            "negocio_sin_intencion_soportada": wilson(int(correctos[fuera_negocio].sum()), len(fuera_negocio)),
        },
        "confianza_media": {"aciertos": round(float(np.mean([c for c, ok in zip(confs, correctos) if ok])), 4),
                            "errores": round(float(np.mean([c for c, ok in zip(confs, correctos) if not ok])), 4)
                            if (~correctos).any() else None},
        "errores_por_umbral": int(sum(1 for e in errores if e["por_umbral"])),
        "concordancia_pkl_vs_reentrenado_en_memoria": round(float((y_pred == reent).mean()), 4),
        "errores": errores,
    }


# ---------------------------------------------------------------- NER
def medir_ner(cat: dict, ruta: Path | None = None, vocab: dict | None = None) -> dict:
    casos = json.loads((ruta or HOLDOUTS["ner"]).read_text(encoding="utf-8"))
    vocab = vocab or vocab_ner(cat)
    contadores = {c: {"ok": 0, "n": 0, "pos_ok": 0, "pos_n": 0, "neg_ok": 0, "neg_n": 0} for c in CAMPOS_NER}
    por_grupo = defaultdict(lambda: {"campos_ok": 0, "campos_n": 0, "casos_exactos": 0, "casos": 0})
    errores = []
    for caso in casos:
        ent = extraer_entidades(caso["texto"], **vocab)
        todo_ok = True
        g = por_grupo[caso.get("grupo", "sin_grupo")]
        for campo in CAMPOS_NER:
            esperado = caso["esperado"].get(campo)
            obtenido = ent.get(campo)
            ok = comparable(esperado) == comparable(obtenido)
            c = contadores[campo]
            c["n"] += 1
            c["ok"] += int(ok)
            if esperado is None:
                c["neg_n"] += 1
                c["neg_ok"] += int(ok)
            else:
                c["pos_n"] += 1
                c["pos_ok"] += int(ok)
            g["campos_n"] += 1
            g["campos_ok"] += int(ok)
            if not ok:
                todo_ok = False
                errores.append({"texto": caso["texto"], "grupo": caso.get("grupo"), "campo": campo,
                                "esperado": esperado, "obtenido": obtenido})
        g["casos"] += 1
        g["casos_exactos"] += int(todo_ok)

    por_campo = {}
    for campo, c in contadores.items():
        entrada = wilson(c["ok"], c["n"]) | {"campo": campo}
        entrada["evaluados"] = entrada.pop("n")
        entrada["con_valor_esperado"] = wilson(c["pos_ok"], c["pos_n"])
        entrada["sin_valor_esperado_(falsos_positivos_=_n-correctos)"] = wilson(c["neg_ok"], c["neg_n"])
        por_campo[campo] = entrada
    total_ok = sum(c["ok"] for c in contadores.values())
    total_n = sum(c["n"] for c in contadores.values())
    return {
        "n_casos": len(casos),
        "vocabulario": {"marcas": len(cat["marcas"]), "modelos": len(cat["modelos"]), "categorias": len(cat["categorias"])},
        "tabla_errores": str(Path(TABLA_ERRORES_PATH).name),
        "exactitud_global_campos": wilson(total_ok, total_n),
        "por_campo": por_campo,
        "por_grupo": {
            k: {**v, "exactitud_campos": round(v["campos_ok"] / v["campos_n"], 4),
                "exactitud_caso_completo": round(v["casos_exactos"] / v["casos"], 4)}
            for k, v in sorted(por_grupo.items())
        },
        "errores": errores,
    }


# ---------------------------------------------------------------- recomendador
def _metricas_ranking(rankeados: list[str], relevantes: set[str]) -> dict:
    top3 = rankeados[:3]
    rr = 0.0
    for i, c in enumerate(rankeados, start=1):
        if c in relevantes:
            rr = 1.0 / i
            break
    return {
        "p1": float(bool(rankeados) and rankeados[0] in relevantes),
        "p3": (sum(1 for c in top3 if c in relevantes) / 3.0),
        "p3_norm": (sum(1 for c in top3 if c in relevantes) / max(1, min(3, len(relevantes)))),
        "hit3": float(any(c in relevantes for c in top3)),
        "mrr": rr,
    }


def _azar(n_cand: int, n_rel: int) -> dict:
    """Esperanza de P@1 y hit@3 de un orden aleatorio (referencia mínima)."""
    hit3 = 1.0 - (math.comb(n_cand - n_rel, 3) / math.comb(n_cand, 3) if n_cand >= 3 else 0.0)
    return {"p1": n_rel / n_cand, "hit3": hit3}


def medir_recomendador(cat: dict, ruta: Path | None = None, vocab: dict | None = None) -> dict:
    casos = json.loads((ruta or HOLDOUTS["recomendador"]).read_text(encoding="utf-8"))
    estrategia = SimilitudTfidfCoseno()
    vocab = vocab or vocab_ner(cat)
    modos = {"solo_ranking": [], "pipeline_completo": []}
    detalle = {"solo_ranking": [], "pipeline_completo": []}
    azar = []
    con_vehiculo = []
    for caso in casos:
        relevantes = set(caso["codigos_correctos"])
        # Modo 1: candidatos = todos los compatibles con stock del vehículo pedido
        # (sin filtro de categoría) -> mide únicamente el ranking TF-IDF + coseno.
        cand = [c for c in candidatos_compatibles(cat, caso["marca"], caso["modelo"], caso["anio"]) if c["stock"] > 0]
        rank = [c["codigo"] for c in estrategia.rankear(caso["texto"], cand)]
        modos["solo_ranking"].append(_metricas_ranking(rank, relevantes))
        azar.append(_azar(len(cand), len(relevantes)))
        detalle["solo_ranking"].append({"texto": caso["texto"], "correctos": sorted(relevantes),
                                        "top3": rank[:3], "n_candidatos": len(cand)})
        # Modo 2: cadena real NER -> candidatos (con filtro de categoría) -> ranking.
        ent = extraer_entidades(caso["texto"], **vocab)
        rank2: list[str] = []
        con_vehiculo.append(bool(ent.get("marca") and ent.get("modelo")))
        if ent.get("marca") and ent.get("modelo"):
            cand2 = candidatos_compatibles(cat, ent["marca"], ent["modelo"], ent.get("anio"), ent.get("motor"),
                                           ent.get("combustible"), ent.get("categoria"))
            if not cand2 and ent.get("categoria"):  # fallback de pipeline._buscar_candidatos_por_vehiculo
                cand2 = [dict(r) for r in cat["repuestos"].values()
                         if comparable(r["categoria"]) == comparable(ent["categoria"]) and r["activo"]]
            cand2 = [c for c in cand2 if c["stock"] > 0]
            rank2 = [c["codigo"] for c in estrategia.rankear(caso["texto"], cand2)]
        modos["pipeline_completo"].append(_metricas_ranking(rank2, relevantes))
        detalle["pipeline_completo"].append({"texto": caso["texto"], "entidades": {k: ent.get(k) for k in ("marca", "modelo", "anio", "categoria")},
                                             "correctos": sorted(relevantes), "top3": rank2[:3]})

    def resumen(lista):
        return {m: ic_bootstrap([x[m] for x in lista]) for m in ("p1", "p3", "p3_norm", "hit3", "mrr")}

    n_cand = [c["n_candidatos"] for c in casos]
    fallos = {k: [d for d, m in zip(detalle[k], modos[k]) if m["p1"] == 0.0] for k in detalle}
    return {
        "n_casos": len(casos),
        "regla": casos[0].get("regla"),
        "candidatos_por_caso": {"min": min(n_cand), "media": round(float(np.mean(n_cand)), 2), "max": max(n_cand)},
        "correctos_por_caso_media": round(float(np.mean([len(c["codigos_correctos"]) for c in casos])), 2),
        "definiciones": {
            "p1": "el primer lugar es un sustituto correcto",
            "p3": "fracción de los 3 primeros que son correctos",
            "p3_norm": "correctos en el top-3 / min(3, nº de correctos del caso)",
            "hit3": "al menos un correcto en el top-3",
            "mrr": "1/posición del primer correcto en la lista completa (0 si no hay)",
        },
        "solo_ranking": resumen(modos["solo_ranking"]),
        "pipeline_completo": resumen(modos["pipeline_completo"]),
        "pipeline_casos_sin_marca_o_modelo": {
            "n": con_vehiculo.count(False),
            "nota": "el pipeline exige marca y modelo para recomendar; sin ellos no devuelve sugerencias",
        },
        "pipeline_completo_solo_con_vehiculo_identificado": resumen(
            [m for m, ok in zip(modos["pipeline_completo"], con_vehiculo) if ok]
        ),
        "referencia_azar_solo_ranking": {"p1": round(float(np.mean([a["p1"] for a in azar])), 4),
                                         "hit3": round(float(np.mean([a["hit3"] for a in azar])), 4)},
        "fallos_p1_solo_ranking": fallos["solo_ranking"],
        "fallos_p1_pipeline_completo": fallos["pipeline_completo"],
    }


# ---------------------------------------------------------------- errores de digitación
def medir_errores(cat: dict, ruta: Path | None = None, vocab: dict | None = None) -> dict:
    filas = leer_csv(ruta or HOLDOUTS["errores"])
    vocab = vocab or vocab_ner(cat)
    marca_de = cat["marca_de_modelo"]
    marcos = {
        "marca": ["tienen repuestos para {x}", "busco algo para el {x} 2019"],
        "modelo": ["tienen repuestos para {x}", "busco algo para {marca} {x} 2019"],
        "categoria": ["tienen {x}", "necesito {x} para un carro 2019"],
    }

    def resolver(tipo, valor, correcto, i_marco):
        marco = marcos[tipo][i_marco]
        texto = marco.format(x=valor, marca=marca_de.get(correcto, "").lower())
        return extraer_entidades(texto, **vocab).get(tipo)

    grupos = defaultdict(lambda: [0, 0])  # clave -> [ok, n]
    fallos = []
    for fila in filas:
        tipo, error, correcto, en_tabla = fila["tipo"], fila["error"], fila["correcto"], fila["en_tabla"]
        for i_marco in (0, 1):
            ok = comparable(resolver(tipo, error, correcto, i_marco)) == comparable(correcto)
            for clave in ("global", f"en_tabla={en_tabla}", f"tipo={tipo}", f"tipo={tipo}|en_tabla={en_tabla}",
                          f"marco{i_marco + 1}"):
                grupos[clave][0] += int(ok)
                grupos[clave][1] += 1
            if not ok:
                fallos.append({"tipo": tipo, "error": error, "correcto": correcto, "en_tabla": int(en_tabla),
                               "marco": i_marco + 1, "obtenido": resolver(tipo, error, correcto, i_marco)})
    # Control: los nombres canónicos escritos bien deben resolverse (sanidad del vocabulario).
    control = []
    for tipo, correcto in sorted({(f["tipo"], f["correcto"]) for f in filas}):
        ok = comparable(resolver(tipo, correcto.lower(), correcto, 0)) == comparable(correcto)
        control.append((tipo, correcto, ok))
    return {
        "n_errores": len(filas),
        "n_evaluaciones": len(filas) * 2,
        "marcos_de_frase": marcos,
        "pct_en_tabla_0": round(sum(1 for f in filas if f["en_tabla"] == "0") / len(filas), 4),
        "exactitud": {k: wilson(*v) for k, v in sorted(grupos.items())},
        "control_nombre_correcto": {"resueltos": sum(1 for _, _, ok in control if ok), "total": len(control),
                                    "no_resueltos": [f"{t}:{c}" for t, c, ok in control if not ok]},
        "fallos": fallos,
    }


# ---------------------------------------------------------------- principal
def _numero_de_ejecucion(salida: Path) -> int:
    """Cuántas veces se midieron los congelados "después": 1 + lo registrado en el archivo previo."""
    try:
        previo = json.loads(Path(salida).read_text(encoding="utf-8"))
        return int(previo.get("numero_de_ejecucion", 0)) + 1
    except (OSError, ValueError):
        return 1


def main(salida: Path | None = None) -> dict:
    """Mide los cuatro congelados. `salida=None`: modo "antes" (reescribe baseline_antes.json);
    con ruta: modo "después" (vocabulario con tabla modelo -> marca y ejecución numerada)."""
    despues = salida is not None
    salida = Path(salida) if despues else SALIDA
    protegidos = [*HOLDOUTS.values(), DATASET_PATH, Path(TABLA_ERRORES_PATH)]
    if Path(MODEL_PATH).exists():
        protegidos.append(Path(MODEL_PATH))
    antes = {str(p): sha256(p) for p in protegidos}

    cat = cargar_catalogo()
    vocab = vocab_ner(cat, con_marca_de_modelo=despues)
    resultado = {
        "descripcion": ("Medición DESPUÉS de las mejoras, con el código y el modelo vigentes, sobre los mismos holdouts v2 congelados."
                        if despues else
                        "Línea base ANTES de mejoras, medida con el código y el modelo actuales sobre los holdouts v2 congelados."),
        "entorno": {"python": platform.python_version(), "scikit_learn": sklearn.__version__,
                    "numpy": np.__version__, "pandas": pd.__version__},
        "notas": [
            "Sin backend: vocabulario del NER y candidatos del recomendador salen de eval/datos_demo/ (emulación aproximada de buscar-compatibles).",
            "NER: anotación cerrada de 7 campos por caso; null esperado = el campo no debe extraerse (mide falsos positivos).",
            "Recomendador: solo_ranking aísla el ranking TF-IDF+coseno; pipeline_completo incluye NER y filtro por categoría.",
            "Empates de similitud se resuelven por el orden de entrada de los candidatos (ID de repuesto ascendente).",
            "Errores de digitación: cada error se evalúa en dos frases (marcos_de_frase); las exactitudes cuentan evaluaciones, no errores únicos.",
        ] + (["Modo después: el NER recibe además la tabla modelo -> marca del catálogo (inferencia de marca por modelo único)."]
             if despues else []),
        "holdouts_sha256": {k: sha256(v) for k, v in HOLDOUTS.items()},
        "catalogo": {"origen": "eval/datos_demo (repuestos.csv, compatibilidad.csv)", "marcas": len(cat["marcas"]),
                     "modelos": len(cat["modelos"]), "categorias": len(cat["categorias"]),
                     "repuestos": len(cat["repuestos"])},
        "intencion": medir_intencion(),
        "ner": medir_ner(cat, vocab=vocab),
        "recomendador": medir_recomendador(cat, vocab=vocab),
        "errores_digitacion": medir_errores(cat, vocab=vocab),
    }
    if despues:
        resultado["numero_de_ejecucion"] = _numero_de_ejecucion(salida)
        resultado["huellas_del_estado_medido"] = huellas_estado()
    despues_h = {str(p): sha256(p) for p in protegidos}
    resultado["integridad"] = {"archivos_verificados": len(antes), "sin_modificaciones": antes == despues_h}
    salida.write_text(json.dumps(resultado, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return resultado


def huellas_estado() -> dict:
    """SHA-256 de lo que determina el resultado: permite saber si una medición sigue vigente."""
    # El .pkl no entra: está fuera de git y sale determinista del dataset y el código que sí entran.
    archivos = [DATASET_PATH, Path(TABLA_ERRORES_PATH),
                RAIZ / "app" / "ner" / "extractor.py", RAIZ / "app" / "preprocessing.py",
                RAIZ / "app" / "intent" / "classifier.py", RAIZ / "app" / "intent" / "modelos.py",
                RAIZ / "app" / "recommender" / "tfidf_cosine.py"]
    return {str(a.relative_to(RAIZ)).replace("\\", "/"): sha256(a) for a in archivos if a.exists()}


def imprimir(r: dict) -> None:
    i, n, rec, e = r["intencion"], r["ner"], r["recomendador"], r["errores_digitacion"]
    print(f"INTENCION  n={i['n']}  accuracy={i['accuracy']} IC95={i['accuracy_ic95_bootstrap']}  "
          f"F1 macro={i['f1_macro']} IC95={i['f1_macro_ic95_bootstrap']}")
    for clase, m in i["por_clase"].items():
        print(f"   {clase:26} P={m['precision']:.3f} R={m['recall']:.3f} F1={m['f1']:.3f} n={m['soporte']}")
    print(f"NER  n={n['n_casos']}  global={n['exactitud_global_campos']['exactitud']}")
    for campo, m in n["por_campo"].items():
        print(f"   {campo:12} {m['correctos']}/{m['evaluados']} = {m['exactitud']} IC95={m['ic95']}")
    print(f"RECOMENDADOR  n={rec['n_casos']}")
    print("   pipeline sin marca/modelo:", rec["pipeline_casos_sin_marca_o_modelo"]["n"])
    for modo in ("solo_ranking", "pipeline_completo", "pipeline_completo_solo_con_vehiculo_identificado"):
        print("   " + modo, {k: (v["media"], v["ic95"]) for k, v in rec[modo].items()})
    print("   azar (solo_ranking)", rec["referencia_azar_solo_ranking"])
    print(f"ERRORES  n={e['n_errores']}  global={e['exactitud']['global']['exactitud']}  "
          f"en_tabla=1: {e['exactitud'].get('en_tabla=1', {}).get('exactitud')}  "
          f"en_tabla=0: {e['exactitud'].get('en_tabla=0', {}).get('exactitud')}")
    print("integridad:", r["integridad"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--salida", type=Path, default=None,
                    help="medición 'después': archivo de salida (p. ej. eval/resultados_despues.json). "
                         "Sin esta opción se reescribe baseline_antes.json (no usar).")
    imprimir(main(ap.parse_args().salida))

"""UNA sola fuente de cifras del asistente NLP: escribe eval/cifras_vigentes.json.

    python eval/generar_cifras.py                  # determinista, sin red
    python eval/generar_cifras.py --medir-tiempos  # además mide tiempos (dependen de la máquina)
    python eval/generar_cifras.py --regenerar-resultados  # además deja al día los resultados_*.json de desarrollo

Qué calcula (todo con semillas fijas, sin fechas ni red):
  * tamaños del dataset y de la tabla de errores, y la línea base de la clase mayoritaria;
  * validación cruzada normal (5 partes x 10 repeticiones) y AGRUPADA de los 13 candidatos de
    app/intent/modelos.py, con diferencias pareadas frente a la configuración previa;
  * la decisión del modelo y del marcador <vehiculo> (reglas explícitas, ver seleccion.py) y los
    pesos del modelo antes y después del marcador;
  * el barrido del umbral de confianza y el umbral elegido;
  * los criterios C1..C8 de docs/CRISP-ML.md con su valor medido;
  * la medición "después" sobre los conjuntos congelados (la lee de eval/resultados_despues.json, que
    escribe `python eval/medir_baseline.py --salida eval/resultados_despues.json`; AQUÍ NO se vuelven a
    evaluar los congelados: se comprueba con huellas SHA-256 que esa medición sigue vigente) y su
    comparación con baseline_antes.json usando SOLO métricas agregadas.

Los tiempos (entrenamiento, latencia p95) no son deterministas. Se miden con --medir-tiempos y se
guardan en la sección "tiempos"; sin esa opción se conserva la que ya tiene el archivo, de modo que
dos corridas seguidas dan exactamente el mismo JSON.

Para no repetir el cálculo pesado (el perceptrón tarda varios minutos) los resultados de la validación
cruzada se guardan en una carpeta temporal indexada por el SHA-256 del dataset y del código que los
produce; --sin-cache los recalcula todos (el resultado es idéntico).
"""
import argparse
import csv
import hashlib
import json
import pickle
import platform
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import sklearn  # noqa: E402
from sklearn.metrics import accuracy_score, f1_score  # noqa: E402

from app import preprocessing  # noqa: E402
from app.intent import classifier, modelos, seleccion as S  # noqa: E402
from app.intent.train import DATASET_PATH, MODEL_PATH, _construir_pipeline  # noqa: E402
from app.ner import extractor  # noqa: E402
from app.preprocessing import normalizar  # noqa: E402
from eval import medir_baseline as mb  # noqa: E402

EVAL = RAIZ / "eval"
SALIDA = EVAL / "cifras_vigentes.json"
ANTES = EVAL / "baseline_antes.json"
DESPUES = EVAL / "resultados_despues.json"
TABLA_ERRORES = Path(extractor.TABLA_ERRORES_PATH)
UMBRALES = [round(0.20 + 0.05 * i, 2) for i in range(11)]  # 0.20 ... 0.70
FILAS_ORIGINALES = 374  # las primeras filas del dataset, anteriores a la ampliación
VERSION_ESQUEMA = 1


# ---------------------------------------------------------------- utilidades
def r4(x):
    return None if x is None else round(float(x), 4)


def sha(ruta: Path) -> str:
    return hashlib.sha256(Path(ruta).read_bytes()).hexdigest()


def huella_codigo() -> str:
    """Hash de lo que determina los resultados de la validación cruzada (para el caché)."""
    h = hashlib.sha256()
    for ruta in (DATASET_PATH, RAIZ / "app" / "intent" / "modelos.py", RAIZ / "app" / "intent" / "seleccion.py",
                 RAIZ / "app" / "preprocessing.py"):
        h.update(Path(ruta).read_bytes())
    h.update(sklearn.__version__.encode())
    h.update(np.__version__.encode())
    return h.hexdigest()[:20]


# ---------------------------------------------------------------- validación cruzada con caché
def correr_cv_cacheada(nombre, modo, X, y, pliegues, cache: Path | None, huella: str):
    ruta = cache / f"{huella}_{nombre}_{modo}.pkl" if cache else None
    if ruta is not None and ruta.exists():
        try:
            return pickle.loads(ruta.read_bytes())
        except Exception:  # caché corrupto: se recalcula
            pass
    t0 = time.time()
    corrida = S.correr_cv(nombre, X, y, pliegues)
    print(f"   CV {nombre:20} {modo:9} {time.time() - t0:6.0f} s", flush=True)
    if ruta is not None:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(pickle.dumps(corrida))
    return corrida


# ---------------------------------------------------------------- pesos del modelo
def pesos_del_modelo(nombre: str, X, y, k=15) -> dict:
    """Los k pesos de mayor valor absoluto por intención del modelo entrenado con todo el dataset.

    "Nombre de vehículo" = las palabras de preprocessing._VEHICULO_UNA_PALABRA (hilux, spark, toyota...).
    Con el marcador activado esas palabras ya no llegan al modelo: su lugar lo toma "<vehiculo>".
    """
    modelo = modelos.construir(nombre).fit(X, y)
    vocab = np.array(modelo["tfidf"].get_feature_names_out())
    indice = {str(t): j for j, t in enumerate(vocab)}
    coef = modelo["clf"].coef_
    clases = [str(c) for c in modelo["clf"].classes_]
    nombres = sorted(t for t in preprocessing._VEHICULO_UNA_PALABRA if t in indice)
    marcador = preprocessing.MARCADOR_VEHICULO
    por_intencion, resumen = {}, {}
    for i, clase in enumerate(clases):
        orden = np.argsort(-np.abs(coef[i]))[:k]
        top = [{"token": str(vocab[j]), "peso": r4(coef[i][j])} for j in orden]
        por_intencion[clase] = top
        resumen[clase] = {
            "nombres_de_vehiculo_en_el_top": sum(1 for t in top if t["token"] in preprocessing._VEHICULO_UNA_PALABRA),
            "marcador_en_el_top": any(t["token"] == marcador for t in top),
            "mayor_peso_abs_de_un_nombre_de_vehiculo": r4(max((abs(coef[i][indice[t]]) for t in nombres), default=0.0)),
        }
    mayor = max(((abs(coef[i][indice[t]]), clases[i], t) for i in range(len(clases)) for t in nombres), default=(0.0, "", ""))
    salida = {"modelo": nombre, "top15_por_intencion": por_intencion, "resumen_por_intencion": resumen,
              "mayor_peso_de_un_nombre_de_vehiculo": {"token": mayor[2], "intencion": mayor[1], "abs_peso": r4(mayor[0])},
              "nombres_de_vehiculo_en_el_vocabulario": len(nombres), "n_terminos": int(len(vocab)),
              "peso_de_hilux_por_intencion": ({c: r4(coef[i][indice["hilux"]]) for i, c in enumerate(clases)}
                                              if "hilux" in indice else None)}
    if marcador in indice:
        salida["peso_del_marcador_por_intencion"] = {c: r4(coef[i][indice[marcador]]) for i, c in enumerate(clases)}
    return salida


# ---------------------------------------------------------------- congelados
def agregados_intencion(i: dict) -> dict:
    return {"n": i["n"], "accuracy": i["accuracy"], "accuracy_ic95": i["accuracy_ic95_bootstrap"],
            "f1_macro": i["f1_macro"], "f1_macro_ic95": i["f1_macro_ic95_bootstrap"],
            "fuera_de_dominio_por_subgrupo": i["fuera_de_dominio_por_subgrupo"],
            "recall_recomendar_sustituto": i["por_clase"]["recomendar_sustituto"]["recall"]}


def agregados_ner(n: dict) -> dict:
    return {"n_casos": n["n_casos"], "exactitud_global_campos": n["exactitud_global_campos"],
            "por_campo": {c: {"correctos": m["correctos"], "evaluados": m["evaluados"], "exactitud": m["exactitud"],
                              "ic95_wilson": m["ic95"]} for c, m in n["por_campo"].items()}}


def agregados_recomendador(r: dict) -> dict:
    claves = ("solo_ranking", "pipeline_completo", "pipeline_completo_solo_con_vehiculo_identificado")
    return {"n_casos": r["n_casos"], "pipeline_casos_sin_marca_o_modelo": r["pipeline_casos_sin_marca_o_modelo"]["n"],
            **{k: {m: {"media": v["media"], "ic95_bootstrap": v["ic95"]} for m, v in r[k].items()} for k in claves}}


def agregados_errores(e: dict) -> dict:
    x = e["exactitud"]
    return {"n_errores": e["n_errores"], "n_evaluaciones": e["n_evaluaciones"], "pct_en_tabla_0": e["pct_en_tabla_0"],
            "exactitud": {k: {"correctos": v["correctos"], "n": v["n"], "exactitud": v["exactitud"], "ic95_wilson": v["ic95"]}
                          for k, v in x.items() if k in ("global", "en_tabla=0", "en_tabla=1", "tipo=marca", "tipo=modelo",
                                                         "tipo=categoria", "tipo=marca|en_tabla=0", "tipo=modelo|en_tabla=0",
                                                         "tipo=categoria|en_tabla=0")}}


def agregados(r: dict) -> dict:
    return {"intencion": agregados_intencion(r["intencion"]), "ner": agregados_ner(r["ner"]),
            "recomendador": agregados_recomendador(r["recomendador"]), "errores_digitacion": agregados_errores(r["errores_digitacion"])}


def diferencias(antes: dict, despues: dict) -> dict:
    """despues - antes de las métricas escalares agregadas (puntos de proporción, no de porcentaje)."""
    d = {"intencion": {"accuracy": r4(despues["intencion"]["accuracy"] - antes["intencion"]["accuracy"]),
                       "f1_macro": r4(despues["intencion"]["f1_macro"] - antes["intencion"]["f1_macro"])}}
    d["ner"] = {c: r4(despues["ner"]["por_campo"][c]["exactitud"] - antes["ner"]["por_campo"][c]["exactitud"])
                for c in antes["ner"]["por_campo"]}
    d["ner"]["global"] = r4(despues["ner"]["exactitud_global_campos"]["exactitud"] - antes["ner"]["exactitud_global_campos"]["exactitud"])
    d["recomendador"] = {modo: {m: r4(despues["recomendador"][modo][m]["media"] - antes["recomendador"][modo][m]["media"])
                                for m in ("p1", "p3", "mrr")}
                         for modo in ("solo_ranking", "pipeline_completo")}
    d["errores_digitacion"] = {k: r4(despues["errores_digitacion"]["exactitud"][k]["exactitud"] - antes["errores_digitacion"]["exactitud"][k]["exactitud"])
                               for k in ("global", "en_tabla=0", "en_tabla=1")}
    return d


def seccion_congelados() -> dict:
    """Medición 'después' y comparación con 'antes'. Lee archivos ya producidos; no evalúa."""
    if not DESPUES.exists():
        return {"estado": "pendiente",
                "como_generar": "python eval/medir_baseline.py --salida eval/resultados_despues.json (una sola vez, al final)"}
    despues = json.loads(DESPUES.read_text(encoding="utf-8"))
    huellas_actuales = mb.huellas_estado()
    huellas_medidas = despues.get("huellas_del_estado_medido", {})
    desactualizadas = sorted(k for k, v in huellas_medidas.items() if huellas_actuales.get(k) != v)
    sec = {
        "estado": "vigente" if not desactualizadas else "DESACTUALIZADA",
        "archivos_cambiados_desde_la_medicion": desactualizadas,
        "numero_de_ejecucion": despues.get("numero_de_ejecucion"),
        "integridad_de_los_congelados": despues["integridad"],
        "holdouts_sha256": despues["holdouts_sha256"],
        "despues": agregados(despues),
    }
    if ANTES.exists():
        antes = json.loads(ANTES.read_text(encoding="utf-8"))
        sec["antes"] = agregados(antes)
        sec["antes_vs_despues"] = diferencias(sec["antes"], sec["despues"])
        sec["holdouts_iguales_antes_y_despues"] = antes.get("holdouts_sha256") == despues["holdouts_sha256"]
    return sec


# ---------------------------------------------------------------- conjuntos de desarrollo
def seccion_dev(cat: dict, X, y) -> dict:
    """Todo sobre conjuntos de DESARROLLO (holdout_* viejos y dev_*): sirven para iterar, no para afirmar generalización."""
    vocab = mb.vocab_ner(cat, con_marca_de_modelo=True)
    pipeline = _construir_pipeline().fit(X, y)
    entrenadas = {normalizar(t) for t in X}

    viejo = pd.read_csv(EVAL / "holdout_intent.csv")
    limpio = viejo[~viejo["texto"].map(normalizar).isin(entrenadas)]
    def evaluar_intencion(df):
        pred = [classifier.predecir_intencion(t, pipeline=pipeline)[0] for t in df["texto"]]
        negocio = {"recomendar_sustituto", "buscar_repuesto", "consultar_stock", "consultar_precio", "consultar_compatibilidad"}
        esp = df["intencion"].to_numpy()
        pr = np.array(pred)
        fuera = esp == "fuera_de_dominio"
        sust = esp == "recomendar_sustituto"
        return {"n": int(len(df)), "accuracy": r4(accuracy_score(esp, pr)),
                "f1_macro": r4(f1_score(esp, pr, average="macro", zero_division=0)),
                "recall_recomendar_sustituto": {"n": int(sust.sum()), "valor": r4((pr[sust] == "recomendar_sustituto").mean()) if sust.any() else None},
                "fuera_de_dominio_tratado_como_negocio": {"n": int(fuera.sum()),
                                                          "valor": r4(np.isin(pr[fuera], list(negocio)).mean()) if fuera.any() else None}}
    ner_viejo = mb.medir_ner(cat, EVAL / "holdout_ner.json", vocab)
    ner_dev = mb.medir_ner(cat, EVAL / "dev_ner.json", vocab)
    rec_dev = mb.medir_recomendador(cat, EVAL / "dev_recomendador.json", vocab)
    err_dev = mb.medir_errores(cat, EVAL / "dev_errores.csv", vocab)
    return {
        "aviso": "Conjuntos de desarrollo: se usaron para iterar y las cifras de dev_* están saturadas; "
                 "la evidencia honesta son los congelados (seccion 'congelados').",
        "intencion_holdout_intent_csv": evaluar_intencion(viejo),
        "intencion_holdout_intent_csv_limpio_de_entrenamiento": evaluar_intencion(limpio),
        "ner_holdout_ner_json": agregados_ner(ner_viejo),
        "ner_dev_ner_json": {**agregados_ner(ner_dev),
                             "por_grupo": {g: v["exactitud_campos"] for g, v in ner_dev["por_grupo"].items()}},
        "recomendador_dev_recomendador_json": agregados_recomendador(rec_dev),
        "errores_dev_errores_csv": agregados_errores(err_dev),
    }


# ---------------------------------------------------------------- tabla de errores
def seccion_tabla_errores() -> dict:
    filas = list(csv.DictReader(TABLA_ERRORES.open(encoding="utf-8", newline="")))
    por_tipo = Counter(f["tipo"] for f in filas)
    por_nombre = Counter((f["tipo"], f["correcto"]) for f in filas)
    cuentas = sorted(por_nombre.values())
    return {"archivo": "data/errores/posibles_errores.csv", "sha256": sha(TABLA_ERRORES), "filas": len(filas),
            "por_tipo": dict(por_tipo), "nombres_distintos": len(por_nombre),
            "variantes_por_nombre": {"min": cuentas[0], "mediana": int(np.median(cuentas)), "max": cuentas[-1]},
            "por_nivel": dict(Counter(f["nivel"] for f in filas)),
            "nota": "Una forma escrita así que NO esté en la tabla se resuelve con los respaldos del extractor "
                    "(fuzzy, fonético, similitud, nombres cortos y palabra distintiva): su exactitud se mide por separado "
                    "(en_tabla=0) en los congelados y en dev_errores.csv."}


# ---------------------------------------------------------------- tiempos
def medir_todos_los_tiempos(X, y, cat) -> dict:
    frases = list(X[::10])
    por_modelo = {n: S.medir_tiempos(n, X, y, frases) for n in modelos.CANDIDATOS}
    # Intención + NER por consulta (criterio C7): modelo de producción y extractor con la tabla real.
    pipeline = _construir_pipeline().fit(X, y)
    vocab = mb.vocab_ner(cat, con_marca_de_modelo=True)
    textos = frases + [c["texto"] for c in json.loads((EVAL / "dev_ner.json").read_text(encoding="utf-8"))]
    extractor.extraer_entidades(textos[0], **vocab)  # carga la tabla de errores
    ms = []
    for _ in range(3):
        for t in textos:
            t0 = time.perf_counter()
            classifier.predecir_intencion(t, pipeline=pipeline)
            extractor.extraer_entidades(t, **vocab)
            ms.append((time.perf_counter() - t0) * 1000.0)
    ms = np.array(ms[len(textos):])
    return {
        "aviso": "Depende de la máquina; se mide con --medir-tiempos. Entrenamiento: mediana de 3 ajustes con todo el dataset. "
                 "Predicción: una frase a la vez.",
        "entorno": {"python": platform.python_version(), "scikit_learn": sklearn.__version__, "sistema": platform.platform(),
                    "cpus": __import__("os").cpu_count()},
        "por_modelo": por_modelo,
        "intencion_mas_ner_por_consulta_ms": {"p50": r4(np.percentile(ms, 50)), "p95": r4(np.percentile(ms, 95)),
                                              "p99": r4(np.percentile(ms, 99)), "n": int(len(ms)),
                                              "incluye": "predecir_intencion + extraer_entidades con la tabla de errores completa; sin backend"},
    }


# ---------------------------------------------------------------- criterios
def criterios(prod: dict, umbral: float, dev: dict, cong: dict, tiempos: dict | None, baseline: dict) -> dict:
    """C1..C8 de docs/CRISP-ML.md (sección 'Criterios de éxito')."""
    n = prod["normal"]["con_umbral"]
    g = prod["agrupada"]["con_umbral"]
    sn = prod["normal"]["sin_umbral"]
    c = {}

    def estado(ok):
        return "cumple" if ok else "NO cumple"

    # C1: F1 macro en validación cruzada >= 0.80
    c["C1"] = {"definicion": "F1 macro en validación cruzada >= 0.80", "meta": 0.80,
               "medido": {"normal_sin_umbral": sn["f1_macro"]["media"], "normal_con_umbral": n["f1_macro"]["media"],
                          "agrupada_con_umbral": g["f1_macro"]["media"]},
               "estado": estado(min(sn["f1_macro"]["media"], n["f1_macro"]["media"], g["f1_macro"]["media"]) >= 0.80)}
    # C2: accuracy en un holdout limpio >= 0.80 (dev limpio y congelado v2)
    dev_limpio = dev["intencion_holdout_intent_csv_limpio_de_entrenamiento"]
    medido2 = {"dev_holdout_intent_csv_limpio": dev_limpio["accuracy"]}
    ok2 = dev_limpio["accuracy"] >= 0.80
    if "despues" in cong:
        medido2["congelado_v2"] = cong["despues"]["intencion"]["accuracy"]
        medido2["congelado_v2_ic95"] = cong["despues"]["intencion"]["accuracy_ic95"]
        ok2 = ok2 and medido2["congelado_v2"] >= 0.80
    c["C2"] = {"definicion": "Accuracy en holdout limpio >= 0.80 (el dev tiene pocas frases; el congelado v2 es la evidencia fuerte)",
               "meta": 0.80, "medido": medido2, "estado": estado(ok2)}
    # C3: recall de recomendar_sustituto en CV >= 0.90
    r3 = {"normal": n["recall_recomendar_sustituto"]["media"], "agrupada": g["recall_recomendar_sustituto"]["media"],
          "dev_holdout_intent_csv": dev["intencion_holdout_intent_csv"]["recall_recomendar_sustituto"]["valor"]}
    c["C3"] = {"definicion": "Recall de recomendar_sustituto (validación cruzada, con el umbral de producción) >= 0.90", "meta": 0.90,
               "umbral_usado": umbral, "medido": r3, "estado": estado(min(r3["normal"], r3["agrupada"]) >= 0.90)}
    # C4: fuera de dominio tratado como negocio <= 15 %
    r4_ = {"normal": n["fuera_tratado_como_negocio"]["media"], "agrupada": g["fuera_tratado_como_negocio"]["media"],
           "normal_no_reconocida_como_fuera": n["fuera_tratado_como_no_fuera"]["media"],
           "agrupada_no_reconocida_como_fuera": g["fuera_tratado_como_no_fuera"]["media"],
           "dev_holdout_intent_csv": dev["intencion_holdout_intent_csv"]["fuera_de_dominio_tratado_como_negocio"]["valor"]}
    c["C4"] = {"definicion": "Frases fuera de dominio tratadas como una de las 5 intenciones de negocio (validación cruzada) <= 15 %",
               "meta": 0.15, "umbral_usado": umbral, "medido": r4_,
               "nota": "'no_reconocida_como_fuera' cuenta además las enviadas a saludo_despedida: es la lectura más estricta.",
               "estado": estado(max(r4_["normal"], r4_["agrupada"]) <= 0.15)}
    # C5: precisión global del NER >= 0.90
    m5 = {"dev_holdout_ner_json_12_casos": dev["ner_holdout_ner_json"]["exactitud_global_campos"]["exactitud"],
          "dev_ner_json_122_casos": dev["ner_dev_ner_json"]["exactitud_global_campos"]["exactitud"]}
    ok5 = min(m5.values()) >= 0.90
    if "despues" in cong:
        m5["congelado_v2"] = cong["despues"]["ner"]["exactitud_global_campos"]["exactitud"]
        m5["congelado_v2_ic95"] = cong["despues"]["ner"]["exactitud_global_campos"]["ic95"]
        ok5 = ok5 and m5["congelado_v2"] >= 0.90
    c["C5"] = {"definicion": "Exactitud global del NER (campo por campo) >= 0.90", "meta": 0.90, "medido": m5, "estado": estado(ok5)}
    # C6: precisión@3 del recomendador >= 0.80 (acierto si hay un correcto entre los 3 primeros)
    pr = dev["recomendador_dev_recomendador_json"]["pipeline_completo"]
    m6 = {"dev_recomendador_json_pipeline_p3_norm": pr["p3_norm"]["media"], "dev_recomendador_json_pipeline_hit3": pr["hit3"]["media"],
          "dev_recomendador_json_pipeline_p1": pr["p1"]["media"]}
    ok6 = m6["dev_recomendador_json_pipeline_p3_norm"] >= 0.80
    if "despues" in cong:
        pc = cong["despues"]["recomendador"]["pipeline_completo"]
        m6["congelado_v2_pipeline_p3_norm"] = pc["p3_norm"]["media"]
        m6["congelado_v2_pipeline_p3_norm_ic95"] = pc["p3_norm"]["ic95_bootstrap"]
        m6["congelado_v2_pipeline_hit3"] = pc["hit3"]["media"]
        m6["congelado_v2_pipeline_p1"] = pc["p1"]["media"]
        ok6 = ok6 and m6["congelado_v2_pipeline_p3_norm"] >= 0.80
    c["C6"] = {"definicion": "Precisión@3 del recomendador >= 0.80 (p3_norm = correctos en el top-3 / min(3, nº de correctos))",
               "meta": 0.80, "medido": m6, "estado": estado(ok6)}
    # C7: latencia p95 intención + NER < 100 ms
    if tiempos:
        p95 = tiempos["intencion_mas_ner_por_consulta_ms"]["p95"]
        c["C7"] = {"definicion": "Latencia p95 de intención + NER < 100 ms (sin contar el backend)", "meta_ms": 100,
                   "medido": {"p95_ms": p95}, "estado": estado(p95 < 100)}
    else:
        c["C7"] = {"definicion": "Latencia p95 de intención + NER < 100 ms", "meta_ms": 100, "medido": None,
                   "estado": "sin medir (correr con --medir-tiempos)"}
    # C8: ventaja sobre la línea base de la clase mayoritaria >= 50 puntos de F1 macro
    ventaja = sn["f1_macro"]["media"] - baseline["f1_macro"]
    c["C8"] = {"definicion": "Ventaja de F1 macro sobre la línea base de la clase mayoritaria >= 0.50", "meta": 0.50,
               "medido": {"f1_modelo": sn["f1_macro"]["media"], "f1_linea_base": baseline["f1_macro"], "ventaja": r4(ventaja)},
               "estado": estado(ventaja >= 0.50)}
    return c


# ---------------------------------------------------------------- principal
def construir_cifras(args) -> dict:
    df = pd.read_csv(DATASET_PATH)
    X, y = df["texto"].to_numpy(dtype=object), df["intencion"].to_numpy(dtype=object)
    cat = mb.cargar_catalogo()
    grupos = S.grupos_casi_duplicados(X)
    tam_grupos = Counter(grupos.tolist())
    cache = None if args.sin_cache else Path(args.cache_dir)
    huella = huella_codigo()

    pliegues = {"normal": S.generar_pliegues("normal", y), "agrupada": S.generar_pliegues("agrupada", y, grupos)}
    n_prueba = int(np.mean([len(te) for _, _, _, te in pliegues["normal"]]))
    n_entrena = int(np.mean([len(tr) for _, _, tr, _ in pliegues["normal"]]))

    print(">> validación cruzada de los candidatos", flush=True)
    corridas = {(n, m): correr_cv_cacheada(n, m, X, y, pliegues[m], cache, huella) for n in modelos.CANDIDATOS for m in S.MODOS}

    # --- tabla de comparación (M2)
    referencia = modelos.NOMBRE_REFERENCIA
    tiempos_prev = None
    if SALIDA.exists():
        try:
            tiempos_prev = json.loads(SALIDA.read_text(encoding="utf-8")).get("tiempos")
        except (OSError, ValueError):
            tiempos_prev = None
    tiempos = tiempos_prev
    if args.medir_tiempos:
        print(">> midiendo tiempos", flush=True)
        tiempos = medir_todos_los_tiempos(X, y, cat)

    filas, tabla_decision = [], {}
    for nombre, (descripcion, familia, _) in modelos.CANDIDATOS.items():
        fila = {"modelo": nombre, "descripcion": descripcion, "familia": familia,
                "tiene_probabilidades": corridas[(nombre, "normal")]["proba"] is not None}
        tabla_decision[nombre] = {"tiene_probabilidades": fila["tiene_probabilidades"]}
        for modo in S.MODOS:
            c = corridas[(nombre, modo)]
            cmp_ = S.comparar_pareado(c, corridas[(referencia, modo)], "f1_macro", n_prueba, n_entrena)
            cmp_acc = S.comparar_pareado(c, corridas[(referencia, modo)], "accuracy", n_prueba, n_entrena)
            fila[modo] = {"por_pliegue": S.resumen_pliegues(c), "vs_referencia_f1_macro": cmp_, "vs_referencia_accuracy": cmp_acc}
            tabla_decision[nombre][modo] = {"vs_referencia": cmp_}
        if tiempos and nombre in tiempos.get("por_modelo", {}):
            t = tiempos["por_modelo"][nombre]
            fila["entrenamiento_s"] = t["entrenamiento_s_mediana"]
            fila["prediccion_ms_p95"] = t["prediccion_ms_p95"]
        else:
            fila["entrenamiento_s"] = fila["prediccion_ms_p95"] = None
        filas.append(fila)

    # --- decisión del modelo (sin la variante con marcador: eso es otra pregunta, M3)
    candidatos_modelo = {k: v for k, v in tabla_decision.items() if k != "lr_c15_vehiculo"}
    decision_modelo = S.elegir_modelo(candidatos_modelo, referencia)
    familia_elegida = decision_modelo["elegido"]

    # --- marcador <vehiculo> (M3): se adopta si NO es peor que sin marcador (no inferioridad) en ambas validaciones
    con_marcador = f"{familia_elegida}_vehiculo" if f"{familia_elegida}_vehiculo" in modelos.CANDIDATOS else None
    decision_marcador = {"adoptado": False, "razon": "no hay variante con marcador para el modelo elegido"}
    if con_marcador:
        difs = {m: S.comparar_pareado(corridas[(con_marcador, m)], corridas[(familia_elegida, m)], "f1_macro", n_prueba, n_entrena)
                for m in S.MODOS}
        no_peor = all(d["diferencia_media"] >= -0.005 for d in difs.values())
        decision_marcador = {
            "regla": "se adopta si la diferencia media de F1 macro (con - sin marcador) es >= -0.005 en la validación normal y en la agrupada",
            "adoptado": bool(no_peor), "comparaciones": difs,
            "lectura": "mejora en ambas validaciones" if all(d["diferencia_media"] > 0 and d["p_corregido"] < 0.05 for d in difs.values())
            else "sin diferencia clara",
        }
    produccion = con_marcador if decision_marcador["adoptado"] else familia_elegida

    # --- modelo de producción: métricas, barrido de umbral y umbral elegido
    cprod = {m: corridas[(produccion, m)] for m in S.MODOS}
    eleccion = S.elegir_umbral(cprod, UMBRALES)
    umbral = eleccion["umbral_elegido"]
    prod = {}
    for m in S.MODOS:
        prod[m] = {"sin_umbral": S.resumen_oof(cprod[m], None), "con_umbral": S.resumen_oof(cprod[m], umbral),
                   "recall_por_clase_con_umbral": S.recall_por_clase(cprod[m], umbral)}
        prod[m]["con_umbral_actual_del_codigo"] = S.resumen_oof(cprod[m], classifier.UMBRAL_CONFIANZA)

    # --- línea base de la clase mayoritaria
    mayoritaria = Counter(y.tolist()).most_common(1)[0][0]
    constante = np.array([mayoritaria] * len(y))
    linea_base = {"clase": mayoritaria, "accuracy": r4(accuracy_score(y, constante)),
                  "f1_macro": r4(f1_score(y, constante, average="macro", zero_division=0))}

    # --- pesos antes / después del marcador (M3)
    print(">> pesos del modelo", flush=True)
    pesos = {"sin_marcador": pesos_del_modelo(familia_elegida, X, y)}
    if con_marcador:
        pesos["con_marcador"] = pesos_del_modelo(con_marcador, X, y)

    print(">> conjuntos de desarrollo", flush=True)
    dev = seccion_dev(cat, X, y)
    cong = seccion_congelados()

    por_intencion = Counter(y.tolist())
    originales = Counter(y[:FILAS_ORIGINALES].tolist())
    cifras = {
        "esquema": VERSION_ESQUEMA,
        "descripcion": "Única fuente de cifras del asistente NLP. Se genera con `python eval/generar_cifras.py`.",
        "entorno": {"python": platform.python_version(), "scikit_learn": sklearn.__version__, "numpy": np.__version__,
                    "pandas": pd.__version__},
        "dataset": {
            "archivo": "data/intents_dataset.csv", "sha256": sha(DATASET_PATH), "n": int(len(df)),
            "n_originales": FILAS_ORIGINALES, "n_ampliacion": int(len(df) - FILAS_ORIGINALES),
            "por_intencion": {k: int(v) for k, v in sorted(por_intencion.items())},
            "por_intencion_originales": {k: int(v) for k, v in sorted(originales.items())},
            "grupos_casi_duplicados": {"n_grupos": int(len(tam_grupos)), "grupo_mas_grande": int(max(tam_grupos.values())),
                                       "definicion": "componentes conexas de frases con el mismo esqueleto (primeras 2 palabras "
                                                     "normalizadas) o el mismo multiconjunto de palabras"},
        },
        "tabla_errores": seccion_tabla_errores(),
        "validacion_cruzada": {"repeticiones": S.REPETICIONES, "partes": S.PARTES, "semilla_base": S.SEMILLA_PLIEGUES,
                               "pliegues_por_validacion": S.REPETICIONES * S.PARTES,
                               "frases_de_prueba_por_pliegue": n_prueba, "frases_de_entrenamiento_por_pliegue": n_entrena,
                               "nota": "sd = desviación estándar entre los 50 pliegues. Diferencias pareadas sobre los MISMOS "
                                       "pliegues; p_corregido usa la corrección de Nadeau-Bengio (guía aproximada)."},
        "linea_base_clase_mayoritaria": linea_base,
        "comparacion_modelos": {"referencia": referencia, "filas": filas,
                                "decision_modelo": {**decision_modelo,
                                                    "criterio": f"un candidato reemplaza a '{referencia}' solo si en la validación normal Y en la agrupada "
                                                                f"mejora el F1 macro en >= {S.UMBRAL_MEJORA_F1}, gana en >= {int(S.MIN_FRACCION_PLIEGUES * 100)} % "
                                                                f"de los pliegues y la prueba t corregida da p < {S.ALFA}; además debe entregar probabilidades"},
                                "decision_marcador_vehiculo": decision_marcador},
        "modelo_produccion": {"nombre": produccion, "descripcion": modelos.CANDIDATOS[produccion][0],
                              "nombre_en_el_codigo": modelos.NOMBRE_PRODUCCION,
                              "coincide_con_el_codigo": produccion == modelos.NOMBRE_PRODUCCION,
                              "umbral_elegido": umbral, "umbral_en_el_codigo": classifier.UMBRAL_CONFIANZA,
                              "umbral_coincide_con_el_codigo": umbral == classifier.UMBRAL_CONFIANZA,
                              **prod},
        "umbral_de_confianza": {"rejilla": UMBRALES, "regla": eleccion["regla"], "elegido": umbral,
                                "barrido": eleccion["barridos"]},
        "sesgo_por_nombres_de_vehiculo": pesos,
        "dev": dev,
        "congelados": cong,
        "tiempos": tiempos,
    }
    cifras["criterios"] = criterios(prod, umbral, dev, cong, tiempos, linea_base)
    cifras["resumen_criterios"] = {k: v["estado"] for k, v in cifras["criterios"].items()}
    return cifras


def regenerar_resultados() -> None:
    """Deja los resultados_*.json de eval/ consistentes con el modelo y el código vigentes (conjuntos de desarrollo)."""
    from eval import eval_intent, eval_ner, eval_ner_rapidfuzz, eval_recomendador

    print(">> regenerando resultados_*.json", flush=True)
    eval_intent.evaluar()
    eval_ner.evaluar()
    eval_recomendador.evaluar_offline()
    eval_ner_rapidfuzz.evaluar()


def main() -> None:
    ap = argparse.ArgumentParser(description="Genera eval/cifras_vigentes.json")
    ap.add_argument("--medir-tiempos", action="store_true", help="mide entrenamiento y latencia (no determinista)")
    ap.add_argument("--sin-cache", action="store_true", help="recalcula toda la validación cruzada")
    ap.add_argument("--cache-dir", default=str(Path(tempfile.gettempdir()) / "electrisys_cv_cache"))
    ap.add_argument("--regenerar-resultados", action="store_true",
                    help="además regenera eval/resultados_{intent,ner,recomendador,ner_rapidfuzz}.json (tarda varios minutos)")
    ap.add_argument("--salida", type=Path, default=SALIDA)
    args = ap.parse_args()
    t0 = time.time()
    cifras = construir_cifras(args)
    args.salida.write_text(json.dumps(cifras, indent=2, ensure_ascii=False, sort_keys=False) + "\n", encoding="utf-8", newline="\n")
    if args.regenerar_resultados:
        regenerar_resultados()
    print(f">> escrito {args.salida} en {time.time() - t0:.0f} s")
    for k, v in cifras["resumen_criterios"].items():
        print(f"   {k}: {v}")
    print(f"   modelo: {cifras['modelo_produccion']['nombre']}  umbral: {cifras['modelo_produccion']['umbral_elegido']}")


if __name__ == "__main__":
    main()

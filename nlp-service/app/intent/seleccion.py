"""Selección del modelo de intención por validación cruzada.

Compara los candidatos de `modelos.py` con los MISMOS pliegues:

  * validación cruzada estratificada de 5 partes repetida 10 veces (semillas fijas);
  * validación cruzada AGRUPADA (misma cantidad de partes y repeticiones): las
    frases casi iguales van siempre juntas en el mismo pliegue, así que un modelo
    que solo memoriza plantillas ya no se ve favorecido. Dos frases pertenecen al
    mismo grupo si comparten el esqueleto (primeras dos palabras normalizadas) o
    el mismo multiconjunto de palabras; los grupos son las componentes conexas.

Todo es determinista (semillas fijas, sin fechas ni tiempos en los resultados
de exactitud). Los tiempos de entrenamiento y de predicción se miden aparte
(`medir_tiempos`) porque dependen de la máquina.
"""
import time

import numpy as np
from joblib import Parallel, delayed
from scipy import stats
from threadpoolctl import threadpool_limits
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import StratifiedGroupKFold, StratifiedKFold

from app.intent.modelos import NOMBRE_REFERENCIA, construir
from app.preprocessing import normalizar

REPETICIONES = 10
PARTES = 5
SEMILLA_PLIEGUES = 20260102
INTENCION_FALLBACK = "fuera_de_dominio"
INTENCION_SUSTITUTO = "recomendar_sustituto"
INTENCIONES_NEGOCIO = (
    "recomendar_sustituto", "buscar_repuesto", "consultar_stock",
    "consultar_precio", "consultar_compatibilidad",
)
MODOS = ("normal", "agrupada")


# ---------------------------------------------------------------- grupos
def grupos_casi_duplicados(textos) -> np.ndarray:
    """Un id de grupo por frase (componentes conexas por esqueleto o multiconjunto)."""
    normalizados = [normalizar(t) for t in textos]
    padre = list(range(len(normalizados)))

    def raiz(x):
        while padre[x] != x:
            padre[x] = padre[padre[x]]
            x = padre[x]
        return x

    def unir(claves):
        primera: dict[str, int] = {}
        for i, clave in enumerate(claves):
            if clave in primera:
                a, b = raiz(i), raiz(primera[clave])
                if a != b:
                    padre[a] = b
            else:
                primera[clave] = i

    unir([" ".join(t.split()[:2]) for t in normalizados])
    unir([" ".join(sorted(t.split())) for t in normalizados])
    raices = [raiz(i) for i in range(len(normalizados))]
    ids = {r: n for n, r in enumerate(dict.fromkeys(raices))}
    return np.array([ids[r] for r in raices])


# ---------------------------------------------------------------- pliegues
def generar_pliegues(modo: str, y, grupos=None, repeticiones=REPETICIONES, partes=PARTES):
    """Lista de (repeticion, parte, indices_entrenamiento, indices_prueba)."""
    y = np.asarray(y)
    X_falso = np.zeros(len(y))
    pliegues = []
    for rep in range(repeticiones):
        semilla = SEMILLA_PLIEGUES + rep
        if modo == "normal":
            separador = StratifiedKFold(partes, shuffle=True, random_state=semilla).split(X_falso, y)
        elif modo == "agrupada":
            separador = StratifiedGroupKFold(partes, shuffle=True, random_state=semilla).split(X_falso, y, grupos)
        else:
            raise ValueError(modo)
        for parte, (tr, te) in enumerate(separador):
            pliegues.append((rep, parte, tr, te))
    return pliegues


# ---------------------------------------------------------------- una corrida
def _un_pliegue(nombre, textos, y_idx, rep, parte, tr, te):
    # Un hilo de BLAS por proceso: con varios procesos en paralelo, hilos de más compiten
    # entre sí y el perceptrón multicapa tarda ~3 veces más sin ganar nada.
    with threadpool_limits(limits=1):
        modelo = construir(nombre)
        t0 = time.perf_counter()
        modelo.fit(textos[tr], y_idx[tr])
        segundos = time.perf_counter() - t0
        if hasattr(modelo, "predict_proba"):
            proba = modelo.predict_proba(textos[te])
            pred = proba.argmax(axis=1)
        else:
            proba = None
            pred = modelo.predict(textos[te])
    return rep, parte, te, pred, proba, segundos


def correr_cv(nombre, textos, y, pliegues, n_jobs=-1) -> dict:
    """Entrena `nombre` en cada pliegue y junta las predicciones fuera de muestra."""
    textos = np.asarray(textos, dtype=object)
    clases = np.array(sorted(set(y)))
    y_idx = np.searchsorted(clases, np.asarray(y))
    resultados = Parallel(n_jobs=n_jobs)(
        delayed(_un_pliegue)(nombre, textos, y_idx, rep, parte, tr, te) for rep, parte, tr, te in pliegues
    )
    n, reps = len(y_idx), max(r[0] for r in resultados) + 1
    pred = np.zeros((reps, n), dtype=int)
    tiene_proba = resultados[0][4] is not None
    proba = np.zeros((reps, n, len(clases))) if tiene_proba else None
    por_pliegue = []
    for rep, parte, te, p, pr, segundos in resultados:
        pred[rep, te] = p
        if tiene_proba:
            proba[rep, te] = pr
        por_pliegue.append({
            "rep": rep, "parte": parte,
            "accuracy": float(accuracy_score(y_idx[te], p)),
            "f1_macro": float(f1_score(y_idx[te], p, average="macro", labels=range(len(clases)), zero_division=0)),
            "segundos_fit": segundos,
        })
    return {"clases": clases, "y_idx": y_idx, "pred": pred, "proba": proba, "por_pliegue": por_pliegue}


# ---------------------------------------------------------------- métricas
def predecir_con_umbral(proba: np.ndarray, clases, umbral: float) -> np.ndarray:
    """Igual que `classifier.predecir_intencion`: confianza baja -> fuera_de_dominio."""
    clases = list(clases)
    idx = proba.argmax(axis=-1)
    fallback = clases.index(INTENCION_FALLBACK)
    return np.where(proba.max(axis=-1) < umbral, fallback, idx)


def metricas_de_prediccion(y_idx, pred, clases) -> dict:
    clases = list(clases)
    sustituto, fuera = clases.index(INTENCION_SUSTITUTO), clases.index(INTENCION_FALLBACK)
    negocio = [clases.index(c) for c in INTENCIONES_NEGOCIO]
    es_sust, es_fuera = y_idx == sustituto, y_idx == fuera
    return {
        "accuracy": float(accuracy_score(y_idx, pred)),
        "f1_macro": float(f1_score(y_idx, pred, average="macro", labels=range(len(clases)), zero_division=0)),
        "recall_recomendar_sustituto": float((pred[es_sust] == sustituto).mean()),
        # C4: frases fuera de dominio que NO se reconocieron como tales ...
        "fuera_tratado_como_no_fuera": float((pred[es_fuera] != fuera).mean()),
        # ... y, más estricto, las que se trataron como una de las 5 intenciones de negocio.
        "fuera_tratado_como_negocio": float(np.isin(pred[es_fuera], negocio).mean()),
    }


def resumen_oof(corrida: dict, umbral: float | None) -> dict:
    """Media y desviación entre repeticiones de las métricas fuera de muestra.

    umbral=None usa el argmax puro; con umbral aplica la regla del servicio
    (requiere probabilidades).
    """
    clases, y_idx = corrida["clases"], corrida["y_idx"]
    filas = []
    for rep in range(corrida["pred"].shape[0]):
        if umbral is None:
            pred = corrida["pred"][rep]
        else:
            pred = predecir_con_umbral(corrida["proba"][rep], clases, umbral)
        filas.append(metricas_de_prediccion(y_idx, pred, clases))
    salida = {}
    for k in filas[0]:
        v = np.array([f[k] for f in filas])
        salida[k] = {"media": round(float(v.mean()), 4), "sd": round(float(v.std(ddof=1)), 4)}
    return salida


def recall_por_clase(corrida: dict, umbral: float | None) -> dict:
    clases, y_idx = list(corrida["clases"]), corrida["y_idx"]
    acum = np.zeros(len(clases))
    reps = corrida["pred"].shape[0]
    for rep in range(reps):
        pred = (corrida["pred"][rep] if umbral is None
                else predecir_con_umbral(corrida["proba"][rep], clases, umbral))
        for i in range(len(clases)):
            acum[i] += (pred[y_idx == i] == i).mean()
    return {c: round(float(a / reps), 4) for c, a in zip(clases, acum)}


def resumen_pliegues(corrida: dict) -> dict:
    out = {}
    for k in ("accuracy", "f1_macro"):
        v = np.array([p[k] for p in corrida["por_pliegue"]])
        out[k] = {"media": round(float(v.mean()), 4), "sd": round(float(v.std(ddof=1)), 4), "n_pliegues": int(len(v))}
    return out


def comparar_pareado(corrida: dict, referencia: dict, metrica="f1_macro", n_prueba=None, n_entrena=None) -> dict:
    """Diferencia (candidato - referencia) pliegue a pliegue.

    Incluye la prueba t con la corrección de Nadeau y Bengio (los pliegues
    repetidos no son independientes): sin corrección el valor p sería
    demasiado optimista. Es una guía aproximada, no una prueba exacta.
    """
    a = np.array([p[metrica] for p in corrida["por_pliegue"]])
    b = np.array([p[metrica] for p in referencia["por_pliegue"]])
    d = a - b
    J = len(d)
    var = d.var(ddof=1)
    razon = (n_prueba / n_entrena) if n_prueba and n_entrena else 0.25
    se = np.sqrt((1.0 / J + razon) * var)
    t = float(d.mean() / se) if se > 0 else 0.0
    p = float(2 * stats.t.sf(abs(t), J - 1)) if se > 0 else 1.0
    return {
        "metrica": metrica,
        "diferencia_media": round(float(d.mean()), 4),
        "diferencia_sd": round(float(d.std(ddof=1)), 4),
        "gana_en": int((d > 0).sum()), "empata_en": int((d == 0).sum()), "pierde_en": int((d < 0).sum()),
        "n_pliegues": int(J),
        "t_corregido": round(t, 3), "p_corregido": round(p, 4),
    }


# ---------------------------------------------------------------- umbral
def barrido_umbral(corrida: dict, umbrales) -> list[dict]:
    filas = []
    for u in umbrales:
        r = resumen_oof(corrida, u)
        filas.append({"umbral": round(float(u), 3), **{k: v["media"] for k, v in r.items()}})
    return filas


def elegir_umbral(corridas: dict, umbrales, max_fuera_como_negocio=0.15) -> dict:
    """Umbral de confianza elegido SOLO con validación cruzada (nunca con un holdout).

    Regla: el menor umbral de la rejilla con el que el criterio C4 (fuera de dominio
    tratado como negocio <= `max_fuera_como_negocio`) se cumple en TODAS las
    validaciones dadas (normal y agrupada), porque subir el umbral cuesta F1 y recall
    de las intenciones de negocio. Si ninguno lo cumple, el que maximiza el F1 macro
    promedio. `corridas` es {modo: corrida} del modelo de producción.
    """
    barridos = {modo: barrido_umbral(c, umbrales) for modo, c in corridas.items()}
    # Se compara con el valor exacto (no redondeado) para no declarar cumplido 0.1501.
    exactos = {modo: [resumen_oof(c, u)["fuera_tratado_como_negocio"]["media"] for u in umbrales]
               for modo, c in corridas.items()}
    cumplen = [u for i, u in enumerate(umbrales) if all(exactos[m][i] <= max_fuera_como_negocio for m in corridas)]
    if cumplen:
        elegido, regla = min(cumplen), "menor umbral que cumple C4 en la validación normal y en la agrupada"
    else:
        f1 = [np.mean([barridos[m][i]["f1_macro"] for m in corridas]) for i in range(len(umbrales))]
        elegido, regla = float(umbrales[int(np.argmax(f1))]), "ninguno cumple C4: el de mayor F1 macro promedio"
    return {"umbral_elegido": round(float(elegido), 3), "regla": regla,
            "max_fuera_como_negocio": max_fuera_como_negocio, "barridos": barridos}


# ---------------------------------------------------------------- decisión
UMBRAL_MEJORA_F1 = 0.010
MIN_FRACCION_PLIEGUES = 0.70
ALFA = 0.05


def elegir_modelo(tabla: dict, referencia=NOMBRE_REFERENCIA, exigir_probabilidades=True) -> dict:
    """Regla de selección: el más simple, salvo que otro gane CLARA y CONSISTENTEMENTE.

    `tabla[nombre][modo]["vs_referencia"]` es la salida de `comparar_pareado`.
    "Clara y consistentemente mejor" = en AMBAS validaciones (normal y agrupada)
    la mejora media de F1 macro es >= 0.010, gana en >= 70 % de los pliegues y la
    prueba t corregida da p < 0.05. Si varios cumplen, gana el de mayor mejora
    mínima entre las dos validaciones.
    """
    razones = {}
    elegibles = []
    for nombre, modos in tabla.items():
        if nombre == referencia:
            continue
        if exigir_probabilidades and not modos.get("tiene_probabilidades", True):
            razones[nombre] = "no entrega probabilidades (el umbral de confianza las necesita)"
            continue
        cumple, mejoras = True, []
        for modo in MODOS:
            c = modos[modo]["vs_referencia"]
            frac = c["gana_en"] / c["n_pliegues"]
            ok = c["diferencia_media"] >= UMBRAL_MEJORA_F1 and frac >= MIN_FRACCION_PLIEGUES and c["p_corregido"] < ALFA
            mejoras.append(c["diferencia_media"])
            if not ok:
                cumple = False
                razones[nombre] = (
                    f"{modo}: dif={c['diferencia_media']:+.4f}, gana {c['gana_en']}/{c['n_pliegues']}, "
                    f"p={c['p_corregido']:.3f} (no es clara y consistentemente mejor)"
                )
                break
        if cumple:
            elegibles.append((min(mejoras), nombre))
    if elegibles:
        elegido = max(elegibles)[1]
        return {"elegido": elegido, "regla_aplicada": "otro modelo gana clara y consistentemente", "no_elegidos": razones}
    return {"elegido": referencia, "regla_aplicada": "ninguno supera a la referencia en ambas validaciones: se conserva el más simple",
            "no_elegidos": razones}


# ---------------------------------------------------------------- tiempos
def medir_tiempos(nombre, textos, y, frases_prueba, repeticiones_fit=3) -> dict:
    """Tiempo de entrenamiento (mediana de `repeticiones_fit`) y latencia de
    predicción de UNA frase a la vez (p50/p95/p99 en ms), con el modelo entrenado
    con todo el dataset. Depende de la máquina: por eso no entra a las cifras
    deterministas, solo se guarda cuando se pide medirlo."""
    segundos = []
    for _ in range(repeticiones_fit):
        modelo = construir(nombre)
        t0 = time.perf_counter()
        modelo.fit(textos, y)
        segundos.append(time.perf_counter() - t0)
    lat = []
    for _ in range(3):  # 3 pasadas: la primera calienta cachés
        for f in frases_prueba:
            t0 = time.perf_counter()
            if hasattr(modelo, "predict_proba"):
                modelo.predict_proba([f])
            else:
                modelo.predict([f])
            lat.append((time.perf_counter() - t0) * 1000.0)
    lat = np.array(lat[len(frases_prueba):])  # descarta la pasada de calentamiento
    return {
        "entrenamiento_s_mediana": round(float(np.median(segundos)), 3),
        "prediccion_ms_p50": round(float(np.percentile(lat, 50)), 3),
        "prediccion_ms_p95": round(float(np.percentile(lat, 95)), 3),
        "prediccion_ms_p99": round(float(np.percentile(lat, 99)), 3),
        "n_predicciones": int(len(lat)),
    }

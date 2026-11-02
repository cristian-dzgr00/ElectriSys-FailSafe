"""Backtest del pronóstico de demanda y de la señal de reabastecimiento.

Evalúa, sobre datos históricos fuera de línea, dos cosas que hasta ahora no
tenían una medición cuantitativa:

1. El pronóstico semanal de `app/demanda/forecast.py` (promedio móvil
   ponderado linealmente) frente a líneas base simples, con validación de
   origen móvil ("rolling origin"): para cada producto y cada semana de
   origen se pronostica la semana siguiente (horizonte 1) y la subsiguiente
   (horizonte 2) usando SOLO lo ocurrido hasta el origen.
2. La señal `reabastecer` y la cantidad sugerida de
   `app/demanda/reabastecimiento.py`, reproduciendo la línea de tiempo de
   stock implícita en ventas y pedidos y contrastándola con lo que
   realmente pasó en las semanas siguientes.

El código del repositorio se LLAMA, no se reimplementa: se invoca
`forecast._calcular` (la aritmética pura de la predicción) y
`reabastecimiento.calcular_sugerencia`. Lo único que se simula es "hoy":
`forecast._calcular` lee `date.today()`, así que durante cada llamada se
sustituye `forecast.date` por una clase que devuelve el domingo de la semana
de origen (así los 12 cubos de 7 días del modelo coinciden con semanas ISO).

Los datos son SINTÉTICOS (demo exportada del esquema real, ~15 semanas): las
conclusiones muestran que el procedimiento funciona, no que el modelo
rinda igual en producción. Ver la lista `limitaciones` del JSON.

Uso (desde nlp-service/):
    python eval/backtest_demanda.py [--salida RUTA] [--datos CARPETA]
                                    [--min-historia 4] [--semilla 20260101]
                                    [--remuestreos 1000]
No modifica ningún archivo de datos del repositorio.
"""
import argparse
import contextlib
import csv
import hashlib
import json
import math
import statistics
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np

BASE_DIR = Path(__file__).resolve().parent
RAIZ = BASE_DIR.parent
if str(RAIZ) not in sys.path:          # permite `python eval/backtest_demanda.py`
    sys.path.insert(0, str(RAIZ))

from app.demanda import forecast, reabastecimiento  # noqa: E402

DATOS_DIR = BASE_DIR / "datos_demo"
SALIDA_DEFECTO = BASE_DIR / "resultados_demanda.json"

MIN_HISTORIA = 4            # semanas de historia mínimas para abrir un origen
SEMILLA = 20260101
REMUESTREOS = 1000
TOP_N = 20
HORIZONTES = (1, 2)
VENTANA_ETIQUETA_DIAS = 14  # "dentro de las próximas 2 semanas"
HORIZONTE_CANTIDAD_DIAS = reabastecimiento.DIAS_ENTREGA + reabastecimiento.DIAS_COBERTURA

MODELOS = ("modelo_repo", "modelo_repo_sin_relleno", "naive_ultima_semana",
           "media_4_semanas", "media_historia", "mediana_historia")
BASELINES = tuple(m for m in MODELOS if m != "modelo_repo")

DESCRIPCION_MODELOS = {
    "modelo_repo": "forecast._calcular tal cual (promedio móvil ponderado de 12 "
                   "semanas; las semanas previas al inicio de los datos cuentan como 0)",
    "modelo_repo_sin_relleno": "forecast._promedio_movil_ponderado sobre las semanas "
                               "realmente observadas (sin rellenar con ceros hacia atrás)",
    "naive_ultima_semana": "demanda de la última semana observada",
    "media_4_semanas": "media de las últimas 4 semanas observadas",
    "media_historia": "media de toda la historia observada",
    "mediana_historia": "mediana de toda la historia observada (sin estacionalidad)",
}


# ── Lectura de datos ─────────────────────────────────────────────────────────

def _leer_csv(ruta: Path) -> list[dict]:
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _fecha_hora(texto: str) -> datetime | None:
    texto = (texto or "").strip()
    if not texto:
        return None
    return datetime.fromisoformat(texto[:19].replace("T", " "))


def sha256_archivo(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def cargar_datos(carpeta: Path) -> dict:
    """Lee los CSV de demostración. Las ventas anuladas se descartan aquí."""
    filas_ventas = _leer_csv(carpeta / "ventas_lineas.csv")
    ventas, anuladas = [], 0
    for f in filas_ventas:
        if f["ESTADO"].strip().lower() != "completada":
            anuladas += 1
            continue
        ventas.append({
            "venta_id": int(f["VENTA_ID"]),
            "fecha": _fecha_hora(f["FECHA_LOCAL"]),
            "repuesto_id": int(f["REPUESTO_ID"]),
            "cantidad": int(f["CANTIDAD"]),
        })

    pedidos = []
    for f in _leer_csv(carpeta / "pedidos_lineas.csv"):
        pedidos.append({
            "pedido_id": int(f["PEDIDO_ID"]),
            "estado": f["ESTADO"].strip().lower(),
            "fecha": _fecha_hora(f["FECHA_LOCAL"]),
            "recibido": _fecha_hora(f["RECIBIDO_LOCAL"]),
            "repuesto_id": int(f["REPUESTO_ID"]),
            "cantidad": int(f["CANTIDAD"]),
        })

    repuestos = {}
    for f in _leer_csv(carpeta / "repuestos.csv"):
        repuestos[int(f["ID"])] = {
            "stock": int(f["STOCK"]),
            "stock_minimo": int(f["STOCK_MINIMO"]),
            "categoria": f["CATEGORIA"],
        }
    return {"ventas": ventas, "lineas_anuladas": anuladas,
            "pedidos": pedidos, "repuestos": repuestos}


# ── Series semanales ─────────────────────────────────────────────────────────

def lunes_de(d: date) -> date:
    return d - timedelta(days=d.weekday())


def semanas_iso(ventas: list[dict]) -> list[date]:
    """Lunes de cada semana ISO, consecutivas, entre la primera y la última venta."""
    if not ventas:
        return []
    primero = lunes_de(min(v["fecha"].date() for v in ventas))
    ultimo = lunes_de(max(v["fecha"].date() for v in ventas))
    lunes, actual = [], primero
    while actual <= ultimo:
        lunes.append(actual)
        actual += timedelta(days=7)
    return lunes


def demanda_semanal(ventas: list[dict], lunes: list[date]) -> dict[int, list[float]]:
    """{repuesto_id: [unidades por semana ISO]} solo con ventas completadas."""
    indice = {l: i for i, l in enumerate(lunes)}
    series: dict[int, list[float]] = {}
    for v in ventas:
        serie = series.setdefault(v["repuesto_id"], [0.0] * len(lunes))
        serie[indice[lunes_de(v["fecha"].date())]] += v["cantidad"]
    return series


def ventas_diarias(ventas: list[dict]) -> dict[int, dict[date, float]]:
    out: dict[int, dict[date, float]] = {}
    for v in ventas:
        dia = out.setdefault(v["repuesto_id"], {})
        d = v["fecha"].date()
        dia[d] = dia.get(d, 0.0) + v["cantidad"]
    return out


# ── Llamada al modelo del repositorio ────────────────────────────────────────

@contextlib.contextmanager
def hoy_fijo(hoy: date):
    """Sustituye `forecast.date` para que `date.today()` devuelva `hoy`."""
    original = forecast.date

    class _FechaFija(date):
        @classmethod
        def today(cls):
            return hoy

    forecast.date = _FechaFija
    try:
        yield
    finally:
        forecast.date = original


def prediccion_repo(dias: dict[date, float], hoy: date, stock: float = 0.0,
                    stock_minimo: float = 0.0, repuesto_id: int = 0) -> dict:
    """forecast._calcular con la serie diaria conocida hasta `hoy` (inclusive)."""
    serie = [{"fecha": d.isoformat(), "unidades": u}
             for d, u in sorted(dias.items()) if d <= hoy]
    with hoy_fijo(hoy):
        return forecast._calcular(
            {"serie": serie, "stock": stock, "stock_minimo": stock_minimo}, repuesto_id)


def pronosticos_en_origen(historia: list[float], prediccion: dict) -> dict[str, float]:
    """Pronóstico semanal de cada modelo dado la historia observada hasta el origen."""
    n_pasos = forecast.DIAS_HISTORIAL // forecast.DIAS_POR_SEMANA
    return {
        "modelo_repo": float(prediccion["demanda_semanal_estimada"]),
        "modelo_repo_sin_relleno": forecast._promedio_movil_ponderado(historia[-n_pasos:]),
        "naive_ultima_semana": historia[-1],
        "media_4_semanas": sum(historia[-4:]) / len(historia[-4:]),
        "media_historia": sum(historia) / len(historia),
        "mediana_historia": float(statistics.median(historia)),
    }


# ── Métricas ─────────────────────────────────────────────────────────────────

def termino_smape(real: float, pronostico: float) -> float:
    """2|f-a| / (|a|+|f|); si real y pronóstico son 0 el error es 0 (acierto)."""
    denom = abs(real) + abs(pronostico)
    return 0.0 if denom == 0 else 2.0 * abs(pronostico - real) / denom


def sumas_error(reales, pronosticos) -> list[float]:
    """[n, sum|e|, sum e^2, sum real, sum terminos_smape]: estadísticos suficientes."""
    n = len(reales)
    abs_e = sum(abs(p - r) for r, p in zip(reales, pronosticos))
    sq_e = sum((p - r) ** 2 for r, p in zip(reales, pronosticos))
    return [float(n), abs_e, sq_e, float(sum(reales)),
            sum(termino_smape(r, p) for r, p in zip(reales, pronosticos))]


def metricas_desde_sumas(s) -> dict:
    """MAE, RMSE, WAPE, sMAPE (%) desde las sumas; funciona también con arreglos."""
    s = np.asarray(s, dtype=float)
    n, abs_e, sq_e, act, smape = (s[..., k] for k in range(5))
    with np.errstate(divide="ignore", invalid="ignore"):
        return {
            "mae": np.where(n > 0, abs_e / n, np.nan),
            "rmse": np.where(n > 0, np.sqrt(sq_e / n), np.nan),
            "wape": np.where(act > 0, abs_e / act, np.nan),
            "smape": np.where(n > 0, 100.0 * smape / n, np.nan),
        }


def metricas_error(reales, pronosticos) -> dict:
    """Métricas puntuales (floats) de un conjunto de pares real/pronóstico."""
    m = metricas_desde_sumas(sumas_error(reales, pronosticos))
    return {k: (None if np.isnan(v) else float(v)) for k, v in m.items()} | {"n": len(reales)}


def _num(x, dec=4):
    if x is None:
        return None
    x = float(x)
    return None if math.isnan(x) or math.isinf(x) else round(x, dec)


def intervalo(muestras, dec=4) -> list | None:
    """Percentiles 2.5 y 97.5 ignorando remuestreos indefinidos."""
    muestras = np.asarray(muestras, dtype=float)
    muestras = muestras[~np.isnan(muestras)]
    if muestras.size == 0:
        return None
    lo, hi = np.percentile(muestras, [2.5, 97.5])
    return [_num(lo, dec), _num(hi, dec)]


def indices_bootstrap(semilla: int, n: int, remuestreos: int) -> np.ndarray:
    rng = np.random.default_rng(semilla)
    return rng.integers(0, n, size=(remuestreos, n))


# ── Backtest de pronóstico ───────────────────────────────────────────────────

def generar_casos(series: dict[int, list[float]], diarias: dict[int, dict[date, float]],
                  lunes: list[date], min_historia: int, horizonte: int) -> list[dict]:
    """Un caso por (producto, semana de origen) con `horizonte` semanas por delante."""
    n_sem = len(lunes)
    casos = []
    for rid in sorted(series):
        serie = series[rid]
        for i in range(min_historia - 1, n_sem - horizonte):
            domingo = lunes[i] + timedelta(days=6)
            pred = prediccion_repo(diarias.get(rid, {}), domingo, repuesto_id=rid)
            pron = pronosticos_en_origen(serie[: i + 1], pred)
            casos.append({"repuesto_id": rid, "origen": i, "real": serie[i + horizonte],
                          "pronosticos": pron})
    return casos


def _sumas_por_producto(casos: list[dict], productos: list[int]) -> dict[str, np.ndarray]:
    """{modelo: arreglo (P,5) de sumas por producto}, en el orden de `productos`."""
    out = {}
    for modelo in MODELOS:
        filas = []
        for rid in productos:
            propios = [c for c in casos if c["repuesto_id"] == rid]
            filas.append(sumas_error([c["real"] for c in propios],
                                     [c["pronosticos"][modelo] for c in propios]))
        out[modelo] = np.array(filas, dtype=float)
    return out


def _resumen_metricas(por_producto: dict[str, np.ndarray], idx: np.ndarray) -> dict:
    """Métricas globales + IC95 por bootstrap sobre productos."""
    res = {}
    for modelo, sumas in por_producto.items():
        puntual = metricas_desde_sumas(sumas.sum(axis=0))
        remuestreo = metricas_desde_sumas(sumas[idx].sum(axis=1))
        res[modelo] = {k: {"valor": _num(puntual[k]), "ic95": intervalo(remuestreo[k])}
                       for k in ("mae", "rmse", "wape", "smape")}
    return res


def _comparacion_pareada(por_producto: dict[str, np.ndarray], idx: np.ndarray) -> dict:
    """modelo_repo contra cada línea base, con los MISMOS remuestreos (pareado)."""
    base = por_producto["modelo_repo"]
    res = {}
    for otro in BASELINES:
        sumas = por_producto[otro]
        d_mae = (metricas_desde_sumas(base[idx].sum(axis=1))["mae"]
                 - metricas_desde_sumas(sumas[idx].sum(axis=1))["mae"])
        d_wape = (metricas_desde_sumas(base[idx].sum(axis=1))["wape"]
                  - metricas_desde_sumas(sumas[idx].sum(axis=1))["wape"])
        punt_mae = metricas_desde_sumas(base.sum(axis=0))["mae"] - metricas_desde_sumas(sumas.sum(axis=0))["mae"]
        punt_wape = metricas_desde_sumas(base.sum(axis=0))["wape"] - metricas_desde_sumas(sumas.sum(axis=0))["wape"]
        err_m, err_b = base[:, 1], sumas[:, 1]
        mejor = int(np.sum(err_m < err_b - 1e-9))
        peor = int(np.sum(err_m > err_b + 1e-9))
        ic_mae, ic_wape = intervalo(d_mae), intervalo(d_wape)
        res[f"modelo_repo_vs_{otro}"] = {
            "diferencia_mae": {"valor": _num(punt_mae), "ic95": ic_mae},
            "diferencia_wape": {"valor": _num(punt_wape), "ic95": ic_wape},
            "prob_modelo_mejor_mae": _num(np.mean(d_mae[~np.isnan(d_mae)] < 0)),
            "productos_modelo_mejor": mejor,
            "productos_modelo_peor": peor,
            "productos_empate": int(len(err_m) - mejor - peor),
            "veredicto": _veredicto(ic_mae),
        }
    return res


def _veredicto(ic) -> str:
    """Lectura prudente de la diferencia (modelo - base) de MAE: negativo = mejor."""
    if ic is None:
        return "indeterminado"
    if ic[1] < 0:
        return "modelo_mejor"
    if ic[0] > 0:
        return "modelo_peor"
    return "sin_diferencia_concluyente"


def backtest_pronostico(datos: dict, min_historia: int, semilla: int,
                        remuestreos: int) -> dict:
    ventas = datos["ventas"]
    lunes = semanas_iso(ventas)
    series = demanda_semanal(ventas, lunes)
    diarias = ventas_diarias(ventas)
    volumen = {rid: sum(s) for rid, s in series.items()}
    productos = sorted(series)
    top = sorted(productos, key=lambda r: (-volumen[r], r))[:TOP_N]

    out = {}
    for h in HORIZONTES:
        casos = generar_casos(series, diarias, lunes, min_historia, h)
        if not casos:
            out[f"horizonte_{h}"] = {"n_casos": 0}
            continue
        todos = _sumas_por_producto(casos, productos)
        solo_top = _sumas_por_producto([c for c in casos if c["repuesto_id"] in top], top)
        idx_todos = indices_bootstrap(semilla + h, len(productos), remuestreos)
        idx_top = indices_bootstrap(semilla + 100 + h, len(top), remuestreos)
        out[f"horizonte_{h}"] = {
            "n_casos": len(casos),
            "n_productos": len(productos),
            "n_origenes": len({c["origen"] for c in casos}),
            "ceros_reales_pct": _num(100.0 * sum(c["real"] == 0 for c in casos) / len(casos), 2),
            "global": _resumen_metricas(todos, idx_todos),
            "top20": {
                "productos": top,
                "n_casos": sum(1 for c in casos if c["repuesto_id"] in top),
                "metricas": _resumen_metricas(solo_top, idx_top),
            },
            "comparacion_pareada": _comparacion_pareada(todos, idx_todos),
            "comparacion_pareada_top20": _comparacion_pareada(solo_top, idx_top),
        }
    return {"semanas": {"n": len(lunes), "primera_semana_lunes": lunes[0].isoformat(),
                        "ultima_semana_lunes": lunes[-1].isoformat()},
            "n_productos_con_ventas": len(productos), **out}


# ── Línea de tiempo de stock y señal de reabastecimiento ─────────────────────

def reconstruir_stock(datos: dict, dia0: date, n_dias: int) -> dict:
    """Stock al cierre de cada día para cada repuesto.

    Supuesto: `repuestos.csv` es la foto del stock al cierre del último día.
    Stock inicial = stock actual + vendido (completadas) - recibido (pedidos
    en estado 'recibido' cuya fecha de recepción cae dentro de la ventana).
    Las ventas anuladas no mueven stock; los pedidos cancelados/en tránsito/
    solicitados no han entrado al inventario.
    """
    vendido = {rid: [0] * n_dias for rid in datos["repuestos"]}
    recibido = {rid: [0] * n_dias for rid in datos["repuestos"]}
    for v in datos["ventas"]:
        d = (v["fecha"].date() - dia0).days
        if 0 <= d < n_dias and v["repuesto_id"] in vendido:
            vendido[v["repuesto_id"]][d] += v["cantidad"]
    for p in datos["pedidos"]:
        if p["estado"] != "recibido" or p["recibido"] is None:
            continue
        d = (p["recibido"].date() - dia0).days
        if 0 <= d < n_dias and p["repuesto_id"] in recibido:
            recibido[p["repuesto_id"]][d] += p["cantidad"]

    out = {}
    for rid, info in datos["repuestos"].items():
        inicial = info["stock"] + sum(vendido[rid]) - sum(recibido[rid])
        nivel, fin = inicial, []
        for d in range(n_dias):
            nivel += recibido[rid][d] - vendido[rid][d]
            fin.append(nivel)
        out[rid] = {"inicial": inicial, "fin_de_dia": fin,
                    "vendido_dia": vendido[rid], "recibido_dia": recibido[rid]}
    return out


def en_transito_al_cierre(pedidos: list[dict], rid: int, fin_dia: datetime) -> float:
    """Unidades pedidas (no canceladas) ya emitidas y todavía no recibidas."""
    total = 0.0
    for p in pedidos:
        if p["repuesto_id"] != rid or p["estado"] == "cancelado" or p["fecha"] > fin_dia:
            continue
        if p["estado"] == "recibido" and p["recibido"] is not None and p["recibido"] <= fin_dia:
            continue
        total += p["cantidad"]
    return total


def evento_en_ventana(stock: list[int], minimo: float, o: int, dias: int):
    """(primer_dia_bajo_minimo|None, primer_dia_agotado|None) en (o, o+dias]."""
    bajo = agotado = None
    for k in range(1, dias + 1):
        nivel = stock[o + k]
        if bajo is None and (nivel < minimo or nivel <= 0):
            bajo = k
        if agotado is None and nivel <= 0:
            agotado = k
    return bajo, agotado


def _confusion(pred: list[bool], real: list[bool]) -> dict:
    tp = sum(p and r for p, r in zip(pred, real))
    fp = sum(p and not r for p, r in zip(pred, real))
    fn = sum(r and not p for p, r in zip(pred, real))
    tn = len(pred) - tp - fp - fn
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn}


def precision_recall(c: dict) -> dict:
    prec = c["tp"] / (c["tp"] + c["fp"]) if c["tp"] + c["fp"] else None
    rec = c["tp"] / (c["tp"] + c["fn"]) if c["tp"] + c["fn"] else None
    if prec is None or rec is None:
        f1 = None
    else:
        f1 = 0.0 if prec + rec == 0 else 2 * prec * rec / (prec + rec)
    return {"precision": _num(prec), "recall": _num(rec), "f1": _num(f1), **c}


def _pr_con_ic(filas: list[dict], clave_pred: str, clave_real: str, semilla: int,
               remuestreos: int, excluir_ya_bajo: bool = False) -> dict:
    """Precisión/recall globales con IC95 bootstrap remuestreando productos."""
    filas = [f for f in filas if not (excluir_ya_bajo and f["ya_bajo_minimo"])]
    pred = [f[clave_pred] for f in filas]
    real = [f[clave_real] for f in filas]
    res = precision_recall(_confusion(pred, real))
    res["n_casos"] = len(filas)
    res["tasa_base"] = _num(sum(real) / len(real)) if real else None

    productos = sorted({f["repuesto_id"] for f in filas})
    if productos:
        cuentas = np.array([[_confusion([f[clave_pred] for f in filas if f["repuesto_id"] == rid],
                                        [f[clave_real] for f in filas if f["repuesto_id"] == rid])[k]
                             for k in ("tp", "fp", "fn")] for rid in productos], dtype=float)
        idx = indices_bootstrap(semilla, len(productos), remuestreos)
        s = cuentas[idx].sum(axis=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            prec = np.where(s[:, 0] + s[:, 1] > 0, s[:, 0] / (s[:, 0] + s[:, 1]), np.nan)
            rec = np.where(s[:, 0] + s[:, 2] > 0, s[:, 0] / (s[:, 0] + s[:, 2]), np.nan)
        res["precision_ic95"] = intervalo(prec)
        res["recall_ic95"] = intervalo(rec)
    return res


def backtest_reabastecimiento(datos: dict, min_historia: int, semilla: int,
                              remuestreos: int) -> dict:
    ventas = datos["ventas"]
    lunes = semanas_iso(ventas)
    diarias = ventas_diarias(ventas)
    n_sem, dia0 = len(lunes), lunes[0]
    n_dias = 7 * n_sem
    linea = reconstruir_stock(datos, dia0, n_dias)
    de, co = reabastecimiento.DIAS_ENTREGA, reabastecimiento.DIAS_COBERTURA

    filas, negativos = [], 0
    for rid, info in sorted(datos["repuestos"].items()):
        minimo = info["stock_minimo"]
        stock = linea[rid]["fin_de_dia"]
        negativos += sum(1 for s in stock if s < 0)
        for i in range(min_historia - 1, n_sem):
            o = 7 * i + 6                                  # domingo = cierre de la semana i
            if o + VENTANA_ETIQUETA_DIAS > n_dias - 1:
                continue
            domingo = lunes[i] + timedelta(days=6)
            cierre = datetime.combine(domingo, datetime.max.time())
            transito = en_transito_al_cierre(datos["pedidos"], rid, cierre)
            pred = prediccion_repo(diarias.get(rid, {}), domingo, stock=stock[o],
                                   stock_minimo=minimo, repuesto_id=rid)
            sug = reabastecimiento.calcular_sugerencia(pred, de, co, en_transito=transito)
            bajo, agotado = evento_en_ventana(stock, minimo, o, VENTANA_ETIQUETA_DIAS)
            fila = {
                "repuesto_id": rid, "origen": i, "semana": domingo.isoformat(),
                "ya_bajo_minimo": stock[o] < minimo or stock[o] <= 0,
                "senal_reabastecer": pred["senal"] == "reabastecer",
                "sugerencia_necesita": bool(sug["necesita_reabastecer"]),
                "regla_estatica_stock_le_minimo": stock[o] <= minimo,
                "bajo_minimo_14d": bajo is not None,
                "agotado_14d": agotado is not None,
                "agotado_en_entrega": agotado is not None and agotado <= de,
                "dia_primer_evento": bajo,
            }
            # Adecuación de la cantidad: solo si hay 37 días de futuro observados.
            if sug["necesita_reabastecer"] and o + HORIZONTE_CANTIDAD_DIAS <= n_dias - 1:
                demanda_obs = sum(linea[rid]["vendido_dia"][o + 1: o + 1 + HORIZONTE_CANTIDAD_DIAS])
                demanda_entrega = sum(linea[rid]["vendido_dia"][o + 1: o + 1 + de])
                objetivo = stock[o] + transito + sug["cantidad_sugerida"]
                fila["cantidad"] = {
                    "sugerida": sug["cantidad_sugerida"],
                    "objetivo_total": objetivo,
                    "demanda_observada": demanda_obs,
                    "cubre": objetivo >= demanda_obs,
                    "stock_cubre_entrega": stock[o] + transito >= demanda_entrega,
                }
            filas.append(fila)

    pares = (("senal_reabastecer", "senal_reabastecer"),
             ("sugerencia_necesita", "sugerencia_necesita"),
             ("regla_estatica_stock_le_minimo", "linea_base_stock_le_minimo"))
    etiquetas = ("bajo_minimo_14d", "agotado_14d", "agotado_en_entrega")
    clasificacion = {}
    for k, (etiq) in enumerate(etiquetas):
        clasificacion[etiq] = {}
        for clave, nombre in pares:
            clasificacion[etiq][nombre] = {
                "todos_los_casos": _pr_con_ic(filas, clave, etiq, semilla + k, remuestreos),
                "solo_caidas_nuevas": _pr_con_ic(filas, clave, etiq, semilla + 10 + k,
                                                 remuestreos, excluir_ya_bajo=True),
            }

    # Margen de anticipación: ¿se alertó con tiempo para que llegara el pedido?
    positivos = [f for f in filas if f["bajo_minimo_14d"]]
    margen = {}
    for nombre, cond in (("evento_dentro_de_entrega", lambda f: f["dia_primer_evento"] <= de),
                         ("evento_con_margen_mayor_a_entrega", lambda f: f["dia_primer_evento"] > de)):
        grupo = [f for f in positivos if cond(f)]
        margen[nombre] = {
            "n": len(grupo),
            "alertados_senal_reabastecer": sum(f["senal_reabastecer"] for f in grupo),
            "alertados_sugerencia": sum(f["sugerencia_necesita"] for f in grupo),
        }

    con_cantidad = [f["cantidad"] for f in filas if "cantidad" in f]
    cubren = sum(c["cubre"] for c in con_cantidad)
    ratios = [c["objetivo_total"] / c["demanda_observada"]
              for c in con_cantidad if c["demanda_observada"] > 0]
    cantidad = {
        "horizonte_dias": HORIZONTE_CANTIDAD_DIAS,
        "n_semanas_con_sugerencia_evaluables": len(con_cantidad),
        "cubren_demanda_observada": cubren,
        "cubren_pct": _num(100.0 * cubren / len(con_cantidad), 1) if con_cantidad else None,
        "stock_actual_cubria_la_entrega": sum(c["stock_cubre_entrega"] for c in con_cantidad),
        "razon_objetivo_sobre_demanda_mediana": _num(statistics.median(ratios)) if ratios else None,
        "sin_demanda_observada": sum(1 for c in con_cantidad if c["demanda_observada"] == 0),
    }

    por_semana = []
    for i in sorted({f["origen"] for f in filas}):
        grupo = [f for f in filas if f["origen"] == i]
        por_semana.append({
            "semana_origen": grupo[0]["semana"],
            "n_productos": len(grupo),
            "positivos_bajo_minimo_14d": sum(f["bajo_minimo_14d"] for f in grupo),
            "alertas_senal_reabastecer": sum(f["senal_reabastecer"] for f in grupo),
            "aciertos_senal_reabastecer": sum(f["senal_reabastecer"] and f["bajo_minimo_14d"] for f in grupo),
            "alertas_sugerencia": sum(f["sugerencia_necesita"] for f in grupo),
        })

    return {
        "parametros": {"dias_entrega": de, "dias_cobertura": co,
                       "factor_seguridad": reabastecimiento.FACTOR_SEGURIDAD,
                       "ventana_etiqueta_dias": VENTANA_ETIQUETA_DIAS},
        "reconstruccion_stock": {
            "supuesto": "STOCK de repuestos.csv = stock al cierre del último día; "
                        "inicial = actual + vendido (completadas) - recibido (estado recibido).",
            "productos": len(datos["repuestos"]),
            "stock_inicial_negativo": sum(1 for v in linea.values() if v["inicial"] < 0),
            "dias_con_stock_negativo": negativos,
            "pedidos_en_transito_o_solicitados": sum(1 for p in datos["pedidos"]
                                                     if p["estado"] in ("en_transito", "solicitado")),
        },
        "n_casos": len(filas),
        "n_origenes": len({f["origen"] for f in filas}),
        "clasificacion": clasificacion,
        "margen_de_anticipacion": margen,
        "adecuacion_de_cantidad": cantidad,
        "por_semana": por_semana,
    }


# ── Orquestación ─────────────────────────────────────────────────────────────

LIMITACIONES = [
    "Datos SINTÉTICOS: demo exportada del esquema real, no ventas de clientes reales; "
    "el comportamiento de compra fue generado, no observado.",
    "Historia muy corta (~16 semanas ISO, del 2026-07-14 al 2026-11-01): con min_historia=4 "
    "hay pocos orígenes por producto y los intervalos de confianza son anchos.",
    "Series intermitentes: la mayoría de los productos vende 0-2 unidades por semana, con "
    "muchas semanas en cero; en ese régimen una mediana/naive de ceros es difícil de superar "
    "en MAE y el sMAPE penaliza duro los falsos positivos de demanda.",
    "El modelo del repositorio promedia 12 semanas hacia atrás y trata las semanas anteriores "
    "al inicio de los datos como demanda 0: en un backtest con historia corta eso lo "
    "subestima. 'modelo_repo_sin_relleno' separa ese efecto del de la fórmula en sí.",
    "El modelo usa buckets de 7 días contados hacia atrás desde 'hoy'; aquí 'hoy' es el "
    "domingo de la semana de origen, de modo que los buckets coinciden con semanas ISO.",
    "Horizonte 2 usa el mismo pronóstico plano que horizonte 1 (el modelo y las líneas base "
    "no tienen tendencia ni estacionalidad), por lo que el error crece solo por deriva real.",
    "La selección del top-20 usa el volumen total del período (incluye semanas posteriores al "
    "origen): solo define el subconjunto reportado, no entra en ningún pronóstico.",
    "Reconstrucción de stock: se asume que STOCK de repuestos.csv es la foto al cierre del "
    "último día y que no hubo ajustes de inventario, mermas ni devoluciones fuera de ventas y "
    "pedidos recibidos; las anulaciones no mueven stock.",
    "Pedidos 'en_transito'/'solicitado' se tratan como pendientes hasta el final del período "
    "(no tienen fecha de recepción); los 'cancelado' se ignoran.",
    "Las etiquetas de reabastecimiento ('bajo mínimo o agotado en 14 días') incluyen "
    "recepciones reales de pedidos que el sistema no habría podido evitar ni provocar: es una "
    "validación retrospectiva, no un experimento causal.",
    "La adecuación de la cantidad sugerida solo puede evaluarse en orígenes con 37 días de "
    "futuro observado (lead time + cobertura), es decir, en las primeras semanas; la "
    "muestra es pequeña y la demanda observada está censurada por el stock disponible.",
    "Pocos eventos positivos (unas decenas de semanas-producto con stock bajo el mínimo en "
    "14 días, y menos aún agotamientos): precisión y recall tienen intervalos muy anchos o "
    "degenerados (0 o 1) y no permiten concluir diferencias entre la señal y la regla estática.",
    "Gran parte de los positivos son productos que ya estaban bajo el mínimo en el origen "
    "(siguen así); por eso se reporta aparte 'solo_caidas_nuevas', que es la parte que el "
    "modelo debería anticipar.",
    "No se validó contra la rotación 'rotacion_baja'; solo la señal 'reabastecer'.",
]


def ejecutar(carpeta_datos: Path = DATOS_DIR, min_historia: int = MIN_HISTORIA,
             semilla: int = SEMILLA, remuestreos: int = REMUESTREOS) -> dict:
    datos = cargar_datos(carpeta_datos)
    pron = backtest_pronostico(datos, min_historia, semilla, remuestreos)
    reab = backtest_reabastecimiento(datos, min_historia, semilla, remuestreos)
    return {
        "metadatos": {
            "descripcion": "Backtest de pronóstico de demanda y señal de reabastecimiento "
                           "sobre datos sintéticos de demostración",
            "parametros": {
                "min_historia_semanas": min_historia, "semilla": semilla,
                "remuestreos_bootstrap": remuestreos, "top_n": TOP_N,
                "horizontes_semanas": list(HORIZONTES),
                "semanas_historial_modelo": forecast.DIAS_HISTORIAL // forecast.DIAS_POR_SEMANA,
            },
            "unidades": {"mae": "unidades/semana", "rmse": "unidades/semana",
                         "wape": "fracción (sum|error| / sum reales)",
                         "smape": "porcentaje 0-200; real=0 y pronóstico=0 cuenta como error 0"},
            "modelos": DESCRIPCION_MODELOS,
            "datos": {
                "ventas_lineas_completadas": len(datos["ventas"]),
                "ventas_lineas_anuladas_excluidas": datos["lineas_anuladas"],
                "sha256": {n: sha256_archivo(carpeta_datos / n)
                           for n in ("ventas_lineas.csv", "pedidos_lineas.csv", "repuestos.csv")},
            },
        },
        "demanda": pron,
        "reabastecimiento": reab,
        "limitaciones": LIMITACIONES,
    }


def resumen_texto(r: dict) -> str:
    lineas = ["Backtest de demanda (datos sintéticos, resultados con cautela)"]
    for h in HORIZONTES:
        bloque = r["demanda"].get(f"horizonte_{h}", {})
        if not bloque.get("n_casos"):
            continue
        lineas.append(f"\nHorizonte {h} semana(s): {bloque['n_casos']} casos, "
                      f"{bloque['n_productos']} productos")
        lineas.append(f"  {'modelo':26s} {'MAE':>7s} {'WAPE':>7s} {'sMAPE%':>7s}")
        for m in MODELOS:
            g = bloque["global"][m]
            lineas.append(f"  {m:26s} {g['mae']['valor']:7.3f} {g['wape']['valor']:7.3f} "
                          f"{g['smape']['valor']:7.1f}")
        for k, v in bloque["comparacion_pareada"].items():
            lineas.append(f"  {k}: dMAE={v['diferencia_mae']['valor']} "
                          f"IC95={v['diferencia_mae']['ic95']} -> {v['veredicto']}")
    sr = r["reabastecimiento"]["clasificacion"]["bajo_minimo_14d"]
    lineas.append("\nSeñal de reabastecimiento vs 'bajo mínimo o agotado en 14 días':")
    for nombre, v in sr.items():
        t = v["todos_los_casos"]
        lineas.append(f"  {nombre:30s} precisión={t['precision']} recall={t['recall']} "
                      f"(casos={t['n_casos']}, tasa base={t['tasa_base']})")
    return "\n".join(lineas)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--salida", type=Path, default=SALIDA_DEFECTO)
    ap.add_argument("--datos", type=Path, default=DATOS_DIR)
    ap.add_argument("--min-historia", type=int, default=MIN_HISTORIA)
    ap.add_argument("--semilla", type=int, default=SEMILLA)
    ap.add_argument("--remuestreos", type=int, default=REMUESTREOS)
    args = ap.parse_args(argv)

    resultado = ejecutar(args.datos, args.min_historia, args.semilla, args.remuestreos)
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(resumen_texto(resultado))
    print(f"\nResultados escritos en {args.salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

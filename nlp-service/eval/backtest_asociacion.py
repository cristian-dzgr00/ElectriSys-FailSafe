"""Backtest de las reglas de asociación ("También suelen llevar").

Evalúa `app/asociacion/reglas.py` con una partición temporal de las ventas
completadas: las reglas se aprenden con el primer 70 % de las ventas (por
fecha) y se prueban con el 30 % restante, de modo que ninguna venta de
entrenamiento es posterior a una de prueba.

Para cada venta de prueba con al menos 2 productos distintos y para cada
producto de esa venta usado como "carrito" de un solo ítem, se piden los 3
mejores complementos a `recomendar_complementos` (el código real del
repositorio, aplicado SOLO a las canastas de entrenamiento) y se mide:

  - hit@3: ¿algún recomendado aparece en la misma venta de prueba?
  - precision@3: aciertos / 3 (los casos sin recomendación cuentan 0) y
    `precision_servidos`: aciertos / recomendaciones entregadas, solo en los
    casos con al menos una recomendación.
  - cobertura: proporción de casos con al menos una recomendación.
  - lift medio de las reglas servidas.

Líneas base (todas con datos de entrenamiento únicamente): los 3 productos
más populares (excluyendo el del carrito), los 3 más populares de la misma
categoría (repuestos.csv) y 3 productos al azar con semilla fija.

Los intervalos de confianza son bootstrap (percentiles 2.5-97.5) sobre las
VENTAS de prueba, porque los casos de una misma venta no son independientes.

Los datos son SINTÉTICOS y cortos; ver `limitaciones` en el JSON.

Uso (desde nlp-service/):
    python eval/backtest_asociacion.py [--salida RUTA] [--datos CARPETA]
                                       [--semilla 20260101] [--remuestreos 1000]
No modifica ningún archivo de datos del repositorio.
"""
import argparse
import contextlib
import csv
import json
import math
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np

BASE_DIR = Path(__file__).resolve().parent
RAIZ = BASE_DIR.parent
if str(RAIZ) not in sys.path:          # permite `python eval/backtest_asociacion.py`
    sys.path.insert(0, str(RAIZ))

from app.asociacion import reglas  # noqa: E402

DATOS_DIR = BASE_DIR / "datos_demo"
SALIDA_DEFECTO = BASE_DIR / "resultados_asociacion.json"

PROPORCION_ENTRENAMIENTO = 0.70
K = 3
SEMILLA = 20260101
REMUESTREOS = 1000
SORTEOS_ALEATORIO = 200      # sorteos por caso para promediar la línea base al azar
SOPORTES_SENSIBILIDAD = (1, 2, 3)

METODOS = ("reglas_repo", "populares_top3", "misma_categoria_top3", "aleatorio_semilla_fija")
BASELINES = METODOS[1:]
# Posición de cada magnitud en el vector de sumas por venta de prueba.
CAMPOS = ("casos", "hit", "prec", "servido", "hit_servidos", "prec_servidos",
          "lift", "n_recs")


# ── Datos y partición ────────────────────────────────────────────────────────

def cargar_ventas(carpeta: Path) -> list[dict]:
    """Ventas completadas agrupadas: [{venta_id, fecha, items(set)}], sin anuladas."""
    por_venta: dict[int, dict] = {}
    with open(carpeta / "ventas_lineas.csv", encoding="utf-8-sig", newline="") as f:
        for fila in csv.DictReader(f):
            if fila["ESTADO"].strip().lower() != "completada":
                continue
            vid = int(fila["VENTA_ID"])
            v = por_venta.setdefault(vid, {
                "venta_id": vid,
                "fecha": datetime.fromisoformat(fila["FECHA_LOCAL"][:19].replace("T", " ")),
                "items": set(),
            })
            v["items"].add(int(fila["REPUESTO_ID"]))
    return sorted(por_venta.values(), key=lambda v: (v["fecha"], v["venta_id"]))


def cargar_repuestos(carpeta: Path) -> dict[int, str]:
    with open(carpeta / "repuestos.csv", encoding="utf-8-sig", newline="") as f:
        return {int(r["ID"]): r["CATEGORIA"] for r in csv.DictReader(f)}


def dividir_temporal(ventas: list[dict], proporcion: float = PROPORCION_ENTRENAMIENTO):
    """(entrenamiento, prueba) con TODA venta de entrenamiento estrictamente
    anterior a toda venta de prueba.

    Se corta por fecha: la marca de tiempo de la venta que ocupa la posición
    `proporcion` del orden cronológico es el inicio de la prueba, y las ventas
    con esa misma marca (empates) quedan en prueba para no filtrar futuro.
    """
    ordenadas = sorted(ventas, key=lambda v: (v["fecha"], v["venta_id"]))
    if len(ordenadas) < 2:
        return ordenadas, []
    corte = ordenadas[min(int(len(ordenadas) * proporcion), len(ordenadas) - 1)]["fecha"]
    entrenamiento = [v for v in ordenadas if v["fecha"] < corte]
    prueba = [v for v in ordenadas if v["fecha"] >= corte]
    return entrenamiento, prueba


def canastas(ventas: list[dict]) -> list[list[int]]:
    return [sorted(v["items"]) for v in ventas]


# ── Recomendadores ───────────────────────────────────────────────────────────

@contextlib.contextmanager
def soporte_minimo(valor: int):
    """Cambia temporalmente reglas.SOPORTE_MINIMO (se lee en cada llamada)."""
    original = reglas.SOPORTE_MINIMO
    reglas.SOPORTE_MINIMO = valor
    try:
        yield
    finally:
        reglas.SOPORTE_MINIMO = original


@contextlib.contextmanager
def modelo_precalculado(canastas_entrenamiento: list[list[int]]):
    """Calcula las reglas UNA vez y hace que `recomendar_complementos` las reutilice.

    `recomendar_complementos` recalcula `calcular_reglas` en cada llamada; con
    cientos de casos de prueba eso es el 95 % del tiempo. Se llama al
    `calcular_reglas` real una sola vez y se le entrega ese resultado a la
    selección real (`recomendar_complementos`), que es lo que se evalúa.
    """
    modelo = reglas.calcular_reglas(canastas_entrenamiento)
    original = reglas.calcular_reglas
    reglas.calcular_reglas = lambda _canastas: modelo
    try:
        yield
    finally:
        reglas.calcular_reglas = original


def popularidad(entrenamiento: list[dict]) -> Counter:
    c = Counter()
    for v in entrenamiento:
        c.update(v["items"])
    return c


def _top_popular(pop: Counter, excluir: set, candidatos=None, k: int = K) -> list[int]:
    pool = [i for i in (candidatos if candidatos is not None else pop) if i not in excluir]
    return sorted(pool, key=lambda i: (-pop.get(i, 0), i))[:k]


def recomendar_reglas(canastas_entrenamiento: list[list[int]], carrito: int,
                      k: int = K) -> list[dict]:
    return reglas.recomendar_complementos(canastas_entrenamiento, [carrito], limite=k)


def recomendar_categoria(pop: Counter, categorias: dict[int, str], carrito: int,
                         k: int = K) -> list[int]:
    categoria = categorias.get(carrito)
    if categoria is None:
        return []
    mismos = [i for i, c in categorias.items() if c == categoria and i != carrito]
    return _top_popular(pop, {carrito}, candidatos=mismos, k=k)


def recomendar_azar(catalogo: list[int], carrito: int, rng: np.random.Generator,
                    k: int = K, sorteos: int = 1) -> np.ndarray:
    """`sorteos` selecciones al azar de k productos distintos (matriz sorteos x k)."""
    pool = np.array([i for i in catalogo if i != carrito])
    k = min(k, len(pool))
    puntajes = rng.random((sorteos, len(pool)))
    return pool[np.argpartition(puntajes, k - 1, axis=1)[:, :k]]


def medidas_azar(catalogo: list[int], carrito: int, verdad: set,
                 rng: np.random.Generator, sorteos: int = SORTEOS_ALEATORIO) -> dict:
    """Medidas esperadas de la línea base al azar, promediadas sobre varios sorteos."""
    picks = recomendar_azar(catalogo, carrito, rng, sorteos=sorteos)
    aciertos = np.isin(picks, list(verdad)).sum(axis=1)
    hit = float((aciertos > 0).mean())
    prec = float(aciertos.mean()) / K
    return {"casos": 1, "hit": hit, "prec": prec, "servido": 1, "hit_servidos": hit,
            "prec_servidos": float(aciertos.mean()) / picks.shape[1], "lift": 0.0, "n_recs": 0}


# ── Evaluación ───────────────────────────────────────────────────────────────

def casos_de_prueba(prueba: list[dict]) -> list[tuple[int, int, set]]:
    """(venta_id, carrito, verdad) para cada producto de cada venta con >=2 productos."""
    casos = []
    for v in prueba:
        if len(v["items"]) < 2:
            continue
        for carrito in sorted(v["items"]):
            casos.append((v["venta_id"], carrito, v["items"] - {carrito}))
    return casos


def _medidas(recomendados: list[int], verdad: set, lifts=None) -> dict:
    aciertos = len(set(recomendados) & verdad)
    servido = 1 if recomendados else 0
    return {
        "casos": 1,
        "hit": 1 if aciertos > 0 else 0,
        "prec": aciertos / K,
        "servido": servido,
        "hit_servidos": (1 if aciertos > 0 else 0) if servido else 0,
        "prec_servidos": (aciertos / len(recomendados)) if servido else 0.0,
        "lift": float(sum(lifts)) if lifts else 0.0,
        "n_recs": len(lifts) if lifts else 0,
    }


def _acumular(destino: dict, medida: dict):
    for k, v in medida.items():
        destino[k] = destino.get(k, 0.0) + v


def evaluar_metodos(entrenamiento: list[dict], prueba: list[dict],
                    categorias: dict[int, str], semilla: int,
                    soporte: int | None = None) -> dict:
    """{metodo: {venta_id: sumas}} con las medidas acumuladas por venta de prueba."""
    canastas_ent = canastas(entrenamiento)
    pop = popularidad(entrenamiento)
    catalogo = sorted(categorias)
    rng = np.random.default_rng(semilla)
    por_metodo = {m: {} for m in METODOS}

    ctx = soporte_minimo(soporte) if soporte is not None else contextlib.nullcontext()
    with ctx, modelo_precalculado(canastas_ent):
        for vid, carrito, verdad in casos_de_prueba(prueba):
            recs = recomendar_reglas(canastas_ent, carrito)
            _acumular(por_metodo["reglas_repo"].setdefault(vid, {}),
                      _medidas([r["repuesto_id"] for r in recs], verdad,
                               lifts=[r["lift"] for r in recs]))
            _acumular(por_metodo["populares_top3"].setdefault(vid, {}),
                      _medidas(_top_popular(pop, {carrito}), verdad))
            _acumular(por_metodo["misma_categoria_top3"].setdefault(vid, {}),
                      _medidas(recomendar_categoria(pop, categorias, carrito), verdad))
            # Al azar: se promedian varios sorteos para que la línea base no dependa
            # de un único azar; la semilla fija mantiene el resultado reproducible.
            _acumular(por_metodo["aleatorio_semilla_fija"].setdefault(vid, {}),
                      medidas_azar(catalogo, carrito, verdad, rng))
    return por_metodo


def _matriz(por_venta: dict) -> np.ndarray:
    ids = sorted(por_venta)
    return np.array([[por_venta[v].get(c, 0.0) for c in CAMPOS] for v in ids], dtype=float)


def metricas_desde_sumas(s) -> dict:
    """hit@3, precision@3, cobertura, precision sobre servidos, lift medio."""
    s = np.asarray(s, dtype=float)
    ix = {c: i for i, c in enumerate(CAMPOS)}
    casos, servido = s[..., ix["casos"]], s[..., ix["servido"]]
    with np.errstate(divide="ignore", invalid="ignore"):
        return {
            "hit_at3": np.where(casos > 0, s[..., ix["hit"]] / casos, np.nan),
            "precision_at3": np.where(casos > 0, s[..., ix["prec"]] / casos, np.nan),
            "cobertura": np.where(casos > 0, servido / casos, np.nan),
            "hit_at3_servidos": np.where(servido > 0, s[..., ix["hit_servidos"]] / servido, np.nan),
            "precision_servidos": np.where(servido > 0, s[..., ix["prec_servidos"]] / servido, np.nan),
            "lift_medio_servido": np.where(s[..., ix["n_recs"]] > 0,
                                           s[..., ix["lift"]] / s[..., ix["n_recs"]], np.nan),
        }


def _num(x, dec=4):
    x = float(x)
    return None if math.isnan(x) or math.isinf(x) else round(x, dec)


def _ic(muestras, dec=4):
    muestras = np.asarray(muestras, dtype=float)
    muestras = muestras[~np.isnan(muestras)]
    if muestras.size == 0:
        return None
    lo, hi = np.percentile(muestras, [2.5, 97.5])
    return [_num(lo, dec), _num(hi, dec)]


def resumir(por_metodo: dict, semilla: int, remuestreos: int) -> dict:
    """Métricas con IC95 por bootstrap sobre ventas, y comparación pareada."""
    matrices = {m: _matriz(por_metodo[m]) for m in METODOS}
    n_ventas = matrices[METODOS[0]].shape[0]
    if n_ventas == 0:
        return {"n_ventas_evaluadas": 0, "n_casos": 0}
    idx = np.random.default_rng(semilla).integers(0, n_ventas, size=(remuestreos, n_ventas))

    res = {"n_ventas_evaluadas": int(n_ventas),
           "n_casos": int(matrices[METODOS[0]][:, 0].sum()), "metodos": {}}
    remuestreados = {}
    for m, mat in matrices.items():
        punt = metricas_desde_sumas(mat.sum(axis=0))
        rem = metricas_desde_sumas(mat[idx].sum(axis=1))
        remuestreados[m] = rem
        res["metodos"][m] = {k: {"valor": _num(punt[k]), "ic95": _ic(rem[k])} for k in punt}

    res["comparacion_pareada"] = {}
    for b in BASELINES:
        entrada = {}
        for met in ("hit_at3", "precision_at3"):
            d = remuestreados["reglas_repo"][met] - remuestreados[b][met]
            punt = (metricas_desde_sumas(matrices["reglas_repo"].sum(axis=0))[met]
                    - metricas_desde_sumas(matrices[b].sum(axis=0))[met])
            ic = _ic(d)
            entrada[f"diferencia_{met}"] = {"valor": _num(punt), "ic95": ic}
        ic = entrada["diferencia_hit_at3"]["ic95"]
        entrada["veredicto_hit_at3"] = (
            "indeterminado" if ic is None else
            "reglas_mejor" if ic[0] > 0 else
            "reglas_peor" if ic[1] < 0 else "sin_diferencia_concluyente")
        res["comparacion_pareada"][f"reglas_repo_vs_{b}"] = entrada
    return res


# ── Dispersión y sensibilidad ────────────────────────────────────────────────

def dispersion(entrenamiento: list[dict], prueba: list[dict]) -> dict:
    def multi(vs):
        return sum(1 for v in vs if len(v["items"]) >= 2)
    out = {}
    for nombre, vs in (("entrenamiento", entrenamiento), ("prueba", prueba)):
        out[nombre] = {
            "ventas": len(vs),
            "ventas_multi_producto": multi(vs),
            "ventas_un_solo_producto": len(vs) - multi(vs),
            "fecha_primera": min(v["fecha"] for v in vs).isoformat() if vs else None,
            "fecha_ultima": max(v["fecha"] for v in vs).isoformat() if vs else None,
        }
    out["casos_de_prueba"] = len(casos_de_prueba(prueba))

    modelo = reglas.calcular_reglas(canastas(entrenamiento))
    out["reglas_aprendidas"] = {
        "soporte_minimo": reglas.SOPORTE_MINIMO,
        "productos_con_reglas": len(modelo["reglas"]),
        "reglas_dirigidas": sum(len(v) for v in modelo["reglas"].values()),
    }
    pares_test = Counter()
    for v in prueba:
        items = sorted(v["items"])
        for i, a in enumerate(items):
            for b in items[i + 1:]:
                pares_test[(a, b)] += 1
    pares_train = Counter()
    for v in entrenamiento:
        items = sorted(v["items"])
        for i, a in enumerate(items):
            for b in items[i + 1:]:
                pares_train[(a, b)] += 1
    out["pares"] = {
        "pares_distintos_en_prueba": len(pares_test),
        "pares_de_prueba_vistos_en_entrenamiento": sum(1 for p in pares_test if p in pares_train),
        "pares_de_entrenamiento_con_soporte_ge_2": sum(1 for c in pares_train.values() if c >= 2),
    }
    return out


def sensibilidad(entrenamiento, prueba, categorias, semilla, remuestreos) -> dict:
    out = {}
    for soporte in SOPORTES_SENSIBILIDAD:
        por_metodo = evaluar_metodos(entrenamiento, prueba, categorias, semilla, soporte)
        resumen = resumir(por_metodo, semilla + soporte, remuestreos)
        with soporte_minimo(soporte):
            modelo = reglas.calcular_reglas(canastas(entrenamiento))
        out[f"soporte_minimo_{soporte}"] = {
            "reglas_dirigidas": sum(len(v) for v in modelo["reglas"].values()),
            "productos_con_reglas": len(modelo["reglas"]),
            "reglas_repo": resumen["metodos"]["reglas_repo"] if resumen["n_casos"] else None,
        }
    return out


# ── Orquestación ─────────────────────────────────────────────────────────────

LIMITACIONES = [
    "Datos SINTÉTICOS: demo exportada del esquema real, no compras de clientes reales; las "
    "asociaciones entre productos son las que el generador de datos introdujo.",
    "Muestra pequeña: ~340 ventas completadas en 3.5 meses; la prueba (30 %) tiene pocas "
    "ventas multi-producto, así que los intervalos de confianza son anchos y las diferencias "
    "pequeñas no son concluyentes.",
    "Con SOPORTE_MINIMO=2 un par debe repetirse al menos dos veces en entrenamiento; en un "
    "historial corto muchos pares de prueba nunca se vieron, lo que limita el hit@3 y la "
    "cobertura de las reglas por construcción.",
    "Cada producto de una venta de prueba se evalúa como carrito de un solo ítem (verdad = "
    "los demás productos de esa venta). Un carrito real con varios productos recibe más "
    "señal; este protocolo subestima ese caso.",
    "Los casos de una misma venta no son independientes: el bootstrap remuestrea ventas "
    "completas, no casos sueltos.",
    "La línea base al azar promedia 200 sorteos por caso con semilla fija; no es un único "
    "sorteo, así que no hay ruido de muestreo propio en esa línea.",
    "La partición temporal corta por marca de tiempo (ventas con la misma marca van a "
    "prueba); la proporción real de entrenamiento puede ser ligeramente inferior al 70 %.",
    "Se mide coincidencia con lo que el cliente compró en la misma venta, no aceptación de "
    "la sugerencia ni margen: una recomendación útil que el cliente no compró cuenta como "
    "fallo.",
    "Las ventas anuladas se excluyen antes de dividir y de aprender reglas.",
    "La sensibilidad a SOPORTE_MINIMO cambia temporalmente la constante del módulo durante "
    "el backtest; el valor del repositorio no se modifica.",
]


def ejecutar(carpeta_datos: Path = DATOS_DIR, semilla: int = SEMILLA,
             remuestreos: int = REMUESTREOS) -> dict:
    ventas = cargar_ventas(carpeta_datos)
    categorias = cargar_repuestos(carpeta_datos)
    entrenamiento, prueba = dividir_temporal(ventas)
    por_metodo = evaluar_metodos(entrenamiento, prueba, categorias, semilla)
    return {
        "metadatos": {
            "descripcion": "Backtest de reglas de asociación con partición temporal 70/30 "
                           "sobre datos sintéticos de demostración",
            "parametros": {
                "proporcion_entrenamiento": PROPORCION_ENTRENAMIENTO, "k": K,
                "semilla": semilla, "remuestreos_bootstrap": remuestreos,
                "sorteos_aleatorio_por_caso": SORTEOS_ALEATORIO,
                "soporte_minimo": reglas.SOPORTE_MINIMO,
                "confianza_minima": reglas.CONFIANZA_MINIMA,
                "lift_minimo": reglas.LIFT_MINIMO,
            },
            "definiciones": {
                "hit_at3": "fracción de casos (venta de prueba, producto-carrito) donde algún "
                           "recomendado aparece en la misma venta; sin recomendación = fallo",
                "precision_at3": "aciertos / 3 promediado sobre todos los casos",
                "cobertura": "fracción de casos con al menos una recomendación",
                "precision_servidos": "aciertos / recomendaciones entregadas, solo casos servidos",
                "lift_medio_servido": "lift promedio de las reglas efectivamente entregadas",
            },
            "metodos": {
                "reglas_repo": "app.asociacion.reglas.recomendar_complementos con canastas de entrenamiento",
                "populares_top3": "3 más vendidos en entrenamiento, sin el producto del carrito",
                "misma_categoria_top3": "3 más vendidos de la misma categoría, sin el del carrito",
                "aleatorio_semilla_fija": "3 productos del catálogo al azar (semilla fija, 200 sorteos promediados)",
            },
            "ventas_completadas": len(ventas),
        },
        "particion": dispersion(entrenamiento, prueba),
        "resultados": resumir(por_metodo, semilla, remuestreos),
        "sensibilidad_soporte_minimo": sensibilidad(entrenamiento, prueba, categorias,
                                                    semilla, remuestreos),
        "limitaciones": LIMITACIONES,
    }


def resumen_texto(r: dict) -> str:
    p, res = r["particion"], r["resultados"]
    lineas = ["Backtest de reglas de asociación (datos sintéticos, resultados con cautela)",
              f"Entrenamiento: {p['entrenamiento']['ventas']} ventas "
              f"({p['entrenamiento']['ventas_multi_producto']} multi-producto) | "
              f"Prueba: {p['prueba']['ventas']} ventas "
              f"({p['prueba']['ventas_multi_producto']} multi-producto, "
              f"{p['casos_de_prueba']} casos) | reglas dirigidas: "
              f"{p['reglas_aprendidas']['reglas_dirigidas']}"]
    if not res.get("n_casos"):
        return "\n".join(lineas + ["Sin casos de prueba."])
    lineas.append(f"  {'metodo':26s} {'hit@3':>20s} {'cobertura':>9s} {'prec@3':>7s}")
    for m in METODOS:
        x = res["metodos"][m]
        lineas.append(f"  {m:26s} {x['hit_at3']['valor']:6.3f} {str(x['hit_at3']['ic95']):>13s} "
                      f"{x['cobertura']['valor']:9.3f} {x['precision_at3']['valor']:7.3f}")
    for k, v in res["comparacion_pareada"].items():
        lineas.append(f"  {k}: d_hit@3={v['diferencia_hit_at3']['valor']} "
                      f"IC95={v['diferencia_hit_at3']['ic95']} -> {v['veredicto_hit_at3']}")
    for k, v in r["sensibilidad_soporte_minimo"].items():
        rr = v["reglas_repo"]
        if rr:
            lineas.append(f"  {k}: reglas={v['reglas_dirigidas']} hit@3={rr['hit_at3']['valor']} "
                          f"cobertura={rr['cobertura']['valor']}")
    return "\n".join(lineas)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--salida", type=Path, default=SALIDA_DEFECTO)
    ap.add_argument("--datos", type=Path, default=DATOS_DIR)
    ap.add_argument("--semilla", type=int, default=SEMILLA)
    ap.add_argument("--remuestreos", type=int, default=REMUESTREOS)
    args = ap.parse_args(argv)

    resultado = ejecutar(args.datos, args.semilla, args.remuestreos)
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(resumen_texto(resultado))
    print(f"\nResultados escritos en {args.salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

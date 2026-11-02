"""Tests de los backtests de demanda/reabastecimiento y de reglas de asociación.

Rápidos y deterministas: las funciones de métricas se prueban con ejemplos
calculados a mano, la partición temporal con datos en línea, y los CSV reales
de eval/datos_demo solo se usan para comprobar la forma de las salidas y que
los scripts no cambian los datos ni dependen del azar.
"""
import hashlib
import json
import math
from datetime import date, datetime
from pathlib import Path

import pytest

from app.asociacion import reglas
from app.demanda import forecast
from eval import backtest_asociacion as ba
from eval import backtest_demanda as bd

DATOS = Path(bd.DATOS_DIR)
hay_datos = pytest.mark.skipif(not (DATOS / "ventas_lineas.csv").exists(),
                               reason="eval/datos_demo no está disponible")

REMUESTREOS_RAPIDOS = 40


def _dt(texto: str) -> datetime:
    return datetime.fromisoformat(texto)


def _escribir_csv(ruta: Path, cabecera: list[str], filas: list[list]):
    lineas = [",".join(f'"{c}"' for c in cabecera)]
    lineas += [",".join("" if v is None else f'"{v}"' for v in fila) for fila in filas]
    ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8")


def _sha(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


# ── Métricas de pronóstico (cálculo a mano) ──────────────────────────────────

def test_metricas_error_con_ejemplo_calculado_a_mano():
    # reales [0,2,4], pronósticos [1,2,2] -> errores [+1, 0, -2]
    m = bd.metricas_error([0, 2, 4], [1, 2, 2])
    assert m["n"] == 3
    assert m["mae"] == pytest.approx(1.0)
    assert m["rmse"] == pytest.approx(math.sqrt(5 / 3))
    assert m["wape"] == pytest.approx(3 / 6)
    # sMAPE: (2*1/1 + 0 + 2*2/6)/3 = 0.8889 -> 88.89 %
    assert m["smape"] == pytest.approx(100 * (2 + 0 + 4 / 6) / 3)


def test_smape_trata_ceros_de_forma_explicita():
    assert bd.termino_smape(0, 0) == 0.0          # acierto, no 0/0
    assert bd.termino_smape(0, 3) == 2.0          # máximo error posible
    assert bd.termino_smape(5, 0) == 2.0
    assert bd.termino_smape(4, 2) == pytest.approx(2 * 2 / 6)


def test_wape_indefinido_cuando_no_hay_demanda_real():
    m = bd.metricas_error([0, 0], [0, 0])
    assert m["mae"] == 0.0 and m["smape"] == 0.0
    assert m["wape"] is None


def test_intervalo_bootstrap_es_reproducible_con_semilla_fija():
    a = bd.indices_bootstrap(7, 10, 25)
    b = bd.indices_bootstrap(7, 10, 25)
    assert (a == b).all()
    assert a.shape == (25, 10) and a.min() >= 0 and a.max() < 10
    assert not (a == bd.indices_bootstrap(8, 10, 25)).all()


def test_intervalo_ignora_indefinidos_y_ordena_extremos():
    assert bd.intervalo([float("nan")]) is None
    lo, hi = bd.intervalo(list(range(101)))
    assert lo == pytest.approx(2.5) and hi == pytest.approx(97.5)


# ── Líneas base y alineación con el modelo del repositorio ───────────────────

def test_pronosticos_en_origen_calculados_a_mano():
    historia = [0.0, 2.0, 4.0, 6.0, 0.0]
    pred = {"demanda_semanal_estimada": 1.5}
    p = bd.pronosticos_en_origen(historia, pred)
    assert p["modelo_repo"] == 1.5
    assert p["naive_ultima_semana"] == 0.0
    assert p["media_4_semanas"] == pytest.approx(3.0)
    assert p["media_historia"] == pytest.approx(2.4)
    assert p["mediana_historia"] == 2.0
    # pesos 1..5: (0*1 + 2*2 + 4*3 + 6*4 + 0*5) / 15
    assert p["modelo_repo_sin_relleno"] == pytest.approx(40 / 15)


def test_prediccion_repo_alinea_semanas_iso_con_los_cubos_del_modelo():
    # Lunes 2026-01-05 y domingo 2026-01-11 son la misma semana ISO.
    dias = {date(2026, 1, 5): 3.0, date(2026, 1, 11): 2.0, date(2026, 1, 14): 4.0}
    pred = bd.prediccion_repo(dias, date(2026, 1, 11))
    assert pred["semanas"][-1] == 5.0
    assert sum(pred["semanas"]) == 5.0              # lo posterior al origen no entra
    n = forecast.DIAS_HISTORIAL // forecast.DIAS_POR_SEMANA
    assert pred["demanda_semanal_estimada"] == pytest.approx(round(5.0 * n / (n * (n + 1) / 2), 2))


def test_prediccion_repo_no_ve_el_futuro():
    base = {date(2026, 1, 5): 3.0}
    con_futuro = {**base, date(2026, 1, 20): 99.0}
    a = bd.prediccion_repo(base, date(2026, 1, 11))
    b = bd.prediccion_repo(con_futuro, date(2026, 1, 11))
    assert a["semanas"] == b["semanas"]
    assert a["demanda_semanal_estimada"] == b["demanda_semanal_estimada"]


def test_hoy_fijo_restaura_forecast_date():
    original = forecast.date
    with bd.hoy_fijo(date(2020, 2, 2)):
        assert forecast.date.today() == date(2020, 2, 2)
    assert forecast.date is original
    assert forecast.date.today() == original.today()


def test_generar_casos_cuenta_origenes_por_horizonte():
    # 8 semanas consecutivas
    lunes = [date.fromordinal(date(2026, 1, 5).toordinal() + 7 * i) for i in range(8)]
    serie = {1: [0.0, 1.0, 0.0, 2.0, 0.0, 3.0, 1.0, 5.0]}
    h1 = bd.generar_casos(serie, {1: {}}, lunes, min_historia=4, horizonte=1)
    h2 = bd.generar_casos(serie, {1: {}}, lunes, min_historia=4, horizonte=2)
    assert [c["origen"] for c in h1] == [3, 4, 5, 6]
    assert [c["origen"] for c in h2] == [3, 4, 5]
    assert [c["real"] for c in h1] == [0.0, 3.0, 1.0, 5.0]       # serie[origen + 1]
    assert [c["real"] for c in h2] == [3.0, 1.0, 5.0]            # serie[origen + 2]
    assert set(h1[0]["pronosticos"]) == set(bd.MODELOS)


# ── Datos: anuladas excluidas ────────────────────────────────────────────────

def _carpeta_minima(tmp_path: Path) -> Path:
    cab_v = ["VENTA_ID", "FECHA_LOCAL", "ESTADO", "CLIENTE_ID", "USUARIO_ID",
             "REPUESTO_ID", "CANTIDAD", "PRECIO_UNIT"]
    _escribir_csv(tmp_path / "ventas_lineas.csv", cab_v, [
        [1, "2026-01-05 10:00:00", "completada", None, 1, 10, 2, 100],
        [1, "2026-01-05 10:00:00", "completada", None, 1, 11, 1, 100],
        [2, "2026-01-06 10:00:00", "anulada", None, 1, 10, 50, 100],
        [3, "2026-01-13 10:00:00", "completada", None, 1, 10, 4, 100],
    ])
    _escribir_csv(tmp_path / "pedidos_lineas.csv",
                  ["PEDIDO_ID", "ESTADO", "FECHA_LOCAL", "RECIBIDO_LOCAL", "REPUESTO_ID",
                   "CANTIDAD", "PRECIO_UNIT"],
                  [[1, "recibido", "2026-01-07 08:00:00", "2026-01-09 08:00:00", 10, 5, 10],
                   [2, "cancelado", "2026-01-08 08:00:00", None, 11, 9, 10]])
    _escribir_csv(tmp_path / "repuestos.csv",
                  ["ID", "CODIGO", "NOMBRE", "DESCRIPCION", "CATEGORIA", "PROVEEDOR",
                   "PRECIO_COMPRA", "PRECIO_VENTA", "STOCK", "STOCK_MINIMO", "ACTIVO"],
                  [[10, "A", "a", "a", "Filtros", "p", 1, 2, 10, 3, 1],
                   [11, "B", "b", "b", "Frenos", "p", 1, 2, 7, 2, 1]])
    return tmp_path


def test_cargar_datos_excluye_ventas_anuladas(tmp_path):
    datos = bd.cargar_datos(_carpeta_minima(tmp_path))
    assert datos["lineas_anuladas"] == 1
    assert len(datos["ventas"]) == 3
    assert sum(v["cantidad"] for v in datos["ventas"] if v["repuesto_id"] == 10) == 6  # sin los 50
    series = bd.demanda_semanal(datos["ventas"], bd.semanas_iso(datos["ventas"]))
    assert series[10] == [2.0, 4.0]


def test_cargar_ventas_de_asociacion_excluye_anuladas_y_agrupa(tmp_path):
    ventas = ba.cargar_ventas(_carpeta_minima(tmp_path))
    assert [v["venta_id"] for v in ventas] == [1, 3]               # la 2 estaba anulada
    assert ventas[0]["items"] == {10, 11}


# ── Línea de tiempo de stock y señal ─────────────────────────────────────────

def test_reconstruir_stock_cierra_en_el_stock_actual(tmp_path):
    datos = bd.cargar_datos(_carpeta_minima(tmp_path))
    linea = bd.reconstruir_stock(datos, date(2026, 1, 5), 14)
    a = linea[10]
    # vendido 2 (día 0) y 4 (día 8); recibido 5 (día 4); stock actual 10
    assert a["inicial"] == 10 + 6 - 5
    assert a["fin_de_dia"][0] == 11 - 2
    assert a["fin_de_dia"][4] == 9 + 5
    assert a["fin_de_dia"][-1] == 10
    assert linea[11]["inicial"] == 7 + 1                           # el pedido 2 está cancelado
    assert linea[11]["fin_de_dia"][-1] == 7


def test_en_transito_descuenta_recibidos_y_cancelados(tmp_path):
    datos = bd.cargar_datos(_carpeta_minima(tmp_path))
    antes = datetime(2026, 1, 8, 23, 59)
    despues = datetime(2026, 1, 9, 23, 59)
    assert bd.en_transito_al_cierre(datos["pedidos"], 10, antes) == 5
    assert bd.en_transito_al_cierre(datos["pedidos"], 10, despues) == 0
    assert bd.en_transito_al_cierre(datos["pedidos"], 11, despues) == 0   # cancelado


def test_evento_en_ventana_detecta_minimo_y_agotamiento():
    stock = [10, 8, 6, 4, 2, 0, 0]
    assert bd.evento_en_ventana(stock, minimo=5, o=0, dias=6) == (3, 5)
    assert bd.evento_en_ventana(stock, minimo=5, o=0, dias=2) == (None, None)
    assert bd.evento_en_ventana([10, 10, 10], minimo=0, o=0, dias=2) == (None, None)


def test_precision_recall_calculados_a_mano():
    pr = bd.precision_recall({"tp": 2, "fp": 2, "fn": 1, "tn": 5})
    assert pr["precision"] == pytest.approx(0.5)
    assert pr["recall"] == pytest.approx(2 / 3, abs=1e-4)
    assert pr["f1"] == pytest.approx(2 * 0.5 * (2 / 3) / (0.5 + 2 / 3), abs=1e-3)
    vacio = bd.precision_recall({"tp": 0, "fp": 0, "fn": 0, "tn": 4})
    assert vacio["precision"] is None and vacio["recall"] is None


# ── Partición temporal y métricas de asociación ──────────────────────────────

def _ventas_lineales(n: int) -> list[dict]:
    return [{"venta_id": i, "fecha": datetime(2026, 1, 1 + i // 4, 8 + i % 4), "items": {i % 5, 7}}
            for i in range(n)]


def test_particion_temporal_sin_fuga():
    ventas = _ventas_lineales(40)
    entren, prueba = ba.dividir_temporal(ventas)
    assert entren and prueba
    assert len(entren) + len(prueba) == len(ventas)
    assert max(v["fecha"] for v in entren) < min(v["fecha"] for v in prueba)
    assert abs(len(entren) / len(ventas) - 0.7) < 0.05


def test_particion_con_marcas_de_tiempo_empatadas_no_filtra_futuro():
    mismo = datetime(2026, 1, 10, 12, 0)
    ventas = [{"venta_id": i, "fecha": mismo if i >= 6 else datetime(2026, 1, 1 + i), "items": {1, 2}}
              for i in range(10)]
    entren, prueba = ba.dividir_temporal(ventas)
    assert max(v["fecha"] for v in entren) < min(v["fecha"] for v in prueba)
    assert {v["venta_id"] for v in ventas if v["fecha"] == mismo} <= {v["venta_id"] for v in prueba}


def test_particion_ignora_el_orden_de_entrada():
    ventas = _ventas_lineales(30)
    a = ba.dividir_temporal(ventas)
    b = ba.dividir_temporal(list(reversed(ventas)))
    assert [v["venta_id"] for v in a[0]] == [v["venta_id"] for v in b[0]]
    assert [v["venta_id"] for v in a[1]] == [v["venta_id"] for v in b[1]]


def test_casos_de_prueba_solo_ventas_multi_producto():
    prueba = [{"venta_id": 1, "fecha": datetime(2026, 1, 1), "items": {1, 2, 3}},
              {"venta_id": 2, "fecha": datetime(2026, 1, 2), "items": {4}}]
    casos = ba.casos_de_prueba(prueba)
    assert [(c[1], sorted(c[2])) for c in casos] == [(1, [2, 3]), (2, [1, 3]), (3, [1, 2])]


def test_medidas_calculadas_a_mano():
    m = ba._medidas([5, 6, 7], {6}, lifts=[2.0, 1.5, 1.2])
    assert m["hit"] == 1 and m["servido"] == 1
    assert m["prec"] == pytest.approx(1 / 3)
    assert m["prec_servidos"] == pytest.approx(1 / 3)
    assert m["lift"] == pytest.approx(4.7) and m["n_recs"] == 3
    sin = ba._medidas([], {6})
    assert sin["hit"] == 0 and sin["servido"] == 0 and sin["prec_servidos"] == 0.0


def test_metricas_desde_sumas_asociacion():
    # 4 casos: 2 aciertos, 3 servidos (2 aciertos), precision acumulada 2/3
    s = [4, 2, 2 / 3 * 1, 3, 2, 2 / 3 * 1.5, 7.0, 3]
    m = ba.metricas_desde_sumas(s)
    assert m["hit_at3"] == pytest.approx(0.5)
    assert m["cobertura"] == pytest.approx(0.75)
    assert m["hit_at3_servidos"] == pytest.approx(2 / 3)
    assert m["lift_medio_servido"] == pytest.approx(7.0 / 3)


CATEGORIAS = {1: "A", 2: "A", 3: "B", 4: "B", 5: "C", 6: "C"}


def _venta(i, items, dia):
    return {"venta_id": i, "fecha": datetime(2026, 1, dia), "items": set(items)}


def test_evaluar_metodos_con_reglas_que_si_aplican():
    # 1 y 2 se venden juntos 3 veces: soporte 3, confianza 1, lift 7/3 > 1.
    entren = [_venta(1, {1, 2}, 1), _venta(2, {1, 2}, 2), _venta(3, {1, 2}, 3),
              _venta(4, {3}, 4), _venta(5, {4}, 5), _venta(6, {5}, 6), _venta(7, {6}, 7)]
    prueba = [_venta(8, {1, 2}, 20)]
    por_metodo = ba.evaluar_metodos(entren, prueba, CATEGORIAS, semilla=1)
    res = ba.resumir(por_metodo, semilla=1, remuestreos=20)
    assert res["n_casos"] == 2 and res["n_ventas_evaluadas"] == 1
    reglas_repo = res["metodos"]["reglas_repo"]
    assert reglas_repo["hit_at3"]["valor"] == 1.0
    assert reglas_repo["cobertura"]["valor"] == 1.0
    assert reglas_repo["lift_medio_servido"]["valor"] == pytest.approx(2.333, abs=1e-3)
    assert res["metodos"]["populares_top3"]["hit_at3"]["valor"] == 1.0
    assert res["metodos"]["misma_categoria_top3"]["hit_at3"]["valor"] == 1.0   # 1 y 2: categoría A
    assert 0.0 <= res["metodos"]["aleatorio_semilla_fija"]["hit_at3"]["valor"] <= 1.0


def test_recomendadores_base_excluyen_el_carrito_y_respetan_categoria():
    pop = ba.Counter({1: 5, 2: 4, 3: 3, 4: 9})
    assert ba._top_popular(pop, {4}) == [1, 2, 3]
    assert ba.recomendar_categoria(pop, CATEGORIAS, 1) == [2]            # único de la categoría A
    assert ba.recomendar_categoria(pop, CATEGORIAS, 99) == []
    rng = ba.np.random.default_rng(0)
    azar = ba.recomendar_azar(sorted(CATEGORIAS), 1, rng, sorteos=50)
    assert azar.shape == (50, 3)
    assert 1 not in azar
    assert all(len(set(fila)) == 3 for fila in azar)
    # Con un catalogo de 5 candidatos y 1 de verdad, P(hit) = 3/5.
    m = ba.medidas_azar(sorted(CATEGORIAS), 1, {2}, ba.np.random.default_rng(0), sorteos=4000)
    assert m["hit"] == pytest.approx(0.6, abs=0.03)


def test_modelo_precalculado_equivale_a_recalcular_en_cada_llamada():
    canastas = [[1, 2], [1, 2], [1, 2, 3], [3, 4], [3, 4], [5], [6], [1, 5]]
    esperado = {c: reglas.recomendar_complementos(canastas, [c], limite=3) for c in range(1, 7)}
    original = reglas.calcular_reglas
    with ba.modelo_precalculado(canastas):
        obtenido = {c: reglas.recomendar_complementos(canastas, [c], limite=3) for c in range(1, 7)}
    assert obtenido == esperado
    assert reglas.calcular_reglas is original


def test_soporte_minimo_se_restaura_tras_la_sensibilidad():
    original = reglas.SOPORTE_MINIMO
    with ba.soporte_minimo(1):
        assert reglas.SOPORTE_MINIMO == 1
    assert reglas.SOPORTE_MINIMO == original
    entren = [_venta(i, {1, 2}, 1 + i) for i in range(4)]
    prueba = [_venta(9, {1, 2}, 25)]
    ba.sensibilidad(entren, prueba, CATEGORIAS, semilla=3, remuestreos=10)
    assert reglas.SOPORTE_MINIMO == original


def test_bootstrap_de_asociacion_es_determinista():
    entren = [_venta(i, {1, 2} if i % 2 else {3, 4}, 1 + i) for i in range(8)]
    prueba = [_venta(20 + i, {1, 2}, 20 + i) for i in range(4)]
    a = ba.resumir(ba.evaluar_metodos(entren, prueba, CATEGORIAS, 5), 5, 30)
    b = ba.resumir(ba.evaluar_metodos(entren, prueba, CATEGORIAS, 5), 5, 30)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


# ── Scripts sobre los CSV reales: forma, determinismo e inmutabilidad ────────

CLAVES_DEMANDA = {"metadatos", "demanda", "reabastecimiento", "limitaciones"}
CLAVES_ASOCIACION = {"metadatos", "particion", "resultados", "sensibilidad_soporte_minimo",
                     "limitaciones"}


def _serializar(resultado: dict) -> bytes:
    """Mismo formato que escriben los scripts en --salida."""
    return (json.dumps(resultado, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


@pytest.fixture(scope="module")
def resultado_demanda():
    return bd.ejecutar(remuestreos=REMUESTREOS_RAPIDOS)


@pytest.fixture(scope="module")
def resultado_asociacion():
    return ba.ejecutar(remuestreos=REMUESTREOS_RAPIDOS)


@hay_datos
def test_backtest_demanda_forma_de_la_salida(resultado_demanda):
    r = resultado_demanda
    assert set(r) == CLAVES_DEMANDA
    assert r["limitaciones"] and all(isinstance(x, str) for x in r["limitaciones"])
    for h in ("horizonte_1", "horizonte_2"):
        bloque = r["demanda"][h]
        assert {"n_casos", "global", "top20", "comparacion_pareada"} <= set(bloque)
        assert set(bloque["global"]) == set(bd.MODELOS)
        for modelo in bd.MODELOS:
            for metrica in ("mae", "rmse", "wape", "smape"):
                assert {"valor", "ic95"} == set(bloque["global"][modelo][metrica])
        assert set(bloque["comparacion_pareada"]) == {f"modelo_repo_vs_{b}" for b in bd.BASELINES}
        assert len(bloque["top20"]["productos"]) == bd.TOP_N
    reab = r["reabastecimiento"]
    assert {"clasificacion", "margen_de_anticipacion", "adecuacion_de_cantidad",
            "reconstruccion_stock", "por_semana"} <= set(reab)
    assert reab["reconstruccion_stock"]["stock_inicial_negativo"] == 0
    assert "senal_reabastecer" in reab["clasificacion"]["bajo_minimo_14d"]


@hay_datos
def test_backtest_demanda_excluye_ventas_anuladas_en_datos_reales():
    datos = bd.cargar_datos(DATOS)
    assert datos["lineas_anuladas"] > 0
    assert len(datos["ventas"]) + datos["lineas_anuladas"] == sum(
        1 for _ in open(DATOS / "ventas_lineas.csv", encoding="utf-8-sig")) - 1


@hay_datos
def test_backtest_demanda_es_determinista_y_no_toca_los_datos(tmp_path, resultado_demanda):
    antes = {p.name: _sha(p) for p in DATOS.glob("*.csv")}
    salida = tmp_path / "demanda.json"
    assert bd.main(["--salida", str(salida), "--remuestreos", str(REMUESTREOS_RAPIDOS)]) == 0
    # Segunda ejecución independiente (la del fixture): mismos bytes.
    assert salida.read_bytes() == _serializar(resultado_demanda)
    json.loads(salida.read_text(encoding="utf-8"))
    assert {p.name: _sha(p) for p in DATOS.glob("*.csv")} == antes


@hay_datos
def test_backtest_asociacion_forma_y_particion_sin_fuga(resultado_asociacion):
    r = resultado_asociacion
    assert set(r) == CLAVES_ASOCIACION
    assert r["limitaciones"]
    p = r["particion"]
    assert p["entrenamiento"]["fecha_ultima"] < p["prueba"]["fecha_primera"]
    assert p["entrenamiento"]["ventas_multi_producto"] <= p["entrenamiento"]["ventas"]
    assert set(r["resultados"]["metodos"]) == set(ba.METODOS)
    for metodo in ba.METODOS:
        m = r["resultados"]["metodos"][metodo]
        assert {"hit_at3", "precision_at3", "cobertura", "lift_medio_servido"} <= set(m)
        assert 0.0 <= m["hit_at3"]["valor"] <= 1.0
        lo, hi = m["hit_at3"]["ic95"]
        assert lo <= hi
    assert set(r["resultados"]["comparacion_pareada"]) == {f"reglas_repo_vs_{b}" for b in ba.BASELINES}
    assert set(r["sensibilidad_soporte_minimo"]) == {f"soporte_minimo_{s}" for s in ba.SOPORTES_SENSIBILIDAD}


@hay_datos
def test_backtest_asociacion_es_determinista_y_no_toca_los_datos(tmp_path, resultado_asociacion):
    antes = {p.name: _sha(p) for p in DATOS.glob("*.csv")}
    salida = tmp_path / "asociacion.json"
    assert ba.main(["--salida", str(salida), "--remuestreos", str(REMUESTREOS_RAPIDOS)]) == 0
    assert salida.read_bytes() == _serializar(resultado_asociacion)
    assert reglas.SOPORTE_MINIMO == 2
    assert {p.name: _sha(p) for p in DATOS.glob("*.csv")} == antes


@hay_datos
def test_particion_real_solo_con_ventas_completadas():
    ventas = ba.cargar_ventas(DATOS)
    entren, prueba = ba.dividir_temporal(ventas)
    ids_anuladas = set()
    ids_completas = set()
    import csv
    with open(DATOS / "ventas_lineas.csv", encoding="utf-8-sig", newline="") as f:
        for fila in csv.DictReader(f):
            (ids_completas if fila["ESTADO"] == "completada" else ids_anuladas).add(int(fila["VENTA_ID"]))
    usados = {v["venta_id"] for v in entren + prueba}
    assert usados <= ids_completas
    assert max(v["fecha"] for v in entren) < min(v["fecha"] for v in prueba)

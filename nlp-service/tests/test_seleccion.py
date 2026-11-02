"""Herramientas de selección del modelo de intención (app/intent/seleccion.py) y marcador <vehiculo>."""
import numpy as np
import pytest

from app.intent import modelos, seleccion as S
from app.preprocessing import (
    MARCADOR_VEHICULO,
    enmascarar_vehiculos,
    normalizar,
    preprocesar,
    preprocesar_busqueda,
    preprocesar_intencion,
    tokenizar,
)


# ---------------------------------------------------------------- marcador de vehículo
def test_los_nombres_de_vehiculo_se_reemplazan_por_un_marcador():
    assert preprocesar_intencion("¿Hay filtro de aceite para Toyota Hilux 2024?") == [
        "filtro", "aceite", MARCADOR_VEHICULO, "2024"]


def test_marca_y_modelo_seguidos_dan_un_solo_marcador():
    assert enmascarar_vehiculos(tokenizar(normalizar("john deere 5075e"))).count(MARCADOR_VEHICULO) == 1
    assert enmascarar_vehiculos(tokenizar(normalizar("mazda 3 2020"))) == [MARCADOR_VEHICULO, "2020"]


def test_palabras_ambiguas_solo_cuentan_junto_a_su_marca():
    assert MARCADOR_VEHICULO not in preprocesar_intencion("tubo de escape")
    assert MARCADOR_VEHICULO in preprocesar_intencion("ford escape 2015")
    assert MARCADOR_VEHICULO not in preprocesar_intencion("dame 3 filtros")
    assert MARCADOR_VEHICULO not in preprocesar_intencion("hubo un gol")


def test_el_preprocesamiento_de_siempre_no_cambia():
    assert preprocesar("¿Hay filtro para Hilux?") == ["filtro", "hilux"]


def test_el_ranking_unifica_plurales_y_viscosidades():
    assert preprocesar_busqueda("llantas para el Accent") == preprocesar_busqueda("Llanta para el Accent")
    assert preprocesar_busqueda("aceite 5w30") == preprocesar_busqueda("Aceite Mobil 5W-30")[:1] + ["5w30"]
    assert "disco" in preprocesar_busqueda("discos de freno")


# ---------------------------------------------------------------- grupos y pliegues
def test_grupos_unen_esqueleto_y_mismo_multiconjunto():
    textos = ["cuanto cuesta el filtro", "cuanto cuesta la bateria", "precio de la bateria", "bateria de la precio",
              "hola buenas"]
    g = S.grupos_casi_duplicados(textos)
    assert g[0] == g[1]          # mismo esqueleto "cuanto cuesta"
    assert g[2] == g[3]          # mismas palabras en otro orden
    assert len({g[0], g[2], g[4]}) == 3


def test_pliegues_agrupados_nunca_separan_un_grupo():
    y = np.array(["a", "b"] * 60)
    grupos = np.repeat(np.arange(24), 5)
    for _, _, tr, te in S.generar_pliegues("agrupada", y, grupos, repeticiones=2):
        assert not set(grupos[tr]) & set(grupos[te])
    assert len(S.generar_pliegues("normal", y, repeticiones=3)) == 15


def test_los_pliegues_son_deterministas():
    y = np.array(["a", "b", "c"] * 40)
    a = S.generar_pliegues("normal", y, repeticiones=2)
    b = S.generar_pliegues("normal", y, repeticiones=2)
    assert all((x[3] == z[3]).all() for x, z in zip(a, b))


# ---------------------------------------------------------------- umbral y métricas
def test_predecir_con_umbral_manda_lo_dudoso_a_fuera_de_dominio():
    clases = ["buscar_repuesto", "fuera_de_dominio"]
    proba = np.array([[0.6, 0.4], [0.9, 0.1]])
    assert list(S.predecir_con_umbral(proba, clases, 0.7)) == [1, 0]
    assert list(S.predecir_con_umbral(proba, clases, 0.5)) == [0, 0]


INTENCIONES = ["buscar_repuesto", "consultar_compatibilidad", "consultar_precio", "consultar_stock",
               "fuera_de_dominio", "recomendar_sustituto", "saludo_despedida"]


def test_metricas_de_c3_y_c4():
    buscar, fuera, sust, saludo = (INTENCIONES.index(c) for c in
                                   ("buscar_repuesto", "fuera_de_dominio", "recomendar_sustituto", "saludo_despedida"))
    y = np.array([sust] * 4 + [fuera] * 4)
    pred = np.array([sust, sust, sust, buscar, fuera, buscar, saludo, fuera])
    m = S.metricas_de_prediccion(y, pred, INTENCIONES)
    assert m["recall_recomendar_sustituto"] == 0.75
    assert m["fuera_tratado_como_no_fuera"] == 0.5      # una a buscar_repuesto, una a saludo
    assert m["fuera_tratado_como_negocio"] == 0.25      # solo la de buscar_repuesto


def test_comparacion_pareada_detecta_una_mejora_consistente():
    def corrida(f1s):
        return {"por_pliegue": [{"f1_macro": f, "accuracy": f} for f in f1s]}

    base = corrida([0.80 + 0.001 * i for i in range(50)])
    mejor = corrida([0.83 + 0.001 * i for i in range(50)])
    c = S.comparar_pareado(mejor, base, "f1_macro")
    assert c["diferencia_media"] == pytest.approx(0.03) and c["gana_en"] == 50 and c["p_corregido"] < 0.001
    igual = S.comparar_pareado(base, base, "f1_macro")
    assert igual["diferencia_media"] == 0 and igual["p_corregido"] == 1.0


def _entrada(dif, gana, p):
    return {"vs_referencia": {"diferencia_media": dif, "gana_en": gana, "n_pliegues": 50, "p_corregido": p}}


def test_el_modelo_mas_simple_se_conserva_si_nadie_gana_en_las_dos_validaciones():
    tabla = {
        "base": {"normal": _entrada(0, 0, 1), "agrupada": _entrada(0, 0, 1), "tiene_probabilidades": True},
        "solo_normal": {"normal": _entrada(0.03, 48, 0.001), "agrupada": _entrada(0.002, 30, 0.5), "tiene_probabilidades": True},
    }
    assert S.elegir_modelo(tabla, "base")["elegido"] == "base"


def test_un_modelo_claramente_mejor_en_ambas_validaciones_reemplaza_al_simple():
    tabla = {
        "base": {"normal": _entrada(0, 0, 1), "agrupada": _entrada(0, 0, 1), "tiene_probabilidades": True},
        "mejor": {"normal": _entrada(0.03, 48, 0.001), "agrupada": _entrada(0.02, 45, 0.01), "tiene_probabilidades": True},
        "sin_proba": {"normal": _entrada(0.05, 50, 0.0), "agrupada": _entrada(0.05, 50, 0.0), "tiene_probabilidades": False},
    }
    d = S.elegir_modelo(tabla, "base")
    assert d["elegido"] == "mejor"
    assert "sin_proba" in d["no_elegidos"]


def test_elegir_umbral_toma_el_menor_que_cumple_c4_en_ambas_validaciones():
    buscar, fuera = INTENCIONES.index("buscar_repuesto"), INTENCIONES.index("fuera_de_dominio")
    y_idx = np.array([fuera] * 10 + [buscar] * 10)
    proba = np.zeros((2, 20, 7))
    for rep in range(2):
        for i in range(10):          # fuera de dominio, pero el modelo duda: confianza en 'buscar' de 0.50 a 0.95
            p = 0.5 + 0.05 * i
            proba[rep, i, buscar], proba[rep, i, fuera] = p, 1 - p
        proba[rep, 10:, buscar] = 0.95
        proba[rep, 10:, fuera] = 0.05
    corrida = {"clases": np.array(INTENCIONES), "y_idx": y_idx, "proba": proba, "pred": proba.argmax(axis=2)}
    e = S.elegir_umbral({"normal": corrida, "agrupada": corrida}, [0.5, 0.6, 0.7, 0.8, 0.9, 1.0], max_fuera_como_negocio=0.2)
    assert e["umbral_elegido"] == 0.9


# ---------------------------------------------------------------- candidatos
def test_cada_candidato_es_un_pipeline_con_tfidf_y_clasificador():
    for nombre in modelos.CANDIDATOS:
        m = modelos.construir(nombre)
        assert list(m.named_steps) == ["tfidf", "clf"], nombre
    assert modelos.NOMBRE_PRODUCCION in modelos.CANDIDATOS and modelos.NOMBRE_REFERENCIA in modelos.CANDIDATOS


def test_un_pliegue_corre_y_devuelve_prediccion_por_cada_frase_de_prueba():
    textos = np.array(["hola buenas", "buenos dias", "cuanto cuesta el filtro", "precio de la bateria"] * 10, dtype=object)
    y = np.array(["saludo", "saludo", "precio", "precio"] * 10)
    pliegues = S.generar_pliegues("normal", y, repeticiones=1, partes=5)
    c = S.correr_cv("lr_c15", textos, y, pliegues, n_jobs=1)
    assert c["pred"].shape == (1, 40) and c["proba"].shape == (1, 40, 2)
    assert S.resumen_pliegues(c)["accuracy"]["media"] > 0.9

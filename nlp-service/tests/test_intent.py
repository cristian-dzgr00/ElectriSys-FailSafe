import joblib
import pytest

from app.intent import train
from app.intent.classifier import INTENCION_FALLBACK, UMBRAL_CONFIANZA, predecir_intencion
from app.intent.train import entrenar


@pytest.fixture(scope="module")
def entrenado(tmp_path_factory):
    """Entrena una vez para todo el módulo, en un directorio temporal.

    Antes esta prueba llamaba a entrenar() sin argumentos y sobrescribía el modelo
    real (models/intent_classifier.pkl, que se sirve) y models/metrics_intent.json
    (que está versionado) cada vez que se corría pytest.
    """
    destino = tmp_path_factory.mktemp("modelo_intencion")
    metricas = entrenar(model_path=destino / "modelo.pkl", metrics_path=destino / "metricas.json")
    return metricas, joblib.load(destino / "modelo.pkl"), destino


@pytest.fixture(scope="module")
def metricas(entrenado):
    return entrenado[0]


@pytest.fixture(scope="module")
def modelo(entrenado):
    return entrenado[1]


def test_entrenar_no_toca_el_modelo_ni_las_metricas_reales(entrenado):
    _, _, destino = entrenado
    assert (destino / "modelo.pkl").exists() and (destino / "metricas.json").exists()
    # Los archivos reales solo cambian si entrenar() se llama sin rutas (python -m app.intent.train).
    assert train.MODEL_PATH.parent != destino and train.METRICS_PATH.parent != destino


def test_entrenar_devuelve_metricas_razonables(metricas):
    # Con 7 clases, adivinar al azar da ~14 % de accuracy. Con el dataset actual (más de
    # 2 000 frases) la validación cruzada da ~0.84; esta cota solo protege contra una
    # regresión grave del pipeline o del dataset, no exige el valor medido (esas cifras
    # y sus criterios de éxito están en eval/generar_cifras.py).
    assert metricas["accuracy"] >= 0.60, (
        f"Accuracy de validación cruzada demasiado baja ({metricas['accuracy']:.2f}); "
        "esto indicaría un problema real en el dataset o el pipeline"
    )
    assert metricas["f1_macro"] >= 0.60
    assert metricas["n_ejemplos"] >= 2000
    assert metricas["umbral_confianza"] == UMBRAL_CONFIANZA


def test_predecir_intencion_caso_recomendar_sustituto(modelo):
    intencion, confianza = predecir_intencion(
        "no hay filtro de aceite original de toyota para hilux 2.7 gasolina 2024, que recomiendo",
        pipeline=modelo,
    )
    assert intencion == "recomendar_sustituto"
    assert confianza >= UMBRAL_CONFIANZA


def test_predecir_intencion_caso_buscar_repuesto(modelo):
    intencion, _ = predecir_intencion("tienen filtro de aceite para toyota hilux 2024", pipeline=modelo)
    assert intencion == "buscar_repuesto"


def test_predecir_intencion_caso_saludo(modelo):
    intencion, _ = predecir_intencion("hola buenos dias", pipeline=modelo)
    assert intencion == "saludo_despedida"


def test_predecir_intencion_texto_ajeno_no_crashea(modelo):
    # No se exige una etiqueta exacta (con dataset chico sería poco confiable
    # e introduciría un test flaky) — solo que responda algo válido.
    intencion, confianza = predecir_intencion("cual es la capital de francia", pipeline=modelo)
    assert isinstance(intencion, str)
    assert 0.0 <= confianza <= 1.0


def test_predecir_intencion_no_crashea_con_texto_raro(modelo):
    intencion, confianza = predecir_intencion("????!!!! 😀😀😀 aaaaa", pipeline=modelo)
    assert isinstance(intencion, str)
    assert 0.0 <= confianza <= 1.0


# --- Pruebas deterministas del umbral de confianza, con un pipeline falso ---
# (no dependen del modelo real ni de su entrenamiento aleatorio)

class _PipelineFalsoConfianzaAlta:
    classes_ = ["intencion_a", "intencion_b"]

    def predict_proba(self, X):
        return [[0.2, 0.8]]


class _PipelineFalsoConfianzaBaja:
    classes_ = ["intencion_a", "intencion_b", "intencion_c"]

    def predict_proba(self, X):
        return [[0.34, 0.33, 0.33]]


def test_predecir_intencion_usa_la_clase_de_mayor_probabilidad():
    intencion, confianza = predecir_intencion("cualquier texto", pipeline=_PipelineFalsoConfianzaAlta())
    assert intencion == "intencion_b"
    assert confianza == 0.8


def test_predecir_intencion_cae_a_fallback_si_confianza_es_baja():
    intencion, confianza = predecir_intencion("cualquier texto", pipeline=_PipelineFalsoConfianzaBaja())
    assert intencion == INTENCION_FALLBACK
    assert confianza < UMBRAL_CONFIANZA

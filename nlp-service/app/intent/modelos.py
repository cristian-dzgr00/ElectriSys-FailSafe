"""Candidatos de modelo para el clasificador de intención.

Cada candidato es una fábrica de `Pipeline` (TF-IDF + clasificador) con un
nombre estable. Sirven para dos cosas:

  * `train._construir_pipeline()` arma el modelo de producción con
    `construir(NOMBRE_PRODUCCION)`;
  * `seleccion.py` los compara por validación cruzada (mismos pliegues para
    todos) y `eval/generar_cifras.py` publica la tabla.

Así la comparación y el servicio usan exactamente las mismas definiciones.
"""
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.naive_bayes import ComplementNB
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

from app.preprocessing import preprocesar, preprocesar_intencion

# Modelo que se sirve. Cambiarlo exige volver a correr `python eval/generar_cifras.py`,
# que comprueba que coincida con el elegido por validación cruzada.
NOMBRE_PRODUCCION = "lr_c15_vehiculo"

SEMILLA_MODELOS = 42


def _tfidf(ngramas=(1, 1), enmascarar=False) -> TfidfVectorizer:
    return TfidfVectorizer(
        tokenizer=preprocesar_intencion if enmascarar else preprocesar,
        token_pattern=None,  # requerido por sklearn al usar tokenizer propio
        ngram_range=ngramas,
        min_df=1,
    )


def _lr(c=15.0, class_weight=None) -> LogisticRegression:
    # solver="liblinear": da resultados ligeramente mejores que "lbfgs" en este
    # dataset y evita un warning de incompatibilidad scipy/sklearn
    # ("Unknown solver options: iprint") que el solver por defecto dispara.
    return LogisticRegression(max_iter=2000, C=c, solver="liblinear", class_weight=class_weight)


def _mlp(oculta: int) -> MLPClassifier:
    # Una sola capa oculta sobre las mismas características TF-IDF, con parada
    # temprana (10 % de validación interna) y semilla fija.
    return MLPClassifier(
        hidden_layer_sizes=(oculta,), early_stopping=True, validation_fraction=0.1,
        n_iter_no_change=10, max_iter=300, random_state=SEMILLA_MODELOS,
    )


# nombre -> (descripción corta, familia, fábrica). `familia` solo agrupa filas en la tabla.
CANDIDATOS = {
    "lr_c15": ("Regresión logística C=15, unigramas (configuración previa)", "lineal",
               lambda: Pipeline([("tfidf", _tfidf()), ("clf", _lr(15))])),
    "lr_c15_vehiculo": ("Regresión logística C=15, unigramas, con marcador <vehiculo>", "lineal",
                        lambda: Pipeline([("tfidf", _tfidf(enmascarar=True)), ("clf", _lr(15))])),
    "lr_c1": ("Regresión logística C=1", "lineal",
              lambda: Pipeline([("tfidf", _tfidf()), ("clf", _lr(1))])),
    "lr_c5": ("Regresión logística C=5", "lineal",
              lambda: Pipeline([("tfidf", _tfidf()), ("clf", _lr(5))])),
    "lr_c50": ("Regresión logística C=50", "lineal",
               lambda: Pipeline([("tfidf", _tfidf()), ("clf", _lr(50))])),
    "lr_c100": ("Regresión logística C=100", "lineal",
                lambda: Pipeline([("tfidf", _tfidf()), ("clf", _lr(100))])),
    "lr_c15_bigramas": ("Regresión logística C=15, unigramas + bigramas", "lineal",
                        lambda: Pipeline([("tfidf", _tfidf((1, 2))), ("clf", _lr(15))])),
    "lr_c15_balanceado": ("Regresión logística C=15, class_weight=balanced", "lineal",
                          lambda: Pipeline([("tfidf", _tfidf()), ("clf", _lr(15, "balanced"))])),
    "nb_complemento": ("Naive Bayes complementario (alpha=0.3)", "bayes",
                       lambda: Pipeline([("tfidf", _tfidf()), ("clf", ComplementNB(alpha=0.3))])),
    "svm_lineal": ("LinearSVC C=1 (sin probabilidades)", "lineal",
                   lambda: Pipeline([("tfidf", _tfidf()), ("clf", LinearSVC(C=1.0, random_state=SEMILLA_MODELOS))])),
    "mlp_64": ("MLP 1 capa oculta de 64", "red",
               lambda: Pipeline([("tfidf", _tfidf()), ("clf", _mlp(64))])),
    "mlp_128": ("MLP 1 capa oculta de 128", "red",
                lambda: Pipeline([("tfidf", _tfidf()), ("clf", _mlp(128))])),
    "mlp_256": ("MLP 1 capa oculta de 256", "red",
                lambda: Pipeline([("tfidf", _tfidf()), ("clf", _mlp(256))])),
}

# Modelo de referencia de las comparaciones pareadas: la configuración previa.
NOMBRE_REFERENCIA = "lr_c15"


def construir(nombre: str) -> Pipeline:
    return CANDIDATOS[nombre][2]()

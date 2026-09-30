"""Corrector de búsquedas del catálogo: "filtro acite" -> "filtro de aceite".

Un POS se usa con prisa y una mano: el cajero escribe mal y la búsqueda
devuelve cero resultados, que es la peor respuesta posible porque no
distingue "no existe" de "lo escribiste mal".

Corrige palabra por palabra contra el vocabulario real del catálogo, no
contra un diccionario del español. Así conoce "Fleetguard", "THHN" o
"M1-102", que ningún diccionario general tiene, y en cambio no propone
palabras que no llevan a ningún producto.

Usa RapidFuzz, el mismo motor que ya usa el NER del asistente
(ner/extractor.py) para reconocer marcas y modelos escritos con erratas.
"""
import logging
import re
import unicodedata

from rapidfuzz import fuzz, process

logger = logging.getLogger(__name__)

# Por debajo de esto la "corrección" es una palabra distinta, no un typo
# arreglado. Con 70 se aceptaría "aceite" cuando escribieron "aceros".
UMBRAL_PALABRA = 78

# Las palabras muy cortas no se corrigen: en 2-3 letras, cambiar una letra da
# puntajes altísimos contra cualquier cosa ("kit" -> "kia" tiene 67).
LARGO_MINIMO = 4

# Palabras que no aportan a la búsqueda y no vale la pena corregir.
VACIAS = {"de", "del", "la", "el", "los", "las", "para", "con", "por", "un", "una"}


def _normalizar(texto: str) -> str:
    """Minúsculas y sin tildes: 'Batería' y 'bateria' son la misma palabra
    para quien busca con prisa."""
    t = unicodedata.normalize("NFD", (texto or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def construir_vocabulario(productos: list[dict]) -> set:
    """Todas las palabras que aparecen en el catálogo, normalizadas."""
    vocabulario = set()
    for p in productos:
        campos = " ".join(str(p.get(c) or "") for c in ("nombre", "categoria", "codigo"))
        for palabra in re.findall(r"[\w\-]+", _normalizar(campos)):
            if len(palabra) >= 3:
                vocabulario.add(palabra)
    return vocabulario


def corregir(consulta: str, productos: list[dict]) -> dict:
    """Devuelve la consulta corregida, o la original si no hay nada que
    corregir o la corrección no es confiable.

    Nunca "inventa": si ninguna palabra supera el umbral, devuelve
    corregida=None y quien llama muestra el "sin resultados" de siempre.
    """
    vocabulario = construir_vocabulario(productos)
    if not vocabulario:
        return {"original": consulta, "corregida": None, "cambios": []}

    lista = list(vocabulario)
    palabras = re.findall(r"[\w\-]+", _normalizar(consulta))
    if not palabras:
        return {"original": consulta, "corregida": None, "cambios": []}

    corregidas = []
    cambios = []

    for palabra in palabras:
        # Ya existe en el catálogo: no se toca. Es clave para no "corregir"
        # un código de producto que el usuario escribió bien.
        if palabra in vocabulario or len(palabra) < LARGO_MINIMO or palabra in VACIAS:
            corregidas.append(palabra)
            continue

        mejor = process.extractOne(palabra, lista, scorer=fuzz.ratio)
        if mejor and mejor[1] >= UMBRAL_PALABRA:
            corregidas.append(mejor[0])
            cambios.append({"de": palabra, "a": mejor[0], "score": round(mejor[1], 1)})
        else:
            corregidas.append(palabra)

    if not cambios:
        return {"original": consulta, "corregida": None, "cambios": []}

    nueva = " ".join(corregidas)
    logger.info("Búsqueda corregida: %r -> %r", consulta, nueva)
    return {"original": consulta, "corregida": nueva, "cambios": cambios}

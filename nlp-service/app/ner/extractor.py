"""Extracción de entidades (NER híbrido: reglas + fuzzy matching).

Los diccionarios de marca/modelo/categoría se reciben como parámetro (ver
dictionary.py) en vez de ir a buscarlos aquí mismo — así estas funciones
son puras y se pueden probar con listas fijas, sin depender de que el
backend esté disponible.

Nota sobre normalización: para marca/modelo/categoría se usa el texto
normalizado (minúsculas, sin tildes, sin puntuación) porque el fuzzy
matching no depende de esos detalles. Para año y motor se usa el texto
ORIGINAL: normalizar() quita el punto de "2.7" (queda "2 7"), lo que
rompería la regex del motor.
"""
import re

from rapidfuzz import fuzz, process

from app.preprocessing import normalizar

UMBRAL_FUZZY = 85  # 0-100; token_set_ratio es permisivo, se exige bastante certeza

COMBUSTIBLES_SINONIMOS = {
    "gasolina": "gasolina", "nafta": "gasolina",
    "diesel": "diesel", "diésel": "diesel", "gasoil": "diesel", "gasoleo": "diesel",
    "hibrido": "hibrido", "híbrido": "hibrido", "hybrid": "hibrido",
    "electrico": "electrico", "eléctrico": "electrico", "electric": "electrico",
    "gas": "gas", "gnv": "gas",
}

# Casos donde la categoría correcta no se puede alcanzar por similitud de
# caracteres (ver docs/evaluacion.md, sección 2): "bujía" y "Encendido" son
# palabras sin parecido ortográfico, relacionadas solo por significado, y
# "correa de distribución" no matcheaba "Correas y Bandas" por ser singular
# vs. plural más una categoría de tres palabras (caso límite del fuzzy
# matching). Se resuelven por sinónimo directo, ANTES de intentar
# _mejor_match(), en vez de bajar el umbral fuzzy global (que degradaría
# la precisión de las demás categorías).
SINONIMOS_CATEGORIA = {
    "bujia": "Encendido",
    "bujias": "Encendido",
    "correa": "Correas y Bandas",
    "correas": "Correas y Bandas",
}

_RE_ANIO = re.compile(r"\b(19[5-9]\d|20[0-4]\d)\b")
_RE_MOTOR = re.compile(r"\b(\d\.\d)\b|\b(\d{3,4})\s?cc\b", re.IGNORECASE)
_RE_CODIGO = re.compile(r"\b[A-Za-z0-9]{1,10}-[A-Za-z0-9]{2,10}\b")


UMBRAL_FUZZY_TYPO = 88  # para comparación palabra-por-palabra (ver abajo)


def _mejor_match(texto_normalizado: str, opciones: list[str]) -> str | None:
    """Busca la opción del vocabulario que mejor aparece dentro del texto.

    Compara ambos lados ya normalizados (sin tildes/mayúsculas) — algunas
    categorías del catálogo llevan tilde ("Baterías", "Suspensión") y el
    texto del usuario no siempre la escribe — y devuelve la opción
    ORIGINAL (con su tilde/mayúscula real) para no alterar el dato tal
    como está en la base de datos.

    Dos pasadas, con propósitos distintos:
    1. token_set_ratio sobre la frase completa: bueno para vocabulario de
       varias palabras (ej. "Spark GT", "Correas y Bandas") y da pocos
       falsos positivos con nombres cortos (ej. "Kia", "3"), porque exige
       que el token aparezca casi tal cual.
    2. Si no hubo match, fuzz.ratio palabra por palabra: tolera errores de
       tipeo en una sola palabra (ej. "toyta" -> "Toyota"), algo que
       token_set_ratio no detecta bien cuando la palabra typo'd está
       insertada dentro de una frase larga (no hay overlap exacto de
       tokens, así que compara la palabra completa contra toda la frase
       y el score sale bajo). Se exige un umbral más estricto aquí y se
       ignoran palabras muy cortas (<4 letras) porque en ellas fuzz.ratio
       es más ruidoso (más falsos positivos).
    """
    if not opciones:
        return None
    opciones_normalizadas = {normalizar(o): o for o in opciones}
    claves = list(opciones_normalizadas.keys())

    resultado = process.extractOne(texto_normalizado, claves, scorer=fuzz.token_set_ratio)
    if resultado is not None and resultado[1] >= UMBRAL_FUZZY:
        return opciones_normalizadas[resultado[0]]

    mejor_valor, mejor_score = None, 0
    for palabra in texto_normalizado.split():
        if len(palabra) < 4:
            continue
        r = process.extractOne(palabra, claves, scorer=fuzz.ratio)
        if r is not None and r[1] > mejor_score:
            mejor_valor, mejor_score = r[0], r[1]

    if mejor_score >= UMBRAL_FUZZY_TYPO:
        return opciones_normalizadas[mejor_valor]

    return None


def extraer_marca(texto_normalizado: str, marcas_conocidas: list[str]) -> str | None:
    return _mejor_match(texto_normalizado, marcas_conocidas)


def extraer_modelo(texto_normalizado: str, modelos_conocidos: list[str]) -> str | None:
    return _mejor_match(texto_normalizado, modelos_conocidos)


def extraer_categoria(texto_normalizado: str, categorias_conocidas: list[str]) -> str | None:
    """Resuelve categoría por sinónimo directo primero; si no aplica, por
    fuzzy matching (_mejor_match).

    El sinónimo solo se usa si la categoría mapeada realmente está en
    categorias_conocidas (el catálogo real) — evita devolver una categoría
    que no existe en este negocio en particular.
    """
    for palabra, categoria in SINONIMOS_CATEGORIA.items():
        if palabra in texto_normalizado and categoria in categorias_conocidas:
            return categoria
    return _mejor_match(texto_normalizado, categorias_conocidas)


def extraer_anio(texto_original: str) -> int | None:
    match = _RE_ANIO.search(texto_original)
    return int(match.group(1)) if match else None


def extraer_motor(texto_original: str) -> str | None:
    match = _RE_MOTOR.search(texto_original)
    if not match:
        return None
    return match.group(1) or f"{match.group(2)}cc"


def extraer_combustible(texto_normalizado: str) -> str | None:
    for palabra, valor in COMBUSTIBLES_SINONIMOS.items():
        if palabra in texto_normalizado:
            return valor
    return None


def extraer_codigo(texto_original: str) -> str | None:
    """Códigos de repuesto tipo '90915-YZZD4', 'HP-1002', 'M1-102'."""
    match = _RE_CODIGO.search(texto_original)
    return match.group(0).upper() if match else None


def extraer_entidades(
    texto: str,
    marcas_conocidas: list[str] | None = None,
    modelos_conocidos: list[str] | None = None,
    categorias_conocidas: list[str] | None = None,
) -> dict:
    """Extrae marca, modelo, año, motor, combustible, código y categoría de un texto."""
    texto_normalizado = normalizar(texto)
    return {
        "marca": extraer_marca(texto_normalizado, marcas_conocidas or []),
        "modelo": extraer_modelo(texto_normalizado, modelos_conocidos or []),
        "anio": extraer_anio(texto),
        "motor": extraer_motor(texto),
        "combustible": extraer_combustible(texto_normalizado),
        "codigo": extraer_codigo(texto),
        "categoria": extraer_categoria(texto_normalizado, categorias_conocidas or []),
    }

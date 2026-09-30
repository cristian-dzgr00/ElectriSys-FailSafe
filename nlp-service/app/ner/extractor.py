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

Tabla de posibles errores (data/errores/posibles_errores.csv): antes de la
lógica fuzzy de siempre, marca/modelo/categoría se buscan en una tabla de
formas mal escritas ya conocidas ("jilus" -> "Hilux"), generada por
generador_errores.py y mantenida al día por agente_errores.py. Si la
tabla está vacía o no existe, el resultado es exactamente el de antes.
"""
import csv
import os
import re
import threading
from pathlib import Path

from rapidfuzz import fuzz, process
from rapidfuzz.distance import DamerauLevenshtein

from app.ner.generador_errores import TIPOS, clave_fonetica, es_palabra_comun
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

# Ruta calculada desde __file__ (y no desde el directorio actual) para que
# funcione igual dentro de Docker (/app/data/...) y fuera. La variable de
# entorno permite apuntarla a otra carpeta (volumen, pruebas).
TABLA_ERRORES_PATH = Path(
    os.getenv("NLP_TABLA_ERRORES_PATH")
    or Path(__file__).resolve().parents[2] / "data" / "errores" / "posibles_errores.csv"
)
UMBRAL_TABLA_ERRORES = 90  # fuzz.ratio contra las claves de la tabla
MIN_LETRAS_FUZZY_TABLA = 5  # en palabras más cortas fuzz.ratio es ruidoso
# Nivel 4 (más allá de la tabla): ediciones arbitrarias de 2+ letras.
UMBRAL_RESPALDO_SIMILITUD = 0.75  # DamerauLevenshtein.normalized_similarity
# Si dos nombres distintos quedan así de cerca, la palabra es ambigua
# ("frotuer": Fortuner y Frontier empatan) y es mejor no adivinar: un
# "no sé" se corrige preguntando, un modelo equivocado da un repuesto que no sirve.
MARGEN_AMBIGUEDAD_TABLA = 3  # puntos de fuzz.ratio
MARGEN_AMBIGUEDAD_SIMILITUD = 0.05

_tabla_en_memoria: dict | None = None
_lock_tabla = threading.Lock()
_indices_fuzzy: dict[int, tuple[dict, dict]] = {}


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


def cargar_tabla_errores(ruta=None) -> dict:
    """Lee la tabla de posibles errores: {tipo: {error_normalizado: correcto}}.

    Si el archivo no existe o está vacío devuelve {} sin lanzar error: el
    NER sigue funcionando igual que sin tabla.
    """
    ruta = Path(ruta) if ruta is not None else TABLA_ERRORES_PATH
    tabla: dict[str, dict[str, str]] = {}
    try:
        with ruta.open(encoding="utf-8", newline="") as f:
            for fila in csv.DictReader(f):
                tipo, error, correcto = fila.get("tipo"), fila.get("error"), fila.get("correcto")
                if tipo in TIPOS and error and correcto:
                    tabla.setdefault(tipo, {})[error] = correcto
    except (OSError, csv.Error, UnicodeDecodeError):
        return {}
    return tabla


def obtener_tabla_errores() -> dict:
    """La tabla en memoria (se carga del CSV la primera vez)."""
    global _tabla_en_memoria
    if _tabla_en_memoria is None:
        with _lock_tabla:
            if _tabla_en_memoria is None:
                _tabla_en_memoria = cargar_tabla_errores()
    return _tabla_en_memoria


def reemplazar_tabla_errores(nueva: dict) -> None:
    """Recarga en caliente: la próxima consulta ya usa la tabla nueva.

    Asignar la referencia es atómico: una consulta en curso termina con la
    tabla vieja y la siguiente usa la nueva, sin locks en la búsqueda.
    """
    global _tabla_en_memoria
    with _lock_tabla:
        _tabla_en_memoria = nueva
        _indices_fuzzy.clear()


def _resolver_tabla(tabla_errores: dict | None) -> dict:
    return obtener_tabla_errores() if tabla_errores is None else tabla_errores


def _indice_fuzzy(errores: dict) -> dict:
    """Claves de la tabla agrupadas por (primera letra, longitud).

    Buscar con fuzz.ratio contra TODAS las claves tarda ~185 ms por frase;
    con este índice solo se compara contra las de misma inicial y longitud
    parecida (±1), que son las únicas que pueden pasar el umbral de 90.
    """
    guardado = _indices_fuzzy.get(id(errores))
    if guardado is not None and guardado[0] is errores:
        return guardado[1]
    indice: dict[tuple[str, int], list[str]] = {}
    for clave in errores:
        if len(clave) >= MIN_LETRAS_FUZZY_TABLA - 1:
            indice.setdefault((clave[0], len(clave)), []).append(clave)
    if len(_indices_fuzzy) > 16:
        _indices_fuzzy.clear()
    _indices_fuzzy[id(errores)] = (errores, indice)
    return indice


def _candidatos(texto_normalizado: str) -> list[tuple[int, str]]:
    """Cada palabra y cada grupo de 2 a 4 palabras consecutivas: (n, texto).

    Hasta 4 porque un nombre de tres palabras con un espacio de más
    ("corr eas y bandas") ocupa cuatro.
    """
    palabras = texto_normalizado.split()
    return [
        (n, " ".join(palabras[i:i + n]))
        for n in (4, 3, 2, 1)
        for i in range(len(palabras) - n + 1)
    ]


def _buscar_en_tabla_errores(texto_normalizado: str, tipo: str, opciones: list[str], tabla: dict) -> str | None:
    """Busca en la frase alguna forma mal escrita conocida de `tipo`.

    Primero coincidencia EXACTA (dict, O(1)); si no hay, fuzz.ratio contra
    las claves de la tabla (solo candidatos de 5+ letras). Gana el grupo de
    más palabras ("sprak gt" antes que "sprak") y después el mejor puntaje.
    Solo devuelve un nombre que exista en `opciones` (el catálogo recibido),
    con su escritura original, igual que SINONIMOS_CATEGORIA: la tabla no
    inventa entidades que este negocio no tiene.
    """
    errores = tabla.get(tipo)
    if not errores or not opciones:
        return None
    opciones_normalizadas = {normalizar(o): o for o in opciones}
    candidatos = _candidatos(texto_normalizado)

    for _, candidato in candidatos:
        correcto = errores.get(candidato)
        if correcto is not None and normalizar(correcto) in opciones_normalizadas:
            return opciones_normalizadas[normalizar(correcto)]

    indice = _indice_fuzzy(errores)
    mejor, mejor_orden = None, None
    for n, candidato in candidatos:
        if len(candidato) < MIN_LETRAS_FUZZY_TABLA or es_palabra_comun(candidato):
            continue
        claves = [
            clave
            for largo in (len(candidato) - 1, len(candidato), len(candidato) + 1)
            for clave in indice.get((candidato[0], largo), ())
        ]
        resultados = process.extract(candidato, claves, scorer=fuzz.ratio,
                                     score_cutoff=UMBRAL_TABLA_ERRORES, limit=10)
        if not resultados:
            continue
        puntaje = resultados[0][1]
        destinos = {normalizar(errores[clave]) for clave, p, _ in resultados
                    if p >= puntaje - MARGEN_AMBIGUEDAD_TABLA}
        if len(destinos) != 1:
            continue  # se parece por igual a errores de dos nombres distintos
        correcto = destinos.pop()
        if correcto in opciones_normalizadas and (mejor_orden is None or (n, puntaje) > mejor_orden):
            mejor, mejor_orden = opciones_normalizadas[correcto], (n, puntaje)
    return mejor


def _candidatos_respaldo(texto_normalizado: str) -> list[tuple[int, str]]:
    """Palabras y pares (juntos, sin espacio) que no son palabras comunes."""
    return [
        (n, candidato.replace(" ", ""))
        for n, candidato in _candidatos(texto_normalizado)
        if n <= 2 and len(candidato.replace(" ", "")) >= MIN_LETRAS_FUZZY_TABLA
        and not es_palabra_comun(candidato)
    ]


def _respaldo_fonetico(texto_normalizado: str, opciones: list[str]) -> str | None:
    """Misma clave fonética que un nombre del catálogo ("shebrolet")."""
    claves = {}
    for o in opciones:
        junto = normalizar(o).replace(" ", "")
        if len(junto) >= MIN_LETRAS_FUZZY_TABLA:
            claves.setdefault(clave_fonetica(junto), o)
    for _, candidato in _candidatos_respaldo(texto_normalizado):
        encontrado = claves.get(clave_fonetica(candidato))
        if encontrado is not None:
            return encontrado
    return None


def _respaldo_similitud(texto_normalizado: str, opciones: list[str]) -> str | None:
    """Nivel 4: errores de 2+ letras que la tabla no enumera.

    Damerau-Levenshtein cuenta el intercambio de dos letras como UN error
    (fuzz.ratio lo cuenta como dos), por eso tolera más sin bajar tanto el
    umbral.
    """
    nombres = {normalizar(o).replace(" ", ""): o for o in opciones}
    nombres = {k: v for k, v in nombres.items() if len(k) >= MIN_LETRAS_FUZZY_TABLA}
    mejor, mejor_orden = None, None
    for n, candidato in _candidatos_respaldo(texto_normalizado):
        puntajes = sorted(
            ((DamerauLevenshtein.normalized_similarity(candidato, junto), original)
             for junto, original in nombres.items()),
            key=lambda x: x[0], reverse=True,
        )
        if not puntajes or puntajes[0][0] < UMBRAL_RESPALDO_SIMILITUD:
            continue
        if len(puntajes) > 1 and puntajes[0][0] - puntajes[1][0] < MARGEN_AMBIGUEDAD_SIMILITUD:
            continue  # ambiguo: no adivinar
        similitud, original = puntajes[0]
        if mejor_orden is None or (similitud, n) > mejor_orden:
            mejor, mejor_orden = original, (similitud, n)
    return mejor


def _extraer_con_tabla(texto_normalizado, tipo, opciones, tabla_errores, logica_actual) -> str | None:
    """Tabla primero; si no hay resultado, la lógica de siempre; al final,
    los respaldos fonético y de similitud (solo si hay tabla cargada, para
    que con tabla vacía el resultado sea idéntico al de antes)."""
    tabla = _resolver_tabla(tabla_errores)
    if tabla:
        encontrado = _buscar_en_tabla_errores(texto_normalizado, tipo, opciones, tabla)
        if encontrado is not None:
            return encontrado
    resultado = logica_actual()
    if resultado is None and tabla and opciones:
        resultado = _respaldo_fonetico(texto_normalizado, opciones) or _respaldo_similitud(texto_normalizado, opciones)
    return resultado


def extraer_marca(texto_normalizado: str, marcas_conocidas: list[str], tabla_errores: dict | None = None) -> str | None:
    return _extraer_con_tabla(
        texto_normalizado, "marca", marcas_conocidas, tabla_errores,
        lambda: _mejor_match(texto_normalizado, marcas_conocidas),
    )


def extraer_modelo(texto_normalizado: str, modelos_conocidos: list[str], tabla_errores: dict | None = None) -> str | None:
    return _extraer_con_tabla(
        texto_normalizado, "modelo", modelos_conocidos, tabla_errores,
        lambda: _mejor_match(texto_normalizado, modelos_conocidos),
    )


def _categoria_sin_tabla(texto_normalizado: str, categorias_conocidas: list[str]) -> str | None:
    for palabra, categoria in SINONIMOS_CATEGORIA.items():
        if palabra in texto_normalizado and categoria in categorias_conocidas:
            return categoria
    return _mejor_match(texto_normalizado, categorias_conocidas)


def extraer_categoria(texto_normalizado: str, categorias_conocidas: list[str], tabla_errores: dict | None = None) -> str | None:
    """Resuelve categoría por la tabla de errores, luego por sinónimo
    directo y, si no aplica, por fuzzy matching (_mejor_match).

    El sinónimo solo se usa si la categoría mapeada realmente está en
    categorias_conocidas (el catálogo real) — evita devolver una categoría
    que no existe en este negocio en particular.
    """
    return _extraer_con_tabla(
        texto_normalizado, "categoria", categorias_conocidas, tabla_errores,
        lambda: _categoria_sin_tabla(texto_normalizado, categorias_conocidas),
    )


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
    tabla_errores: dict | None = None,
) -> dict:
    """Extrae marca, modelo, año, motor, combustible, código y categoría de un texto.

    tabla_errores: None usa la tabla en memoria; {} la desactiva.
    """
    texto_normalizado = normalizar(texto)
    tabla = _resolver_tabla(tabla_errores)
    return {
        "marca": extraer_marca(texto_normalizado, marcas_conocidas or [], tabla),
        "modelo": extraer_modelo(texto_normalizado, modelos_conocidos or [], tabla),
        "anio": extraer_anio(texto),
        "motor": extraer_motor(texto),
        "combustible": extraer_combustible(texto_normalizado),
        "codigo": extraer_codigo(texto),
        "categoria": extraer_categoria(texto_normalizado, categorias_conocidas or [], tabla),
    }

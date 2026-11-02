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

# Vocabulario de mostrador -> categoría del catálogo. Cada regla es
# (expresión sobre el texto normalizado, categoría, prioridad):
#   3 = frase específica ("banda de freno" es Frenos aunque "banda" sola sea
#       Correas y Bandas; "motor de arranque" no es la categoría Motor);
#   2 = palabra propia de la categoría;
#   1 = palabra débil que aparece en otros contextos ("motor", "aceite").
# Gana la prioridad más alta y, a igual prioridad, lo que se nombra primero.
# Una regla solo cuenta si su categoría está en el catálogo recibido.
_REGLAS_CATEGORIA_TEXTO = [
    # --- Frenos
    (r"\bbandas?\s+de\s+frenos?\b", "Frenos", 3), (r"\bdiscos?\s+(?:de\s+)?(?:frenos?|ventilados?)\b", "Frenos", 3),
    (r"\bcilindros?\s+maestros?\b", "Frenos", 3), (r"\bliquido\s+de\s+frenos?\b", "Frenos", 3),
    (r"\bfrenos?\b", "Frenos", 2), (r"\bpastillas?\b", "Frenos", 2), (r"\bbalatas?\b", "Frenos", 2),
    (r"\bzapatas?\b", "Frenos", 2), (r"\bcalipers?\b", "Frenos", 2),
    # --- Baterías
    (r"\bbaterias?\b", "Baterías", 2), (r"\bacumulador(?:es)?\b", "Baterías", 2),
    # --- Neumáticos
    (r"\bllantas?\b", "Neumáticos", 2), (r"\bcauchos?\b", "Neumáticos", 2), (r"\bneumaticos?\b", "Neumáticos", 2),
    # --- Hidráulica
    (r"\bfiltros?\s+(?:de\s+\w+\s+)?hidraulic\w*", "Hidráulica", 3), (r"\bhidraulic\w*", "Hidráulica", 2),
    # --- Enganches y Acoples
    (r"\brotulas?\s+de\s+enganche\b", "Enganches y Acoples", 3), (r"\btoma\s+de\s+fuerza\b", "Enganches y Acoples", 3),
    (r"\btres\s+puntos\b", "Enganches y Acoples", 3), (r"\benganch\w*", "Enganches y Acoples", 2),
    (r"\bacoples?\b", "Enganches y Acoples", 2), (r"\bpto\b", "Enganches y Acoples", 2),
    # --- Sistema Eléctrico
    (r"\bmotor(?:es)?\s+de\s+arranque\b", "Sistema Eléctrico", 3), (r"\balternador(?:es)?\b", "Sistema Eléctrico", 2),
    (r"\barranque\b", "Sistema Eléctrico", 2), (r"\bbombill[oa]s?\b", "Sistema Eléctrico", 2),
    (r"\breles?\b", "Sistema Eléctrico", 2), (r"\bfusibles?\b", "Sistema Eléctrico", 2),
    (r"\bhalogen\w*", "Sistema Eléctrico", 2), (r"\bsistema\s+electrico\b", "Sistema Eléctrico", 3),
    # --- Encendido
    (r"\bcables?\s+de\s+bujia\b", "Encendido", 3), (r"\bbujias?\b", "Encendido", 2), (r"\bbobinas?\b", "Encendido", 2),
    (r"\bencendido\b", "Encendido", 2), (r"\bignicion\b", "Encendido", 2),
    # --- Correas y Bandas
    (r"\bkit\s+de\s+distribucion\b", "Correas y Bandas", 3), (r"\bcorreas?\b", "Correas y Bandas", 2),
    (r"\bbandas?\b", "Correas y Bandas", 2), (r"\btensor(?:es)?\b", "Correas y Bandas", 2),
    (r"\bpoly\s?v\b", "Correas y Bandas", 2),
    # --- Transmisión
    (r"\baceite\s+de\s+(?:transmision|caja)\b", "Transmisión", 3), (r"\bembragues?\b", "Transmisión", 2),
    (r"\b(?:clutch|croche|cloche)\b", "Transmisión", 2), (r"\bhomocinetic\w*", "Transmisión", 2),
    (r"\btransmision\b", "Transmisión", 2), (r"\bcaja\s+de\s+(?:cambios|velocidades)\b", "Transmisión", 3),
    (r"\bdiferencial(?:es)?\b", "Transmisión", 2), (r"\batf\b", "Transmisión", 2),
    # --- Suspensión
    (r"\bamortiguador(?:es)?\b", "Suspensión", 2), (r"\bsuspension\b", "Suspensión", 2),
    (r"\bresortes?\b", "Suspensión", 2), (r"\brotulas?\b", "Suspensión", 2),
    (r"\bterminal(?:es)?\s+de\s+direccion\b", "Suspensión", 3), (r"\bbuje[s]?\b", "Suspensión", 2),
    (r"\bbarras?\s+estabilizadoras?\b", "Suspensión", 3), (r"\bbieletas?\b", "Suspensión", 2),
    # --- Filtros
    (r"\bseparador(?:es)?\s+de\s+agua\b", "Filtros", 3), (r"\bfiltros?\b", "Filtros", 2),
    # --- Motor (lo más ambiguo, al final)
    (r"\bbombas?\s+de\s+agua\b", "Motor", 3), (r"\bjuntas?\s+de\s+culata\b", "Motor", 3),
    (r"\bradiador(?:es)?\b", "Motor", 2), (r"\btermostatos?\b", "Motor", 2), (r"\bempaques?\b", "Motor", 2),
    (r"\bculatas?\b", "Motor", 2), (r"\bpistones?\b", "Motor", 2),
    (r"\b(?:sae\s)?\d{1,2} ?w ?\d{2,3}\b", "Motor", 2),
    (r"\blubricantes?\b", "Motor", 1), (r"\baceites?\b", "Motor", 1), (r"\bmotor(?:es)?\b", "Motor", 1),
]
_REGLAS_CATEGORIA = [(re.compile(p), cat, prio) for p, cat, prio in _REGLAS_CATEGORIA_TEXTO]
# "motor 2.7", "con motor diesel", "motor de 1600cc": el motor del vehículo, no la categoría Motor.
_RE_MOTOR_DESCRIPTIVO = re.compile(r"\b(?:con\s+)?motor(?:es)?\s+(?:de\s+)?(?:\d+\w*|diesel|gasolina|hibrido|electrico|turbo)\b")

# Cifras que NO son modelo de vehículo ni código de repuesto.
_RE_VISCOSIDAD = re.compile(r"\b(?:sae\s*)?\d{1,2}\s?w\s?-?\s?\d{2,3}\b", re.IGNORECASE)  # 5W-30, 10W40
_RE_ANIO = re.compile(r"\b(19[5-9]\d|20[0-4]\d)\b")
# Cilindrada: "2.7", "2,7", "2.7L", "1600cc". No es motor un decimal pegado a otra magnitud
# ("1.1 bar", "3.5 mm", "12.5v") ni parte de un número mayor ("18.4-46", "T6.120").
_RE_MOTOR = re.compile(
    r"(?<![\w.,])(\d)[.,](\d)(?!\d)(?!\s?(?:bar|mm|cm|kg|psi|ml|hp|nm|amp\w*|volt\w*)\b)(?![vaw]\b)"
    r"|\b(\d{3,4})\s?cc\b",
    re.IGNORECASE,
)
# Código de repuesto: segmentos separados por guion y sufijo opcional con barra
# ("90915-YZZD4", "HP-1002", "KN-33-2304", "W-610/3").
_RE_CODIGO = re.compile(r"(?<![\w-])[A-Za-z0-9]{1,10}(?:-[A-Za-z0-9]{1,10}){1,3}(?:/[A-Za-z0-9]{1,4})?(?![\w-])")
_RE_MAGNITUD = re.compile(r"^\d+(?:v|ah|a|w|mm|cm|kg|ml|l|lt|hp|nm|psi|bar|amp)$", re.IGNORECASE)
_RE_GAS_DE_AMORTIGUADOR = re.compile(r"\b(?:amortiguador\w*|resorte\w*|cilindro\w*|gato)\b")


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
    # Las más largas primero: con un empate de puntaje gana el nombre más completo
    # ("Spark GT" antes que "Spark" cuando el texto dice "spark gt").
    claves = sorted(opciones_normalizadas.keys(), key=lambda k: (-len(k), k))

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


MAX_LETRAS_NOMBRE_CORTO = 4  # "Kia", "Rio", "Ford", "Sail", "Onix", "Aveo"
# Pares de letras que suenan igual (o casi) y se confunden al escribir.
_PARES_FONETICOS = frozenset(frozenset(p) for p in ("kq", "kc", "qc", "sz", "sc", "zc", "bv", "gj", "xs"))
_VOCALES_Y = set("aeiouy")


def _es_error_corto(candidato: str, nombre: str) -> bool:
    """¿`candidato` es una escritura plausible de un nombre CORTO (<= 4 letras)?

    Con nombres tan cortos una distancia de edición genérica da demasiados
    falsos positivos ("rin" no es "Rio", "kiu" y "roi" tampoco: ver
    tests/test_ner_errores.py), así que solo valen los errores de oído más
    corrientes: una vocal INTERNA por otra ("seil" por "sail", "kya" por "kia"),
    una letra por su par fonético ("qia" por "kia", "onis" por "onix"), una
    letra repetida ("foord") o una "h" muda de más.
    """
    n, c = len(nombre), len(candidato)
    if c == n:
        diferentes = [(i, a, b) for i, (a, b) in enumerate(zip(candidato, nombre)) if a != b]
        if len(diferentes) != 1:
            return False
        i, a, b = diferentes[0]
        vocales_internas = 0 < i < n - 1 and a in _VOCALES_Y and b in _VOCALES_Y
        return vocales_internas or frozenset((a, b)) in _PARES_FONETICOS
    if c == n + 1:  # una letra de más: repetida ("foord") o "h" muda
        for i in range(c):
            if candidato[:i] + candidato[i + 1:] == nombre:
                extra = candidato[i]
                if extra == "h" or (i > 0 and candidato[i - 1] == extra) or (i + 1 < c and candidato[i + 1] == extra):
                    return True
    return False


def _respaldo_nombres_cortos(texto_normalizado: str, opciones: list[str]) -> str | None:
    """Errores de nombres de 3-4 letras ("qia", "seil", "onyx") que la tabla no trae."""
    cortos = {normalizar(o): o for o in opciones if 3 <= len(normalizar(o)) <= MAX_LETRAS_NOMBRE_CORTO
              and " " not in normalizar(o) and not normalizar(o).isdigit()}
    if not cortos:
        return None
    encontrados = set()
    for palabra in texto_normalizado.split():
        if not 3 <= len(palabra) <= MAX_LETRAS_NOMBRE_CORTO + 1 or palabra in cortos or es_palabra_comun(palabra):
            continue
        for nombre, original in cortos.items():
            if _es_error_corto(palabra, nombre):
                encontrados.add(original)
    return encontrados.pop() if len(encontrados) == 1 else None  # varios: ambiguo, no adivinar


def _respaldo_palabra_distintiva(texto_normalizado: str, opciones: list[str]) -> str | None:
    """Nombres de varias palabras ("New Holland") cuando solo se escribe la palabra
    que los distingue ("holland", "holan"): debe ser larga, única entre las
    opciones y no una palabra común."""
    distintivas: dict[str, set[str]] = {}
    for o in opciones:
        palabras = normalizar(o).split()
        if len(palabras) < 2:
            continue
        for p in palabras:
            if len(p) >= 6 and not p.isdigit():
                distintivas.setdefault(p, set()).add(o)
    unicas = {p: next(iter(v)) for p, v in distintivas.items() if len(v) == 1}
    if not unicas:
        return None
    para_sola = {normalizar(o) for o in opciones}  # una palabra que ya es una opción por sí sola no cuenta
    for palabra in texto_normalizado.split():
        if len(palabra) < 6 or palabra in para_sola:
            continue
        for distintiva, opcion in unicas.items():
            # La palabra exacta ("holland") basta; una parecida ("holan") no puede ser
            # una palabra común.
            if palabra == distintiva or (
                    DamerauLevenshtein.normalized_similarity(palabra, distintiva) >= 0.85 and not es_palabra_comun(palabra)):
                return opcion
    return None


def _extraer_con_tabla(texto_normalizado, tipo, opciones, tabla_errores, logica_actual) -> str | None:
    """Tabla primero; si no hay resultado, la lógica de siempre; al final,
    los respaldos fonético, de similitud, de nombres cortos y de palabra
    distintiva (solo si hay tabla cargada, para que con tabla vacía el
    resultado sea idéntico al de antes)."""
    tabla = _resolver_tabla(tabla_errores)
    if tabla:
        encontrado = _buscar_en_tabla_errores(texto_normalizado, tipo, opciones, tabla)
        if encontrado is not None:
            return encontrado
    resultado = logica_actual()
    if resultado is None and tabla and opciones:
        resultado = (
            _respaldo_fonetico(texto_normalizado, opciones)
            or _respaldo_similitud(texto_normalizado, opciones)
            or _respaldo_nombres_cortos(texto_normalizado, opciones)
            or (_respaldo_palabra_distintiva(texto_normalizado, opciones) if tipo == "marca" else None)
        )
    return resultado


def extraer_marca(texto_normalizado: str, marcas_conocidas: list[str], tabla_errores: dict | None = None) -> str | None:
    return _extraer_con_tabla(
        texto_normalizado, "marca", marcas_conocidas, tabla_errores,
        lambda: _mejor_match(texto_normalizado, marcas_conocidas),
    )


def _es_modelo_numerico_corto(modelo: str) -> bool:
    return modelo.isdigit() and len(modelo) <= 2


def _es_marca(token: str, marcas_conocidas: list[str], tabla: dict) -> bool:
    """¿La palabra es una marca conocida, escrita bien o con un error corriente?"""
    marcas = {normalizar(m).replace(" ", "") for m in marcas_conocidas}
    if token in marcas:
        return True
    correcto = tabla.get("marca", {}).get(token)
    if correcto is not None and normalizar(correcto).replace(" ", "") in marcas:
        return True
    return len(token) >= 5 and any(DamerauLevenshtein.normalized_similarity(token, m) >= 0.8 for m in marcas)


def _modelo_numerico_corto(texto_normalizado, cortos, marcas_conocidas, tabla) -> str | None:
    """Modelos que son solo un número chico ("Mazda 3"): únicamente cuentan pegados a
    una marca ("mazda 3", "mazda3"). Un "3" suelto es una cantidad o parte de una
    medida, no un vehículo."""
    tokens = texto_normalizado.split()
    for i, t in enumerate(tokens):
        if t in cortos and i > 0 and _es_marca(tokens[i - 1], marcas_conocidas, tabla):
            return cortos[t]
        pegado = re.fullmatch(r"([a-z]{4,})(\d{1,2})", t)
        if pegado and pegado.group(2) in cortos and _es_marca(pegado.group(1), marcas_conocidas, tabla):
            return cortos[pegado.group(2)]
    return None


def extraer_modelo(
    texto_normalizado: str,
    modelos_conocidos: list[str],
    tabla_errores: dict | None = None,
    marcas_conocidas: list[str] | None = None,
) -> str | None:
    """Modelo del vehículo. Los modelos que son un número de 1-2 dígitos ("3") solo se
    reconocen junto a una marca (ver _modelo_numerico_corto)."""
    cortos = {m: m for m in modelos_conocidos if _es_modelo_numerico_corto(m)}
    normales = [m for m in modelos_conocidos if m not in cortos]
    resultado = _extraer_con_tabla(
        texto_normalizado, "modelo", normales, tabla_errores,
        lambda: _mejor_match(texto_normalizado, normales),
    )
    if resultado is None and cortos:
        resultado = _modelo_numerico_corto(texto_normalizado, cortos, marcas_conocidas or [],
                                           _resolver_tabla(tabla_errores))
    return resultado


def _categoria_por_reglas(texto_normalizado: str, categorias_conocidas: list[str]) -> str | None:
    """Mejor categoría según _REGLAS_CATEGORIA (prioridad más alta, luego lo primero que se nombra)."""
    por_nombre = {normalizar(c): c for c in categorias_conocidas}
    mejor, mejor_clave = None, None
    for patron, categoria, prioridad in _REGLAS_CATEGORIA:
        real = por_nombre.get(normalizar(categoria))
        if real is None:
            continue
        m = patron.search(texto_normalizado)
        if m is None:
            continue
        clave = (prioridad, -m.start())
        if mejor_clave is None or clave > mejor_clave:
            mejor, mejor_clave = real, clave
    return mejor


# Palabras de 6+ letras de las reglas contra las que se tolera un error de escritura.
_PALABRAS_CATEGORIA = {
    "bateria": "Baterías", "acumulador": "Baterías", "amortiguador": "Suspensión", "suspension": "Suspensión",
    "rotula": "Suspensión", "alternador": "Sistema Eléctrico", "embrague": "Transmisión",
    "transmision": "Transmisión", "homocinetica": "Transmisión", "radiador": "Motor",
    "termostato": "Motor", "empaque": "Motor", "bobina": "Encendido", "llanta": "Neumáticos",
    "neumatico": "Neumáticos", "balata": "Frenos", "zapata": "Frenos", "pastilla": "Frenos",
    "hidraulico": "Hidráulica", "enganche": "Enganches y Acoples", "correa": "Correas y Bandas",
    "filtro": "Filtros", "bombillo": "Sistema Eléctrico",
}


def _categoria_por_palabra_parecida(texto_normalizado: str, categorias_conocidas: list[str]) -> str | None:
    """Una palabra mal escrita que se parece a un sinónimo ("vateria", "amortigador")."""
    por_nombre = {normalizar(c): c for c in categorias_conocidas}
    encontradas = set()
    for palabra in texto_normalizado.split():
        if len(palabra) < 6 or palabra in _PALABRAS_CATEGORIA or es_palabra_comun(palabra):
            continue
        for sinonimo, categoria in _PALABRAS_CATEGORIA.items():
            if abs(len(palabra) - len(sinonimo)) > 2:
                continue
            raiz = sinonimo.rstrip("s")
            tolerancia = 1 if len(raiz) <= 8 else 2
            if (DamerauLevenshtein.distance(palabra.rstrip("s"), raiz) <= tolerancia
                    and (palabra[0] == sinonimo[0] or frozenset((palabra[0], sinonimo[0])) in _PARES_FONETICOS)):
                real = por_nombre.get(normalizar(categoria))
                if real is not None:
                    encontradas.add(real)
    return encontradas.pop() if len(encontradas) == 1 else None


def _categoria_sin_tabla(texto_normalizado: str, categorias_conocidas: list[str]) -> str | None:
    texto_normalizado = _RE_MOTOR_DESCRIPTIVO.sub(" ", texto_normalizado)
    return (
        _categoria_por_reglas(texto_normalizado, categorias_conocidas)
        or _mejor_match(texto_normalizado, categorias_conocidas)
        or _categoria_por_palabra_parecida(texto_normalizado, categorias_conocidas)
    )


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


# Después de un año: "2000 pesos", "2018 unidades" no es un año (es un precio o una cantidad).
_RE_NO_ES_ANIO = re.compile(r"\s?(?:pesos|cop|mil\b|unidades|und\b|km\b|ml\b|cc\b|x\b)", re.IGNORECASE)


def extraer_anio(texto_original: str) -> int | None:
    for match in _RE_ANIO.finditer(texto_original):
        despues = texto_original[match.end():match.end() + 10]
        if "$" in texto_original[max(0, match.start() - 2):match.start()] or _RE_NO_ES_ANIO.match(despues):
            continue
        return int(match.group(1))
    return None


def _buscar_motor(texto_original: str):
    return _RE_MOTOR.search(texto_original)


def extraer_motor(texto_original: str) -> str | None:
    """Cilindrada: "2.7", "2,7", "2.7L" -> "2.7"; "1600cc" -> "1600cc"."""
    match = _buscar_motor(texto_original)
    if not match:
        return None
    if match.group(3):
        return f"{match.group(3)}cc"
    return f"{match.group(1)}.{match.group(2)}"


def extraer_combustible(texto_normalizado: str) -> str | None:
    """Combustible por palabra completa ("gas" no debe salir de "amortiguador a gas" ni de "gastos")."""
    for palabra, valor in COMBUSTIBLES_SINONIMOS.items():
        if not re.search(rf"\b{re.escape(normalizar(palabra))}\b", texto_normalizado):
            continue
        if valor == "gas" and _RE_GAS_DE_AMORTIGUADOR.search(texto_normalizado):
            continue  # "amortiguador a gas": es el tipo de amortiguador, no el combustible
        return valor
    return None


def _es_codigo_valido(candidato: str, modelos_normalizados: set[str]) -> bool:
    """Un código real mezcla letras y cifras ("HP-1002") o son dos bloques numéricos largos
    ("26300-35505"). No lo son: viscosidades (5W-30), rangos de años (2015-2020), magnitudes
    (12V-60Ah), palabras con guion (poly-V, start-stop) ni el nombre de un modelo (CX-5)."""
    cuerpo = candidato.split("/")[0]
    partes = cuerpo.split("-")
    if len(partes) == 2 and len(partes[1]) < 2:
        return False
    if _RE_VISCOSIDAD.fullmatch(cuerpo) or normalizar(candidato) in modelos_normalizados:
        return False
    if all(_RE_MAGNITUD.match(p) for p in partes):
        return False
    if all(p.isdigit() for p in partes):
        todos_anios = all(_RE_ANIO.fullmatch(p) for p in partes)
        return not todos_anios and any(len(p) >= 4 for p in partes) and sum(len(p) for p in partes) >= 6
    return any(c.isdigit() for c in candidato) and any(c.isalpha() for c in candidato)


def _buscar_codigo(texto_original: str, modelos_conocidos: list[str] | None = None):
    modelos_normalizados = {normalizar(m) for m in (modelos_conocidos or [])}
    for match in _RE_CODIGO.finditer(texto_original):
        if _es_codigo_valido(match.group(0), modelos_normalizados):
            return match
    return None


def extraer_codigo(texto_original: str, modelos_conocidos: list[str] | None = None) -> str | None:
    """Códigos de repuesto tipo '90915-YZZD4', 'HP-1002', 'M1-102', 'KN-33-2304', 'W-610/3'."""
    match = _buscar_codigo(texto_original, modelos_conocidos)
    return match.group(0).upper() if match else None


def _ocultar_cifras_ajenas(texto: str, codigo) -> str:
    """El texto sin viscosidades (5W-30), cilindradas (3.2, 2.7L, 1600cc) ni el código.

    Se usa para buscar marca y modelo: de otro modo el "3" de "3.2" o de "W-610/3"
    se leería como el modelo "Mazda 3".
    """
    spans = [m.span() for m in _RE_VISCOSIDAD.finditer(texto)]
    spans += [m.span() for m in _RE_MOTOR.finditer(texto)]
    if codigo is not None:
        spans.append(codigo.span())
    for inicio, fin in sorted(set(spans), reverse=True):
        texto = texto[:inicio] + " " + texto[fin:]
    return texto


def _marca_unica_del_modelo(modelo: str, marcas_conocidas: list[str], marca_de_modelo: dict) -> str | None:
    """La marca de un modelo si el catálogo solo lo conoce con UNA marca.

    Un modelo que existe en dos marcas distintas queda sin resolver: preguntar
    "¿de qué marca?" es mejor que adivinar y ofrecer un repuesto equivocado.
    """
    candidatas = marca_de_modelo.get(modelo)
    if candidatas is None:
        por_nombre = {normalizar(k): v for k, v in marca_de_modelo.items()}
        candidatas = por_nombre.get(normalizar(modelo))
    if isinstance(candidatas, str):
        candidatas = [candidatas]
    distintas = {normalizar(c): c for c in (candidatas or [])}
    if len(distintas) != 1:
        return None
    clave, original = next(iter(distintas.items()))
    for marca in marcas_conocidas:
        if normalizar(marca) == clave:
            return marca
    return original


def extraer_entidades(
    texto: str,
    marcas_conocidas: list[str] | None = None,
    modelos_conocidos: list[str] | None = None,
    categorias_conocidas: list[str] | None = None,
    tabla_errores: dict | None = None,
    marca_de_modelo=None,
) -> dict:
    """Extrae marca, modelo, año, motor, combustible, código y categoría de un texto.

    tabla_errores: None usa la tabla en memoria; {} la desactiva.
    marca_de_modelo: {modelo: marca o [marcas]} del catálogo (o una función que lo
        devuelve, para consultarlo solo si hace falta). Si el texto nombra un
        modelo sin marca y el catálogo lo conoce con una sola marca, se completa
        ("hilux" -> Toyota); si es ambiguo la marca queda en None.
    """
    texto_normalizado = normalizar(texto)
    tabla = _resolver_tabla(tabla_errores)
    marcas, modelos = marcas_conocidas or [], modelos_conocidos or []
    codigo = _buscar_codigo(texto, modelos)
    texto_vehiculo = normalizar(_ocultar_cifras_ajenas(texto, codigo))

    marca = extraer_marca(texto_vehiculo, marcas, tabla)
    modelo = extraer_modelo(texto_vehiculo, modelos, tabla, marcas)
    if marca is None and modelo is not None and marca_de_modelo:
        # Puede ser una función: así el catálogo solo se consulta cuando de verdad falta la marca.
        mapa = marca_de_modelo() if callable(marca_de_modelo) else marca_de_modelo
        marca = _marca_unica_del_modelo(modelo, marcas, mapa) if mapa else None
    return {
        "marca": marca,
        "modelo": modelo,
        "anio": extraer_anio(texto),
        "motor": extraer_motor(texto),
        "combustible": extraer_combustible(texto_normalizado),
        "codigo": codigo.group(0).upper() if codigo else None,
        "categoria": extraer_categoria(texto_normalizado, categorias_conocidas or [], tabla),
    }

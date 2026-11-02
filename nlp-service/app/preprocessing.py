"""Preprocesamiento de texto en español para el pipeline de NLP.

Normaliza, tokeniza y filtra stopwords. Se usa como paso previo tanto para
la clasificación de intención (Sprint 3) como para el motor de recomendación
(Sprint 4).
"""
import re
import unicodedata

# Stopwords en español. Deliberadamente NO incluye partículas de negación
# ("no", "sin", "nunca", "tampoco", "ni"): frases como "no hay filtro de
# aceite" dependen de "no" para distinguir la intención "recomendar_sustituto"
# de "buscar_repuesto" ("hay filtro de aceite"). Quitarla perdería la señal
# más importante del dataset.
STOPWORDS_ES = {
    "de", "la", "que", "el", "en", "y", "a", "los", "del", "se", "las",
    "por", "un", "para", "con", "una", "su", "al", "lo", "como",
    "mas", "pero", "sus", "le", "ya", "o", "este", "si", "porque", "esta",
    "entre", "cuando", "muy", "sobre", "tambien", "me", "hasta", "hay",
    "donde", "quien", "desde", "todo", "nos", "durante", "todos", "uno",
    "les", "contra", "otros", "ese", "eso", "ante", "ellos", "e", "esto",
    "mi", "antes", "algunos", "unos", "yo", "otro", "otras", "otra",
    "tanto", "esa", "estos", "mucho", "quienes", "nada", "muchos", "cual",
    "poco", "ella", "estar", "estas", "algunas", "algo", "nosotros",
    "mis", "tu", "te", "ti", "tus", "ellas", "nosotras", "os",
    "esos", "esas", "es", "son", "soy", "eres", "somos",
}


def quitar_acentos(texto: str) -> str:
    """Descompone caracteres acentuados y elimina las marcas diacríticas."""
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes, sin puntuación, espacios colapsados."""
    texto = texto.strip().lower()
    texto = quitar_acentos(texto)
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto


def tokenizar(texto: str) -> list[str]:
    """Tokeniza un texto ya normalizado (separado por espacios)."""
    return texto.split() if texto else []


def quitar_stopwords(tokens: list[str]) -> list[str]:
    return [t for t in tokens if t not in STOPWORDS_ES]


def preprocesar(texto: str) -> list[str]:
    """Pipeline completo: normalizar -> tokenizar -> quitar stopwords."""
    return quitar_stopwords(tokenizar(normalizar(texto)))


_RE_VISCOSIDAD_NORMALIZADA = re.compile(r"\b(\d{1,2}) ?w ?(\d{2,3})\b")


def _singular(palabra: str) -> str:
    """Quita el plural más común del español ("llantas" -> "llanta", "amortiguadores" -> "amortiguador").

    No pretende ser un lematizador: consulta y catálogo pasan por la misma
    función, así que basta con que "llantas" y "llanta" den el mismo token.
    """
    if len(palabra) <= 3 or palabra.endswith("ss"):
        return palabra
    if palabra.endswith("es") and len(palabra) > 4 and palabra[-3] in "lrndzj":
        return palabra[:-2]
    if palabra.endswith("s"):
        return palabra[:-1]
    return palabra


def preprocesar_busqueda(texto: str) -> list[str]:
    """Preprocesamiento para comparar la consulta con el catálogo (ranking TF-IDF).

    Igual que `preprocesar`, más: plurales en singular y viscosidades unidas
    ("5W-30", "5w30" y "5 w 30" dan el mismo token "5w30"), porque el
    catálogo escribe "Llanta ... 5W-30" y el cliente "llantas"/"5w30".
    """
    normalizado = _RE_VISCOSIDAD_NORMALIZADA.sub(r"\1w\2", normalizar(texto))
    return [_singular(t) for t in quitar_stopwords(tokenizar(normalizado))]


# ---------------------------------------------------------------------------
# Marcador de vehículo (solo para el clasificador de intención)
#
# El análisis de pesos del clasificador mostró que los nombres de vehículo
# cargaban mucha señal hacia una intención ("hilux" -> recomendar_sustituto,
# 3.91): un artefacto de cómo se escribió el dataset, no una pista real. Se
# reemplaza cada nombre de marca/modelo conocido por un único token marcador
# para que el modelo aprenda de las demás palabras. El NER NO usa esto: sigue
# leyendo el texto original.
#
# Vocabulario: marcas y modelos del catálogo (eval/datos_demo/marcas.csv y
# modelos.csv) más los vehículos que aparecen en data/intents_dataset.csv.
# Todo va ya normalizado (minúsculas, sin tildes ni puntuación).
# ---------------------------------------------------------------------------
MARCADOR_VEHICULO = "<vehiculo>"

# Una sola palabra, sin ambigüedad con el vocabulario de repuestos.
_VEHICULO_UNA_PALABRA = frozenset({
    # marcas
    "chevrolet", "ford", "hyundai", "kia", "mazda", "nissan", "renault", "suzuki", "toyota",
    "mitsubishi", "volkswagen", "vw", "mf", "chevy",
    # modelos
    "aveo", "spark", "onix", "sail", "fiesta", "ranger", "accent", "tucson", "picanto", "rio",
    "sportage", "cx5", "l200", "frontier", "sentra", "duster", "logan", "sandero", "swift",
    "corolla", "fortuner", "hilux", "yaris", "tracker", "montero", "vitara", "captiva",
    # tractores (modelos con letras y dígitos)
    "5075e", "6110m", "tl90", "4707", "6713", "t6120",
})

# Varias palabras (ya normalizadas) o palabras ambiguas que solo cuentan como
# vehículo junto a su marca ("escape" suelto es el tubo de escape; "3" suelto
# es un número).
_VEHICULO_VARIAS_PALABRAS = frozenset({
    ("spark", "gt"), ("cx", "5"), ("john", "deere"), ("case", "ih"), ("new", "holland"),
    ("massey", "ferguson"), ("t6", "120"), ("farmall", "75c"), ("puma", "165"),
    ("ford", "escape"), ("mazda", "3"), ("massey", "290"), ("mf", "290"),
    ("volkswagen", "gol"), ("vw", "gol"), ("volkswagen", "polo"), ("vw", "polo"),
    ("volkswagen", "golf"), ("vw", "golf"),
})
_LARGO_MAXIMO_VEHICULO = max(len(v) for v in _VEHICULO_VARIAS_PALABRAS)


def enmascarar_vehiculos(tokens: list[str]) -> list[str]:
    """Reemplaza marcas/modelos de vehículo por MARCADOR_VEHICULO.

    Recibe tokens ya normalizados. Los nombres consecutivos ("toyota hilux",
    "mazda 3", "john deere 5075e") se colapsan en un solo marcador.
    """
    salida: list[str] = []
    i = 0
    while i < len(tokens):
        largo = 0
        for n in range(_LARGO_MAXIMO_VEHICULO, 1, -1):
            if tuple(tokens[i:i + n]) in _VEHICULO_VARIAS_PALABRAS:
                largo = n
                break
        if not largo and tokens[i] in _VEHICULO_UNA_PALABRA:
            largo = 1
        if largo:
            if not salida or salida[-1] != MARCADOR_VEHICULO:
                salida.append(MARCADOR_VEHICULO)
            i += largo
        else:
            salida.append(tokens[i])
            i += 1
    return salida


def preprocesar_intencion(texto: str) -> list[str]:
    """Preprocesamiento del clasificador de intención: el de siempre, pero
    con los nombres de vehículo reemplazados por un marcador."""
    tokens = tokenizar(normalizar(texto))
    return quitar_stopwords(enmascarar_vehiculos(tokens))

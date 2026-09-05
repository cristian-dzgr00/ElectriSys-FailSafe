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

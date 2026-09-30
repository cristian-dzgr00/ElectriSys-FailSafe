"""Generador determinista de posibles errores de escritura (tabla de errores).

RapidFuzz compara la palabra del usuario con el nombre oficial y no sabe que
"jilus" es como se escribe "hilux" de oído: fuzz.ratio le da 60/100. Este
módulo enumera de antemano las formas mal escritas de cada marca, modelo y
categoría, para que el NER las encuentre por coincidencia exacta (O(1)).

Niveles (de lo mínimo a lo extremo):
- Nivel 1: TODAS las ediciones de una sola letra (borrar, repetir,
  intercambiar contiguas, cambiar por cualquier otra, insertar cualquiera;
  alfabeto a-z y 0-9, que es todo lo que deja normalizar()) más las
  variantes de espacio ("sparkgt", "hi lux").
- Nivel 2: errores fonéticos del español (b/v, c/s/z, ll/y, h muda, k/c/qu,
  g/j, x/s/ks, w/gu/u, y/i, doble letra), solos y de a dos; transliteración
  de nombres extranjeros tal como los escribe un hispanohablante
  ("renault" -> "reno", "geely" -> "yili"); apodos por sílabas ("chevy") y
  partes/siglas de nombres compuestos ("sgt").
- Nivel 3: dos errores realistas (letra vecina en el teclado, borrado,
  repetición, intercambio), un error fonético más un error de tipeo,
  nombres truncados y letras repetidas de más ("toyotaaa").
- Nivel 4: ediciones arbitrarias de 2 o más letras. NO se enumeran (más de
  100 mil variantes por nombre): las cubre el respaldo por similitud del
  extractor (Damerau-Levenshtein) y la clave fonética de este módulo.

Mínimos de longitud (letras del nombre sin espacios):
- 3 o menos (Kia, Rio, "3", "CX-5"): casi cualquier edición es una palabra
  normal ("tia", "dia", "rie") o un código, así que solo se generan letras
  repetidas y la variante sin separador ("cx5"). El resto queda para las
  filas manuales. Los nombres solo numéricos no generan nada.
- 4 letras: niveles 1 y 2.
- 5 o más: niveles 1, 2 y 3. Apodos desde 6 letras, truncados desde 7.

No usa internet ni ninguna API: mismo nombre, mismas filas.
"""
import csv
import re
from functools import lru_cache
from itertools import combinations, product
from pathlib import Path

import numpy as np
from rapidfuzz import process
from rapidfuzz.distance import DamerauLevenshtein

from app.preprocessing import STOPWORDS_ES, normalizar

COLUMNAS = ["tipo", "error", "correcto", "nivel", "origen", "nota"]
TIPOS = ("marca", "modelo", "categoria")

ALFABETO = "abcdefghijklmnopqrstuvwxyz0123456789"
VOCALES = "aeiou"
CONECTORES = {"y", "e", "de", "del", "la", "el"}

MIN_LETRAS_NIVEL_1 = 4
MIN_LETRAS_NIVEL_3 = 5
MIN_LETRAS_APODO = 6
MIN_LETRAS_TRUNCADO = 7
MIN_LETRAS_ERROR = 3
MAX_CAMBIOS_TRANSLITERACION = 3
MAX_LETRAS_CONTEXTO = 4  # nombres cortos: sus errores solo valen junto a su pareja

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
PALABRAS_COMUNES_PATH = DATA_DIR / "palabras_comunes_es.txt"
# Solo archivos que viajan en la imagen de Docker (data/): si se usara
# eval/, el mismo nombre daría filas distintas dentro y fuera del contenedor.
_FUENTES_VOCABULARIO = (DATA_DIR / "intents_dataset.csv", DATA_DIR / "frases_por_categoria.txt")

# Teclado QWERTY español (la ñ no existe tras normalizar()).
_FILAS_TECLADO = ("qwertyuiop", "asdfghjkl", "zxcvbnm")


def _vecinas_teclado() -> dict[str, str]:
    vecinas = {}
    for r, fila in enumerate(_FILAS_TECLADO):
        for i, letra in enumerate(fila):
            cercanas = {fila[j] for j in (i - 1, i + 1) if 0 <= j < len(fila)}
            if r > 0:
                arriba = _FILAS_TECLADO[r - 1]
                cercanas |= {arriba[j] for j in (i, i + 1) if 0 <= j < len(arriba)}
            if r < len(_FILAS_TECLADO) - 1:
                abajo = _FILAS_TECLADO[r + 1]
                cercanas |= {abajo[j] for j in (i - 1, i) if 0 <= j < len(abajo)}
            vecinas[letra] = "".join(sorted(cercanas))
    return vecinas


VECINAS_TECLADO = _vecinas_teclado()

# Reglas fonéticas del español: (patrón, reemplazo). Cada aplicación cambia
# UNA aparición del patrón; el nivel 2 combina hasta dos.
REGLAS_FONETICAS = [
    (r"b", "v"), (r"v", "b"),
    (r"c(?=[ei])", "s"), (r"c(?=[ei])", "z"), (r"s(?=[ei])", "c"), (r"s", "z"),
    (r"z", "s"), (r"z(?=[ei])", "c"),
    (r"ll", "y"), (r"y(?=[aeiou])", "ll"),
    (r"(?<![cs])h", ""), (r"^(?=[aeiou])", "h"), (r"(?<![cs])h", "j"),
    (r"c(?=[aou]|[^aeiouh]|$)", "k"), (r"k(?=[aou])", "c"), (r"k(?=[ei])", "qu"),
    (r"qu(?=[ei])", "k"),
    (r"g(?=[ei])", "j"), (r"j(?=[ei])", "g"),
    (r"x", "s"), (r"x", "ks"), (r"x", "cs"), (r"ks", "x"), (r"cs", "x"), (r"s", "x"),
    (r"w", "gu"), (r"w", "u"), (r"gu(?=[aeiou])", "w"), (r"u(?=[aeiou])", "w"),
    (r"y", "i"), (r"i", "y"),
    (r"([a-z])\1", r"\1"),
    (r"sh", "ch"), (r"ch", "sh"),
]
_REGLAS_FONETICAS = [(re.compile(p), r) for p, r in REGLAS_FONETICAS]

# Transliteración de nombres extranjeros "como suenan" (inglés, francés,
# alemán): (patrón, alternativas). El idioma se deduce por los patrones
# mismos (-ault, eau, ee, oo, w, th...). Se cambian hasta 3 apariciones a
# la vez porque una lectura extranjera toca varias letras juntas
# ("geely" -> "yili" son tres cambios).
REGLAS_EXTRANJERAS = [
    (r"ee", ("i",)), (r"ea", ("i",)), (r"oo", ("u",)), (r"ou", ("u",)),
    (r"ay", ("ei", "ai")), (r"ey", ("ei", "i")), (r"ai", ("ei",)),
    (r"y$", ("i",)), (r"y(?=[^aeiou])", ("i",)),
    (r"^j", ("y",)), (r"g(?=[eiy])", ("y", "j")),
    (r"^h", ("j", "")), (r"hy", ("ji", "y", "i")),
    (r"th", ("t",)), (r"ph", ("f",)), (r"ck", ("k", "c")),
    (r"w", ("gu", "u", "v")),
    (r"cc", ("ks", "x", "c")), (r"cs", ("s", "x")),
    (r"ault$", ("o", "ol")), (r"eau", ("o",)), (r"au", ("o",)), (r"eu", ("e",)),
    (r"et$", ("e",)), (r"ot$", ("o",)), (r"geo", ("jo", "yo")),
    (r"ei", ("ai",)), (r"ie", ("i",)), (r"sch", ("sh", "ch")),
    (r"qu", ("k",)),
]
_REGLAS_EXTRANJERAS = [(re.compile(p), alts) for p, alts in REGLAS_EXTRANJERAS]

_INSEPARABLES = {"bl", "br", "cl", "cr", "dr", "fl", "fr", "gl", "gr", "kl", "kr",
                 "pl", "pr", "tr", "ch", "ll", "rr", "sh", "th"}


def _letras(texto: str) -> int:
    return len(texto.replace(" ", ""))


# ---------------------------------------------------------------- nivel 1


def ediciones_una_letra(palabra: str) -> dict[str, str]:
    """Todas las ediciones de una sola letra, con la nota del tipo de error."""
    res: dict[str, str] = {}

    def agregar(variante: str, nota: str) -> None:
        if variante != palabra and variante not in res:
            res[variante] = nota

    for i in range(len(palabra)):
        agregar(palabra[:i] + palabra[i + 1:], "falta una letra")
        agregar(palabra[:i] + palabra[i] + palabra[i:], "letra repetida")
        if i < len(palabra) - 1:
            agregar(palabra[:i] + palabra[i + 1] + palabra[i] + palabra[i + 2:], "letras intercambiadas")
    for i in range(len(palabra)):
        for c in ALFABETO:
            agregar(palabra[:i] + c + palabra[i + 1:], "letra cambiada")
    for i in range(len(palabra) + 1):
        for c in ALFABETO:
            agregar(palabra[:i] + c + palabra[i:], "letra de más")
    return res


def _espacios_internos(palabra: str) -> set[str]:
    """Un espacio de más dentro de la palabra: "hilux" -> "hi lux"."""
    return {palabra[:i] + " " + palabra[i:] for i in range(2, len(palabra) - 1)}


def _repeticiones(palabra: str) -> set[str]:
    return {palabra[:i] + palabra[i] + palabra[i:] for i in range(len(palabra)) if palabra[i].isalpha()}


# ---------------------------------------------------------------- nivel 2


def fonetico_una_regla(texto: str) -> set[str]:
    res = set()
    for patron, reemplazo in _REGLAS_FONETICAS:
        for m in patron.finditer(texto):
            res.add(texto[:m.start()] + m.expand(reemplazo) + texto[m.end():])
    res.discard(texto)
    return res


def fonetico_dos_reglas(texto: str) -> set[str]:
    una = fonetico_una_regla(texto)
    dos = set()
    for variante in una:
        dos |= fonetico_una_regla(variante)
    return (una | dos) - {texto}


def transliteraciones(palabra: str) -> set[str]:
    """Lecturas de un nombre extranjero por un hispanohablante."""
    apariciones = []
    for patron, alternativas in _REGLAS_EXTRANJERAS:
        for m in patron.finditer(palabra):
            apariciones.append((m.start(), m.end(), alternativas))
    apariciones.sort()
    res = set()
    for k in range(1, MAX_CAMBIOS_TRANSLITERACION + 1):
        for grupo in combinations(apariciones, k):
            if any(a[1] > b[0] for a, b in zip(grupo, grupo[1:])):
                continue  # dos reglas sobre las mismas letras
            for elegidas in product(*(g[2] for g in grupo)):
                partes, cursor = [], 0
                for (inicio, fin, _), alt in zip(grupo, elegidas):
                    partes += [palabra[cursor:inicio], alt]
                    cursor = fin
                partes.append(palabra[cursor:])
                res.add("".join(partes))
    res.discard(palabra)
    return res


def silabas(palabra: str) -> list[str]:
    """Silabeo simple del español (núcleos vocálicos, grupos inseparables)."""
    es_vocal = [c in VOCALES or (c == "y" and (i == len(palabra) - 1 or palabra[i + 1] not in VOCALES))
                for i, c in enumerate(palabra)]
    nucleos, i = [], 0
    while i < len(palabra):
        if es_vocal[i]:
            j = i
            while j + 1 < len(palabra) and es_vocal[j + 1]:
                j += 1
            nucleos.append((i, j))
            i = j + 1
        else:
            i += 1
    if len(nucleos) <= 1:
        return [palabra]
    cortes = []
    for (_, fin), (inicio, _) in zip(nucleos, nucleos[1:]):
        grupo = palabra[fin + 1:inicio]
        if len(grupo) <= 1:
            cortes.append(fin + 1)
        elif len(grupo) == 2:
            cortes.append(fin + 1 if grupo in _INSEPARABLES else fin + 2)
        else:
            cortes.append(inicio - 2 if grupo[-2:] in _INSEPARABLES else inicio - 1)
    trozos, previo = [], 0
    for c in cortes:
        trozos.append(palabra[previo:c])
        previo = c
    trozos.append(palabra[previo:])
    return trozos


def apodos(palabra: str) -> set[str]:
    """Acortamientos coloquiales: "chevrolet" -> "chevy", "toyota" -> "toyo"."""
    if len(palabra) < MIN_LETRAS_APODO:
        return set()
    trozos = silabas(palabra)
    res = set()
    for k in range(1, len(trozos)):
        prefijo = "".join(trozos[:k])
        siguiente = trozos[k]
        # "chev" (termina en consonante) ya sirve de base; "to" necesita la
        # consonante que sigue: "toy".
        bases = {prefijo} if k >= 2 or prefijo[-1] not in VOCALES else set()
        if prefijo[-1] in VOCALES and siguiente[0] not in VOCALES:
            bases.add(prefijo + siguiente[0])
        for base in bases:
            res.add(base)
            if base[-1] not in VOCALES:
                res |= {base + "i"} if base[-1] == "y" else {base + "i", base + "y"}
    return {a for a in res if len(a) >= MIN_LETRAS_ERROR + 1 and a != palabra and len(a) < len(palabra) - 1}


def partes_y_siglas(normalizado: str) -> set[str]:
    """Partes sueltas y siglas de nombres compuestos ("Spark GT" -> "sgt").

    Las siglas de 2 letras no se generan: sin contexto chocan con cualquier
    abreviatura ("mb", "cc"); quedan para filas manuales.
    """
    palabras = normalizado.split()
    if len(palabras) < 2:
        return set()
    res = {p for p in palabras if len(p) >= MIN_LETRAS_NIVEL_1 and p not in CONECTORES}
    con_conector = "".join(p[0] for p in palabras)
    sin_conector = "".join(p[0] for p in palabras if p not in CONECTORES)
    # Las palabras de 3 letras o menos ("gt") se conservan completas: "sgt".
    siglas_mixtas = "".join(p[0] if len(p) > 3 else p for p in palabras if p not in CONECTORES)
    res |= {s for s in (con_conector, sin_conector, siglas_mixtas) if len(s) >= 3}
    res.discard(normalizado)
    return res


# ---------------------------------------------------------------- nivel 3


def ediciones_realistas(palabra: str) -> set[str]:
    """Errores de tipeo realistas: borrar, repetir, intercambiar, letra vecina."""
    res = set()
    for i in range(len(palabra)):
        res.add(palabra[:i] + palabra[i + 1:])
        res.add(palabra[:i] + palabra[i] + palabra[i:])
        if i < len(palabra) - 1:
            res.add(palabra[:i] + palabra[i + 1] + palabra[i] + palabra[i + 2:])
        for c in VECINAS_TECLADO.get(palabra[i], ""):
            res.add(palabra[:i] + c + palabra[i + 1:])
    res.discard(palabra)
    return res


def _truncados(palabra: str) -> set[str]:
    if len(palabra) < MIN_LETRAS_TRUNCADO:
        return set()
    return {palabra[:n] for n in range(max(5, len(palabra) - 3), len(palabra) - 1)}


def _repeticiones_de_mas(palabra: str) -> set[str]:
    res = {palabra + palabra[-1] * k for k in (2, 3)}
    res |= {palabra[:i] + palabra[i] * 2 + palabra[i:] for i in range(len(palabra)) if palabra[i].isalpha()}
    return res


# ---------------------------------------------------------------- generador


def _variantes_palabra(palabra: str, niveles) -> dict[str, tuple[int, str]]:
    """Variantes de UNA palabra -> (nivel, nota), respetando los mínimos."""
    res: dict[str, tuple[int, str]] = {}

    def agregar(variantes, nivel: int, nota) -> None:
        for v in sorted(variantes):
            if v != palabra and v not in res:
                res[v] = (nivel, nota(v) if callable(nota) else nota)

    letras = len(palabra)
    if palabra.isdigit():
        return res
    if letras < MIN_LETRAS_NIVEL_1:
        if 1 in niveles:
            agregar(_repeticiones(palabra), 1, "letra repetida")
        return res

    if 1 in niveles:
        una = ediciones_una_letra(palabra)
        agregar(una, 1, una.get)
        agregar(_espacios_internos(palabra), 1, "espacio")
    if 2 in niveles:
        extranjeras = transliteraciones(palabra)
        agregar(extranjeras, 2, "fonético extranjero")
        agregar(fonetico_dos_reglas(palabra), 2, "fonético")
        agregar(apodos(palabra), 2, "apodo")
    if 3 in niveles and letras >= MIN_LETRAS_NIVEL_3:
        realistas = ediciones_realistas(palabra)
        dos_tipeos = set()
        for v in realistas:
            dos_tipeos |= ediciones_realistas(v)
        fonetico_mas_tipeo = set()
        for v in fonetico_una_regla(palabra) | transliteraciones(palabra):
            fonetico_mas_tipeo |= ediciones_realistas(v)
        agregar(dos_tipeos, 3, "dos errores de tipeo")
        agregar(fonetico_mas_tipeo, 3, "fonético + tipeo")
        agregar(_truncados(palabra), 3, "truncado")
        agregar(_repeticiones_de_mas(palabra), 3, "letras repetidas de más")
    return res


def generar_errores(nombre: str, tipo: str, niveles=(1, 2, 3)) -> list[dict]:
    """Posibles errores de escritura de un nombre del catálogo.

    Trabaja sobre el nombre normalizado pero devuelve "correcto" tal como
    está en el catálogo. NO aplica el control de colisiones contra otros
    nombres (depende del catálogo completo): eso lo hace filtrar_errores().
    Sí descarta lo que no puede ser un error útil (igual al nombre, menos
    de 3 letras). Determinista: salida ordenada.
    """
    if tipo not in TIPOS:
        raise ValueError(f"Tipo inválido: {tipo!r}. Válidos: {', '.join(TIPOS)}")
    normalizado = normalizar(nombre)
    if not normalizado:
        return []
    palabras = normalizado.split()
    niveles = set(niveles)
    variantes: dict[str, tuple[int, str]] = {}

    def agregar(texto: str, nivel: int, nota: str) -> None:
        texto = re.sub(r"\s+", " ", texto).strip()
        if texto and texto != normalizado and (texto not in variantes or variantes[texto][0] > nivel):
            variantes[texto] = (nivel, nota)

    if len(palabras) > 1 and _letras(normalizado) < MIN_LETRAS_NIVEL_1:
        # Nombre corto con separador ("CX-5"): solo la forma junta y letras repetidas.
        if 1 in niveles:
            agregar("".join(palabras), 1, "espacio")
            for i, palabra in enumerate(palabras):
                for v in _repeticiones(palabra):
                    agregar(" ".join(palabras[:i] + [v] + palabras[i + 1:]), 1, "letra repetida")
    elif len(palabras) == 1:
        for v, (nivel, nota) in _variantes_palabra(normalizado, niveles).items():
            agregar(v, nivel, nota)
    else:
        # Palabra por palabra, dejando las demás igual.
        for i, palabra in enumerate(palabras):
            for v, (nivel, nota) in _variantes_palabra(palabra, niveles).items():
                agregar(" ".join(palabras[:i] + [v] + palabras[i + 1:]), nivel, nota)
        # Del conjunto: espacio de menos, conector omitido, errores sobre la forma junta.
        junto = "".join(palabras)
        sin_conector = [p for p in palabras if p not in CONECTORES]
        if 1 in niveles:
            agregar(junto, 1, "espacio")
            agregar(" ".join(sin_conector), 1, "espacio")
            agregar("".join(sin_conector), 1, "espacio")
            if len(junto) >= MIN_LETRAS_NIVEL_1 and not junto.isdigit():
                for v, nota in ediciones_una_letra(junto).items():
                    agregar(v, 1, nota)
        if 2 in niveles:
            for v in fonetico_una_regla(normalizado):
                agregar(v, 2, "fonético")
            for v in partes_y_siglas(normalizado):
                agregar(v, 2, "sigla" if " " not in v and v not in palabras else "parte")
        if 3 in niveles:
            # Un error realista en cada una de las dos palabras más largas.
            largas = sorted((i for i, p in enumerate(palabras) if len(p) >= MIN_LETRAS_NIVEL_3),
                            key=lambda i: (-len(palabras[i]), i))[:2]
            if len(largas) == 2:
                a, b = sorted(largas)
                for va in sorted(ediciones_realistas(palabras[a])):
                    for vb in sorted(ediciones_realistas(palabras[b])):
                        copia = list(palabras)
                        copia[a], copia[b] = va, vb
                        agregar(" ".join(copia), 3, "dos errores de tipeo")

    filas = [
        {"tipo": tipo, "error": error, "correcto": nombre.strip(), "nivel": nivel,
         "origen": "auto", "nota": nota}
        for error, (nivel, nota) in variantes.items()
        if _letras(error) >= MIN_LETRAS_ERROR
    ]
    return sorted(filas, key=lambda f: (f["nivel"], f["error"]))


def generar_errores_contextuales(marca: str, modelo: str) -> list[dict]:
    """Errores de nombres cortos que solo se aceptan junto a su pareja.

    Solos, casi todos los errores de "Kia", "Rio" o "Ford" son palabras
    normales o ruido ("kiu", "roi", "fod"), por eso generar_errores() no
    los produce. Pegados a la otra mitad del vehículo el contexto los
    desambigua: "kiu rio" -> Kia, "kia roi" -> Rio, "fprdd escape" -> Ford.
    Se genera para el lado de 4 letras o menos: nivel 1 completo (todas las
    ediciones de una letra) y nivel 3 (dos errores de tipeo realistas).
    """
    marca_n, modelo_n = normalizar(marca), normalizar(modelo)
    if not marca_n or not modelo_n:
        return []
    filas = []
    for tipo, nombre, propio, pareja, delante in (
        ("marca", marca, marca_n, modelo_n, True),
        ("modelo", modelo, modelo_n, marca_n, False),
    ):
        if _letras(propio) > MAX_LETRAS_CONTEXTO or propio.replace(" ", "").isdigit():
            continue
        tokens = propio.split()
        variantes: dict[str, tuple[int, str]] = {}
        for i, token in enumerate(tokens):
            if token.isdigit():
                continue
            una = ediciones_una_letra(token)
            dos = set()
            for v in ediciones_realistas(token):
                dos |= ediciones_realistas(v)
            for v, nivel, nota in [(v, 1, n) for v, n in sorted(una.items())] + \
                                  [(v, 3, "dos errores de tipeo") for v in sorted(dos - set(una))]:
                if not v:
                    continue
                texto = " ".join(tokens[:i] + [v] + tokens[i + 1:])
                if texto != propio and texto not in variantes:
                    variantes[texto] = (nivel, f"{nota} (contexto)")
        for texto, (nivel, nota) in variantes.items():
            error = f"{texto} {pareja}" if delante else f"{pareja} {texto}"
            filas.append({"tipo": tipo, "error": error, "correcto": nombre.strip(), "nivel": nivel,
                          "origen": "auto", "nota": nota})
    return sorted(filas, key=lambda f: (f["tipo"], f["nivel"], f["error"]))


# ---------------------------------------------------------------- colisiones


@lru_cache(maxsize=1)
def palabras_comunes() -> frozenset[str]:
    """Palabras que NO pueden ser un error de marca/modelo/categoría.

    Lista a mano (data/palabras_comunes_es.txt) + stopwords del
    preprocesamiento + todo el vocabulario de las frases de entrenamiento
    (data/): si una palabra aparece en consultas reales, es una palabra que
    la gente usa con su propio significado.
    """
    palabras = set(STOPWORDS_ES)
    if PALABRAS_COMUNES_PATH.exists():
        for linea in PALABRAS_COMUNES_PATH.read_text(encoding="utf-8").splitlines():
            linea = linea.split("#", 1)[0].strip()
            if linea:
                palabras.add(normalizar(linea))
    for ruta in _FUENTES_VOCABULARIO:
        if ruta.exists():
            with ruta.open(encoding="utf-8", newline="") as f:
                for fila in csv.reader(f):
                    for celda in fila[:1]:
                        palabras.update(normalizar(celda).split())
    return frozenset(p for p in palabras if p)


def formas_de(nombre: str) -> set[str]:
    """Formas con que un nombre oficial puede aparecer ya normalizado."""
    n = normalizar(nombre)
    return {n, n.replace(" ", "")} if n else set()


def es_palabra_comun(error: str, comunes=None, nombre_propio: str | None = None) -> bool:
    """¿El error es (o está hecho solo de) palabras comunes?

    nombre_propio: el nombre del que es error. Su forma junta y sus propias
    palabras no cuentan como comunes: "ba terias" junto es "baterias", que
    es el nombre mismo, y "correas bandas" solo usa palabras de "Correas y
    Bandas".
    """
    comunes = palabras_comunes() if comunes is None else comunes
    tokens = error.split()
    junto = error.replace(" ", "")
    if nombre_propio:
        propio = normalizar(nombre_propio)
        if junto == propio.replace(" ", "") or (len(tokens) > 1 and set(tokens) <= set(propio.split())):
            return False
    return error in comunes or junto in comunes or all(t in comunes for t in tokens)


def clave_fonetica(texto: str) -> str:
    """Clave fonética del español (tipo Soundex, hecha a mano).

    Dos escrituras que suenan igual dan la misma clave: "chebrolet",
    "shevrolet" y "chevrolet" -> "chebrolet"; "hilux", "ilux" -> "ilus".
    """
    t = normalizar(texto).replace(" ", "")
    for patron, reemplazo in (
        (r"ee", "i"), (r"oo", "u"), (r"ph", "f"), (r"th", "t"), (r"sh", "ch"), (r"ck", "k"),
        (r"w", "u"), (r"qu(?=[ei])", "k"), (r"c(?=[ei])", "s"), (r"ch", "\x00"), (r"c", "k"),
        (r"z", "s"), (r"x", "s"), (r"ks", "s"), (r"g(?=[ei])", "j"), (r"gu(?=[ei])", "g"),
        (r"ll", "y"), (r"v", "b"), (r"h", ""), (r"\x00", "ch"), (r"y", "i"),
    ):
        t = re.sub(patron, reemplazo, t)
    return re.sub(r"([a-z])\1+", r"\1", t)


COLUMNAS_AVISOS = ["tipo", "error", "correcto", "nivel", "motivo"]
MOTIVO_COLISION = "apunta a dos nombres distintos"


def _aviso(fila: dict, motivo: str) -> dict:
    return {"tipo": fila["tipo"], "error": fila["error"], "correcto": fila["correcto"],
            "nivel": fila["nivel"], "motivo": motivo}


def cerca_de_nombres(errores: list[str], nombres: list[str]) -> list[list[str]]:
    """Para cada error, los nombres oficiales a distancia 0 o 1 (Damerau-Levenshtein).

    Vectorizado con process.cdist: comparar 50 mil errores contra todo el
    catálogo en un bucle de Python tardaría varios segundos.
    """
    formas = [(forma, nombre) for nombre in nombres for forma in sorted(formas_de(nombre))]
    resultado: list[list[str]] = [[] for _ in errores]
    if not errores or not formas:
        return resultado
    textos = [f for f, _ in formas]
    for inicio in range(0, len(errores), 20000):
        bloque = errores[inicio:inicio + 20000]
        matriz = process.cdist(bloque, textos, scorer=DamerauLevenshtein.distance,
                               score_cutoff=1, dtype=np.int32, workers=-1)
        for fila, col in zip(*np.nonzero(matriz <= 1)):
            nombre = formas[col][1]
            if nombre not in resultado[inicio + fila]:
                resultado[inicio + fila].append(nombre)
    return resultado


def filtrar_errores(candidatas, nombres_oficiales, existentes=None, bloqueadas=frozenset(), comunes=None):
    """Control de colisiones y falsos positivos antes de aceptar un error.

    Se descarta (y se devuelve como aviso con el motivo) todo error que:
    1. sea igual a otro nombre oficial del catálogo o esté a un paso de él;
    2. sea una palabra común del español;
    3. apunte a dos nombres distintos (con cualquier tipo). Si uno de los
       dos es una fila manual, gana la manual.

    candidatas: filas nuevas. nombres_oficiales: todos los nombres del
    catálogo (de cualquier tipo). existentes: {error: fila} ya aceptadas,
    para detectar la colisión 3 contra lo que ya está en la tabla.
    bloqueadas: errores que ya colisionaron antes (no se vuelven a aceptar).

    Devuelve (aceptadas, avisos, errores_a_quitar_de_existentes).
    """
    existentes = existentes or {}
    comunes = palabras_comunes() if comunes is None else comunes
    oficiales = sorted({n.strip() for n in nombres_oficiales if normalizar(n)})
    avisos: list[dict] = []

    # Deduplicar: mismo error y mismo nombre -> nivel más bajo, manual antes que auto.
    unicas: dict[tuple, dict] = {}
    for fila in candidatas:
        clave = (fila["tipo"], fila["error"], normalizar(fila["correcto"]))
        previa = unicas.get(clave)
        orden = (fila["origen"] == "auto", int(fila["nivel"]))
        if previa is None or orden < (previa["origen"] == "auto", int(previa["nivel"])):
            unicas[clave] = fila
    filas = sorted(unicas.values(), key=lambda f: (f["tipo"], f["correcto"], int(f["nivel"]), f["error"]))

    vivas = []
    cercanos = cerca_de_nombres([f["error"] for f in filas], oficiales)
    for fila, nombres in zip(filas, cercanos):
        propio = normalizar(fila["correcto"])
        if fila["error"] == propio:
            avisos.append(_aviso(fila, "igual al nombre correcto"))
            continue
        otros = [n for n in nombres if normalizar(n) != propio]
        if otros:
            iguales = [n for n in otros if fila["error"] in formas_de(n)]
            motivo = (f"igual al nombre oficial '{iguales[0]}'" if iguales
                      else f"a un paso del nombre oficial '{otros[0]}'")
            avisos.append(_aviso(fila, motivo))
            continue
        if es_palabra_comun(fila["error"], comunes, fila["correcto"]):
            avisos.append(_aviso(fila, "palabra común del español"))
            continue
        if fila["error"] in bloqueadas:
            avisos.append(_aviso(fila, MOTIVO_COLISION))
            continue
        vivas.append(fila)

    # Colisión 3: el mismo error hacia dos nombres distintos (nuevas + existentes).
    por_error: dict[str, list[dict]] = {}
    for fila in vivas:
        por_error.setdefault(fila["error"], []).append(fila)
    aceptadas, quitar = [], []
    for error, grupo in por_error.items():
        previa = existentes.get(error)
        todos = grupo + ([previa] if previa is not None else [])
        destinos = {(f["tipo"], normalizar(f["correcto"])) for f in todos}
        if len(destinos) == 1:
            if previa is None:
                aceptadas.append(grupo[0])
            continue
        manuales = {(f["tipo"], normalizar(f["correcto"])) for f in todos if f["origen"] == "manual"}
        ganadora = next(iter(manuales)) if len(manuales) == 1 else None
        for f in todos:
            if ganadora is not None and (f["tipo"], normalizar(f["correcto"])) == ganadora:
                if f is not previa:
                    aceptadas.append(f)
                continue
            avisos.append(_aviso(f, MOTIVO_COLISION))
            if f is previa:
                quitar.append(error)
    aceptadas.sort(key=lambda f: (f["tipo"], f["correcto"], int(f["nivel"]), f["error"]))
    return aceptadas, avisos, quitar

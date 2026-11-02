"""Verifica por programa que el material de entrenamiento no se solape con los conjuntos congelados.

Compara, tras normalizar (minúsculas, sin tildes ni puntuación, espacios colapsados):
  (a) data/intents_dataset.csv           contra eval/holdout_intent_v2.csv   (por texto)
  (b) data/errores/posibles_errores.csv y data/posibles_errores_manuales.csv
      contra eval/holdout_errores_v2.csv                                      (mismo tipo + mismo error)

Este script LEE los archivos congelados porque es un programa; nunca imprime su contenido.
Imprime solo conteos y, por cada fila NUEVA del entrenamiento que se solapa, el texto / la fila
y su posición, para poder quitarla de lo agregado. Las filas anteriores (las que ya estaban en la
línea base) solo se cuentan: no se pueden tocar.

Qué es "nueva": la que no está en la línea base. La línea base se toma, en este orden, de
  1. --base DIR   (carpeta con copias de intents_dataset.csv, posibles_errores.csv y
                   posibles_errores_manuales.csv tal como estaban antes de ampliar);
  2. git show HEAD:<ruta>  si el comando git está disponible y la ruta está versionada;
  3. si no hay línea base, todas las filas se tratan como nuevas.

Opciones --emitir-intents / --emitir-errores: escriben a un archivo las filas nuevas solapadas
(una por línea; los errores como "tipo<TAB>error") para que el generador las excluya y se vuelva
a ejecutar hasta llegar a cero.

Para las frases el criterio es el de tests/test_holdouts_v2.py: igual tras normalizar, mismo
núcleo de palabras (sin dígitos ni stopwords) o token_sort_ratio >= 90 contra alguna frase del
congelado. Para los errores basta el par (tipo, error) idéntico. Los pares de la tabla que ya
existían y coinciden con el congelado son intencionales (columna en_tabla=1 del holdout): se
cuentan como informativos y no son fallo.

Código de salida: 0 si no hay solapamiento accionable; 1 si lo hay (filas nuevas solapadas, o
cualquier solapamiento del dataset de intenciones); 2 si falta un archivo.
"""
import argparse
import csv
import io
import re
import subprocess
import sys
from pathlib import Path

from rapidfuzz import fuzz, process

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.preprocessing import STOPWORDS_ES, normalizar  # noqa: E402

DATASET = ROOT / "data" / "intents_dataset.csv"
TABLA = ROOT / "data" / "errores" / "posibles_errores.csv"
MANUALES = ROOT / "data" / "posibles_errores_manuales.csv"
HOLDOUT_INTENT = ROOT / "eval" / "holdout_intent_v2.csv"
HOLDOUT_ERRORES = ROOT / "eval" / "holdout_errores_v2.csv"
UMBRAL_FUZZY_VARIANTE = 90  # el mismo que tests/test_holdouts_v2.py
_PREVIAS_ERRORES = [0]
_NUEVAS_SOLAPADAS = [0]  # acumulador de filas nuevas solapadas (intenciones + errores)


def leer_filas(texto: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(texto, newline="")))


def leer_archivo(ruta: Path) -> str:
    return ruta.read_text(encoding="utf-8-sig")


def indice_columnas(cabecera: list[str], nombres: tuple[str, ...], por_defecto: tuple[int, ...]) -> list[int]:
    minusculas = [c.strip().lower() for c in cabecera]
    if all(n in minusculas for n in nombres):
        return [minusculas.index(n) for n in nombres]
    return list(por_defecto)


def linea_base(nombre: str, ruta: Path, base_dir: Path | None) -> str | None:
    if base_dir is not None:
        candidato = base_dir / nombre
        return leer_archivo(candidato) if candidato.exists() else None
    try:
        rel = ruta.relative_to(ROOT.parent).as_posix()
        salida = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=ROOT.parent, capture_output=True, check=True)
        return salida.stdout.decode("utf-8-sig")
    except (OSError, subprocess.CalledProcessError, ValueError):
        return None


def claves_texto(texto: str | None, columna: tuple[str, ...], por_defecto: tuple[int, ...]) -> set:
    if texto is None:
        return set()
    filas = leer_filas(texto)
    if not filas:
        return set()
    cols = indice_columnas(filas[0], columna, por_defecto)
    return {tuple(normalizar(f[c]) if i == len(cols) - 1 or len(cols) == 1 else f[c].strip().lower()
                  for i, c in enumerate(cols)) for f in filas[1:] if len(f) > max(cols)}


def _nucleo(normalizado: str) -> frozenset:
    """Tokens sin dígitos ni stopwords (igual que tests/test_holdouts_v2.py)."""
    sin_digitos = re.sub(r"\d+", " ", normalizado)
    return frozenset(t for t in sin_digitos.split() if t not in STOPWORDS_ES)


def verificar_intenciones(base_dir, emitir) -> int:
    """Una frase del entrenamiento choca con el congelado si es igual (normalizada), tiene el
    mismo núcleo de palabras o su similitud token_sort_ratio llega a 90 (variante trivial)."""
    if not DATASET.exists() or not HOLDOUT_INTENT.exists():
        print("FALTA un archivo: dataset de intenciones o holdout de intenciones")
        return -1
    congelado = leer_filas(leer_archivo(HOLDOUT_INTENT))
    cols_h = indice_columnas(congelado[0], ("texto",), (0,))
    normalizados = {normalizar(f[cols_h[0]]) for f in congelado[1:] if len(f) > cols_h[0]}
    normalizados.discard("")
    lista = sorted(normalizados)
    nucleos = {_nucleo(t) for t in lista}

    def motivo(norm: str) -> str | None:
        if norm in normalizados:
            return "igual"
        if _nucleo(norm) in nucleos:
            return "mismo nucleo"
        if lista and process.extractOne(norm, lista, scorer=fuzz.token_sort_ratio,
                                        score_cutoff=UMBRAL_FUZZY_VARIANTE) is not None:
            return "muy parecida"
        return None

    base = claves_texto(linea_base("intents_dataset.csv", DATASET, base_dir), ("texto",), (0,))
    filas = leer_filas(leer_archivo(DATASET))
    cols = indice_columnas(filas[0], ("texto",), (0,))
    total, nuevas, solapadas_previas, solapadas_nuevas = 0, 0, 0, []
    for indice, fila in enumerate(filas[1:], start=2):  # 1 = cabecera; las filas de datos empiezan en 2
        if len(fila) <= cols[0]:
            continue
        total += 1
        norm = normalizar(fila[cols[0]])
        es_nueva = (norm,) not in base if base else True
        nuevas += es_nueva
        razon = motivo(norm)
        if razon:
            if es_nueva:
                solapadas_nuevas.append((indice, fila[cols[0]], razon))
            else:
                solapadas_previas += 1
    print(f"[intenciones] filas={total} nuevas={nuevas} congeladas={len(normalizados)}")
    print(f"[intenciones] solapadas_nuevas={len(solapadas_nuevas)} solapadas_previas_no_tocables={solapadas_previas}")
    for indice, texto, razon in solapadas_nuevas:
        print(f"  fila {indice} ({razon}): {texto}")
    _NUEVAS_SOLAPADAS[0] += len(solapadas_nuevas)
    if emitir:
        Path(emitir).write_text("".join(t + "\n" for _, t, _ in solapadas_nuevas), encoding="utf-8")
    return len(solapadas_nuevas) + solapadas_previas


def verificar_errores(base_dir, emitir) -> int:
    if not HOLDOUT_ERRORES.exists() or not TABLA.exists():
        print("FALTA un archivo: tabla de errores o holdout de errores")
        return -1
    congelado = leer_filas(leer_archivo(HOLDOUT_ERRORES))
    cols_h = indice_columnas(congelado[0], ("tipo", "error"), (0, 1))
    pares_congelados = {(f[cols_h[0]].strip().lower(), normalizar(f[cols_h[1]])) for f in congelado[1:]
                        if len(f) > max(cols_h)}
    resultado = 0
    nuevas_solapadas_total = []
    for nombre, ruta in (("posibles_errores.csv", TABLA), ("posibles_errores_manuales.csv", MANUALES)):
        if not ruta.exists():
            continue
        texto_base = linea_base(nombre, ruta, base_dir)
        base = set()
        if texto_base:
            fb = leer_filas(texto_base)
            cb = indice_columnas(fb[0], ("tipo", "error"), (0, 1))
            base = {(f[cb[0]].strip().lower(), normalizar(f[cb[1]])) for f in fb[1:] if len(f) > max(cb)}
        filas = leer_filas(leer_archivo(ruta))
        cols = indice_columnas(filas[0], ("tipo", "error"), (0, 1))
        total, nuevas, previas, solapadas = 0, 0, 0, []
        for indice, fila in enumerate(filas[1:], start=2):
            if len(fila) <= max(cols):
                continue
            total += 1
            par = (fila[cols[0]].strip().lower(), normalizar(fila[cols[1]]))
            es_nueva = par not in base if base else True
            nuevas += es_nueva
            if par in pares_congelados:
                if es_nueva:
                    solapadas.append((indice, fila))
                else:
                    previas += 1
        print(f"[errores:{nombre}] filas={total} nuevas={nuevas} congelados={len(pares_congelados)}")
        print(f"[errores:{nombre}] solapadas_nuevas={len(solapadas)} solapadas_previas_no_tocables={previas}")
        for indice, fila in solapadas:
            print(f"  fila {indice}: {','.join(fila[:3])}")
        resultado += len(solapadas)  # las previas son el diseno de la columna en_tabla=1: solo informativas
        _PREVIAS_ERRORES[0] += previas
        _NUEVAS_SOLAPADAS[0] += len(solapadas)
        nuevas_solapadas_total += [(f[cols[0]].strip().lower(), normalizar(f[cols[1]])) for _, f in solapadas]
    if emitir:
        Path(emitir).write_text("".join(f"{t}\t{e}\n" for t, e in sorted(set(nuevas_solapadas_total))),
                                encoding="utf-8")
    return resultado


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", type=Path, default=None, help="carpeta con las copias originales (línea base)")
    ap.add_argument("--emitir-intents", default=None, help="archivo donde escribir las frases nuevas solapadas")
    ap.add_argument("--emitir-errores", default=None, help="archivo donde escribir los pares tipo<TAB>error nuevos solapados")
    args = ap.parse_args()
    a = verificar_intenciones(args.base, args.emitir_intents)
    b = verificar_errores(args.base, args.emitir_errores)
    if a < 0 or b < 0:
        return 2
    total = a + b
    print(f"SOLAPAMIENTO TOTAL = {total} (filas nuevas solapadas = {_NUEVAS_SOLAPADAS[0]}; "
          f"errores previos con en_tabla=1, informativo = {_PREVIAS_ERRORES[0]})")
    return 0 if total == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

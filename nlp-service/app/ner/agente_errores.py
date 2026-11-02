"""Agente que mantiene al día la tabla de posibles errores.

"Agente" = componente automático y determinista (no un LLM): cuando entra
una marca, un modelo o una categoría nueva al catálogo, genera todos sus
posibles errores con generador_errores.py, aplica el control de
colisiones, los agrega al CSV y actualiza la tabla EN MEMORIA del
extractor, de modo que el nombre nuevo queda buscable de inmediato, sin
reiniciar el servicio.

Se entera por dos vías:
1. Aviso directo: POST /nlp/errores/registrar (lo llama el backend PHP al
   crear un vehículo, ver backend/src/patterns/observer/ErroresNlpObserver.php).
2. Sincronización: sincronizar_catalogo() al arrancar el servicio y cada vez
   que dictionary.py refresca su caché, como red de seguridad si el aviso
   directo falló (backend sin red hacia el microservicio, servicio caído).

Persistencia: data/errores/ se monta como volumen en docker-compose. Aunque
se perdiera, las filas "auto" se regeneran solas porque el generador es
determinista; las "manual" vienen versionadas en data/posibles_errores_manuales.csv.

Uso manual (regenerar la tabla del catálogo semilla):
    python -m app.ner.agente_errores
"""
import csv
import logging
import os
import tempfile
import threading
import time
from pathlib import Path

from app.ner import extractor, repositorio_oracle
from app.ner.generador_errores import (
    COLUMNAS,
    COLUMNAS_AVISOS,
    DATA_DIR,
    MOTIVO_COLISION,
    TIPOS,
    _aviso,
    cerca_de_nombres,
    filtrar_errores,
    generar_errores,
    generar_errores_contextuales,
)
from app.preprocessing import normalizar

logger = logging.getLogger(__name__)

RUTA_TABLA = extractor.TABLA_ERRORES_PATH
RUTA_AVISOS = RUTA_TABLA.with_name("posibles_errores_avisos.csv")
RUTA_MANUALES = DATA_DIR / "posibles_errores_manuales.csv"

# Foto del catálogo semilla (database/seed_vehiculos.sql y /api/categorias),
# la misma que usan tests/test_ner.py y eval/eval_ner.py.
CATALOGO_SEMILLA = {
    "marca": ["Toyota", "Chevrolet", "Mazda", "Nissan", "Hyundai", "Kia", "Renault", "Ford", "Suzuki"],
    "modelo": [
        "Hilux", "Corolla", "Fortuner", "Spark", "Spark GT", "Aveo", "3", "CX-5",
        "Sentra", "Frontier", "Tucson", "Accent", "Rio", "Sportage", "Logan",
        "Duster", "Escape", "Fiesta", "Swift",
    ],
    "categoria": [
        "Filtros", "Frenos", "Baterías", "Suspensión", "Motor", "Transmisión",
        "Encendido", "Correas y Bandas",
    ],
}
# Parejas marca-modelo del catálogo semilla: los errores de nombres cortos
# (Kia, Rio, Ford...) se generan pegados a su pareja ("kiu rio").
PARES_SEMILLA = {
    "Toyota": ["Hilux", "Corolla", "Fortuner"], "Chevrolet": ["Spark", "Spark GT", "Aveo"],
    "Mazda": ["3", "CX-5"], "Nissan": ["Sentra", "Frontier"], "Hyundai": ["Tucson", "Accent"],
    "Kia": ["Rio", "Sportage"], "Renault": ["Logan", "Duster"], "Ford": ["Escape", "Fiesta"],
    "Suzuki": ["Swift"],
}

_lock = threading.RLock()
_estado: dict | None = None  # {"filas": {error: fila}, "avisos": [...], "nombres": {(tipo, norm): original}}


def _leer_csv(ruta: Path) -> list[dict]:
    try:
        with ruta.open(encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    except OSError:
        return []


def _escribir_csv_atomico(ruta: Path, columnas: list[str], filas: list[dict]) -> None:
    """Escribe a un temporal en la misma carpeta y lo cambia con os.replace.

    os.replace es atómico: quien lea el CSV ve el archivo viejo completo o
    el nuevo completo, nunca uno a medias. En Windows puede fallar un
    instante si otro proceso tiene el archivo abierto (antivirus, OneDrive):
    se reintenta un par de veces antes de rendirse.
    """
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fd, temporal = tempfile.mkstemp(dir=ruta.parent, prefix=f".{ruta.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            escritor = csv.DictWriter(f, fieldnames=columnas, extrasaction="ignore")
            escritor.writeheader()
            escritor.writerows(filas)
            f.flush()
            os.fsync(f.fileno())
        for intento in range(5):
            try:
                os.replace(temporal, ruta)
                return
            except PermissionError:
                if intento == 4:
                    raise
                time.sleep(0.05 * (intento + 1))
    finally:
        if os.path.exists(temporal):
            os.remove(temporal)


def _ordenar(filas) -> list[dict]:
    return sorted(filas, key=lambda f: (f["tipo"], f["correcto"], int(f["nivel"]), f["error"]))


def _tabla_para_extractor(filas: dict) -> dict:
    tabla: dict[str, dict[str, str]] = {}
    for fila in filas.values():
        tabla.setdefault(fila["tipo"], {})[fila["error"]] = fila["correcto"]
    return tabla


def _cargar_estado() -> dict:
    """Estado en memoria desde Oracle (si está configurado) o, si no, del CSV.

    Se lee una sola vez. El CSV es el respaldo: si Oracle no responde o su
    tabla está vacía, el servicio sigue funcionando igual que antes.
    """
    global _estado
    if _estado is None:
        desde_oracle = repositorio_oracle.leer()
        filas_leidas, avisos = desde_oracle if desde_oracle else (_leer_csv(RUTA_TABLA), _leer_csv(RUTA_AVISOS))
        filas = {f["error"]: f for f in filas_leidas if f.get("tipo") in TIPOS and f.get("error")}
        nombres = {(f["tipo"], normalizar(f["correcto"])): f["correcto"] for f in filas.values()}
        _estado = {"filas": filas, "avisos": avisos, "nombres": nombres}
    return _estado


def _bloqueadas(estado: dict) -> set[str]:
    return {a["error"] for a in estado["avisos"] if a.get("motivo") == MOTIVO_COLISION}


def _guardar_y_publicar(estado: dict) -> None:
    _escribir_csv_atomico(RUTA_TABLA, COLUMNAS, _ordenar(estado["filas"].values()))
    _escribir_csv_atomico(RUTA_AVISOS, COLUMNAS_AVISOS, estado["avisos"])
    repositorio_oracle.guardar(_ordenar(estado["filas"].values()), estado["avisos"])
    extractor.reemplazar_tabla_errores(_tabla_para_extractor(estado["filas"]))


def _cambiar_y_guardar(estado: dict, cambio) -> tuple[int, int]:
    """Aplica `cambio(estado)` y lo persiste; si falla la escritura, deshace
    el cambio en memoria para que memoria y disco sigan iguales (y un
    reintento vuelva a intentarlo en vez de decir "ya registrado")."""
    respaldo = (dict(estado["filas"]), list(estado["avisos"]), dict(estado["nombres"]))
    try:
        resultado = cambio(estado)
        _guardar_y_publicar(estado)
        return resultado
    except BaseException:
        estado["filas"], estado["avisos"], estado["nombres"] = respaldo
        raise


def _agregar_avisos(estado: dict, nuevos: list[dict]) -> None:
    vistos = {(a["tipo"], a["error"], a["correcto"], a["motivo"]) for a in estado["avisos"]}
    for a in nuevos:
        clave = (a["tipo"], a["error"], a["correcto"], a["motivo"])
        if clave not in vistos:
            vistos.add(clave)
            estado["avisos"].append(a)


def _incorporar(estado: dict, candidatas: list[dict], nombres_nuevos: list[tuple[str, str]]) -> tuple[int, int]:
    """Agrega filas nuevas con el control de colisiones. Devuelve (agregadas, descartadas)."""
    for tipo, nombre in nombres_nuevos:
        estado["nombres"][(tipo, normalizar(nombre))] = nombre
    oficiales = list(estado["nombres"].values())

    # Un nombre oficial nuevo puede volver inválidos errores que ya estaban
    # (ej. modelo nuevo "Hilus": "hilus" dejaba de ser error de Hilux).
    existentes = list(estado["filas"].values())
    cercanos = cerca_de_nombres([f["error"] for f in existentes], [n for _, n in nombres_nuevos])
    quitados = []
    for fila, nombres in zip(existentes, cercanos):
        otros = [n for n in nombres if normalizar(n) != normalizar(fila["correcto"])]
        if otros:
            quitados.append(_aviso(fila, f"a un paso del nombre oficial nuevo '{otros[0]}'"))
            del estado["filas"][fila["error"]]

    aceptadas, avisos, quitar = filtrar_errores(
        candidatas, oficiales, existentes=estado["filas"], bloqueadas=_bloqueadas(estado)
    )
    for error in quitar:
        estado["filas"].pop(error, None)
    for fila in aceptadas:
        estado["filas"][fila["error"]] = {k: fila[k] for k in COLUMNAS}
    _agregar_avisos(estado, quitados + avisos)
    return len(aceptadas), len(avisos) + len(quitados)


def _filas_manuales() -> list[dict]:
    return [f for f in _leer_csv(RUTA_MANUALES) if f.get("tipo") in TIPOS and f.get("error")]


def registrar_nombre(tipo: str, nombre: str, marca: str | None = None) -> dict:
    """Genera y agrega a la tabla los posibles errores de un nombre nuevo.

    Idempotente (registrar dos veces no duplica nada), seguro con hilos y
    con escritura atómica. Al terminar, el nombre ya es buscable en el
    extractor. Para un modelo, `marca` agrega además los errores con
    contexto de la pareja ("kiu rio"), que valen aunque el modelo ya
    estuviera registrado con otra marca.
    """
    if tipo not in TIPOS:
        raise ValueError(f"Tipo inválido: {tipo!r}. Válidos: {', '.join(TIPOS)}")
    nombre = (nombre or "").strip()
    if not normalizar(nombre):
        raise ValueError("El nombre no puede estar vacío")

    inicio = time.perf_counter()
    with _lock:
        estado = _cargar_estado()
        ya_registrado = (tipo, normalizar(nombre)) in estado["nombres"]
        candidatas = []
        if not ya_registrado:
            candidatas = [f for f in _filas_manuales()
                          if f["tipo"] == tipo and normalizar(f["correcto"]) == normalizar(nombre)]
            candidatas += generar_errores(nombre, tipo)
        if tipo == "modelo" and marca and normalizar(marca):
            descartados = {(a["error"], normalizar(a["correcto"])) for a in estado["avisos"]}
            candidatas += [f for f in generar_errores_contextuales(marca, nombre)
                           if f["error"] not in estado["filas"]
                           and (f["error"], normalizar(f["correcto"])) not in descartados]
        if not candidatas:
            return {"tipo": tipo, "nombre": nombre, "ya_registrado": ya_registrado, "agregadas": 0,
                    "descartadas": 0, "ms": round((time.perf_counter() - inicio) * 1000, 1)}
        agregadas, descartadas = _cambiar_y_guardar(
            estado, lambda e: _incorporar(e, candidatas, [] if ya_registrado else [(tipo, nombre)])
        )
    resumen = {"tipo": tipo, "nombre": nombre, "ya_registrado": ya_registrado, "agregadas": agregadas,
               "descartadas": descartadas, "ms": round((time.perf_counter() - inicio) * 1000, 1)}
    logger.info("Errores registrados para %s %r%s: %s", tipo, nombre, f" (marca {marca})" if marca else "", resumen)
    return resumen


def sincronizar_catalogo(catalogo: dict[str, list[str]] | None = None) -> dict:
    """Registra los nombres del catálogo que todavía no tienen errores en la tabla.

    Sin argumento pide el catálogo a dictionary.py (al arrancar el servicio).
    dictionary.py la llama con los valores recién refrescados de su caché.
    """
    if catalogo is None:
        from app.ner import dictionary  # diferido: dictionary.py importa este módulo

        catalogo = {
            "marca": dictionary.obtener_marcas(),
            "modelo": dictionary.obtener_modelos(),
            "categoria": dictionary.obtener_categorias(),
        }
    inicio = time.perf_counter()
    registrados, agregadas, descartadas = [], 0, 0
    with _lock:
        estado = _cargar_estado()
        # Filas manuales agregadas al repo después de crear el volumen.
        descartados_antes = {(a["error"], normalizar(a["correcto"])) for a in estado["avisos"]}
        manuales = [f for f in _filas_manuales()
                    if (f["tipo"], normalizar(f["correcto"])) in estado["nombres"]
                    and f["error"] not in estado["filas"]
                    and (f["error"], normalizar(f["correcto"])) not in descartados_antes]
        if manuales:
            n, d = _cambiar_y_guardar(estado, lambda e: _incorporar(e, manuales, []))
            agregadas, descartadas = agregadas + n, descartadas + d
        for tipo in TIPOS:
            for nombre in sorted(set(catalogo.get(tipo) or [])):
                if (tipo, normalizar(nombre)) in estado["nombres"] or not normalizar(nombre):
                    continue
                r = registrar_nombre(tipo, nombre)
                registrados.append(f"{tipo}:{nombre}")
                agregadas += r["agregadas"]
                descartadas += r["descartadas"]
    return {"registrados": registrados, "agregadas": agregadas, "descartadas": descartadas,
            "ms": round((time.perf_counter() - inicio) * 1000, 1)}


def regenerar_tabla(catalogo: dict[str, list[str]] | None = None, pares: dict | None = None) -> dict:
    """Reconstruye la tabla completa desde cero (filas manuales + generadas).

    Sin argumentos usa el catálogo semilla y sus parejas marca-modelo.
    """
    global _estado
    if catalogo is None:
        catalogo, pares = CATALOGO_SEMILLA, PARES_SEMILLA if pares is None else pares
    pares = pares or {}
    inicio = time.perf_counter()
    with _lock:
        _estado = {"filas": {}, "avisos": [], "nombres": {}}
        en_catalogo = {(t, normalizar(n)) for t in TIPOS for n in catalogo.get(t, [])}
        candidatas = [f for f in _filas_manuales() if (f["tipo"], normalizar(f["correcto"])) in en_catalogo]
        nombres = []
        for tipo in TIPOS:
            for nombre in catalogo.get(tipo, []):
                candidatas += generar_errores(nombre, tipo)
                nombres.append((tipo, nombre))
        for marca, modelos in pares.items():
            for modelo in modelos:
                candidatas += generar_errores_contextuales(marca, modelo)
        agregadas, descartadas = _incorporar(_estado, candidatas, nombres)
        _guardar_y_publicar(_estado)
    return {"agregadas": agregadas, "descartadas": descartadas,
            "ms": round((time.perf_counter() - inicio) * 1000, 1)}


def _reiniciar_estado() -> None:
    """Olvida el estado en memoria (lo vuelve a leer del CSV). Para pruebas."""
    global _estado
    with _lock:
        _estado = None


if __name__ == "__main__":
    print(regenerar_tabla())

"""Acceso opcional a las tablas posibles_errores y posibles_errores_avisos en Oracle.

Es opcional: solo se usa si ORACLE_NLP_DSN está definida y el paquete
oracledb está instalado. Cualquier fallo (sin variable, sin driver, sin red,
tablas ausentes) devuelve None y el agente sigue trabajando con el CSV, que
sigue siendo la copia de respaldo.

Variables de entorno: ORACLE_NLP_DSN (host:puerto/servicio), ORACLE_NLP_USER,
ORACLE_NLP_PASSWORD.
"""
import logging
import os

logger = logging.getLogger(__name__)

_COLS_FILAS = ("tipo", "error", "correcto", "nivel", "origen", "nota")
_COLS_AVISOS = ("tipo", "error", "correcto", "nivel", "motivo")


def disponible() -> bool:
    return bool(os.getenv("ORACLE_NLP_DSN"))


def _conectar():
    import oracledb  # import perezoso: el servicio arranca aunque no esté instalado

    return oracledb.connect(
        user=os.getenv("ORACLE_NLP_USER", "electrisys"),
        password=os.getenv("ORACLE_NLP_PASSWORD", ""),
        dsn=os.environ["ORACLE_NLP_DSN"],
    )


def _como_dict(columnas, fila) -> dict:
    return {c: ("" if v is None else str(v)) for c, v in zip(columnas, fila)}


def leer() -> tuple[list[dict], list[dict]] | None:
    """Devuelve (filas, avisos) desde Oracle, o None si no se pudo (usar el CSV)."""
    if not disponible():
        return None
    try:
        with _conectar() as conexion, conexion.cursor() as cursor:
            cursor.execute(f"SELECT {', '.join(_COLS_FILAS)} FROM posibles_errores")
            filas = [_como_dict(_COLS_FILAS, f) for f in cursor.fetchall()]
            cursor.execute(f"SELECT {', '.join(_COLS_AVISOS)} FROM posibles_errores_avisos")
            avisos = [_como_dict(_COLS_AVISOS, f) for f in cursor.fetchall()]
        if not filas:
            return None  # tabla vacía: mejor el CSV que quedarse sin tabla de errores
        return filas, avisos
    except Exception as exc:  # noqa: BLE001 - el respaldo CSV cubre cualquier causa
        logger.warning("No se pudo leer posibles_errores de Oracle, se usa el CSV: %s", exc)
        return None


def guardar(filas: list[dict], avisos: list[dict]) -> bool:
    """Reemplaza el contenido de ambas tablas en una sola transacción.

    Devuelve False si falló; el CSV ya quedó escrito, así que no se pierde nada.
    """
    if not disponible():
        return False
    try:
        with _conectar() as conexion, conexion.cursor() as cursor:
            cursor.execute("DELETE FROM posibles_errores")
            cursor.execute("DELETE FROM posibles_errores_avisos")
            cursor.executemany(
                "INSERT INTO posibles_errores (tipo, error, correcto, nivel, origen, nota) "
                "VALUES (:1, :2, :3, :4, :5, :6)",
                [(f["tipo"], f["error"], f["correcto"], int(f["nivel"]),
                  f.get("origen") or "auto", f.get("nota") or None) for f in filas],
            )
            cursor.executemany(
                "INSERT INTO posibles_errores_avisos (tipo, error, correcto, nivel, motivo) "
                "VALUES (:1, :2, :3, :4, :5)",
                [(a["tipo"], a["error"], a["correcto"], int(a["nivel"]), a["motivo"]) for a in avisos],
            )
            conexion.commit()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudo guardar posibles_errores en Oracle (el CSV quedó al día): %s", exc)
        return False

"""Acceso a la tabla POSIBLES_ERRORES de Oracle (oracle/13_posibles_errores.sql).

Oracle es la fuente principal de la tabla de errores del NER; el CSV
(data/errores/posibles_errores.csv) queda como respaldo cuando la base no
responde (ver extractor.obtener_tabla_errores y agente_errores).

Usa python-oracledb en modo "thin": se conecta por red al listener sin
instalar Oracle Instant Client en la imagen.

Configuración (mismas variables que el backend PHP, ver docker-compose.yml):
    DB_HOST, DB_PORT (1521), DB_SERVICE_NAME (FREEPDB1), DB_USER, DB_PASS
Sin DB_HOST o DB_USER, Oracle queda desactivado (desarrollo local y tests).

Todas las funciones LANZAN si la base falla: decidir qué hacer en ese caso
(usar el CSV, dejar la sincronización pendiente) es trabajo de quien llama.
"""
import logging
import os

logger = logging.getLogger(__name__)

TIMEOUT_CONEXION_SEGUNDOS = 3
TAMANO_LOTE = 1000  # filas por executemany: equilibrio entre viajes y memoria

SQL_CARGAR = "SELECT tipo, error, correcto FROM posibles_errores"
SQL_CARGAR_FILAS = "SELECT tipo, error, correcto, nivel, origen, nota FROM posibles_errores"

# Consulta puntual por la clave natural: la resuelve el índice único
# uq_posibles_errores (tipo, error) con un INDEX UNIQUE SCAN.
SQL_BUSCAR = "SELECT correcto FROM posibles_errores WHERE tipo = :tipo AND error = :error"

SQL_CONTAR = "SELECT COUNT(*) FROM posibles_errores"

# MERGE y no INSERT: registrar dos veces el mismo nombre (o reintentar una
# sincronización a medias) no debe fallar con ORA-00001 ni duplicar filas.
SQL_MERGE = """
MERGE INTO posibles_errores d
USING (SELECT :tipo AS tipo, :error AS error, :correcto AS correcto,
              :nivel AS nivel, :origen AS origen, :nota AS nota FROM dual) s
ON (d.tipo = s.tipo AND d.error = s.error)
WHEN MATCHED THEN UPDATE SET
    d.correcto = s.correcto, d.nivel = s.nivel, d.origen = s.origen,
    d.nota = s.nota, d.actualizado_en = SYSTIMESTAMP
    WHERE d.correcto <> s.correcto OR d.nivel <> s.nivel
WHEN NOT MATCHED THEN INSERT (tipo, error, correcto, nivel, origen, nota)
    VALUES (s.tipo, s.error, s.correcto, s.nivel, s.origen, s.nota)
"""

# Solo para errores que el agente invalidó (chocan con un nombre oficial
# nuevo): dejarlos haría que el NER confundiera el nombre nuevo con otro.
SQL_BORRAR = "DELETE FROM posibles_errores WHERE tipo = :tipo AND error = :error"


def configurado() -> bool:
    return bool(os.getenv("DB_HOST") and os.getenv("DB_USER"))


def _dsn() -> str:
    return "{}:{}/{}".format(
        os.getenv("DB_HOST"), os.getenv("DB_PORT", "1521"), os.getenv("DB_SERVICE_NAME", "FREEPDB1")
    )


def conectar():
    """Conexión nueva (import diferido: sin Oracle configurado no hace falta el driver)."""
    import oracledb

    return oracledb.connect(
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS", ""),
        dsn=_dsn(),
        tcp_connect_timeout=TIMEOUT_CONEXION_SEGUNDOS,
    )


def cargar() -> dict[str, dict[str, str]]:
    """Toda la tabla en memoria: {tipo: {error: correcto}}."""
    tabla: dict[str, dict[str, str]] = {}
    with conectar() as conexion, conexion.cursor() as cursor:
        cursor.arraysize = 5000  # ~60 mil filas en pocas idas y vueltas
        cursor.execute(SQL_CARGAR)
        for tipo, error, correcto in cursor:
            tabla.setdefault(tipo, {})[error] = correcto
    return tabla


def cargar_filas() -> list[dict]:
    """Todas las filas con sus columnas (el agente las necesita completas)."""
    with conectar() as conexion, conexion.cursor() as cursor:
        cursor.arraysize = 5000
        cursor.execute(SQL_CARGAR_FILAS)
        return [
            {"tipo": t, "error": e, "correcto": c, "nivel": str(n), "origen": o, "nota": nota or ""}
            for t, e, c, n, o, nota in cursor
        ]


def buscar(tipo: str, error: str) -> str | None:
    """El nombre correcto de un error puntual, o None."""
    with conectar() as conexion, conexion.cursor() as cursor:
        cursor.execute(SQL_BUSCAR, tipo=tipo, error=error)
        fila = cursor.fetchone()
        return fila[0] if fila else None


def contar() -> int:
    with conectar() as conexion, conexion.cursor() as cursor:
        cursor.execute(SQL_CONTAR)
        return int(cursor.fetchone()[0])


def guardar(filas: list[dict], borrar: list[tuple[str, str]] | None = None) -> None:
    """MERGE de filas nuevas y borrado de errores invalidados, en UNA transacción."""
    if not filas and not borrar:
        return
    with conectar() as conexion, conexion.cursor() as cursor:
        if borrar:
            cursor.executemany(SQL_BORRAR, [{"tipo": t, "error": e} for t, e in borrar])
        datos = [
            {"tipo": f["tipo"], "error": f["error"], "correcto": f["correcto"],
             "nivel": int(f["nivel"]), "origen": f["origen"], "nota": f.get("nota") or None}
            for f in filas
        ]
        for inicio in range(0, len(datos), TAMANO_LOTE):
            cursor.executemany(SQL_MERGE, datos[inicio:inicio + TAMANO_LOTE])
        conexion.commit()

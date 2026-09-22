#!/bin/sh
# ============================================================
# ElectriSys — Restauración del esquema desde un backup Data Pump.
#
# Escenario real de recuperación ante desastre: se perdió el esquema
# ELECTRISYS por completo y se restaura desde el último .dmp con el
# MISMO nombre de esquema (no remapeado).
#
# Uso:
#   DUMPFILE=electrisys_backup_20260921_020000_01.dmp \
#   ORACLE_PASS=... ./restaurar_logico.sh
#   (o pasando el dump como primer argumento)
#
# Variables de entorno — las credenciales NUNCA van en el script, que
# está versionado en el repositorio:
#   ORACLE_USER            usuario dueño del esquema      (def. electrisys)
#   ORACLE_PASS            contraseña                     (OBLIGATORIA)
#   ORACLE_CONNECT_STRING  //host:puerto/servicio         (def. //oracle-db:1521/freepdb1)
#   BACKUP_DIR_OBJECT      nombre del DIRECTORY de Oracle (def. electrisys_backup_dir)
#   DUMPFILE               archivo .dmp a restaurar       (o $1)
#
# ── Procedimiento completo de recuperación ─────────────────────────
# 1) Levantar la base (si el desastre fue del contenedor):
#      docker compose -f docker/docker-compose.yml up -d oracle-db
# 2) Recrear el usuario/esquema vacío, conectado AS SYSDBA:
#      docker compose exec oracle-db sqlplus / as sysdba \
#        @/scripts/01_usuario_y_esquema.sql
#    (o el script oracle/01_usuario_y_esquema.sql montado donde corresponda)
# 3) Recrear el DIRECTORY si se perdió, AS SYSDBA:
#      oracle/backup/10_directorio_backup_sysdba.sql
# 4) Listar los dumps disponibles en el volumen:
#      docker compose -f docker/docker-compose.yml \
#        -f docker/docker-compose.backup.yml run --rm oracle-backup \
#        ls -lh /opt/oracle/backups/electrisys
# 5) Restaurar el dump elegido:
#      docker compose -f docker/docker-compose.yml \
#        -f docker/docker-compose.backup.yml run --rm \
#        -e DUMPFILE=electrisys_backup_AAAAMMDD_HHMMSS_01.dmp \
#        oracle-backup /scripts/restaurar_logico.sh
# 6) Verificar que la aplicación levanta y los datos están:
#      docker compose -f docker/docker-compose.yml up -d
#      y entrar al POS; contrastar el conteo de ventas/repuestos con el
#      log de la restauración (electrisys_restore.log en el mismo volumen).
#
# IMPORTANTE sobre TYPE + REMAP_SCHEMA: si en vez de esto restaurás
# el dump remapeado a un esquema con OTRO nombre (útil para probar el
# backup sin tocar el esquema real, como se hizo en la validación de
# este proyecto), los tipos objeto (T_ITEM_VENTA/T_ITEMS_VENTA) fallan
# al recrearse por un OID embebido en el dump — limitación conocida de
# Data Pump con REMAP_SCHEMA sobre TYPEs, no una falla del backup. En
# una restauración real al mismo nombre de esquema esto no ocurre.
# ============================================================
set -e

ORACLE_USER="${ORACLE_USER:-electrisys}"
ORACLE_CONNECT_STRING="${ORACLE_CONNECT_STRING:-//oracle-db:1521/freepdb1}"
BACKUP_DIR_OBJECT="${BACKUP_DIR_OBJECT:-electrisys_backup_dir}"
DUMPFILE="${1:-${DUMPFILE}}"

if [ -z "${ORACLE_PASS}" ]; then
    echo "ERROR: falta la variable de entorno ORACLE_PASS." >&2
    exit 1
fi
if [ -z "${DUMPFILE}" ]; then
    echo "ERROR: indica el dump a restaurar (primer argumento o \$DUMPFILE)." >&2
    echo "       Ej: DUMPFILE=electrisys_backup_20260921_020000_01.dmp $0" >&2
    exit 1
fi

echo "[$(date '+%F %T')] Restaurando ${DUMPFILE} sobre el esquema ${ORACLE_USER}…"

# table_exists_action=replace: si la tabla ya existe, se reemplaza con el
# contenido del dump. Es lo correcto para una recuperación ante desastre
# (queremos EXACTAMENTE el estado del backup), pero destruye lo que haya
# en el esquema — por eso este script no corre solo ni en un cron.
# impdp NO devuelve 0 cuando "completa con errores": devuelve 5. Y sobre un
# esquema que ya existe casi siempre completa con errores, porque
# table_exists_action=replace aplica solo a TABLAS — los packages, tipos y
# secuencias ya están y Data Pump los reporta como ORA-31684 "already
# exists", que en este flujo son ruido esperado, no un fallo.
#
# Con `set -e`, ese 5 abortaba el script justo ANTES de recompilar, y el
# operador veía el import terminar creyendo que todo acabó. Por eso se
# captura el código y se decide explícitamente qué hacer con cada valor.
set +e
impdp "${ORACLE_USER}/${ORACLE_PASS}@${ORACLE_CONNECT_STRING}" \
    directory="${BACKUP_DIR_OBJECT}" \
    dumpfile="${DUMPFILE}" \
    logfile=electrisys_restore.log \
    schemas="${ORACLE_USER}" \
    table_exists_action=replace
CODIGO_IMPDP=$?
set -e

case "${CODIGO_IMPDP}" in
    0)
        echo "[$(date '+%F %T')] Import completado sin errores."
        ;;
    5)
        echo "[$(date '+%F %T')] Import completado CON errores (código 5)."
        echo "                    Sobre un esquema existente esto es normal:"
        echo "                    son los ORA-31684 de objetos que ya estaban."
        ;;
    *)
        echo "[$(date '+%F %T')] ERROR: impdp falló con código ${CODIGO_IMPDP}." >&2
        echo "                    NO se recompila nada: el esquema puede haber" >&2
        echo "                    quedado a medias. Revisá electrisys_restore.log." >&2
        exit "${CODIGO_IMPDP}"
        ;;
esac

# ── Recompilar lo que el import invalidó ─────────────────────
# impdp recrea las tablas, y eso deja inválidos los packages y las vistas
# que dependen de ellas. Oracle los recompila solo al primer uso, pero eso
# significa que el primer usuario tras la recuperación es quien descubre si
# algo quedó roto. Se hace acá para que cualquier problema salga ahora.
echo "[$(date '+%F %T')] Recompilando objetos invalidados por el import…"
sqlplus -S "${ORACLE_USER}/${ORACLE_PASS}@${ORACLE_CONNECT_STRING}" @"$(dirname "$0")/12_recompilar_invalidos.sql" </dev/null

echo "[$(date '+%F %T')] Restauración completada. Revisá electrisys_restore.log en el DIRECTORY."

#!/bin/sh
# ============================================================
# ElectriSys — Backup lógico del esquema Oracle con Data Pump.
#
# Requiere haber corrido oracle/backup/10_directorio_backup_sysdba.sql
# (crea el DIRECTORY object ELECTRISYS_BACKUP_DIR).
#
# Las credenciales llegan por variables de entorno, NUNCA hardcodeadas:
# este archivo está versionado en el repositorio y el repo se despliega.
#   ORACLE_USER            usuario dueño del esquema      (def. electrisys)
#   ORACLE_PASS            contraseña                     (OBLIGATORIA)
#   ORACLE_CONNECT_STRING  //host:puerto/servicio         (def. //oracle-db:1521/freepdb1)
#   BACKUP_DIR_OBJECT      nombre del DIRECTORY de Oracle (def. electrisys_backup_dir)
#   BACKUP_RETENCION_DIAS  borra dumps más viejos que esto (def. 14; 0 = no borrar)
#   BACKUP_PATH            ruta real del DIRECTORY, solo para la retención
#
# El host por defecto es "oracle-db" —el nombre del servicio en
# docker/docker-compose.yml—, no localhost: este script corre dentro de un
# contenedor de la red electrisys_net, no en la máquina de desarrollo.
#
# compression=all NO se usa: es una opción de Advanced Compression,
# no disponible en Oracle Database Free.
# ============================================================
set -e

ORACLE_USER="${ORACLE_USER:-electrisys}"
ORACLE_CONNECT_STRING="${ORACLE_CONNECT_STRING:-//oracle-db:1521/freepdb1}"
BACKUP_DIR_OBJECT="${BACKUP_DIR_OBJECT:-electrisys_backup_dir}"
BACKUP_RETENCION_DIAS="${BACKUP_RETENCION_DIAS:-14}"
BACKUP_PATH="${BACKUP_PATH:-/opt/oracle/backups/electrisys}"

if [ -z "${ORACLE_PASS}" ]; then
    echo "ERROR: falta la variable de entorno ORACLE_PASS." >&2
    echo "       Definila en docker/.env (DB_PASS) — nunca dentro de este script." >&2
    exit 1
fi

TS=$(date +%Y%m%d_%H%M%S)
echo "[$(date '+%F %T')] Iniciando backup lógico del esquema ${ORACLE_USER}…"

# La contraseña va en la línea de comandos de expdp, que es visible en el
# `ps` del contenedor. Es aceptable porque el contenedor de backup no
# ejecuta nada más ni acepta sesiones; la alternativa (un wallet de Oracle)
# no está disponible en Free sin configuración extra del servidor.
expdp "${ORACLE_USER}/${ORACLE_PASS}@${ORACLE_CONNECT_STRING}" \
    directory="${BACKUP_DIR_OBJECT}" \
    dumpfile="electrisys_backup_${TS}_%U.dmp" \
    logfile="electrisys_backup_${TS}.log" \
    schemas="${ORACLE_USER}"

echo "[$(date '+%F %T')] Backup completado: electrisys_backup_${TS}_*.dmp"

# ── Retención ────────────────────────────────────────────────
# Sin esto el volumen crece hasta llenar el disco del Droplet y el backup
# empieza a fallar justo cuando más falta hace. Solo se aplica si el
# proceso ve la carpeta (el contenedor de backup monta el mismo volumen
# que oracle-db); si no la ve, se avisa y no se borra nada.
if [ "${BACKUP_RETENCION_DIAS}" -gt 0 ] 2>/dev/null; then
    if [ -d "${BACKUP_PATH}" ]; then
        find "${BACKUP_PATH}" -maxdepth 1 -name 'electrisys_backup_*' \
            -type f -mtime "+${BACKUP_RETENCION_DIAS}" -print -delete
        echo "[$(date '+%F %T')] Retención aplicada: se conservan los últimos ${BACKUP_RETENCION_DIAS} días."
    else
        echo "[$(date '+%F %T')] AVISO: ${BACKUP_PATH} no es visible desde acá; retención omitida." >&2
    fi
fi

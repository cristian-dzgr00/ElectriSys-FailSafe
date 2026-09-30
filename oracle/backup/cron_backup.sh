#!/bin/sh
# ============================================================
# ElectriSys — Planificador del backup lógico nocturno.
#
# Es el entrypoint del servicio "oracle-backup" de
# docker/docker-compose.backup.yml. Duerme hasta la hora configurada,
# corre backup_logico.sh, y vuelve a dormir.
#
# ¿Por qué un bucle y no cron/ofelia?
#   - cron dentro del contenedor obliga a exportarle el entorno a mano
#     (las variables del `docker run` no llegan al proceso de cron) y a
#     redirigir su log a stdout para que `docker compose logs` sirva.
#   - ofelia dispara jobs vía el socket de Docker: montarlo en un
#     contenedor equivale a darle root sobre el host del Droplet, por un
#     backup diario que se puede agendar con 10 líneas de shell.
# Este bucle no necesita ninguna de las dos cosas, y su log es el log
# del contenedor.
#
# Variables (además de las que usa backup_logico.sh):
#   BACKUP_HORA           hora local de ejecución, 00-23   (def. 02)
#   BACKUP_MINUTO         minuto                           (def. 00)
#   BACKUP_AL_ARRANCAR    "1" corre un backup al levantar  (def. 0)
#                         — útil para verificar el despliegue sin
#                         esperar a la madrugada.
#   BACKUP_PATH           carpeta del DIRECTORY de Oracle dentro del volumen
# ============================================================
set -u

BACKUP_HORA="${BACKUP_HORA:-02}"
BACKUP_MINUTO="${BACKUP_MINUTO:-00}"
BACKUP_AL_ARRANCAR="${BACKUP_AL_ARRANCAR:-0}"
BACKUP_PATH="${BACKUP_PATH:-/opt/oracle/backups/electrisys}"
SCRIPT_BACKUP="$(dirname "$0")/backup_logico.sh"

# El volumen nombrado se crea vacío y propiedad de root; quien escribe el
# .dmp es el proceso de Oracle del contenedor oracle-db (usuario oracle).
# Sin este ajuste, el primer expdp falla con ORA-39087 (directorio no
# escribible) y el backup nunca arranca.
mkdir -p "${BACKUP_PATH}"
chown -R oracle:oinstall "$(dirname "${BACKUP_PATH}")" 2>/dev/null \
    || echo "AVISO: no se pudieron ajustar los permisos de ${BACKUP_PATH} (¿el servicio no corre como root?)" >&2

# expdp/impdp viven en $ORACLE_HOME/bin; en algunas variantes de la imagen
# no queda en el PATH del entrypoint.
if ! command -v expdp >/dev/null 2>&1; then
    if [ -n "${ORACLE_HOME:-}" ] && [ -x "${ORACLE_HOME}/bin/expdp" ]; then
        PATH="${ORACLE_HOME}/bin:${PATH}"
        export PATH
    else
        echo "ERROR: no se encontró expdp en el PATH ni en \$ORACLE_HOME/bin." >&2
        exit 1
    fi
fi

correr_backup() {
    echo "[$(date '+%F %T')] Disparando backup programado…"
    if sh "${SCRIPT_BACKUP}"; then
        echo "[$(date '+%F %T')] Backup OK."
    else
        # No se sale del bucle: un backup fallido (base caída, disco lleno)
        # no debe dejar al sistema sin backups los días siguientes.
        echo "[$(date '+%F %T')] ERROR: el backup falló. Se reintenta mañana." >&2
    fi
}

echo "[$(date '+%F %T')] Planificador de backups iniciado — diario a las ${BACKUP_HORA}:${BACKUP_MINUTO} (hora del contenedor: $(date '+%Z'))."

if [ "${BACKUP_AL_ARRANCAR}" = "1" ]; then
    correr_backup
fi

while true; do
    ahora=$(date +%s)
    objetivo=$(date -d "today ${BACKUP_HORA}:${BACKUP_MINUTO}" +%s 2>/dev/null) || {
        echo "ERROR: 'date -d' no está disponible en esta imagen." >&2
        exit 1
    }
    if [ "${objetivo}" -le "${ahora}" ]; then
        objetivo=$(date -d "tomorrow ${BACKUP_HORA}:${BACKUP_MINUTO}" +%s)
    fi

    espera=$((objetivo - ahora))
    echo "[$(date '+%F %T')] Próximo backup en ${espera}s."
    sleep "${espera}"

    correr_backup
done

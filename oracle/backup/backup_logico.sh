#!/bin/sh
# ============================================================
# ElectriSys — Backup lógico del esquema Oracle con Data Pump.
# Requiere: haber corrido oracle/backup/10_directorio_backup_sysdba.sql
# (crea el DIRECTORY object ELECTRISYS_BACKUP_DIR -> C:\oracle_backups\electrisys)
#
# compression=all NO se usa: es una opción de Advanced Compression,
# no disponible en Oracle Database Free.
# ============================================================
set -e

TS=$(date +%Y%m%d_%H%M%S)

expdp "electrisys/ElectriOra_2026!@//localhost:1521/freepdb1" \
    directory=electrisys_backup_dir \
    dumpfile="electrisys_backup_${TS}_%U.dmp" \
    logfile="electrisys_backup_${TS}.log" \
    schemas=electrisys

echo "Backup completado. Dump y log en C:\\oracle_backups\\electrisys"

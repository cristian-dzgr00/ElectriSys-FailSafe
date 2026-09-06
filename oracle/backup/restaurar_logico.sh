#!/bin/sh
# ============================================================
# ElectriSys — Restauración del esquema desde un backup Data Pump.
#
# Escenario real de recuperación ante desastre: se perdió el esquema
# ELECTRISYS por completo y se restaura desde el último .dmp con el
# MISMO nombre de esquema (no remapeado).
#
# IMPORTANTE sobre TYPE + REMAP_SCHEMA: si en vez de esto restauras
# el dump remapeado a un esquema con OTRO nombre (útil para probar el
# backup sin tocar el esquema real, como se hizo en la validación de
# este proyecto), los tipos objeto (T_ITEM_VENTA/T_ITEMS_VENTA) fallan
# al recrearse por un OID embebido en el dump — limitación conocida de
# Data Pump con REMAP_SCHEMA sobre TYPEs, no una falla del backup. En
# una restauración real al mismo nombre de esquema esto no ocurre.
# ============================================================
set -e

# 1) Recrear el usuario/esquema vacío (ver oracle/01_usuario_y_esquema.sql)
#    sqlplus sys/<password>@//localhost:1521/freepdb1 as sysdba @../01_usuario_y_esquema.sql

# 2) Importar el contenido del dump más reciente
impdp "electrisys/ElectriOra_2026!@//localhost:1521/freepdb1" \
    directory=electrisys_backup_dir \
    dumpfile="$1" \
    logfile=electrisys_restore.log \
    schemas=electrisys \
    table_exists_action=replace

echo "Restauracion completada. Ver electrisys_restore.log en C:\\oracle_backups\\electrisys"

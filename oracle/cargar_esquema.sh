#!/bin/sh
# ============================================================
# ElectriSys — Carga completa del esquema Oracle, en orden.
#
# Pensado para correrse DENTRO del contenedor oracle-db, que es donde
# está sqlplus y donde se monta esta carpeta como /scripts:
#
#   docker compose exec oracle-db sh /scripts/cargar_esquema.sh
#
# ¿Por qué un script y no /container-entrypoint-initdb.d?
# La imagen gvenzl/oracle-free ejecuta automáticamente todo .sql que
# encuentre en esa carpeta, sin orden garantizado entre subdirectorios y
# siempre con el mismo usuario. Acá los scripts NO son intercambiables:
# 01 y 09 necesitan SYSDBA (crear tablespace, crear usuarios) y el resto
# corre como ELECTRISYS, y 02 tiene que ir antes que 03/04 o los índices
# y triggers apuntan a tablas que todavía no existen. Montar la carpeta
# entera ahí también ejecutaría los scripts de backup/ y los planes de
# ejecución, que no son parte del esquema.
#
# Variables:
#   DB_PASS        contraseña del usuario electrisys (OBLIGATORIA)
#   PDB            servicio de la PDB (def. freepdb1)
#
# Es idempotente solo la primera vez: volver a correrlo sobre un esquema
# ya cargado falla con ORA-00955 (objeto ya existe). Es a propósito — no
# debe poder borrar datos en producción por un doble enter.
# ============================================================
set -e

PDB="${PDB:-freepdb1}"
DIR="$(dirname "$0")"

if [ -z "${DB_PASS:-}" ]; then
    echo "ERROR: falta DB_PASS (contraseña del usuario electrisys)." >&2
    exit 1
fi

sysdba() {
    echo ">> [SYSDBA] $1"
    sqlplus -S "/ as sysdba" @"${DIR}/$1" <<'EOF'
EXIT
EOF
}

app() {
    echo ">> [ELECTRISYS] $1"
    sqlplus -S "electrisys/${DB_PASS}@//localhost:1521/${PDB}" @"${DIR}/$1" <<'EOF'
EXIT
EOF
}

# El 01 crea el tablespace y el usuario dentro de la PDB. Recibe la
# contraseña como parámetro: no está escrita en el .sql versionado.
echo ">> [SYSDBA] 01_usuario_y_esquema.sql"
sqlplus -S "/ as sysdba" @"${DIR}/01_usuario_y_esquema.sql" "${DB_PASS}" <<'EOF'
EXIT
EOF

# Tablas, índices, triggers y datos base (esquema original, previo a la 3FN).
app 02_ddl_tablas.sql
app 03_indices.sql
app 04_triggers.sql
app 05_seed.sql

# Módulo de pedidos a proveedor (Sprint 2) y ciclo de cotizaciones.
# Los 4 GRANT a roles del final de 10 dan ORA-01917 en una base nueva (los roles
# se crean en 08); 08 los repite, no hace falta hacer nada.
app 10_pedidos.sql
app 11_cotizaciones_estados.sql

# Asistente de lenguaje natural (Sprint 3, tarjeta 3.14): corpus NLP y posibles errores.
app 12_nlp_dataset.sql
app 13_posibles_errores.sql
app 14_seed_posibles_errores.sql

# 3FN (Sprint 3): la carga desde cero es la cadena de migraciones.
#   15 = fase 1 (marcas, modelos, respuestas del asistente en tablas atómicas)
#   16 = fase 2 (esquema final del modelo ER: sin columnas derivadas, PK compuestas,
#        porcentajes en las cabeceras, intencion_id, marca_id/modelo_id/categoria_id)
app 15_normalizacion_3fn.sql
app 16_normalizacion_3fn_fase2.sql

# Packages, vistas y roles se escriben ya contra el esquema final, por eso van después.
# 06 define fn_fecha_local (la usa 07); 07 recompila los packages al terminar.
# 08 crea los roles (los GRANT de 10/15/16 a roles se repiten allí).
app 06_packages_plsql.sql
app 07_vistas.sql
app 08_roles_privilegios.sql

# Crear usuarios de base de datos es privilegio de sistema.
sysdba 09_usuarios_demo_sysdba.sql

# Backup: el DIRECTORY lo crea SYSDBA; el package corre como la aplicación.
sysdba backup/10_directorio_backup_sysdba.sql
app    backup/11_pkg_backup_plsql.sql

echo "Esquema ELECTRISYS cargado completo."

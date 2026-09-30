-- ============================================================
-- ElectriSys — Migración a Oracle 23ai
-- 11. Package PL/SQL para disparar el backup lógico bajo demanda
-- Ejecutar conectado como ELECTRISYS.
--
-- ¿Por qué un package y no invocar expdp desde PHP?
-- El backend PHP corre en su propio contenedor y no tiene instalado el
-- cliente de Oracle ni acceso al socket de Docker. Darle cualquiera de las
-- dos cosas para poder lanzar un backup sería abrirle al proceso web una
-- puerta mucho más grande que la función que necesita. DBMS_DATAPUMP hace
-- exactamente el mismo export que expdp pero desde dentro de la base, con
-- la conexión que el backend ya tiene y con los privilegios que ya posee
-- sobre su propio esquema.
--
-- El backup automático nocturno NO pasa por acá: lo hace
-- oracle/backup/backup_logico.sh desde el contenedor de backup. Este
-- package es solo para el botón "Respaldar ahora" de la vista de
-- administración (backend/src/routes/admin_backup.php), pensado para
-- antes de una operación riesgosa.
-- ============================================================

CREATE OR REPLACE PACKAGE pkg_backup AS

    -- Lanza un export Data Pump del esquema completo y devuelve el nombre
    -- base de los archivos generados (sin extensión). El job corre en
    -- segundo plano dentro de la base: la llamada retorna de inmediato, no
    -- espera a que el .dmp esté escrito.
    FUNCTION exportar_esquema RETURN VARCHAR2;

END pkg_backup;
/

CREATE OR REPLACE PACKAGE BODY pkg_backup AS

    FUNCTION exportar_esquema RETURN VARCHAR2 IS
        v_handle NUMBER;
        v_ts     VARCHAR2(20)  := TO_CHAR(SYSTIMESTAMP, 'YYYYMMDD_HH24MISS');
        v_base   VARCHAR2(100) := 'electrisys_backup_' || v_ts;
        v_job    VARCHAR2(30)  := 'ES_BKP_' || v_ts;
    BEGIN
        -- Mismo nombre de archivo que genera backup_logico.sh, para que los
        -- backups manuales y los automáticos se ordenen juntos por fecha en
        -- el listado y en la retención.
        v_handle := DBMS_DATAPUMP.OPEN(
            operation => 'EXPORT',
            job_mode  => 'SCHEMA',
            job_name  => v_job
        );

        DBMS_DATAPUMP.ADD_FILE(
            handle    => v_handle,
            filename  => v_base || '_%U.dmp',
            directory => 'ELECTRISYS_BACKUP_DIR',
            filetype  => DBMS_DATAPUMP.KU$_FILE_TYPE_DUMP_FILE
        );

        DBMS_DATAPUMP.ADD_FILE(
            handle    => v_handle,
            filename  => v_base || '.log',
            directory => 'ELECTRISYS_BACKUP_DIR',
            filetype  => DBMS_DATAPUMP.KU$_FILE_TYPE_LOG_FILE
        );

        -- Solo el esquema de la aplicación. Exportar la base completa
        -- exigiría DATAPUMP_EXP_FULL_DATABASE, un privilegio que el usuario
        -- de la aplicación no tiene ni debe tener.
        DBMS_DATAPUMP.METADATA_FILTER(
            handle => v_handle,
            name   => 'SCHEMA_EXPR',
            value  => '= ''ELECTRISYS'''
        );

        DBMS_DATAPUMP.START_JOB(v_handle);

        -- DETACH y no WAIT_FOR_JOB: el request HTTP que dispara esto no
        -- puede quedarse colgado los segundos/minutos que tarde el export.
        -- El job sigue corriendo en la base; la vista lo ve aparecer cuando
        -- el archivo queda escrito.
        DBMS_DATAPUMP.DETACH(v_handle);

        RETURN v_base;
    END exportar_esquema;

END pkg_backup;
/

-- El dueño puede disparar un respaldo manual antes de una operación
-- riesgosa; el vendedor no tiene nada que hacer acá.
GRANT EXECUTE ON pkg_backup TO rol_electrisys_admin;
GRANT EXECUTE ON pkg_backup TO rol_electrisys_dueno;

PROMPT Package PKG_BACKUP creado correctamente.

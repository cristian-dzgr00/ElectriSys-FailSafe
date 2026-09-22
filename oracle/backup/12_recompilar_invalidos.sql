-- ============================================================
-- ElectriSys — Recompilar objetos inválidos tras una restauración
-- Ejecutar conectado como ELECTRISYS.
--
-- Data Pump recrea las TABLAS (table_exists_action=replace), y eso invalida
-- todo lo que depende de ellas: los packages (PKG_VENTAS, PKG_REPORTES) y
-- las vistas de reportes. Oracle los recompila solo la primera vez que
-- alguien los usa, así que técnicamente "funciona" sin hacer nada — pero
-- entonces el primer usuario después de una recuperación es quien descubre
-- si alguno quedó roto, y lo descubre como un error en pantalla.
--
-- Recompilar acá convierte ese riesgo en una verificación: si algo del
-- esquema no compila contra los datos restaurados, se ve en el momento de
-- restaurar, que es cuando todavía hay margen para actuar.
--
-- Lo llama restaurar_logico.sh al terminar el impdp.
-- ============================================================

SET SERVEROUTPUT ON

DECLARE
    v_total    NUMBER := 0;
    v_fallidos NUMBER := 0;
BEGIN
    -- Orden importante: primero las vistas, después las especificaciones de
    -- package y por último los cuerpos. Compilar un body antes que su spec
    -- lo dejaría inválido otra vez.
    FOR obj IN (
        SELECT object_name, object_type
          FROM user_objects
         WHERE status != 'VALID'
           AND object_type IN ('VIEW', 'PACKAGE', 'PACKAGE BODY', 'PROCEDURE', 'FUNCTION', 'TRIGGER')
         ORDER BY DECODE(object_type, 'VIEW', 1, 'PACKAGE', 2, 'PACKAGE BODY', 3, 4)
    ) LOOP
        v_total := v_total + 1;
        BEGIN
            IF obj.object_type = 'PACKAGE BODY' THEN
                EXECUTE IMMEDIATE 'ALTER PACKAGE "' || obj.object_name || '" COMPILE BODY';
            ELSE
                EXECUTE IMMEDIATE 'ALTER ' || obj.object_type ||
                                  ' "' || obj.object_name || '" COMPILE';
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                -- No se corta el bucle: interesa recompilar todo lo que se
                -- pueda y reportar el resto junto, no frenar en el primero.
                v_fallidos := v_fallidos + 1;
                DBMS_OUTPUT.PUT_LINE('  No compila: ' || obj.object_type || ' ' ||
                                     obj.object_name || ' -> ' || SUBSTR(SQLERRM, 1, 120));
        END;
    END LOOP;

    DBMS_OUTPUT.PUT_LINE('Objetos invalidos procesados: ' || v_total);

    -- Se vuelve a contar en vez de confiar en v_fallidos: compilar un objeto
    -- puede invalidar otro que dependa de el.
    SELECT COUNT(*) INTO v_total FROM user_objects WHERE status != 'VALID';
    IF v_total = 0 THEN
        DBMS_OUTPUT.PUT_LINE('OK: no quedan objetos invalidos en el esquema.');
    ELSE
        DBMS_OUTPUT.PUT_LINE('ATENCION: quedan ' || v_total ||
                             ' objetos invalidos. Revisalos antes de dar por buena la restauracion.');
    END IF;
END;
/

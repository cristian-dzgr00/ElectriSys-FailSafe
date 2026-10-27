-- ============================================================
-- ElectriSys — Oracle 23ai
-- 16. Normalización a 3FN (fase 2): deja el esquema como en
--     docs/sprint3/modelo_er_3fn.png
-- Ejecutar conectado como ELECTRISYS, después de 15 (fase 1).
--
-- QUÉ HACE
--  1. VEHICULOS: quita marca y modelo (ahora salen de MODELOS/MARCAS vía
--     modelo_id, que pasa a NOT NULL) y el trigger de compatibilidad de la
--     fase 1. Nueva unicidad: (modelo_id, anio_desde, anio_hasta, motor,
--     combustible).
--  2. VENTAS y COTIZACIONES: descuento_pct e iva_pct reemplazan a los montos
--     guardados subtotal/descuento/impuesto/total (dato derivado de las
--     líneas). Los montos se calculan en vw_totales_documento (07).
--  3. PEDIDOS: se quitan subtotal y total.
--  4. DETALLE_VENTAS, DETALLE_COTIZACIONES y PEDIDO_DETALLE: PK compuesta
--     (documento, repuesto); se quitan id y subtotal.
--  5. REPUESTO_COMPATIBILIDAD: PK compuesta (repuesto, vehiculo); sin id.
--  6. CONSULTAS_ASISTENTE: intencion_id (FK a nlp_intenciones) y confianza
--     reemplazan a intencion_detectada, entidades_json y respuesta_json. Lo
--     que viajaba en los JSON se copia antes a CONSULTA_ENTIDADES y
--     CONSULTA_RECOMENDACIONES.
--  7. POSIBLES_ERRORES y POSIBLES_ERRORES_AVISOS: marca_id / modelo_id /
--     categoria_id (exactamente uno, según tipo) reemplazan a correcto.
--
-- SEGURIDAD
--  * Antes de cambiar nada se validan los prerrequisitos (fase 1 aplicada,
--     sin líneas repetidas por documento y repuesto, sin vehículos repetidos).
--     Si algo falla se aborta con un mensaje claro y la base queda intacta:
--     nunca se fusionan filas en silencio.
--  * Lo que se pierde de forma inevitable (consultas con intención que no
--     existe en nlp_intenciones, errores sin coincidencia en el catálogo)
--     se cuenta y se imprime antes de borrarlo.
--
-- RE-EJECUTABLE: cada paso comprueba si ya se aplicó. Sobre una base ya
-- migrada no cambia nada.
--
-- DESPUÉS: volver a ejecutar 06 (packages), 07 (vistas) y 08 (roles). Las
-- vistas y packages de la versión anterior quedan INVALID al quitar las
-- columnas que usaban.
-- ============================================================
SET SERVEROUTPUT ON SIZE UNLIMITED
SET DEFINE OFF

DECLARE
    -- ── Utilidades ───────────────────────────────────────────────
    FUNCTION existe_tabla(p_t VARCHAR2) RETURN BOOLEAN IS
        n NUMBER;
    BEGIN
        SELECT COUNT(*) INTO n FROM user_tables WHERE table_name = UPPER(p_t);
        RETURN n > 0;
    END;

    FUNCTION existe_col(p_t VARCHAR2, p_c VARCHAR2) RETURN BOOLEAN IS
        n NUMBER;
    BEGIN
        SELECT COUNT(*) INTO n FROM user_tab_columns
         WHERE table_name = UPPER(p_t) AND column_name = UPPER(p_c);
        RETURN n > 0;
    END;

    FUNCTION col_acepta_nulos(p_t VARCHAR2, p_c VARCHAR2) RETURN BOOLEAN IS
        v VARCHAR2(1);
    BEGIN
        SELECT nullable INTO v FROM user_tab_columns
         WHERE table_name = UPPER(p_t) AND column_name = UPPER(p_c);
        RETURN v = 'Y';
    END;

    FUNCTION existe_cons(p_n VARCHAR2) RETURN BOOLEAN IS
        n NUMBER;
    BEGIN
        SELECT COUNT(*) INTO n FROM user_constraints WHERE constraint_name = UPPER(p_n);
        RETURN n > 0;
    END;

    FUNCTION tiene_pk(p_t VARCHAR2) RETURN BOOLEAN IS
        n NUMBER;
    BEGIN
        SELECT COUNT(*) INTO n FROM user_constraints
         WHERE table_name = UPPER(p_t) AND constraint_type = 'P';
        RETURN n > 0;
    END;

    FUNCTION existe_idx(p_n VARCHAR2) RETURN BOOLEAN IS
        n NUMBER;
    BEGIN
        SELECT COUNT(*) INTO n FROM user_indexes WHERE index_name = UPPER(p_n);
        RETURN n > 0;
    END;

    FUNCTION existe_trigger(p_n VARCHAR2) RETURN BOOLEAN IS
        n NUMBER;
    BEGIN
        SELECT COUNT(*) INTO n FROM user_triggers WHERE trigger_name = UPPER(p_n);
        RETURN n > 0;
    END;

    FUNCTION cuenta(p_sql VARCHAR2) RETURN NUMBER IS
        n NUMBER;
    BEGIN
        EXECUTE IMMEDIATE p_sql INTO n;
        RETURN n;
    END;

    PROCEDURE ddl(p_sql VARCHAR2, p_msg VARCHAR2 DEFAULT NULL) IS
    BEGIN
        EXECUTE IMMEDIATE p_sql;
        IF p_msg IS NOT NULL THEN
            DBMS_OUTPUT.PUT_LINE(p_msg);
        END IF;
    END;

    -- Ejecuta un INSERT/UPDATE/DELETE e imprime cuántas filas tocó.
    PROCEDURE dml(p_sql VARCHAR2, p_msg VARCHAR2) IS
    BEGIN
        EXECUTE IMMEDIATE p_sql;
        DBMS_OUTPUT.PUT_LINE(p_msg || ': ' || SQL%ROWCOUNT);
        COMMIT;
    END;

    -- ── 0. Prerrequisitos (no cambia nada) ───────────────────────
    PROCEDURE validar IS
        v NUMBER;
    BEGIN
        IF NOT (existe_tabla('MARCAS') AND existe_tabla('MODELOS')
                AND existe_col('VEHICULOS', 'MODELO_ID')
                AND existe_tabla('CONSULTA_ENTIDADES') AND existe_tabla('CONSULTA_RECOMENDACIONES')) THEN
            RAISE_APPLICATION_ERROR(-20100,
                'Falta la fase 1 (marcas, modelos, vehiculos.modelo_id, consulta_*): ejecute 15_normalizacion_3fn.sql antes.');
        END IF;
        IF NOT existe_tabla('NLP_INTENCIONES') OR NOT existe_tabla('POSIBLES_ERRORES') THEN
            RAISE_APPLICATION_ERROR(-20100,
                'Faltan nlp_intenciones o posibles_errores: ejecute 12 y 13 antes.');
        END IF;

        IF existe_col('VEHICULOS', 'MARCA') THEN
            v := cuenta('SELECT COUNT(*) FROM vehiculos WHERE modelo_id IS NULL');
            IF v > 0 THEN
                RAISE_APPLICATION_ERROR(-20101, v || ' vehiculos sin modelo_id: complete la fase 1 antes de migrar.');
            END IF;
            v := cuenta('SELECT COUNT(*) FROM (SELECT 1 FROM vehiculos '
                     || 'GROUP BY modelo_id, anio_desde, anio_hasta, motor, combustible HAVING COUNT(*) > 1)');
            IF v > 0 THEN
                RAISE_APPLICATION_ERROR(-20102,
                    v || ' variantes de vehiculo repetidas (mismo modelo, anios, motor y combustible): depurelas antes de migrar.');
            END IF;
        END IF;

        IF existe_col('DETALLE_VENTAS', 'ID') THEN
            v := cuenta('SELECT COUNT(*) FROM (SELECT 1 FROM detalle_ventas '
                     || 'GROUP BY venta_id, repuesto_id HAVING COUNT(*) > 1)');
            IF v > 0 THEN
                RAISE_APPLICATION_ERROR(-20103,
                    v || ' ventas con el mismo repuesto en mas de una linea (detalle_ventas): unifiquelas a mano antes de migrar.');
            END IF;
        END IF;
        IF existe_col('DETALLE_COTIZACIONES', 'ID') THEN
            v := cuenta('SELECT COUNT(*) FROM (SELECT 1 FROM detalle_cotizaciones '
                     || 'GROUP BY cotizacion_id, repuesto_id HAVING COUNT(*) > 1)');
            IF v > 0 THEN
                RAISE_APPLICATION_ERROR(-20104,
                    v || ' cotizaciones con el mismo repuesto en mas de una linea (detalle_cotizaciones): unifiquelas a mano antes de migrar.');
            END IF;
        END IF;
        IF existe_col('PEDIDO_DETALLE', 'ID') THEN
            v := cuenta('SELECT COUNT(*) FROM (SELECT 1 FROM pedido_detalle '
                     || 'GROUP BY pedido_id, repuesto_id HAVING COUNT(*) > 1)');
            IF v > 0 THEN
                RAISE_APPLICATION_ERROR(-20105,
                    v || ' pedidos con el mismo repuesto en mas de una linea (pedido_detalle): unifiquelas a mano antes de migrar.');
            END IF;
        END IF;
        DBMS_OUTPUT.PUT_LINE('0. Prerrequisitos verificados.');
    END validar;

    -- ── 1. VEHICULOS ─────────────────────────────────────────────
    PROCEDURE paso_vehiculos IS
    BEGIN
        IF existe_trigger('TRG_VEHICULOS_MODELO_ID') THEN
            ddl('DROP TRIGGER trg_vehiculos_modelo_id', '1. Trigger trg_vehiculos_modelo_id eliminado.');
        END IF;
        IF existe_cons('UQ_VEHICULO') THEN
            ddl('ALTER TABLE vehiculos DROP CONSTRAINT uq_vehiculo');
        END IF;
        IF existe_idx('IDX_VEHICULOS_MARCA_MODELO') THEN
            ddl('DROP INDEX idx_vehiculos_marca_modelo');
        END IF;
        IF existe_col('VEHICULOS', 'MARCA') THEN
            ddl('ALTER TABLE vehiculos DROP (marca, modelo)', '1. VEHICULOS.marca y VEHICULOS.modelo eliminadas.');
        END IF;
        IF col_acepta_nulos('VEHICULOS', 'MODELO_ID') THEN
            ddl('ALTER TABLE vehiculos MODIFY (modelo_id NOT NULL)', '1. VEHICULOS.modelo_id ahora es NOT NULL.');
        END IF;
        IF NOT existe_cons('UQ_VEHICULOS_VARIANTE') THEN
            ddl('ALTER TABLE vehiculos ADD CONSTRAINT uq_vehiculos_variante '
                || 'UNIQUE (modelo_id, anio_desde, anio_hasta, motor, combustible)',
                '1. Unicidad uq_vehiculos_variante creada.');
        END IF;
        -- Con la unicidad anterior (modelo_id es su primera columna) este índice sobra.
        IF existe_idx('IDX_VEHICULOS_MODELO') THEN
            ddl('DROP INDEX idx_vehiculos_modelo');
        END IF;
    END paso_vehiculos;

    -- ── 2. VENTAS y COTIZACIONES: porcentajes en vez de montos ───
    -- p_det/p_fk: tabla de líneas y su columna hacia la cabecera.
    PROCEDURE paso_cabecera(p_t VARCHAR2, p_det VARCHAR2, p_fk VARCHAR2,
                            p_ck_desc VARCHAR2, p_ck_iva VARCHAR2, p_ck_total VARCHAR2) IS
        v_n      NUMBER;
        v_difs   NUMBER;
        v_difs_n NUMBER;
        v_fuera  NUMBER;
        c_suma   CONSTANT VARCHAR2(300) :=
            '(SELECT ' || p_fk || ' AS doc, SUM(cantidad * precio_unit - NVL(descuento, 0)) AS s FROM '
            || p_det || ' GROUP BY ' || p_fk || ') d ON d.doc = h.id';
    BEGIN
        IF NOT existe_col(p_t, 'DESCUENTO_PCT') THEN
            ddl('ALTER TABLE ' || p_t || ' ADD ('
                || 'descuento_pct NUMBER(5,2) DEFAULT 0 NOT NULL CONSTRAINT ' || p_ck_desc
                || ' CHECK (descuento_pct BETWEEN 0 AND 100), '
                || 'iva_pct NUMBER(5,2) DEFAULT 19 NOT NULL CONSTRAINT ' || p_ck_iva
                || ' CHECK (iva_pct BETWEEN 0 AND 100))',
                '2. ' || UPPER(p_t) || ': columnas descuento_pct e iva_pct agregadas.');
        END IF;

        IF existe_col(p_t, 'SUBTOTAL') THEN
            v_n := cuenta('SELECT COUNT(*) FROM ' || p_t);

            -- Evidencia 1: cabeceras cuyo total guardado no cuadra con sus líneas.
            v_difs := cuenta('SELECT COUNT(*) FROM ' || p_t || ' h LEFT JOIN ' || c_suma
                          || ' WHERE h.total <> NVL(d.s, 0) - h.descuento + h.impuesto');
            DBMS_OUTPUT.PUT_LINE('2. ' || UPPER(p_t) || ': ' || v_difs || ' de ' || v_n
                || ' documentos tienen un total guardado distinto del recalculado desde sus lineas.');

            -- Porcentajes a partir de los montos guardados en la cabecera.
            v_fuera := cuenta('SELECT COUNT(*) FROM ' || p_t || ' WHERE '
                || '(subtotal > 0 AND (descuento * 100 / subtotal > 100 OR descuento < 0)) OR '
                || '(subtotal - descuento > 0 AND (impuesto * 100 / (subtotal - descuento) > 100 OR impuesto < 0))');
            ddl('UPDATE ' || p_t || ' SET '
                || 'descuento_pct = CASE WHEN subtotal > 0 '
                ||     'THEN LEAST(100, GREATEST(0, ROUND(descuento * 100 / subtotal, 2))) ELSE 0 END, '
                || 'iva_pct = CASE WHEN (subtotal - descuento) > 0 '
                ||     'THEN LEAST(100, GREATEST(0, ROUND(impuesto * 100 / (subtotal - descuento), 2))) ELSE 0 END');
            COMMIT;
            DBMS_OUTPUT.PUT_LINE('2. ' || UPPER(p_t) || ': porcentajes calculados para ' || v_n
                || ' documentos (' || v_fuera || ' fuera de 0..100, ajustados al limite).');

            -- Evidencia 2: cuántos cambiarían de total con el modelo nuevo (por redondeo de porcentajes).
            v_difs_n := cuenta('SELECT COUNT(*) FROM ' || p_t || ' h LEFT JOIN ' || c_suma
                || ' WHERE h.total <> (NVL(d.s, 0) - ROUND(NVL(d.s, 0) * h.descuento_pct / 100, 2))'
                || ' + ROUND((NVL(d.s, 0) - ROUND(NVL(d.s, 0) * h.descuento_pct / 100, 2)) * h.iva_pct / 100, 2)');
            DBMS_OUTPUT.PUT_LINE('2. ' || UPPER(p_t) || ': ' || v_difs_n
                || ' documentos tendran un total distinto con el modelo nuevo (lineas + porcentajes).');

            IF p_ck_total IS NOT NULL AND existe_cons(p_ck_total) THEN
                ddl('ALTER TABLE ' || p_t || ' DROP CONSTRAINT ' || p_ck_total);
            END IF;
            ddl('ALTER TABLE ' || p_t || ' DROP (subtotal, descuento, impuesto, total)',
                '2. ' || UPPER(p_t) || ': subtotal, descuento, impuesto y total eliminadas.');
        END IF;
    END paso_cabecera;

    -- ── 3. PEDIDOS ───────────────────────────────────────────────
    PROCEDURE paso_pedidos IS
    BEGIN
        IF existe_col('PEDIDOS', 'SUBTOTAL') THEN
            IF existe_cons('CK_PEDIDOS_TOTAL') THEN
                ddl('ALTER TABLE pedidos DROP CONSTRAINT ck_pedidos_total');
            END IF;
            ddl('ALTER TABLE pedidos DROP (subtotal, total)', '3. PEDIDOS: subtotal y total eliminadas.');
        END IF;
    END paso_pedidos;

    -- ── 4. Detalles: PK compuesta, sin id ni subtotal ────────────
    PROCEDURE paso_detalle(p_t VARCHAR2, p_fk VARCHAR2, p_pk VARCHAR2, p_idx_viejo VARCHAR2) IS
    BEGIN
        IF existe_col(p_t, 'ID') THEN
            IF tiene_pk(p_t) THEN
                ddl('ALTER TABLE ' || p_t || ' DROP PRIMARY KEY');
            END IF;
            ddl('ALTER TABLE ' || p_t || ' DROP COLUMN id');
        END IF;
        IF existe_col(p_t, 'SUBTOTAL') THEN
            ddl('ALTER TABLE ' || p_t || ' DROP COLUMN subtotal');
        END IF;
        -- El índice viejo se borra ANTES de la PK: si no, Oracle lo reutilizaría
        -- para respaldar la PK y luego no se podría eliminar.
        IF p_idx_viejo IS NOT NULL AND existe_idx(p_idx_viejo) THEN
            ddl('DROP INDEX ' || p_idx_viejo);
        END IF;
        IF NOT existe_cons(p_pk) THEN
            ddl('ALTER TABLE ' || p_t || ' ADD CONSTRAINT ' || p_pk
                || ' PRIMARY KEY (' || p_fk || ', repuesto_id)',
                '4. ' || UPPER(p_t) || ': PK (' || p_fk || ', repuesto_id) creada; id y subtotal eliminadas.');
        END IF;
    END paso_detalle;

    -- ── 5. REPUESTO_COMPATIBILIDAD ───────────────────────────────
    PROCEDURE paso_compat IS
    BEGIN
        IF existe_col('REPUESTO_COMPATIBILIDAD', 'ID') THEN
            IF tiene_pk('REPUESTO_COMPATIBILIDAD') THEN
                ddl('ALTER TABLE repuesto_compatibilidad DROP PRIMARY KEY');
            END IF;
            ddl('ALTER TABLE repuesto_compatibilidad DROP COLUMN id');
        END IF;
        IF existe_cons('UQ_REPUESTO_VEHICULO') THEN
            ddl('ALTER TABLE repuesto_compatibilidad DROP CONSTRAINT uq_repuesto_vehiculo');
        END IF;
        IF existe_idx('IDX_COMPAT_REPUESTO') THEN
            ddl('DROP INDEX idx_compat_repuesto');
        END IF;
        IF NOT existe_cons('PK_REPUESTO_COMPAT') THEN
            ddl('ALTER TABLE repuesto_compatibilidad ADD CONSTRAINT pk_repuesto_compat '
                || 'PRIMARY KEY (repuesto_id, vehiculo_id)',
                '5. REPUESTO_COMPATIBILIDAD: PK (repuesto_id, vehiculo_id) creada; id eliminada.');
        END IF;
    END paso_compat;

    -- ── 6. CONSULTAS_ASISTENTE ───────────────────────────────────
    PROCEDURE paso_consultas IS
        v_esp   NUMBER;
        v_sin   NUMBER;
    BEGIN
        IF NOT existe_col('CONSULTAS_ASISTENTE', 'INTENCION_ID') THEN
            ddl('ALTER TABLE consultas_asistente ADD (intencion_id NUMBER, confianza NUMBER(5,4))',
                '6. CONSULTAS_ASISTENTE: columnas intencion_id y confianza agregadas.');
        END IF;
        IF NOT existe_cons('FK_CONSULTAS_INTENCION') THEN
            ddl('ALTER TABLE consultas_asistente ADD CONSTRAINT fk_consultas_intencion '
                || 'FOREIGN KEY (intencion_id) REFERENCES nlp_intenciones(id)');
        END IF;
        IF NOT existe_cons('CK_CONSULTAS_CONFIANZA') THEN
            ddl('ALTER TABLE consultas_asistente ADD CONSTRAINT ck_consultas_confianza '
                || 'CHECK (confianza BETWEEN 0 AND 1)');
        END IF;

        IF existe_col('CONSULTAS_ASISTENTE', 'INTENCION_DETECTADA') THEN
            -- Intención: nombre -> id.
            dml('UPDATE consultas_asistente c SET intencion_id = '
                || '(SELECT i.id FROM nlp_intenciones i WHERE i.nombre = c.intencion_detectada) '
                || 'WHERE c.intencion_id IS NULL AND c.intencion_detectada IS NOT NULL',
                '6. Consultas con intencion_id asignada');

            -- Confianza: sale del JSON de la respuesta. Un valor ilegible o fuera de 0..1 queda NULL.
            dml('MERGE INTO consultas_asistente c USING ('
                || 'SELECT id, CASE WHEN x BETWEEN 0 AND 1 THEN ROUND(x, 4) END AS conf FROM ('
                ||   'SELECT id, JSON_VALUE(respuesta_json, ''$.confianza'' RETURNING NUMBER DEFAULT NULL ON ERROR) AS x '
                ||   'FROM consultas_asistente)) s ON (c.id = s.id) '
                || 'WHEN MATCHED THEN UPDATE SET c.confianza = s.conf '
                || 'WHERE c.confianza IS NULL AND s.conf IS NOT NULL',
                '6. Consultas con confianza copiada del JSON');

            -- Entidades -> CONSULTA_ENTIDADES (solo consultas que aún no tienen filas).
            -- codigo se guarda como tipo 'repuesto'; motor y combustible no tienen tipo en la fase 1.
            dml('INSERT INTO consulta_entidades (consulta_id, tipo, valor) '
                || 'SELECT consulta_id, tipo, valor FROM ('
                ||   'SELECT c.id AS consulta_id, jt.marca, jt.modelo, jt.anio, jt.categoria, jt.codigo '
                ||     'FROM consultas_asistente c, JSON_TABLE(c.entidades_json, ''$'' COLUMNS ('
                ||       'marca VARCHAR2(200) PATH ''$.marca'', modelo VARCHAR2(200) PATH ''$.modelo'', '
                ||       'anio VARCHAR2(200) PATH ''$.anio'', categoria VARCHAR2(200) PATH ''$.categoria'', '
                ||       'codigo VARCHAR2(200) PATH ''$.codigo'')) jt '
                ||    'WHERE NOT EXISTS (SELECT 1 FROM consulta_entidades e WHERE e.consulta_id = c.id)) '
                || 'UNPIVOT (valor FOR tipo IN (marca AS ''marca'', modelo AS ''modelo'', anio AS ''anio'', '
                ||                              'categoria AS ''categoria'', codigo AS ''repuesto''))',
                '6. Filas insertadas en CONSULTA_ENTIDADES');

            -- Sugerencias -> CONSULTA_RECOMENDACIONES. puntaje = similitud * 100.
            -- Un repuesto repetido en una misma respuesta se toma una sola vez (PK consulta+repuesto);
            -- las sugerencias cuyo repuesto ya no existe no se pueden respaldar (FK).
            dml('INSERT INTO consulta_recomendaciones (consulta_id, repuesto_id, posicion, es_sustituto, puntaje) '
                || 'SELECT q.consulta_id, q.repuesto_id, q.posicion, q.es_sustituto, q.puntaje FROM ('
                ||   'SELECT c.id AS consulta_id, jt.rid AS repuesto_id, jt.pos AS posicion, '
                ||          'CASE WHEN c.intencion_detectada = ''recomendar_sustituto'' THEN 1 ELSE 0 END AS es_sustituto, '
                ||          'CASE WHEN jt.sim BETWEEN 0 AND 9.9999 THEN ROUND(jt.sim * 100, 2) END AS puntaje, '
                ||          'ROW_NUMBER() OVER (PARTITION BY c.id, jt.rid ORDER BY jt.pos) AS rn '
                ||     'FROM consultas_asistente c, JSON_TABLE(c.respuesta_json, ''$.sugerencias[*]'' COLUMNS ('
                ||       'pos FOR ORDINALITY, rid NUMBER PATH ''$.id'', sim NUMBER PATH ''$.similitud'')) jt '
                ||    'WHERE NOT EXISTS (SELECT 1 FROM consulta_recomendaciones x WHERE x.consulta_id = c.id)) q '
                || 'JOIN repuestos r ON r.id = q.repuesto_id '
                || 'WHERE q.rn = 1 AND q.posicion BETWEEN 1 AND 999',
                '6. Filas insertadas en CONSULTA_RECOMENDACIONES');

            -- Lo que no se pudo respaldar (se imprime ANTES de borrar las columnas JSON).
            v_esp := cuenta('SELECT COUNT(*) FROM consultas_asistente c WHERE '
                || 'JSON_VALUE(entidades_json, ''$.marca'') IS NOT NULL OR JSON_VALUE(entidades_json, ''$.modelo'') IS NOT NULL OR '
                || 'JSON_VALUE(entidades_json, ''$.anio'') IS NOT NULL OR JSON_VALUE(entidades_json, ''$.categoria'') IS NOT NULL OR '
                || 'JSON_VALUE(entidades_json, ''$.codigo'') IS NOT NULL');
            v_sin := cuenta('SELECT COUNT(*) FROM consultas_asistente c WHERE '
                || '(JSON_VALUE(entidades_json, ''$.marca'') IS NOT NULL OR JSON_VALUE(entidades_json, ''$.modelo'') IS NOT NULL OR '
                || 'JSON_VALUE(entidades_json, ''$.anio'') IS NOT NULL OR JSON_VALUE(entidades_json, ''$.categoria'') IS NOT NULL OR '
                || 'JSON_VALUE(entidades_json, ''$.codigo'') IS NOT NULL) '
                || 'AND NOT EXISTS (SELECT 1 FROM consulta_entidades e WHERE e.consulta_id = c.id)');
            DBMS_OUTPUT.PUT_LINE('6. Consultas con entidades en el JSON: ' || v_esp || '; sin poder respaldar: ' || v_sin);
            v_esp := cuenta('SELECT COUNT(*) FROM consultas_asistente c '
                || 'WHERE JSON_EXISTS(respuesta_json, ''$.sugerencias[0]'')');
            v_sin := cuenta('SELECT COUNT(*) FROM consultas_asistente c '
                || 'WHERE JSON_EXISTS(respuesta_json, ''$.sugerencias[0]'') '
                || 'AND NOT EXISTS (SELECT 1 FROM consulta_recomendaciones x WHERE x.consulta_id = c.id)');
            DBMS_OUTPUT.PUT_LINE('6. Consultas con sugerencias en el JSON: ' || v_esp || '; sin poder respaldar: ' || v_sin);
            v_sin := cuenta('SELECT COUNT(*) FROM consultas_asistente '
                || 'WHERE respuesta_json IS NOT NULL AND confianza IS NULL');
            DBMS_OUTPUT.PUT_LINE('6. Consultas con respuesta_json pero sin confianza legible: ' || v_sin);
            v_sin := cuenta('SELECT COUNT(*) FROM consultas_asistente '
                || 'WHERE intencion_detectada IS NOT NULL AND intencion_id IS NULL');
            DBMS_OUTPUT.PUT_LINE('6. Consultas con intencion que no existe en nlp_intenciones (quedan sin intencion): ' || v_sin);

            IF existe_idx('IDX_CONSULTAS_INTENCION') THEN
                ddl('DROP INDEX idx_consultas_intencion');
            END IF;
            ddl('ALTER TABLE consultas_asistente DROP (intencion_detectada, entidades_json, respuesta_json)',
                '6. CONSULTAS_ASISTENTE: intencion_detectada, entidades_json y respuesta_json eliminadas.');
        END IF;

        IF NOT existe_idx('IDX_CONSULTAS_INTENCION') THEN
            ddl('CREATE INDEX idx_consultas_intencion ON consultas_asistente(intencion_id)');
        END IF;
    END paso_consultas;

    -- ── 7. POSIBLES_ERRORES y AVISOS ─────────────────────────────
    -- p_p: prefijo de los nombres de constraint/índice (pe | pea).
    PROCEDURE paso_errores(p_t VARCHAR2, p_p VARCHAR2) IS
        v_sin_marca  NUMBER;
        v_sin_modelo NUMBER;
        v_sin_cat    NUMBER;
        v_ambiguos   NUMBER;
        v_total      NUMBER;
    BEGIN
        IF NOT existe_col(p_t, 'MARCA_ID') THEN
            ddl('ALTER TABLE ' || p_t || ' ADD (marca_id NUMBER, modelo_id NUMBER, categoria_id NUMBER)',
                '7. ' || UPPER(p_t) || ': columnas marca_id, modelo_id y categoria_id agregadas.');
        END IF;

        IF existe_col(p_t, 'CORRECTO') THEN
            v_total := cuenta('SELECT COUNT(*) FROM ' || p_t);
            dml('UPDATE ' || p_t || ' e SET marca_id = (SELECT m.id FROM marcas m WHERE m.nombre = e.correcto) '
                || 'WHERE e.tipo = ''marca'' AND e.marca_id IS NULL',
                '7. ' || UPPER(p_t) || ' (marca) enlazadas al catalogo');
            -- El modelo debe ser inequívoco entre marcas: con 2 o más coincidencias queda NULL.
            dml('UPDATE ' || p_t || ' e SET modelo_id = '
                || '(SELECT MIN(mo.id) FROM modelos mo WHERE mo.nombre = e.correcto HAVING COUNT(*) = 1) '
                || 'WHERE e.tipo = ''modelo'' AND e.modelo_id IS NULL',
                '7. ' || UPPER(p_t) || ' (modelo) enlazadas al catalogo');
            dml('UPDATE ' || p_t || ' e SET categoria_id = (SELECT c.id FROM categorias c WHERE c.nombre = e.correcto) '
                || 'WHERE e.tipo = ''categoria'' AND e.categoria_id IS NULL',
                '7. ' || UPPER(p_t) || ' (categoria) enlazadas al catalogo');

            v_ambiguos := cuenta('SELECT COUNT(*) FROM ' || p_t || ' e WHERE e.tipo = ''modelo'' '
                || 'AND (SELECT COUNT(*) FROM modelos mo WHERE mo.nombre = e.correcto) > 1');
            v_sin_marca  := cuenta('SELECT COUNT(*) FROM ' || p_t || ' WHERE tipo = ''marca'' AND marca_id IS NULL');
            v_sin_modelo := cuenta('SELECT COUNT(*) FROM ' || p_t || ' WHERE tipo = ''modelo'' AND modelo_id IS NULL');
            v_sin_cat    := cuenta('SELECT COUNT(*) FROM ' || p_t || ' WHERE tipo = ''categoria'' AND categoria_id IS NULL');
            DBMS_OUTPUT.PUT_LINE('7. ' || UPPER(p_t) || ': ' || v_total || ' filas; sin coincidencia en el catalogo -> marca '
                || v_sin_marca || ', modelo ' || v_sin_modelo || ' (de ellas ' || v_ambiguos
                || ' ambiguas entre marcas), categoria ' || v_sin_cat
                || '. Se eliminan (el agente NLP las regenera).');
            dml('DELETE FROM ' || p_t || ' WHERE (tipo = ''marca'' AND marca_id IS NULL) '
                || 'OR (tipo = ''modelo'' AND modelo_id IS NULL) OR (tipo = ''categoria'' AND categoria_id IS NULL)',
                '7. ' || UPPER(p_t) || ': filas eliminadas');
        END IF;

        IF NOT existe_cons('FK_' || p_p || '_MARCA') THEN
            ddl('ALTER TABLE ' || p_t || ' ADD CONSTRAINT fk_' || p_p || '_marca FOREIGN KEY (marca_id) REFERENCES marcas(id)');
        END IF;
        IF NOT existe_cons('FK_' || p_p || '_MODELO') THEN
            ddl('ALTER TABLE ' || p_t || ' ADD CONSTRAINT fk_' || p_p || '_modelo FOREIGN KEY (modelo_id) REFERENCES modelos(id)');
        END IF;
        IF NOT existe_cons('FK_' || p_p || '_CATEGORIA') THEN
            ddl('ALTER TABLE ' || p_t || ' ADD CONSTRAINT fk_' || p_p || '_categoria FOREIGN KEY (categoria_id) REFERENCES categorias(id)');
        END IF;
        IF NOT existe_idx('IDX_' || p_p || '_MARCA') THEN
            ddl('CREATE INDEX idx_' || p_p || '_marca ON ' || p_t || '(marca_id)');
        END IF;
        IF NOT existe_idx('IDX_' || p_p || '_MODELO') THEN
            ddl('CREATE INDEX idx_' || p_p || '_modelo ON ' || p_t || '(modelo_id)');
        END IF;
        IF NOT existe_idx('IDX_' || p_p || '_CATEGORIA') THEN
            ddl('CREATE INDEX idx_' || p_p || '_categoria ON ' || p_t || '(categoria_id)');
        END IF;

        -- Exactamente una de las tres referencias, la que corresponde a tipo.
        IF NOT existe_cons('CK_' || p_p || '_DESTINO') THEN
            ddl('ALTER TABLE ' || p_t || ' ADD CONSTRAINT ck_' || p_p || '_destino CHECK ('
                || '(tipo = ''marca''     AND marca_id IS NOT NULL AND modelo_id IS NULL AND categoria_id IS NULL) OR '
                || '(tipo = ''modelo''    AND modelo_id IS NOT NULL AND marca_id IS NULL AND categoria_id IS NULL) OR '
                || '(tipo = ''categoria'' AND categoria_id IS NOT NULL AND marca_id IS NULL AND modelo_id IS NULL))',
                '7. ' || UPPER(p_t) || ': CHECK ck_' || p_p || '_destino creado.');
        END IF;

        IF p_t = 'posibles_errores' THEN
            IF existe_cons('UQ_PE_ERROR_CORRECTO') THEN
                ddl('ALTER TABLE posibles_errores DROP CONSTRAINT uq_pe_error_correcto');
            END IF;
            IF NOT existe_cons('UQ_PE_ERROR_DESTINO') THEN
                ddl('ALTER TABLE posibles_errores ADD CONSTRAINT uq_pe_error_destino '
                    || 'UNIQUE (tipo, error, marca_id, modelo_id, categoria_id)',
                    '7. POSIBLES_ERRORES: unicidad uq_pe_error_destino creada.');
            END IF;
            IF existe_idx('IDX_PE_CORRECTO') THEN
                ddl('DROP INDEX idx_pe_correcto');
            END IF;
        END IF;

        IF existe_col(p_t, 'CORRECTO') THEN
            ddl('ALTER TABLE ' || p_t || ' DROP COLUMN correcto', '7. ' || UPPER(p_t) || ': columna correcto eliminada.');
        END IF;
    END paso_errores;

BEGIN
    validar;
    paso_vehiculos;
    paso_cabecera('ventas',       'detalle_ventas',       'venta_id',       'ck_ventas_descuento_pct', 'ck_ventas_iva_pct', 'ck_ventas_total');
    paso_cabecera('cotizaciones', 'detalle_cotizaciones', 'cotizacion_id',  'ck_cotiz_descuento_pct',  'ck_cotiz_iva_pct',  NULL);
    paso_pedidos;
    paso_detalle('detalle_ventas',       'venta_id',      'pk_detalle_ventas',       'idx_detven_venta_repuesto');
    paso_detalle('detalle_cotizaciones', 'cotizacion_id', 'pk_detalle_cotizaciones', NULL);
    paso_detalle('pedido_detalle',       'pedido_id',     'pk_pedido_detalle',       'idx_peddet_pedido');
    paso_compat;
    paso_consultas;
    paso_errores('posibles_errores',        'pe');
    paso_errores('posibles_errores_avisos', 'pea');
END;
/

-- Revalida lo que quedó INVALID al quitar columnas (vistas y packages de la
-- versión anterior se reemplazan al volver a ejecutar 06 y 07).
BEGIN DBMS_UTILITY.COMPILE_SCHEMA(USER, FALSE); END;
/
PROMPT Objetos INVALID tras la migracion (esperado: los de la version anterior de 06/07, hasta volver a ejecutarlos):
SELECT object_type, object_name FROM user_objects WHERE status = 'INVALID' ORDER BY 1, 2;
PROMPT Normalizacion 3FN (fase 2) lista. Ahora ejecute 06_packages_plsql.sql, 07_vistas.sql y 08_roles_privilegios.sql.

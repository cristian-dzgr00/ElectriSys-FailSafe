-- ============================================================
-- ElectriSys — Oracle 23ai
-- 17. Datos de demostración: unos 3,5 meses de operación (2026-07-14 a 2026-11-01)
--
-- Uso (conectado como ELECTRISYS, desde la carpeta oracle/):
--     @17_datos_demo.sql ROLLBACK     -- ensayo: carga todo, imprime el resumen y DESHACE
--     @17_datos_demo.sql COMMIT       -- carga definitiva
-- Sin argumento, o con cualquier otro valor, se comporta como ROLLBACK.
--
-- CARACTERÍSTICAS
--  * Una sola transacción, sin DDL. Con ROLLBACK la base queda como estaba
--    (las secuencias de numeración SEQ_NUMERO_* solo se avanzan con COMMIT).
--  * Idempotente: si ya existe dueno@electrisys.com aborta sin tocar nada.
--  * Determinista: generador congruencial propio con semilla fija; dos
--    ejecuciones sobre la misma base de partida producen los mismos datos.
--  * No desactiva triggers. Los triggers de stock, updated_at y auditoría de
--    repuestos se dejan actuar; sus filas de auditoría 'cambio_repuesto' se
--    eliminan al final (solo las de esta ejecución) y se reemplazan por los
--    eventos que la aplicación realmente produciría.
--  * Las filas se insertan ya en su estado final (anulada, recibido, vencida...)
--    para que los triggers BEFORE UPDATE no estampen SYSTIMESTAMP en las
--    columnas updated_at / recibido_en.
--  * Los TIMESTAMP de la base están en UTC; el negocio razona en hora de
--    Colombia (UTC-5, ver fn_fecha_local). Todo se genera en hora local y se
--    guarda sumando 5 horas.
--
-- Ver oracle/docs/datos-demo.md para el modelo de stock y el detalle.
-- ============================================================

SET DEFINE ON
SET VERIFY OFF
SET FEEDBACK OFF
SET ECHO OFF
SET SQLBLANKLINES ON
SET SERVEROUTPUT ON SIZE UNLIMITED
SET LINESIZE 220
SET TRIMSPOOL ON
WHENEVER SQLERROR EXIT FAILURE ROLLBACK
WHENEVER OSERROR EXIT FAILURE ROLLBACK

-- ── Argumento COMMIT | ROLLBACK (opcional; por defecto ROLLBACK) ──
SET TERMOUT OFF
COLUMN a1 NEW_VALUE 1 NOPRINT
SELECT '' AS a1 FROM dual WHERE 1 = 0;
SET TERMOUT ON
DEFINE modo = "&1"
-- A partir de aquí el carácter de sustitución es la tilde para que "&" (K&N Filtros)
-- viaje literal dentro de los textos.
SET DEFINE '~'

PROMPT ============================================================
PROMPT  ElectriSys · datos de demostración (modo solicitado: ~modo)
PROMPT ============================================================

-- ── 0. Guarda de idempotencia ──────────────────────────────────
DECLARE
    v_n NUMBER;
BEGIN
    SELECT COUNT(*) INTO v_n FROM usuarios WHERE email = 'dueno@electrisys.com';
    IF v_n > 0 THEN
        RAISE_APPLICATION_ERROR(-20900,
            'Los datos de demostracion ya fueron cargados (existe dueno@electrisys.com). No se cambio nada.');
    END IF;
END;
/

-- ── 1. Línea base (ids máximos y conteos previos) ──────────────
VARIABLE b_rep NUMBER
VARIABLE b_cli NUMBER
VARIABLE b_ven NUMBER
VARIABLE b_ped NUMBER
VARIABLE b_cot NUMBER
VARIABLE b_aud NUMBER
VARIABLE b_cnt VARCHAR2(4000)
VARIABLE n_ven NUMBER
VARIABLE n_ped NUMBER
VARIABLE modo_ok VARCHAR2(10)

DECLARE
    v_n NUMBER;
BEGIN
    SELECT NVL(MAX(id), 0) INTO :b_rep FROM repuestos;
    SELECT NVL(MAX(id), 0) INTO :b_cli FROM clientes;
    SELECT NVL(MAX(id), 0) INTO :b_ven FROM ventas;
    SELECT NVL(MAX(id), 0) INTO :b_ped FROM pedidos;
    SELECT NVL(MAX(id), 0) INTO :b_cot FROM cotizaciones;
    SELECT NVL(MAX(id), 0) INTO :b_aud FROM audit_log;
    :b_cnt := ';';
    FOR t IN (SELECT column_value AS tn FROM TABLE(sys.odcivarchar2list(
                'USUARIOS','PROVEEDORES','MARCAS','MODELOS','VEHICULOS','REPUESTOS','REPUESTO_COMPATIBILIDAD',
                'CLIENTES','VENTAS','DETALLE_VENTAS','COTIZACIONES','DETALLE_COTIZACIONES','PEDIDOS',
                'PEDIDO_DETALLE','AUDIT_LOG','LOGIN_ATTEMPTS','CONSULTAS_ASISTENTE','CONSULTA_ENTIDADES',
                'CONSULTA_RECOMENDACIONES'))) LOOP
        EXECUTE IMMEDIATE 'SELECT COUNT(*) FROM ' || t.tn INTO v_n;
        :b_cnt := :b_cnt || t.tn || '=' || v_n || ';';
    END LOOP;
    :modo_ok := CASE WHEN UPPER(TRIM('~modo')) = 'COMMIT' THEN 'COMMIT' ELSE 'ROLLBACK' END;
END;
/

-- ============================================================
-- 2. DATOS MAESTROS: usuarios, proveedores, vehículos, repuestos,
--    compatibilidad y clientes
-- Formato de las listas: campos separados por "|"; fechas en hora local.
-- ============================================================
DECLARE
    v_n   PLS_INTEGER;
    v_rid NUMBER;
    v_cat NUMBER;
    v_prv NUMBER;
    v_pos PLS_INTEGER;
    v_key VARCHAR2(200);
    v_lst VARCHAR2(1000);
    v_cod VARCHAR2(60);
    v_a   VARCHAR2(400);
    v_b   VARCHAR2(400);
    v_c   VARCHAR2(400);
    v_d   VARCHAR2(400);
    v_e   VARCHAR2(400);
    v_g   VARCHAR2(400);
    v_t   TIMESTAMP;
    v_pc  NUMBER;
    v_pv  NUMBER;
    v_st  NUMBER;
    v_mi  NUMBER;

    FUNCTION f(p VARCHAR2, n PLS_INTEGER) RETURN VARCHAR2 IS
        v_s PLS_INTEGER;
        v_e PLS_INTEGER;
    BEGIN
        IF n = 1 THEN v_s := 1; ELSE v_s := INSTR(p, '|', 1, n - 1) + 1; END IF;
        v_e := INSTR(p, '|', 1, n);
        IF v_e = 0 THEN RETURN SUBSTR(p, v_s); END IF;
        RETURN SUBSTR(p, v_s, v_e - v_s);
    END f;

    -- 'YYYY-MM-DD' (hora local, 09:00) -> TIMESTAMP en UTC
    FUNCTION ts9(p VARCHAR2, p_h PLS_INTEGER DEFAULT 9) RETURN TIMESTAMP IS
    BEGIN
        RETURN CAST(TO_DATE(p, 'YYYY-MM-DD') + (p_h + 5) / 24 AS TIMESTAMP);
    END ts9;

BEGIN
    -- ── Usuarios (misma contraseña/hash que admin; nunca se escribe una clave) ──
    FOR r IN (SELECT column_value AS l FROM TABLE(sys.odcivarchar2list(
        'Andrés Felipe Torres|dueno@electrisys.com|dueno|2026-07-14|7',
        'Laura Gómez|laura.gomez@electrisys.com|vendedor|2026-07-20|8',
        'Camilo Rojas|camilo.rojas@electrisys.com|vendedor|2026-08-18|8'))) LOOP
        v_a := f(r.l, 1); v_b := f(r.l, 2); v_c := f(r.l, 3);
        v_t := ts9(f(r.l, 4), TO_NUMBER(f(r.l, 5)));
        INSERT INTO usuarios (nombre, email, password, rol_id, activo, creado_en)
        SELECT v_a, v_b, a.password, (SELECT id FROM roles WHERE nombre = v_c), 1, v_t
          FROM usuarios a WHERE a.email = 'admin@electrisys.com';
        IF SQL%ROWCOUNT <> 1 THEN
            RAISE_APPLICATION_ERROR(-20901, 'No se encontro admin@electrisys.com para copiar el hash de contrasena.');
        END IF;
    END LOOP;

    -- ── Proveedores nuevos ──
    FOR r IN (SELECT column_value AS l FROM TABLE(sys.odcivarchar2list(
        'Distribuidora Autopartes Colmotores|Mauricio Ríos|3207781245|mrios@colmotores.com.co|Cra 30 # 12-45, Bogotá D.C.|2026-07-14',
        'Frenos y Embragues del Pacífico|Yesenia Carvajal|3156620981|ycarvajal@frenospacifico.com.co|Calle 15 # 8-32, Cali|2026-07-14',
        'Lubricantes y Filtros Andina|Jhon Fredy Mejía|3118894402|jmejia@lubrifiltros.com.co|Av. Bolivariana # 45-10, Medellín|2026-07-21',
        'Llantas y Rines Centro Sur|Paola Andrea Zapata|3002459983|pzapata@llantascentrosur.com.co|Cra 5 # 22-18, Ibagué|2026-08-03',
        'Importadora Eléctrica Cafetera|Wilmer Sánchez|3176650234|wsanchez@iecafetera.com.co|Calle 21 # 14-60, Pereira|2026-08-11'))) LOOP
        v_t := ts9(f(r.l, 6));
        v_a := f(r.l, 1); v_b := f(r.l, 2); v_c := f(r.l, 3); v_d := f(r.l, 4); v_e := f(r.l, 5);
        INSERT INTO proveedores (nombre, contacto, telefono, email, direccion, activo, creado_en)
        VALUES (v_a, v_b, v_c, v_d, v_e, 1, v_t);
    END LOOP;

    -- ── Marcas, modelos y vehículos nuevos (mercado colombiano) ──
    FOR r IN (SELECT column_value AS l FROM TABLE(sys.odcivarchar2list(
        'Chevrolet|Onix|2019|2024|1.0|gasolina',
        'Chevrolet|Sail|2013|2019|1.4|gasolina',
        'Renault|Sandero|2015|2023|1.6|gasolina',
        'Kia|Picanto|2017|2024|1.2|gasolina',
        'Mitsubishi|L200|2016|2023|2.4|diesel',
        'Ford|Ranger|2016|2022|3.2|diesel',
        'Toyota|Yaris|2015|2022|1.5|gasolina',
        'New Holland|TL90|2014|2022|3.4|diesel',
        'Massey Ferguson|290|2000|2012|3.9|diesel'))) LOOP
        v_t := ts9('2026-07-14');
        v_a := f(r.l, 1); v_b := f(r.l, 2); v_c := f(r.l, 5); v_d := f(r.l, 6);
        v_pc := TO_NUMBER(f(r.l, 3)); v_pv := TO_NUMBER(f(r.l, 4));
        INSERT INTO marcas (nombre, creado_en)
        SELECT v_a, v_t FROM dual WHERE NOT EXISTS (SELECT 1 FROM marcas WHERE nombre = v_a);
        INSERT INTO modelos (marca_id, nombre, creado_en)
        SELECT m.id, v_b, v_t FROM marcas m
         WHERE m.nombre = v_a
           AND NOT EXISTS (SELECT 1 FROM modelos mo WHERE mo.marca_id = m.id AND mo.nombre = v_b);
        INSERT INTO vehiculos (modelo_id, anio_desde, anio_hasta, motor, combustible, creado_en)
        SELECT mo.id, v_pc, v_pv, v_c, v_d, v_t
          FROM modelos mo JOIN marcas m ON m.id = mo.marca_id
         WHERE m.nombre = v_a AND mo.nombre = v_b;
    END LOOP;

    -- ── Repuestos nuevos ──
    -- codigo|nombre|descripcion|categoria|proveedor|compra|venta|stock inicial|minimo|alta|compatibilidad (Marca Modelo;...)
    FOR r IN (SELECT column_value AS l FROM TABLE(sys.odcivarchar2list(
        -- Filtros
        'FRAM-PH5796|Filtro de aceite Fram PH5796|Filtro de aceite roscado para motores 1.0 a 1.6 gasolina|Filtros|Lubricantes y Filtros Andina|14500|22500|36|10|2026-07-14|Chevrolet Spark;Chevrolet Spark GT;Chevrolet Aveo;Chevrolet Onix;Chevrolet Sail;Renault Logan',
        'MANN-C25114|Filtro de aire Mann C25114|Filtro de aire de panel para motores Renault 1.6|Filtros|Distribuidora Autopartes Colmotores|32000|46500|14|5|2026-07-14|Renault Logan;Renault Sandero;Renault Duster',
        'BSH-F026400|Filtro de aire Bosch F026400|Filtro de aire de papel de alta eficiencia para Toyota 1.5 y 1.8|Filtros|Bosch Autopartes|29500|43000|16|5|2026-07-14|Toyota Corolla;Toyota Yaris',
        'KN-33-2304|Filtro de aire K&N 33-2304 lavable|Filtro de aire de alto flujo, lavable y reutilizable|Filtros|K&N Filtros|185000|265000|5|2|2026-07-21|Toyota Hilux;Toyota Fortuner;Mazda 3',
        'FG-FS19532|Separador de agua Fleetguard FS19532|Filtro separador de agua y combustible para motores diésel|Filtros|Fleetguard Filtros Industriales|76000|112000|10|4|2026-07-14|Nissan Frontier;Mitsubishi L200;Ford Ranger;John Deere 5075E;Case IH Farmall 75C',
        'FG-AF25550|Filtro de aire primario Fleetguard AF25550|Filtro de aire primario para tractores de 100 a 180 HP|Filtros|Fleetguard Filtros Industriales|88000|129000|8|3|2026-07-14|John Deere 6110M;Case IH Puma 165;Massey Ferguson 6713;New Holland T6.120',
        'MOB-M1-110A|Filtro de aceite Mobil 1 M1-110A|Filtro de aceite sintético de larga duración para motores 2.0 y 2.5|Filtros|Mobil 1 Distribuidora|25000|39000|20|6|2026-07-14|Mazda 3;Mazda CX-5;Hyundai Tucson;Kia Sportage',
        'FRAM-CA10242|Filtro de cabina Fram CA10242|Filtro de cabina antipolen con carbón activado|Filtros|Lubricantes y Filtros Andina|21000|33500|18|5|2026-08-04|Mazda 3;Kia Sportage;Hyundai Tucson;Toyota Corolla',
        -- Frenos
        'BSH-0986AB|Disco de freno delantero Bosch 0986AB|Disco de freno ventilado delantero (par)|Frenos|Bosch Autopartes|138000|198000|8|3|2026-07-14|Toyota Corolla;Toyota Yaris;Mazda 3',
        'BRM-09A729|Disco de freno ventilado Brembo 09.A729|Disco de freno delantero de alto rendimiento (par)|Frenos|Brembo Colombia|245000|355000|6|2|2026-07-14|Toyota Hilux;Toyota Fortuner;Mazda CX-5',
        'FRP-PD512|Pastillas de freno traseras PD512|Juego de pastillas de freno traseras semi-metálicas|Frenos|Frenos y Embragues del Pacífico|42000|66000|18|6|2026-07-14|Chevrolet Spark;Chevrolet Aveo;Chevrolet Sail;Chevrolet Onix',
        'FRP-BZ220|Bandas de freno traseras (zapatas) BZ220|Juego de zapatas de freno de tambor trasero|Frenos|Frenos y Embragues del Pacífico|38000|59000|14|5|2026-07-14|Renault Logan;Renault Sandero;Nissan Sentra;Kia Rio',
        'BRM-P85020|Pastillas de freno delanteras Brembo P85020|Juego de pastillas de freno delanteras cerámicas|Frenos|Brembo Colombia|88000|128000|12|4|2026-07-14|Kia Rio;Kia Picanto;Hyundai Accent;Suzuki Swift',
        'FRP-DOT4|Líquido de frenos DOT 4 (500 ml)|Líquido de frenos sintético DOT 4|Frenos|Frenos y Embragues del Pacífico|11000|17500|40|12|2026-07-14|Toyota Hilux;Chevrolet Spark;Renault Logan;Mazda 3;Kia Rio;Hyundai Accent',
        'FRP-CIL-MAE|Cilindro maestro de freno FRP-CIL-MAE|Cilindro maestro de freno con depósito|Frenos|Frenos y Embragues del Pacífico|135000|195000|4|2|2026-08-04|Nissan Frontier;Mitsubishi L200;Ford Ranger',
        -- Baterías
        'MAC-34HI|Batería Mac 34HI|Batería de 12V 45Ah libre de mantenimiento para autos pequeños|Baterías|Mac Baterías|150000|215000|9|3|2026-07-14|Chevrolet Spark;Chevrolet Onix;Kia Picanto;Renault Sandero',
        'MAC-27HI|Batería Mac 27HI|Batería de 12V 85Ah para camperos y pickups|Baterías|Mac Baterías|240000|345000|7|3|2026-07-14|Toyota Hilux;Toyota Fortuner;Nissan Frontier;Mitsubishi L200;Ford Ranger',
        'BSH-S4005|Batería Bosch S4 005|Batería de 12V 60Ah sellada de larga duración|Baterías|Bosch Autopartes|205000|290000|6|3|2026-07-28|Mazda 3;Toyota Corolla;Hyundai Accent;Kia Rio',
        'MAC-N120|Batería Mac N120|Batería de 12V 120Ah para tractores y maquinaria|Baterías|Mac Baterías|380000|540000|4|2|2026-08-04|John Deere 5075E;Massey Ferguson 4707;Case IH Puma 165;New Holland TL90',
        -- Suspensión
        'MNR-AM3500|Amortiguador trasero Monroe AM3500|Amortiguador a gas para suspensión trasera|Suspensión|Bosch Autopartes|88000|132000|10|4|2026-07-14|Toyota Corolla;Mazda 3;Nissan Sentra',
        'CMT-ROT-INF|Rótula de suspensión inferior|Rótula de suspensión inferior reforzada|Suspensión|Distribuidora Autopartes Colmotores|52000|79000|14|5|2026-07-14|Chevrolet Spark;Chevrolet Aveo;Chevrolet Sail;Hyundai Accent',
        'CMT-TER-DIR|Terminal de dirección exterior|Terminal de dirección con rótula exterior|Suspensión|Distribuidora Autopartes Colmotores|28000|41000|20|6|2026-07-14|Renault Logan;Renault Duster;Hyundai Accent;Kia Rio',
        'CMT-BUJ-BRZ|Bujes de brazo de suspensión (juego)|Juego de bujes de caucho para brazo de suspensión|Suspensión|Distribuidora Autopartes Colmotores|45000|68000|12|4|2026-08-04|Toyota Hilux;Toyota Fortuner;Nissan Frontier',
        'CMT-RES-DEL|Resorte helicoidal delantero|Resorte helicoidal de suspensión delantera|Suspensión|Distribuidora Autopartes Colmotores|98000|148000|6|2|2026-08-18|Chevrolet Aveo;Chevrolet Sail;Renault Logan',
        -- Motor
        'CMT-JUN-CUL|Junta de culata (empaque) multicapa|Junta de culata multicapa de acero|Motor|Distribuidora Autopartes Colmotores|120000|178000|6|2|2026-07-14|Chevrolet Aveo;Chevrolet Sail;Hyundai Accent;Kia Rio',
        'GAT-TH192|Termostato con carcasa Gates TH192|Termostato de 82 °C con carcasa|Motor|Gates Correas|36000|56000|12|4|2026-07-14|Renault Logan;Renault Sandero;Nissan Sentra;Chevrolet Aveo',
        'BSH-BOM-AGU|Bomba de agua Bosch|Bomba de agua con empaque incluido|Motor|Bosch Autopartes|78000|118000|9|3|2026-07-14|Toyota Corolla;Toyota Yaris;Mazda 3',
        'CMT-TAP-RAD|Tapa de radiador 1.1 bar|Tapa de radiador de presión 1.1 bar|Motor|Distribuidora Autopartes Colmotores|12000|19000|25|8|2026-07-14|Chevrolet Spark;Renault Logan;Kia Rio;Hyundai Accent;Toyota Corolla',
        'MOB-5W30|Aceite Mobil 1 5W-30 sintético (galón)|Aceite sintético 5W-30 para motores a gasolina, presentación de un galón|Motor|Mobil 1 Distribuidora|168000|235000|16|6|2026-07-14|Toyota Corolla;Toyota Yaris;Mazda 3;Mazda CX-5;Hyundai Tucson;Kia Sportage;Chevrolet Onix',
        'MOB-15W40|Aceite Mobil Delvac 15W-40 (galón)|Aceite mineral 15W-40 para motores diésel, presentación de un galón|Motor|Mobil 1 Distribuidora|92000|138000|20|8|2026-07-14|Nissan Frontier;Mitsubishi L200;Ford Ranger;John Deere 5075E;Case IH Puma 165;Massey Ferguson 4707',
        -- Transmisión
        'FRP-KIT-EMB|Kit de embrague completo|Disco, plato y balinera de embrague|Transmisión|Frenos y Embragues del Pacífico|385000|545000|5|2|2026-07-14|Chevrolet Spark;Chevrolet Aveo;Renault Logan;Kia Rio;Hyundai Accent',
        'FRP-HOM-DEL|Junta homocinética delantera|Junta homocinética lado rueda con fuelle|Transmisión|Frenos y Embragues del Pacífico|110000|165000|6|2|2026-08-04|Mazda 3;Toyota Corolla;Nissan Sentra',
        'MFR-DISC-EM|Disco de embrague Massey Ferguson|Disco de embrague para tractores serie 4700|Transmisión|Massey Ferguson Repuestos|520000|740000|3|1|2026-07-14|Massey Ferguson 4707;Massey Ferguson 6713',
        'MOB-ATF-VI|Aceite de transmisión ATF Dexron VI (galón)|Fluido ATF para cajas automáticas, presentación de un galón|Transmisión|Mobil 1 Distribuidora|98000|145000|10|4|2026-08-04|Toyota Corolla;Mazda 3;Hyundai Tucson;Kia Sportage',
        -- Encendido
        'NGK-ILFR6B|Bujía NGK Laser Iridium ILFR6B|Bujía de iridio de larga duración|Encendido|NGK Bujías|28000|44000|40|12|2026-07-14|Mazda 3;Mazda CX-5;Hyundai Tucson;Kia Sportage',
        'NGK-BKR5E|Bujía NGK BKR5E|Bujía de níquel estándar|Encendido|NGK Bujías|8500|13500|80|20|2026-07-14|Chevrolet Spark;Chevrolet Aveo;Suzuki Swift;Renault Logan;Chevrolet Sail',
        'BSH-BOB-ENC|Bobina de encendido Bosch 0221|Bobina de encendido tipo lápiz|Encendido|Bosch Autopartes|98000|145000|10|3|2026-07-14|Toyota Corolla;Toyota Yaris;Chevrolet Onix',
        'NGK-CAB-6|Cables de bujía NGK (juego)|Juego de cables de bujía de alta tensión|Encendido|NGK Bujías|62000|94000|8|3|2026-08-04|Chevrolet Aveo;Ford Fiesta;Ford Escape',
        -- Correas y Bandas
        'GAT-K060|Correa poly-V Gates K060|Correa de accesorios poly-V|Correas y Bandas|Gates Correas|32000|49000|18|6|2026-07-14|Chevrolet Aveo;Chevrolet Spark;Kia Rio;Hyundai Accent',
        'GAT-KIT-DIS|Kit de distribución Gates con bomba|Kit de correa de distribución, tensor y bomba de agua|Correas y Bandas|Gates Correas|295000|420000|6|2|2026-07-14|Renault Logan;Renault Sandero;Renault Duster;Chevrolet Aveo',
        'JD-CORREA-VEN|Correa del ventilador John Deere|Correa de ventilador para tractores serie 5000 y 6000|Correas y Bandas|John Deere Partes|62000|93000|8|3|2026-07-14|John Deere 5075E;John Deere 6110M',
        -- Sistema Eléctrico
        'BSH-MOT-ARR|Motor de arranque Bosch reconstruido|Motor de arranque 12V reconstruido|Sistema Eléctrico|Bosch Autopartes|245000|355000|5|2|2026-07-14|Toyota Hilux;Toyota Fortuner;Nissan Frontier',
        'IEC-H4-60|Bombillo halógeno H4 12V 60/55W (par)|Par de bombillos halógenos H4|Sistema Eléctrico|Importadora Eléctrica Cafetera|14000|20500|30|10|2026-08-11|Chevrolet Spark;Chevrolet Aveo;Renault Logan;Kia Rio;Hyundai Accent;Suzuki Swift;Ford Fiesta',
        'IEC-LED-H7|Bombillos LED H7 6000K (par)|Par de bombillos LED H7 de luz blanca|Sistema Eléctrico|Importadora Eléctrica Cafetera|58000|89000|12|4|2026-08-11|Mazda 3;Mazda CX-5;Hyundai Tucson;Kia Sportage;Toyota Corolla',
        'IEC-REL-40|Relé automotriz 12V 40A|Relé de 5 pines 12V 40A|Sistema Eléctrico|Importadora Eléctrica Cafetera|6500|9500|40|10|2026-08-11|Toyota Hilux;Chevrolet Spark;Nissan Frontier;Ford Ranger',
        'CIH-ALT-95|Alternador Case IH 95A|Alternador 12V 95A para tractores serie Puma y Farmall|Sistema Eléctrico|Case IH Repuestos|520000|745000|3|1|2026-07-14|Case IH Puma 165;Case IH Farmall 75C',
        -- Hidráulica
        'JD-MANG-HID|Manguera hidráulica 3/8 pulgada John Deere (metro)|Manguera hidráulica de alta presión, se vende por metro|Hidráulica|John Deere Partes|38000|58000|25|8|2026-07-14|John Deere 5075E;John Deere 6110M',
        'MFR-SELL-HID|Kit de sellos de cilindro hidráulico Massey Ferguson|Kit de sellos para el cilindro hidráulico del levante|Hidráulica|Massey Ferguson Repuestos|72000|110000|7|2|2026-07-14|Massey Ferguson 4707;Massey Ferguson 6713;Massey Ferguson 290',
        'CIH-FILT-HID|Filtro hidráulico Case IH|Filtro de aceite hidráulico y de transmisión|Hidráulica|Case IH Repuestos|71000|105000|9|3|2026-07-14|Case IH Puma 165;Case IH Farmall 75C',
        'FG-HF6177|Filtro hidráulico Fleetguard HF6177|Filtro de aceite hidráulico|Hidráulica|Fleetguard Filtros Industriales|54000|82000|10|3|2026-07-14|John Deere 6110M;New Holland T6.120;New Holland TL90',
        -- Enganches y Acoples
        'MFR-ROT-ENG|Rótula de enganche categoría II Massey Ferguson|Rótula de enganche para brazos inferiores categoría II|Enganches y Acoples|Massey Ferguson Repuestos|85000|130000|6|2|2026-07-14|Massey Ferguson 4707;Massey Ferguson 6713;Massey Ferguson 290',
        'CIH-EJE-PTO|Eje de toma de fuerza (PTO) Case IH|Eje de toma de fuerza de 540 rpm|Enganches y Acoples|Case IH Repuestos|410000|590000|3|1|2026-08-04|Case IH Puma 165;Case IH Farmall 75C',
        'JD-PIN-ENG|Pasador de enganche John Deere (par)|Par de pasadores de enganche categoría II con clip|Enganches y Acoples|John Deere Partes|24000|37000|20|6|2026-07-14|John Deere 5075E;John Deere 6110M',
        -- Neumáticos
        'MI-P185|Llanta Michelin Energy 185/65R15|Neumático radial para automóvil|Neumáticos|Michelin Agro|175000|265000|16|6|2026-07-14|Chevrolet Sail;Chevrolet Aveo;Renault Logan;Hyundai Accent;Kia Rio',
        'LLC-P215|Llanta Hankook 215/60R17|Neumático radial para camioneta|Neumáticos|Llantas y Rines Centro Sur|235000|345000|12|4|2026-08-04|Hyundai Tucson;Kia Sportage;Mazda CX-5',
        'LLC-P265|Llanta Pirelli Scorpion 265/65R17|Neumático radial para pickup y camperos|Neumáticos|Llantas y Rines Centro Sur|410000|585000|8|3|2026-08-04|Toyota Hilux;Toyota Fortuner;Mitsubishi L200;Ford Ranger',
        'MI-AGR1428|Llanta agrícola Michelin 14.9-28|Neumático trasero agrícola de tractor|Neumáticos|Michelin Agro|980000|1420000|4|2|2026-08-18|John Deere 5075E;Massey Ferguson 4707;New Holland TL90'
        ))) LOOP
        v_a := f(r.l, 4); v_b := f(r.l, 5);
        SELECT id INTO v_cat FROM categorias WHERE nombre = v_a;
        SELECT id INTO v_prv FROM proveedores WHERE nombre = v_b;
        v_t := ts9(f(r.l, 10));
        v_c := f(r.l, 1); v_d := f(r.l, 2); v_e := f(r.l, 3);
        v_pc := TO_NUMBER(f(r.l, 6)); v_pv := TO_NUMBER(f(r.l, 7));
        v_st := TO_NUMBER(f(r.l, 8)); v_mi := TO_NUMBER(f(r.l, 9));
        INSERT INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra,
                               precio_venta, stock, stock_minimo, activo, creado_en)
        VALUES (v_c, v_d, v_e, v_cat, v_prv, v_pc, v_pv, v_st, v_mi, 1, v_t)
        RETURNING id INTO v_rid;
        v_lst := f(r.l, 11) || ';';
        WHILE v_lst IS NOT NULL LOOP
            v_pos := INSTR(v_lst, ';');
            v_key := SUBSTR(v_lst, 1, v_pos - 1);
            v_lst := SUBSTR(v_lst, v_pos + 1);
            INSERT INTO repuesto_compatibilidad (repuesto_id, vehiculo_id, creado_en)
            SELECT v_rid, v.id, v_t FROM vw_vehiculos v
             WHERE v.marca || ' ' || v.modelo = v_key;
            IF SQL%ROWCOUNT = 0 THEN
                RAISE_APPLICATION_ERROR(-20902, 'Vehiculo no encontrado para la compatibilidad: ' || v_key);
            END IF;
        END LOOP;
    END LOOP;

    -- ── Compatibilidad adicional para repuestos que ya existían ──
    FOR r IN (SELECT column_value AS l FROM TABLE(sys.odcivarchar2list(
        'NGK-BKR6E|Chevrolet Spark;Chevrolet Spark GT;Suzuki Swift;Chevrolet Sail;Renault Logan',
        'MAC-48D|Chevrolet Onix;Kia Picanto;Renault Sandero',
        'BRM-FD204|Toyota Corolla;Hyundai Tucson;Kia Sportage',
        'BSH-0281|Toyota Corolla;Toyota Yaris;Hyundai Tucson;Kia Sportage',
        'MI-P205|Mazda 3;Toyota Corolla;Chevrolet Onix;Kia Rio;Hyundai Accent',
        'MNR-AM204|Chevrolet Aveo;Chevrolet Sail;Renault Logan',
        'GAT-T295|Renault Logan;Chevrolet Aveo',
        'BSH-ALT120|Toyota Corolla;Mazda 3;Chevrolet Aveo',
        'JD-BAT31|Massey Ferguson 4707;New Holland TL90',
        'FG-LF3970|John Deere 5075E;Case IH Puma 165;Massey Ferguson 4707',
        'JD-RE504836|John Deere 6110M'))) LOOP
        v_cod := f(r.l, 1);
        v_t := ts9('2026-07-14');
        SELECT id INTO v_rid FROM repuestos WHERE codigo = v_cod;
        v_lst := f(r.l, 2) || ';';
        WHILE v_lst IS NOT NULL LOOP
            v_pos := INSTR(v_lst, ';');
            v_key := SUBSTR(v_lst, 1, v_pos - 1);
            v_lst := SUBSTR(v_lst, v_pos + 1);
            INSERT INTO repuesto_compatibilidad (repuesto_id, vehiculo_id, creado_en)
            SELECT v_rid, v.id, v_t FROM vw_vehiculos v
             WHERE v.marca || ' ' || v.modelo = v_key
               AND NOT EXISTS (SELECT 1 FROM repuesto_compatibilidad c
                                WHERE c.repuesto_id = v_rid AND c.vehiculo_id = v.id);
        END LOOP;
    END LOOP;

    -- ── Clientes nuevos ──
    -- nombre|tipo_doc|identificacion|telefono|email|direccion|alta
    FOR r IN (SELECT column_value AS l FROM TABLE(sys.odcivarchar2list(
        'Carlos Eduardo Ramírez Peña|CC|79456123|3104567890|ceramirez79@gmail.com|Cra 68 # 24-15, Bogotá D.C.|2026-07-15',
        'Diana Marcela Cortés Rojas|CC|1018456732|3125678901|dmcortes@hotmail.com|Calle 45 # 13-20, Bogotá D.C.|2026-07-22',
        'Jhon Alexander Suárez|CC|80765432|3016789012|jhon.suarez80@gmail.com|Cra 7 # 112-30, Bogotá D.C.|2026-07-29',
        'Sandra Milena Vargas Duque|CC|52876541|3207890123|smvargas@outlook.com|Calle 10 # 4-50, Ibagué|2026-08-05',
        'Fabián Andrés Moreno|CC|1030567821|3158901234|fabian.moreno@gmail.com|Av. Boyacá # 63-12, Bogotá D.C.|2026-08-12',
        'Luz Dary Ospina|CC|43521987|3009012345|luzdary.ospina@gmail.com|Cra 43A # 18-60, Medellín|2026-08-19',
        'Oscar Iván Pineda|CC|79123654|3112345670|oscar.pineda@yahoo.com|Calle 80 # 20-14, Bogotá D.C.|2026-08-26',
        'Yudy Paola Herrera|CC|1110456789|3173456781|yudyherrera@gmail.com|Cra 5 # 32-18, Ibagué|2026-09-02',
        'Wilson Fernando Castaño|CC|16789543|3184567892|wcastano@hotmail.com|Calle 23 # 9-40, Cali|2026-09-09',
        'Gloria Esperanza Rincón|CC|41567890|3215678903|gloria.rincon@gmail.com|Cra 15 # 85-22, Bogotá D.C.|2026-09-16',
        'Mauricio Antonio Giraldo|CC|71654321|3006789014|mgiraldo71@gmail.com|Cra 70 # 44-10, Medellín|2026-09-23',
        'Natalia Andrea Quintero|CC|1065432198|3147890125|nataliaquintero@outlook.com|Calle 12 # 21-33, Neiva|2026-09-30',
        'Édgar Alfonso Beltrán|CC|17345678|3128901236|edgar.beltran@gmail.com|Cra 33 # 38-75, Villavicencio|2026-10-07',
        'Héctor Julio Salcedo|CC|91234567|3169012347|hjsalcedo@gmail.com|Calle 35 # 19-08, Bucaramanga|2026-10-14',
        'Ricardo Alberto Lozano|CC|1049876543|3102345678|ricardo.lozano@hotmail.com|Cra 11 # 19-50, Tunja|2026-10-21',
        'José Luis Cardona|CC|98765432|3193456789|jlcardona@gmail.com|Calle 19 # 7-24, Pereira|2026-10-26',
        'Yorman José Rodríguez Mendoza|CE|4569871|3224567890|yorman.rodriguez@gmail.com|Calle 8 # 12-30, Cúcuta|2026-09-12',
        'Taller Automotriz Los Andes|NIT|900234511|6013456721|contacto@tallerlosandes.com|Av. Caracas # 52-30, Bogotá D.C.|2026-07-16',
        'Mecánica Diésel del Llano S.A.S|NIT|901122334|3118765432|ventas@mecanicadiesel.com|Cra 22 # 6-15, Villavicencio|2026-07-27',
        'Frenos y Suspensión Cundinamarca|NIT|830145672|6017654321|info@frenoscundinamarca.com|Calle 13 # 28-40, Bogotá D.C.|2026-08-10',
        'Autos Servicio Chapinero|NIT|900876123|3139988776|serviciochapinero@gmail.com|Calle 63 # 11-20, Bogotá D.C.|2026-09-03',
        'Lubricentro El Cóndor|NIT|800654987|3201122334|elcondor@lubricentro.com.co|Cra 50 # 70-12, Medellín|2026-09-21',
        'Ferretería Industrial La 80|NIT|860234765|6014321098|compras@ferreteria80.com|Av. Calle 80 # 98-10, Bogotá D.C.|2026-07-18',
        'Ferrelectricos del Centro S.A.S|NIT|901345678|6026543210|pedidos@ferrelectricos.com|Cra 9 # 11-45, Cali|2026-08-24',
        'Ferretería y Repuestos San José|NIT|800321654|3146677889|sanjose@ferreteriasanjose.com|Calle 16 # 5-30, Ibagué|2026-10-05',
        'Hacienda La Palmira|NIT|900567890|3162233445|administracion@haciendalapalmira.com|Vereda La Palmira, Granada, Meta|2026-07-20',
        'Agroinsumos del Tolima S.A.S|NIT|901234987|3175566778|compras@agroinsumostolima.com|Km 4 vía Ibagué-Espinal, Tolima|2026-08-14',
        'Cultivos de Arroz Casanare Ltda|NIT|844001235|3108899001|gerencia@arrozcasanare.com|Km 12 vía Yopal-Aguazul, Casanare|2026-08-31',
        'Palmas del Meta S.A.|NIT|900998877|3196677112|mantenimiento@palmasdelmeta.com|Km 20 vía Puerto López, Meta|2026-09-14',
        'Cooperativa de Caficultores del Huila|NIT|891100234|3219988001|repuestos@cafihuila.com|Cra 5 # 8-60, Neiva, Huila|2026-10-02',
        'Transportes Rápido del Valle S.A.S|NIT|900445566|3114455667|flota@rapidovalle.com|Calle 25 # 3N-40, Cali|2026-08-07',
        'Inversiones Gómez y Cía S.C.A|NIT|800778899|6012233445|contabilidad@inversionesgomez.com|Cra 13 # 90-45, Bogotá D.C.|2026-09-28',
        'Logística Carga Pesada S.A.S|NIT|901556677|3127788990|operaciones@cargapesada.com|Zona Industrial Montevideo, Bogotá D.C.|2026-10-12'))) LOOP
        v_a := f(r.l, 1); v_b := f(r.l, 3); v_c := f(r.l, 2); v_d := f(r.l, 4); v_e := f(r.l, 5); v_g := f(r.l, 6);
        v_t := ts9(f(r.l, 7));
        INSERT INTO clientes (nombre, identificacion, tipo_doc, telefono, email, direccion, activo, creado_en)
        VALUES (v_a, v_b, v_c, v_d, v_e, v_g, 1, v_t);
    END LOOP;
END;
/

-- ============================================================
-- 3. SIMULACIÓN DE LA OPERACIÓN (ventas, cotizaciones, pedidos, auditoría,
--    asistente). Se ejecuta dos veces con la misma semilla:
--      paso A (solo memoria)  -> cuenta ventas/pedidos para poder renumerar
--                                los registros de prueba conservados;
--      paso B (escribe)       -> inserta todo en orden cronológico.
-- ============================================================
DECLARE
    -- ───────────── Parámetros ─────────────
    c_ini    CONSTANT DATE := DATE '2026-07-14';
    c_fin    CONSTANT DATE := DATE '2026-11-01';
    c_ahora  CONSTANT DATE := TO_DATE('2026-11-01 20:00', 'YYYY-MM-DD HH24:MI');  -- "ahora" local
    c_ventas CONSTANT NUMBER := 320;    -- ventas regulares esperadas (sin las nacidas de cotización)
    c_cots   CONSTANT NUMBER := 45;     -- cotizaciones esperadas
    c_asist  CONSTANT NUMBER := 150;    -- consultas al asistente esperadas
    c_lunes  CONSTANT DATE := DATE '2026-01-05';

    -- ───────────── Tipos ─────────────
    TYPE t_map   IS TABLE OF PLS_INTEGER INDEX BY PLS_INTEGER;
    TYPE t_nmap  IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    TYPE t_smap  IS TABLE OF PLS_INTEGER INDEX BY VARCHAR2(80);
    TYPE t_dates IS TABLE OF DATE INDEX BY PLS_INTEGER;

    TYPE t_lin  IS RECORD (p PLS_INTEGER, cant NUMBER, precio NUMBER, dscto NUMBER);
    TYPE t_lins IS TABLE OF t_lin INDEX BY PLS_INTEGER;

    TYPE t_part IS RECORD (
        id NUMBER, codigo VARCHAR2(50), nombre VARCHAR2(200), termino VARCHAR2(120),
        cat_id NUMBER, cat VARCHAR2(100), prov NUMBER, compra NUMBER, venta NUMBER,
        stock NUMBER, stock0 NUMBER, minimo NUMBER, desde DATE, w NUMBER, agro NUMBER,
        hold_a DATE, hold_b DATE, boost NUMBER, pend DATE, recibido NUMBER, vendido NUMBER);
    TYPE t_parts IS TABLE OF t_part INDEX BY PLS_INTEGER;

    TYPE t_cli  IS RECORD (id NUMBER, nombre VARCHAR2(150), perfil VARCHAR2(10), desde DATE, w NUMBER);
    TYPE t_clis IS TABLE OF t_cli INDEX BY PLS_INTEGER;

    -- 1 Carlos, 2 Laura, 3 Camilo, 4 Administrador, 5 Dueño
    TYPE t_usr  IS RECORD (id NUMBER, nombre VARCHAR2(100), desde DATE, w NUMBER, act DATE, ip VARCHAR2(45));
    TYPE t_usrs IS TABLE OF t_usr INDEX BY PLS_INTEGER;

    TYPE t_veh  IS RECORD (id NUMBER, marca VARCHAR2(80), modelo VARCHAR2(80), d NUMBER, h NUMBER, motor VARCHAR2(50));
    TYPE t_vehs IS TABLE OF t_veh INDEX BY PLS_INTEGER;
    TYPE t_cmp  IS RECORD (p PLS_INTEGER, v PLS_INTEGER);
    TYPE t_cmps IS TABLE OF t_cmp INDEX BY PLS_INTEGER;

    TYPE t_cot  IS RECORD (
        num VARCHAR2(30), fecha DATE, uid PLS_INTEGER, cli PLS_INTEGER, dpct NUMBER,
        vence DATE, notas VARCHAR2(200), estado VARCHAR2(12), upd DATE, conv DATE, lins t_lins);
    TYPE t_cots IS TABLE OF t_cot INDEX BY PLS_INTEGER;

    TYPE t_ped  IS RECORD (
        id NUMBER, num VARCHAR2(20), fecha DATE, prov NUMBER, uid PLS_INTEGER, estado VARCHAR2(12),
        esp DATE, recv DATE, trans DATE, canc DATE, notas VARCHAR2(200), lins t_lins, aplicado NUMBER);
    TYPE t_peds IS TABLE OF t_ped INDEX BY PLS_INTEGER;

    TYPE t_aud  IS RECORD (ts DATE, uid NUMBER, accion VARCHAR2(100), det VARCHAR2(4000), ip VARCHAR2(45));
    TYPE t_auds IS TABLE OF t_aud INDEX BY PLS_INTEGER;

    TYPE t_ev   IS RECORD (d DATE, cod VARCHAR2(50), pct NUMBER);
    TYPE t_evs  IS TABLE OF t_ev INDEX BY PLS_INTEGER;

    -- ───────────── Estado ─────────────
    g_w     BOOLEAN := FALSE;
    g_seed  NUMBER;
    g_part  t_parts;  g_np PLS_INTEGER := 0;
    g_pcod  t_smap;
    g_pidx  t_map;
    g_cli   t_clis;   g_nc PLS_INTEGER := 0;
    g_usr   t_usrs;
    g_veh   t_vehs;   g_nv_veh PLS_INTEGER := 0;
    g_vidx  t_map;
    g_cmp   t_cmps;   g_ncmp PLS_INTEGER := 0;
    g_cot   t_cots;   g_nco PLS_INTEGER := 0;
    g_ped   t_peds;   g_nped PLS_INTEGER := 0;
    g_aud   t_auds;   g_na PLS_INTEGER := 0;
    g_ev    t_evs;    g_nev PLS_INTEGER := 0;
    g_provn t_smap;
    g_provs t_map;   g_nprov PLS_INTEGER := 0;
    g_int   t_smap;
    g_vt    t_nmap;                          -- venta_id -> total calculado en memoria

    g_nvt   PLS_INTEGER := 0;               -- ventas generadas (numeración)
    g_ncomp PLS_INTEGER := 0;               -- ventas completadas
    g_nanu  PLS_INTEGER := 0;               -- ventas anuladas
    g_nconv PLS_INTEGER := 0;               -- ventas nacidas de una cotización
    g_omit  PLS_INTEGER := 0;               -- ventas omitidas por falta de stock
    g_convf PLS_INTEGER := 0;               -- conversiones fallidas por stock
    g_ncons PLS_INTEGER := 0;               -- consultas al asistente


    -- ───────────── Utilidades ─────────────
    FUNCTION rnd RETURN NUMBER IS
    BEGIN
        g_seed := MOD(g_seed * 1103515245 + 12345, 2147483648);
        RETURN g_seed / 2147483648;
    END rnd;

    FUNCTION rint(a NUMBER, b NUMBER) RETURN NUMBER IS
    BEGIN
        RETURN a + TRUNC(rnd * (b - a + 1));
    END rint;

    FUNCTION f(p VARCHAR2, n PLS_INTEGER) RETURN VARCHAR2 IS
        v_s PLS_INTEGER;
        v_e PLS_INTEGER;
    BEGIN
        IF n = 1 THEN v_s := 1; ELSE v_s := INSTR(p, '|', 1, n - 1) + 1; END IF;
        v_e := INSTR(p, '|', 1, n);
        IF v_e = 0 THEN RETURN SUBSTR(p, v_s); END IF;
        RETURN SUBSTR(p, v_s, v_e - v_s);
    END f;

    -- Fecha local -> TIMESTAMP en UTC (la base guarda UTC; hora local = UTC-5)
    FUNCTION ts(p DATE) RETURN TIMESTAMP IS
    BEGIN
        RETURN CAST(p + 5 / 24 AS TIMESTAMP);
    END ts;

    FUNCTION fnum(p NUMBER) RETURN VARCHAR2 IS
    BEGIN
        RETURN TO_CHAR(p, 'TM9', 'NLS_NUMERIC_CHARACTERS=''.,''');
    END fnum;

    FUNCTION dow(p DATE) RETURN PLS_INTEGER IS          -- 0 = lunes ... 6 = domingo
    BEGIN
        RETURN MOD(TRUNC(p) - c_lunes, 7);
    END dow;

    FUNCTION sin_domingo(p DATE) RETURN DATE IS         -- los pedidos no llegan en domingo
    BEGIN
        RETURN CASE WHEN dow(p) = 6 THEN p + 1 ELSE p END;
    END sin_domingo;

    PROCEDURE ordenar(p IN OUT NOCOPY t_dates) IS
        v_x DATE;
    BEGIN
        FOR i IN 1 .. p.COUNT - 1 LOOP
            FOR j IN i + 1 .. p.COUNT LOOP
                IF p(j) < p(i) THEN v_x := p(i); p(i) := p(j); p(j) := v_x; END IF;
            END LOOP;
        END LOOP;
    END ordenar;

    -- Auditoría en memoria, ordenada por fecha (la clave es segundos*100 + desempate)
    PROCEDURE aud(p_ts DATE, p_u PLS_INTEGER, p_acc VARCHAR2, p_det VARCHAR2) IS
        v_k PLS_INTEGER;
        v_r t_aud;
    BEGIN
        g_na := g_na + 1;
        v_k := TRUNC((p_ts - DATE '2026-07-01') * 86400) * 100 + MOD(g_na, 100);
        WHILE g_aud.EXISTS(v_k) LOOP v_k := v_k + 1; END LOOP;
        v_r.ts := p_ts;
        v_r.accion := p_acc;
        v_r.det := p_det;
        IF p_u > 0 THEN v_r.uid := g_usr(p_u).id; v_r.ip := g_usr(p_u).ip; END IF;
        g_aud(v_k) := v_r;
    END aud;

    -- Evento sin usuario ni IP (lo escribe un trigger de la base, no la aplicación)
    PROCEDURE aud_sys(p_ts DATE, p_acc VARCHAR2, p_det VARCHAR2) IS
        v_k PLS_INTEGER;
        v_r t_aud;
    BEGIN
        g_na := g_na + 1;
        v_k := TRUNC((p_ts - DATE '2026-07-01') * 86400) * 100 + MOD(g_na, 100);
        WHILE g_aud.EXISTS(v_k) LOOP v_k := v_k + 1; END LOOP;
        v_r.ts := p_ts;
        v_r.accion := p_acc;
        v_r.det := p_det;
        g_aud(v_k) := v_r;
    END aud_sys;

    -- Registra la primera actividad del día de un usuario (genera su login) y la IP del día
    PROCEDURE actividad(p_u PLS_INTEGER, p_ts DATE) IS
        v_r NUMBER;
    BEGIN
        IF g_usr(p_u).act IS NULL OR p_ts < g_usr(p_u).act THEN
            g_usr(p_u).act := p_ts;
        END IF;
        IF g_usr(p_u).ip IS NULL THEN
            v_r := rnd;
            g_usr(p_u).ip := CASE p_u
                WHEN 4 THEN CASE WHEN v_r < 0.60 THEN '191.104.38.206' ELSE '190.85.112.40' END
                WHEN 5 THEN CASE WHEN v_r < 0.30 THEN '191.104.38.206' ELSE '181.52.147.9' END
                ELSE        CASE WHEN v_r < 0.92 THEN '191.104.38.206' ELSE '181.63.20.115' END
            END;
        END IF;
    END actividad;

    -- ───────────── Carga del estado inicial desde la base ─────────────
    PROCEDURE cargar IS
        v_r    NUMBER;
        v_pr   NUMBER;
        v_cm   NUMBER;
        v_i    PLS_INTEGER;
        v_nom  VARCHAR2(150);
    BEGIN
        g_part.DELETE; g_np := 0; g_pcod.DELETE; g_pidx.DELETE;
        g_cli.DELETE;  g_nc := 0;
        g_veh.DELETE;  g_nv_veh := 0; g_vidx.DELETE;
        g_cmp.DELETE;  g_ncmp := 0;
        g_provn.DELETE; g_provs.DELETE; g_nprov := 0;
        g_int.DELETE;

        FOR r IN (SELECT r.id, r.codigo, r.nombre, r.categoria_id, c.nombre AS cat, r.proveedor_id,
                         r.precio_compra, r.precio_venta, r.stock, r.stock_minimo,
                         TRUNC(CAST(r.creado_en AS DATE) - 5 / 24) AS alta,
                         REGEXP_SUBSTR(LOWER(r.nombre), '^[^ ]+( de [^ ]+| [^ ]+)?') AS termino,
                         CASE WHEN EXISTS (
                                SELECT 1 FROM repuesto_compatibilidad rc
                                  JOIN vehiculos v ON v.id = rc.vehiculo_id
                                  JOIN modelos mo ON mo.id = v.modelo_id
                                  JOIN marcas ma ON ma.id = mo.marca_id
                                 WHERE rc.repuesto_id = r.id
                                   AND ma.nombre IN ('John Deere', 'Case IH', 'Massey Ferguson', 'New Holland'))
                              THEN 1 ELSE 0 END AS agro
                    FROM repuestos r LEFT JOIN categorias c ON c.id = r.categoria_id
                   ORDER BY r.id) LOOP
            g_np := g_np + 1;
            g_part(g_np).id := r.id;       g_part(g_np).codigo := r.codigo;
            g_part(g_np).nombre := r.nombre; g_part(g_np).termino := r.termino;
            g_part(g_np).cat_id := r.categoria_id; g_part(g_np).cat := r.cat;
            g_part(g_np).prov := r.proveedor_id;
            g_part(g_np).compra := r.precio_compra; g_part(g_np).venta := r.precio_venta;
            g_part(g_np).stock := r.stock;  g_part(g_np).stock0 := r.stock;
            g_part(g_np).minimo := r.stock_minimo;
            g_part(g_np).desde := CASE WHEN r.id <= :b_rep THEN c_ini ELSE GREATEST(c_ini, r.alta) END;
            g_part(g_np).agro := r.agro;
            g_part(g_np).hold_a := c_ini; g_part(g_np).hold_b := c_ini; g_part(g_np).boost := 1;
            g_part(g_np).pend := NULL;
            g_part(g_np).recibido := 0; g_part(g_np).vendido := 0;
            -- Popularidad: más rotación en lo barato y de consumo; poca en lo costoso
            v_pr := CASE WHEN r.precio_venta < 20000 THEN 9 WHEN r.precio_venta < 50000 THEN 8
                         WHEN r.precio_venta < 100000 THEN 6 WHEN r.precio_venta < 200000 THEN 4
                         WHEN r.precio_venta < 400000 THEN 2.5 WHEN r.precio_venta < 1000000 THEN 0.9
                         ELSE 0.3 END;
            v_cm := CASE r.cat WHEN 'Filtros' THEN 1.5 WHEN 'Frenos' THEN 1.3 WHEN 'Encendido' THEN 1.2
                               WHEN 'Motor' THEN 1.2 WHEN 'Baterías' THEN 0.9 WHEN 'Neumáticos' THEN 0.8
                               WHEN 'Enganches y Acoples' THEN 0.7 ELSE 1 END;
            g_part(g_np).w := v_pr * v_cm * (0.6 + rnd * 0.9);
            g_pcod(r.codigo) := g_np;
            g_pidx(r.id) := g_np;
        END LOOP;

        -- Casos de la historia: sin stock hasta que llega el pedido de las últimas semanas
        g_part(g_pcod('90915-YZZD4')).hold_b := DATE '2026-10-28';
        g_part(g_pcod('FG-FF5320')).hold_b   := DATE '2026-10-28';
        -- Repuestos que se quedan sin reposición en las últimas semanas (el proveedor demoró la cotización)
        FOR r IN (SELECT column_value AS cod FROM TABLE(sys.odcivarchar2list(
                    'GAT-K060', 'CMT-ROT-INF', 'MI-P185', 'MNR-AM3500', 'BRM-P85020', 'JD-PIN-ENG',
                    'BRM-FD204', 'JD-MANG-HID'))) LOOP
            g_part(g_pcod(r.cod)).hold_a := DATE '2026-10-05';
            g_part(g_pcod(r.cod)).hold_b := DATE '2026-10-31';
            g_part(g_pcod(r.cod)).boost := 1.6;       -- en esas semanas se venden más rápido de lo previsto
        END LOOP;

        FOR r IN (SELECT id, nombre, identificacion, TRUNC(CAST(creado_en AS DATE) - 5 / 24) AS alta
                    FROM clientes WHERE identificacion <> '9999999991' ORDER BY id) LOOP
            g_nc := g_nc + 1;
            g_cli(g_nc).id := r.id;
            g_cli(g_nc).nombre := r.nombre;
            g_cli(g_nc).desde := CASE WHEN r.id <= :b_cli THEN c_ini ELSE GREATEST(c_ini, r.alta) END;
            v_nom := r.nombre;
            g_cli(g_nc).perfil :=
                CASE WHEN v_nom LIKE 'Hacienda%' OR v_nom LIKE 'Agro%' OR v_nom LIKE 'Cultivos%'
                          OR v_nom LIKE 'Palmas%' OR v_nom LIKE 'Cooperativa%' OR v_nom LIKE 'Finca%'
                          OR v_nom LIKE 'Agroinsumos%' THEN 'agro'
                     WHEN v_nom LIKE 'Taller%' OR v_nom LIKE 'Mecánica%' OR v_nom LIKE 'Frenos%'
                          OR v_nom LIKE 'Autos%' OR v_nom LIKE 'Lubricentro%'
                          OR v_nom LIKE 'Distribuidora de Repuestos%' THEN 'taller'
                     WHEN v_nom LIKE '%S.A.S%' OR v_nom LIKE '%Ltda%' OR v_nom LIKE '%S.A.%'
                          OR v_nom LIKE 'Ferreter%' OR v_nom LIKE 'Ferrelect%' OR v_nom LIKE 'Constructora%'
                          OR v_nom LIKE 'Inversiones%' OR v_nom LIKE 'Transportes%' THEN 'empresa'
                     ELSE 'persona' END;
            g_cli(g_nc).w := CASE g_cli(g_nc).perfil WHEN 'empresa' THEN 3 WHEN 'taller' THEN 2.5
                                                     WHEN 'agro' THEN 2.5 ELSE 1 END * (0.5 + rnd * 1.5);
        END LOOP;

        -- Usuarios
        g_usr.DELETE;
        FOR i IN 1 .. 5 LOOP g_usr(i).act := NULL; g_usr(i).ip := NULL; END LOOP;
        SELECT id INTO g_usr(1).id FROM usuarios WHERE email = 'vendedor@electrisys.com';
        SELECT id INTO g_usr(2).id FROM usuarios WHERE email = 'laura.gomez@electrisys.com';
        SELECT id INTO g_usr(3).id FROM usuarios WHERE email = 'camilo.rojas@electrisys.com';
        SELECT id INTO g_usr(4).id FROM usuarios WHERE email = 'admin@electrisys.com';
        SELECT id INTO g_usr(5).id FROM usuarios WHERE email = 'dueno@electrisys.com';
        g_usr(1).nombre := 'Carlos Vendedor'; g_usr(1).desde := c_ini;                 g_usr(1).w := 3;
        g_usr(2).nombre := 'Laura Gómez';     g_usr(2).desde := DATE '2026-07-21';      g_usr(2).w := 3;
        g_usr(3).nombre := 'Camilo Rojas';    g_usr(3).desde := DATE '2026-08-19';      g_usr(3).w := 2.5;
        g_usr(4).nombre := 'Administrador';   g_usr(4).desde := c_ini;                 g_usr(4).w := 0.7;
        g_usr(5).nombre := 'Andrés Felipe Torres'; g_usr(5).desde := c_ini;            g_usr(5).w := 0;

        -- Vehículos y compatibilidad
        FOR r IN (SELECT v.id, ma.nombre AS marca, mo.nombre AS modelo, v.anio_desde, v.anio_hasta, v.motor
                    FROM vehiculos v JOIN modelos mo ON mo.id = v.modelo_id
                    JOIN marcas ma ON ma.id = mo.marca_id ORDER BY v.id) LOOP
            g_nv_veh := g_nv_veh + 1;
            g_veh(g_nv_veh).id := r.id; g_veh(g_nv_veh).marca := r.marca; g_veh(g_nv_veh).modelo := r.modelo;
            g_veh(g_nv_veh).d := r.anio_desde; g_veh(g_nv_veh).h := r.anio_hasta; g_veh(g_nv_veh).motor := r.motor;
            g_vidx(r.id) := g_nv_veh;
        END LOOP;
        FOR r IN (SELECT repuesto_id, vehiculo_id FROM repuesto_compatibilidad ORDER BY repuesto_id, vehiculo_id) LOOP
            IF g_pidx.EXISTS(r.repuesto_id) AND g_vidx.EXISTS(r.vehiculo_id) THEN
                g_ncmp := g_ncmp + 1;
                g_cmp(g_ncmp).p := g_pidx(r.repuesto_id);
                g_cmp(g_ncmp).v := g_vidx(r.vehiculo_id);
            END IF;
        END LOOP;

        FOR r IN (SELECT id, nombre FROM proveedores ORDER BY id) LOOP
            g_provn(r.nombre) := r.id;
        END LOOP;
        FOR i IN 1 .. g_np LOOP
            v_i := g_part(i).prov;
            IF NOT g_provs.EXISTS(v_i) THEN
                g_nprov := g_nprov + 1;
                g_provs(v_i) := g_nprov;
            END IF;
        END LOOP;
        FOR r IN (SELECT id, nombre FROM nlp_intenciones) LOOP
            g_int(r.nombre) := r.id;
        END LOOP;
    END cargar;

    FUNCTION nombre_prov(p_id NUMBER) RETURN VARCHAR2 IS
        v_n VARCHAR2(150);
    BEGIN
        SELECT nombre INTO v_n FROM proveedores WHERE id = p_id;
        RETURN v_n;
    END nombre_prov;

    -- ───────────── Calendario de demanda ─────────────
    FUNCTION peso_dia(p_d DATE) RETURN NUMBER IS
        v_w  NUMBER;
        v_dd NUMBER := TO_NUMBER(TO_CHAR(p_d, 'DD'));
    BEGIN
        v_w := CASE dow(p_d) WHEN 0 THEN 1.0 WHEN 1 THEN 1.0 WHEN 2 THEN 1.0 WHEN 3 THEN 1.05
                             WHEN 4 THEN 1.1 WHEN 5 THEN 1.45 ELSE 0.12 END;      -- sábado fuerte, domingo casi nada
        v_w := v_w * (0.90 + 0.35 * (p_d - c_ini) / (c_fin - c_ini));              -- tendencia de crecimiento (cerca de +30 % de agosto a octubre)
        IF v_dd >= TO_NUMBER(TO_CHAR(LAST_DAY(p_d), 'DD')) - 2 THEN v_w := v_w * 1.45;   -- fin de mes
        ELSIF v_dd BETWEEN 14 AND 16 THEN v_w := v_w * 1.15;                              -- quincena
        END IF;
        IF p_d IN (DATE '2026-08-07', DATE '2026-08-17', DATE '2026-10-12') THEN v_w := v_w * 0.3; END IF;  -- festivos
        RETURN v_w;
    END peso_dia;

    -- n instantes ordenados dentro del horario comercial del día
    PROCEDURE horas(p_d DATE, p_n PLS_INTEGER, o_t OUT NOCOPY t_dates) IS
        v_a NUMBER; v_b NUMBER; v_s NUMBER;
    BEGIN
        o_t.DELETE;
        CASE dow(p_d)
            WHEN 6 THEN v_a := 9 * 3600; v_b := 13 * 3600;
            WHEN 5 THEN v_a := 8 * 3600; v_b := 16 * 3600;
            ELSE        v_a := 8 * 3600; v_b := 18 * 3600 + 1800;
        END CASE;
        FOR i IN 1 .. p_n LOOP
            v_s := TRUNC(v_a + (v_b - v_a) * (rnd + rnd) / 2);
            o_t(i) := TRUNC(p_d) + v_s / 86400;
        END LOOP;
        ordenar(o_t);
    END horas;

    -- Conteo del día por acumulado: reparte exactamente p_obj eventos a lo largo del periodo,
    -- en proporción al peso de cada día (sin la varianza de un sorteo independiente por día)
    FUNCTION n_dia(p_obj NUMBER, p_acum_ant NUMBER, p_acum NUMBER, p_wtot NUMBER) RETURN PLS_INTEGER IS
    BEGIN
        RETURN ROUND(p_obj * p_acum / p_wtot) - ROUND(p_obj * p_acum_ant / p_wtot);
    END n_dia;

    -- ───────────── Selección de repuestos, clientes y vendedores ─────────────
    FUNCTION pick_seller(p_ts DATE) RETURN PLS_INTEGER IS
        v_tot NUMBER := 0; v_r NUMBER; v_acc NUMBER := 0;
    BEGIN
        FOR u IN 1 .. 4 LOOP IF g_usr(u).desde <= p_ts THEN v_tot := v_tot + g_usr(u).w; END IF; END LOOP;
        v_r := rnd * v_tot;
        FOR u IN 1 .. 4 LOOP
            IF g_usr(u).desde <= p_ts THEN
                v_acc := v_acc + g_usr(u).w;
                IF v_acc >= v_r THEN RETURN u; END IF;
            END IF;
        END LOOP;
        RETURN 1;
    END pick_seller;

    FUNCTION pick_cliente(p_d DATE) RETURN PLS_INTEGER IS
        v_tot NUMBER := 0; v_r NUMBER; v_acc NUMBER := 0;
    BEGIN
        FOR i IN 1 .. g_nc LOOP IF g_cli(i).desde <= p_d THEN v_tot := v_tot + g_cli(i).w; END IF; END LOOP;
        IF v_tot = 0 THEN RETURN 0; END IF;
        v_r := rnd * v_tot;
        FOR i IN 1 .. g_nc LOOP
            IF g_cli(i).desde <= p_d THEN
                v_acc := v_acc + g_cli(i).w;
                IF v_acc >= v_r THEN RETURN i; END IF;
            END IF;
        END LOOP;
        RETURN 0;
    END pick_cliente;

    FUNCTION eleg(p_i PLS_INTEGER, p_d DATE, p_agro NUMBER, p_lim BOOLEAN, p_used t_map) RETURN BOOLEAN IS
    BEGIN
        RETURN g_part(p_i).desde <= p_d
           AND (p_agro < 0 OR g_part(p_i).agro = p_agro)
           AND NOT p_used.EXISTS(p_i)
           AND (NOT p_lim OR g_part(p_i).stock > 0);
    END eleg;

    -- Popularidad efectiva: algunos repuestos aceleran sus ventas en octubre (ver cargar)
    FUNCTION peso_ef(p_i PLS_INTEGER, p_d DATE) RETURN NUMBER IS
    BEGIN
        RETURN CASE WHEN p_d >= DATE '2026-10-05' THEN g_part(p_i).w * g_part(p_i).boost ELSE g_part(p_i).w END;
    END peso_ef;

    FUNCTION pick_part(p_d DATE, p_agro NUMBER, p_lim BOOLEAN, p_used t_map) RETURN PLS_INTEGER IS
        v_tot NUMBER := 0; v_r NUMBER; v_acc NUMBER := 0;
    BEGIN
        FOR i IN 1 .. g_np LOOP
            IF eleg(i, p_d, p_agro, p_lim, p_used) THEN v_tot := v_tot + peso_ef(i, p_d); END IF;
        END LOOP;
        IF v_tot = 0 THEN RETURN 0; END IF;
        v_r := rnd * v_tot;
        FOR i IN 1 .. g_np LOOP
            IF eleg(i, p_d, p_agro, p_lim, p_used) THEN
                v_acc := v_acc + peso_ef(i, p_d);
                IF v_acc >= v_r THEN RETURN i; END IF;
            END IF;
        END LOOP;
        RETURN 0;
    END pick_part;

    -- Otro repuesto compatible con el mismo vehículo que el repuesto p_base (compras "para el mismo carro")
    FUNCTION pick_companion(p_base PLS_INTEGER, p_d DATE, p_lim BOOLEAN, p_used t_map) RETURN PLS_INTEGER IS
        v_veh PLS_INTEGER := 0; v_tot NUMBER := 0; v_r NUMBER; v_acc NUMBER := 0; v_k PLS_INTEGER; v_n PLS_INTEGER := 0;
    BEGIN
        FOR k IN 1 .. g_ncmp LOOP
            IF g_cmp(k).p = p_base THEN
                v_n := v_n + 1;
                IF v_veh = 0 OR rnd < 1 / v_n THEN v_veh := g_cmp(k).v; END IF;
            END IF;
        END LOOP;
        IF v_veh = 0 THEN RETURN 0; END IF;
        FOR k IN 1 .. g_ncmp LOOP
            IF g_cmp(k).v = v_veh AND eleg(g_cmp(k).p, p_d, -1, p_lim, p_used) THEN
                v_tot := v_tot + g_part(g_cmp(k).p).w;
            END IF;
        END LOOP;
        IF v_tot = 0 THEN RETURN 0; END IF;
        v_r := rnd * v_tot;
        FOR k IN 1 .. g_ncmp LOOP
            IF g_cmp(k).v = v_veh AND eleg(g_cmp(k).p, p_d, -1, p_lim, p_used) THEN
                v_acc := v_acc + g_part(g_cmp(k).p).w;
                IF v_acc >= v_r THEN RETURN g_cmp(k).p; END IF;
            END IF;
        END LOOP;
        RETURN 0;
    END pick_companion;

    FUNCTION qty_de(p_i PLS_INTEGER, p_perf VARCHAR2) RETURN NUMBER IS
        v_r NUMBER := rnd;
        v_q NUMBER;
        v_p NUMBER := g_part(p_i).venta;
    BEGIN
        IF v_p < 25000 THEN
            v_q := CASE WHEN v_r < 0.35 THEN 1 WHEN v_r < 0.60 THEN 2 WHEN v_r < 0.80 THEN 4 WHEN v_r < 0.92 THEN 6 ELSE 8 END;
        ELSIF v_p < 100000 THEN
            v_q := CASE WHEN v_r < 0.55 THEN 1 WHEN v_r < 0.85 THEN 2 WHEN v_r < 0.95 THEN 3 ELSE 4 END;
        ELSIF v_p < 400000 THEN
            v_q := CASE WHEN v_r < 0.80 THEN 1 ELSE 2 END;
        ELSE
            v_q := 1;
        END IF;
        IF p_perf = 'taller' AND v_p < 400000 THEN v_q := v_q * 2; END IF;
        RETURN v_q;
    END qty_de;

    PROCEDURE armar_lineas(p_d DATE, p_perf VARCHAR2, p_lim BOOLEAN, p_pagro NUMBER, o_l IN OUT NOCOPY t_lins) IS
        v_used t_map; v_agro NUMBER; v_n PLS_INTEGER; v_i PLS_INTEGER; v_try PLS_INTEGER := 0;
        v_r NUMBER; v_q NUMBER; v_ln t_lin; v_base PLS_INTEGER := 0;
    BEGIN
        o_l.DELETE;
        v_agro := CASE WHEN rnd < p_pagro THEN 1 ELSE 0 END;
        v_r := rnd;
        v_n := CASE WHEN v_r < 0.42 THEN 1 WHEN v_r < 0.72 THEN 2 WHEN v_r < 0.90 THEN 3 ELSE 4 END;
        IF p_perf IN ('taller', 'empresa', 'agro') THEN v_n := LEAST(5, v_n + 1); END IF;
        WHILE o_l.COUNT < v_n AND v_try < 14 LOOP
            v_try := v_try + 1;
            IF v_base > 0 AND rnd < 0.55 THEN
                v_i := pick_companion(v_base, p_d, p_lim, v_used);
                IF v_i = 0 THEN v_i := pick_part(p_d, v_agro, p_lim, v_used); END IF;
            ELSE
                v_i := pick_part(p_d, v_agro, p_lim, v_used);
            END IF;
            EXIT WHEN v_i = 0;
            v_q := qty_de(v_i, p_perf);
            IF p_lim THEN v_q := LEAST(v_q, g_part(v_i).stock); END IF;
            IF v_q >= 1 THEN
                v_used(v_i) := 1;
                IF v_base = 0 THEN v_base := v_i; END IF;
                v_ln.p := v_i; v_ln.cant := v_q; v_ln.precio := g_part(v_i).venta; v_ln.dscto := 0;
                o_l(o_l.COUNT + 1) := v_ln;
            END IF;
        END LOOP;
    END armar_lineas;

    -- ───────────── Ventas ─────────────
    PROCEDURE hacer_venta(p_ts DATE, p_cot PLS_INTEGER) IS
        v_u PLS_INTEGER; v_cli PLS_INTEGER := 0; v_perf VARCHAR2(10) := 'persona'; v_mp VARCHAR2(20);
        v_lins t_lins; v_dpct NUMBER := 0; v_anul BOOLEAN := FALSE; v_notas VARCHAR2(200);
        v_sub NUMBER := 0; v_dsc NUMBER; v_iva NUMBER; v_tot NUMBER; v_id NUMBER; v_num VARCHAR2(20);
        v_pagro NUMBER; v_r NUMBER; v_cid NUMBER; v_anu_ts DATE; v_anu_u PLS_INTEGER; v_ok BOOLEAN := TRUE;
        v_ln t_lin; v_tsc TIMESTAMP; v_tsu TIMESTAMP; v_est VARCHAR2(20); v_ver NUMBER; v_uid NUMBER; v_rid NUMBER;
    BEGIN
        IF p_cot > 0 THEN
            -- Conversión de una cotización: mismos ítems y precios cotizados
            v_u := g_cot(p_cot).uid; v_cli := g_cot(p_cot).cli; v_dpct := g_cot(p_cot).dpct;
            v_lins := g_cot(p_cot).lins;
            FOR i IN 1 .. v_lins.COUNT LOOP
                IF v_lins(i).cant > g_part(v_lins(i).p).stock THEN v_ok := FALSE; END IF;
            END LOOP;
            IF NOT v_ok THEN g_convf := g_convf + 1; RETURN; END IF;
            v_notas := 'Generada desde la cotización ' || g_cot(p_cot).num;
        ELSE
            v_u := pick_seller(p_ts);
            IF rnd < 0.30 THEN v_cli := pick_cliente(TRUNC(p_ts)); END IF;
            IF v_cli > 0 THEN v_perf := g_cli(v_cli).perfil; END IF;
            v_pagro := CASE v_perf WHEN 'agro' THEN 0.8 WHEN 'taller' THEN 0.03 WHEN 'empresa' THEN 0.12
                                   ELSE CASE WHEN v_cli > 0 THEN 0.05 ELSE 0.12 END END;
            armar_lineas(TRUNC(p_ts), v_perf, TRUE, v_pagro, v_lins);
            IF v_lins.COUNT = 0 THEN g_omit := g_omit + 1; RETURN; END IF;
            v_r := rnd;
            v_notas := CASE WHEN v_r < 0.02 THEN 'Cliente solicita factura electrónica'
                            WHEN v_r < 0.04 THEN 'Entrega en el taller del cliente'
                            WHEN v_r < 0.055 THEN 'Pago parcial al contado, saldo pendiente de confirmar'
                            WHEN v_r < 0.07 THEN 'Garantía de 3 meses por defectos de fábrica'
                            ELSE NULL END;
            -- 1 de cada 31 ventas regulares se anula (reparto fijo, sin sorteo): unas 10 anuladas en el periodo
            v_anul := (TRUNC(p_ts) < c_fin) AND (MOD((g_nvt + 1) * 13, 31) = 7);
        END IF;
        IF v_cli > 0 THEN v_perf := g_cli(v_cli).perfil; END IF;

        FOR i IN 1 .. v_lins.COUNT LOOP
            v_sub := v_sub + v_lins(i).cant * v_lins(i).precio - v_lins(i).dscto;
        END LOOP;
        v_dsc := ROUND(v_sub * v_dpct / 100, 2);
        v_iva := ROUND((v_sub - v_dsc) * 19 / 100, 2);
        v_tot := v_sub - v_dsc + v_iva;

        v_r := rnd;
        IF v_perf IN ('empresa', 'agro', 'taller') THEN
            v_mp := CASE WHEN v_r < 0.45 THEN 'transferencia' WHEN v_r < 0.75 THEN 'efectivo' ELSE 'tarjeta' END;
        ELSE
            v_mp := CASE WHEN v_r < 0.50 THEN 'efectivo' WHEN v_r < 0.82 THEN 'tarjeta' ELSE 'transferencia' END;
        END IF;
        IF v_tot > 1500000 AND v_mp = 'efectivo' THEN v_mp := 'transferencia'; END IF;

        g_nvt := g_nvt + 1;
        v_num := 'VT-2026-' || LPAD(g_nvt, 6, '0');
        v_cid := CASE WHEN v_cli > 0 THEN g_cli(v_cli).id END;
        IF v_anul THEN
            v_anu_u := CASE WHEN rnd < 0.5 THEN 4 ELSE v_u END;
            v_anu_ts := p_ts + rint(8, 95) / 1440;
            g_nanu := g_nanu + 1;
        ELSE
            g_ncomp := g_ncomp + 1;
        END IF;
        IF p_cot > 0 THEN g_nconv := g_nconv + 1; END IF;

        actividad(v_u, p_ts);
        IF g_w THEN
            v_tsc := ts(p_ts);
            v_tsu := CASE WHEN v_anul THEN ts(v_anu_ts) END;
            v_est := CASE WHEN v_anul THEN 'anulada' ELSE 'completada' END;
            v_ver := CASE WHEN v_anul THEN 2 ELSE 1 END;
            v_uid := g_usr(v_u).id;
            INSERT INTO ventas (numero, cliente_id, usuario_id, descuento_pct, iva_pct, metodo_pago, estado,
                                notas, version, creado_en, updated_at)
            VALUES (v_num, v_cid, v_uid, v_dpct, 19, v_mp, v_est, v_notas, v_ver, v_tsc, v_tsu)
            RETURNING id INTO v_id;
            FOR i IN 1 .. v_lins.COUNT LOOP
                v_rid := g_part(v_lins(i).p).id;
                INSERT INTO detalle_ventas (venta_id, repuesto_id, cantidad, precio_unit, descuento)
                VALUES (v_id, v_rid, v_lins(i).cant, v_lins(i).precio, v_lins(i).dscto);
            END LOOP;
            IF v_anul THEN
                -- Equivale a trg_ventas_anulada_restaura_stock, sin pasar por un UPDATE de ventas
                FOR i IN 1 .. v_lins.COUNT LOOP
                    v_rid := g_part(v_lins(i).p).id;
                    UPDATE repuestos SET stock = stock + v_lins(i).cant WHERE id = v_rid;
                END LOOP;
            END IF;
            g_vt(v_id) := v_tot;
        END IF;

        -- Efecto en memoria: una venta anulada no consume stock (se repone)
        IF NOT v_anul THEN
            FOR i IN 1 .. v_lins.COUNT LOOP
                g_part(v_lins(i).p).stock := g_part(v_lins(i).p).stock - v_lins(i).cant;
                g_part(v_lins(i).p).vendido := g_part(v_lins(i).p).vendido + v_lins(i).cant;
            END LOOP;
        END IF;

        aud(p_ts + 2 / 86400, v_u, 'crear_venta', 'Venta ' || v_num || ' por $' || fnum(v_tot));
        IF v_anul THEN
            actividad(v_anu_u, v_anu_ts);
            aud(v_anu_ts, v_anu_u, 'anular_venta', 'Venta ID ' || v_id || ' anulada');
        END IF;
        IF p_cot > 0 THEN
            g_cot(p_cot).estado := 'realizada';
            g_cot(p_cot).upd := p_ts;
        END IF;
    END hacer_venta;

    -- ───────────── Cotizaciones ─────────────
    PROCEDURE hacer_cotizacion(p_ts DATE) IS
        v_c t_cot; v_u PLS_INTEGER; v_cli PLS_INTEGER := 0; v_perf VARCHAR2(10) := 'persona'; v_pagro NUMBER;
        v_hex VARCHAR2(10); v_r NUMBER; v_dup BOOLEAN;
    BEGIN
        v_u := pick_seller(p_ts);
        IF rnd < 0.85 THEN v_cli := pick_cliente(TRUNC(p_ts)); END IF;
        IF v_cli > 0 THEN v_perf := g_cli(v_cli).perfil; END IF;
        v_pagro := CASE v_perf WHEN 'agro' THEN 0.8 WHEN 'taller' THEN 0.03 WHEN 'empresa' THEN 0.12 ELSE 0.08 END;
        armar_lineas(TRUNC(p_ts), v_perf, FALSE, v_pagro, v_c.lins);
        IF v_c.lins.COUNT = 0 THEN RETURN; END IF;
        LOOP
            v_hex := LPAD(TO_CHAR(TRUNC(rnd * 16777216), 'FMXXXXXX'), 6, '0');
            v_c.num := 'COT-' || TO_CHAR(p_ts, 'YYYYMMDD') || '-' || v_hex;
            v_dup := FALSE;
            FOR i IN 1 .. g_nco LOOP IF g_cot(i).num = v_c.num THEN v_dup := TRUE; END IF; END LOOP;
            EXIT WHEN NOT v_dup;
        END LOOP;
        v_c.fecha := p_ts; v_c.uid := v_u; v_c.cli := v_cli;
        v_c.dpct := CASE WHEN v_perf IN ('empresa', 'taller', 'agro') AND v_c.lins.COUNT >= 3 THEN 5 ELSE 0 END;
        v_c.vence := TRUNC(p_ts) + CASE WHEN rnd < 0.5 THEN 15 ELSE 30 END;
        v_r := rnd;
        v_c.notas := CASE WHEN v_r < 0.10 THEN 'Cotización para flota de vehículos'
                          WHEN v_r < 0.20 THEN 'Precios sujetos a disponibilidad de inventario'
                          WHEN v_r < 0.28 THEN 'Incluye instalación sin costo en el taller'
                          WHEN v_r < 0.34 THEN 'Cliente compara con otro proveedor'
                          ELSE NULL END;
        v_c.estado := 'activa'; v_c.upd := NULL; v_c.conv := NULL;
        IF v_cli > 0 AND rnd < 0.5 THEN
            v_c.conv := sin_domingo(TRUNC(p_ts) + rint(1, 9));
            IF v_c.conv > c_fin THEN v_c.conv := NULL; END IF;
        END IF;
        g_nco := g_nco + 1;
        g_cot(g_nco) := v_c;
        actividad(v_u, p_ts);
    END hacer_cotizacion;

    -- ───────────── Pedidos a proveedor ─────────────
    FUNCTION lead_de(p_nom VARCHAR2) RETURN PLS_INTEGER IS
    BEGIN
        RETURN CASE
            WHEN p_nom LIKE 'Toyota%' THEN rint(6, 9)
            WHEN p_nom LIKE 'John Deere%' OR p_nom LIKE 'Case IH%' OR p_nom LIKE 'Massey%' THEN rint(3, 5)
            WHEN p_nom LIKE 'Fleetguard%' OR p_nom LIKE 'Michelin%' THEN rint(5, 8)
            ELSE rint(2, 5) END;
    END lead_de;

    PROCEDURE crear_pedido(p_ts DATE, p_prov NUMBER, p_lins t_lins) IS
        v_p t_ped; v_nom VARCHAR2(150); v_lead PLS_INTEGER; v_rd DATE; v_id NUMBER; v_r NUMBER;
        v_tsc TIMESTAMP; v_tsu TIMESTAMP; v_tsr TIMESTAMP; v_uidn NUMBER; v_rdt DATE; v_rid NUMBER;
    BEGIN
        g_nped := g_nped + 1;
        v_p.num := 'PED-' || LPAD(g_nped, 6, '0');
        v_p.fecha := p_ts; v_p.prov := p_prov; v_p.lins := p_lins; v_p.aplicado := 0;
        v_p.uid := CASE WHEN rnd < 0.45 THEN 5 ELSE 4 END;
        v_p.notas := NULL; v_p.recv := NULL; v_p.trans := NULL; v_p.canc := NULL;
        v_nom := nombre_prov(p_prov);
        v_lead := lead_de(v_nom);
        v_rd := sin_domingo(TRUNC(p_ts) + v_lead);
        v_p.esp := v_rd;
        IF g_nped IN (7, 19) THEN
            v_p.estado := 'cancelado';
            v_p.canc := TRUNC(p_ts) + 1 + rint(10, 16) / 24;
            v_p.notas := CASE g_nped WHEN 7 THEN 'Cancelado: el proveedor no tenía existencias'
                                     ELSE 'Cancelado: se consiguió mejor precio con otro proveedor' END;
            FOR i IN 1 .. v_p.lins.COUNT LOOP g_part(v_p.lins(i).p).pend := TRUNC(v_p.canc); END LOOP;
        ELSE
            v_p.recv := v_rd + (430 + rint(0, 45)) / 1440;             -- llega entre 07:10 y 07:55
            IF v_p.recv <= c_ahora THEN
                v_p.estado := 'recibido';
                v_p.trans := TRUNC(p_ts) + 1 + rint(10, 15) / 24;
            ELSIF c_ahora - p_ts >= 2 THEN
                v_p.estado := 'en_transito';
                v_p.trans := TRUNC(p_ts) + 1 + rint(10, 15) / 24;
                v_p.recv := NULL;
            ELSE
                v_p.estado := 'solicitado';
                v_p.recv := NULL;
            END IF;
            v_r := rnd;
            v_p.notas := CASE WHEN v_r < 0.12 THEN 'Reposición programada de inventario'
                              WHEN v_r < 0.22 THEN 'Pedido urgente por stock bajo'
                              WHEN v_r < 0.28 THEN 'Incluye descuento por volumen acordado con el proveedor'
                              ELSE NULL END;
            FOR i IN 1 .. v_p.lins.COUNT LOOP g_part(v_p.lins(i).p).pend := v_rd; END LOOP;
        END IF;
        actividad(v_p.uid, p_ts);
        IF g_w THEN
            v_tsc := ts(p_ts);
            v_tsu := CASE v_p.estado WHEN 'recibido' THEN ts(v_p.recv) WHEN 'en_transito' THEN ts(v_p.trans)
                                     WHEN 'cancelado' THEN ts(v_p.canc) END;
            v_tsr := CASE WHEN v_p.estado = 'recibido' THEN ts(v_p.recv) END;
            v_uidn := g_usr(v_p.uid).id;
            v_rdt := TRUNC(v_rd);
            INSERT INTO pedidos (numero, proveedor_id, usuario_id, estado, fecha_esperada, notas, creado_en,
                                 updated_at, recibido_en)
            VALUES (v_p.num, p_prov, v_uidn, v_p.estado, v_rdt, v_p.notas, v_tsc, v_tsu, v_tsr)
            RETURNING id INTO v_id;
            v_p.id := v_id;
            FOR i IN 1 .. v_p.lins.COUNT LOOP
                v_rid := g_part(v_p.lins(i).p).id;
                INSERT INTO pedido_detalle (pedido_id, repuesto_id, cantidad, precio_unit)
                VALUES (v_id, v_rid, v_p.lins(i).cant, v_p.lins(i).precio);
            END LOOP;
        END IF;
        g_ped(g_nped) := v_p;
        aud(p_ts, v_p.uid, 'crear_pedido', 'Pedido ' || v_p.num || ' creado (' || v_p.lins.COUNT || ' línea(s))');
        IF v_p.estado = 'cancelado' THEN
            actividad(v_p.uid, v_p.canc);
            aud(v_p.canc, v_p.uid, 'cancelar_pedido', 'Pedido ID ' || v_p.id || ' → estado "cancelado"');
        ELSIF v_p.estado IN ('en_transito', 'recibido') THEN
            actividad(v_p.uid, v_p.trans);
            aud(v_p.trans, v_p.uid, 'estado_pedido', 'Pedido ID ' || v_p.id || ' → estado "en_transito"');
            IF v_p.estado = 'recibido' THEN
                actividad(v_p.uid, v_p.recv);
                aud(v_p.recv, v_p.uid, 'estado_pedido', 'Pedido ID ' || v_p.id || ' → estado "recibido"');
            END IF;
        END IF;
    END crear_pedido;

    -- Calendario de revisión de inventario:
    --   2 = revisión programada (lunes cada tres semanas y un cierre el sábado 31 de octubre)
    --   1 = revisión urgente (jueves): solo lo que está casi agotado
    FUNCTION tipo_revision(p_d DATE) RETURN PLS_INTEGER IS
    BEGIN
        IF dow(p_d) = 0 AND MOD(TRUNC((p_d - DATE '2026-07-13') / 7), 3) = 0 THEN RETURN 2; END IF;
        IF p_d = DATE '2026-10-31' THEN RETURN 2; END IF;
        IF dow(p_d) = 3 THEN RETURN 1; END IF;
        RETURN 0;
    END tipo_revision;

    -- Punto de reorden de un repuesto según el tipo de revisión
    FUNCTION punto_reorden(p_i PLS_INTEGER, p_tipo PLS_INTEGER) RETURN NUMBER IS
        v_pr NUMBER := g_part(p_i).venta;
    BEGIN
        IF p_tipo = 2 THEN
            RETURN CASE WHEN v_pr < 50000 THEN g_part(p_i).minimo + 4
                        WHEN v_pr < 400000 THEN g_part(p_i).minimo + 2 ELSE g_part(p_i).minimo END;
        END IF;
        RETURN FLOOR(g_part(p_i).minimo / 3);
    END punto_reorden;

    -- Agrupa por proveedor lo que está bajo el punto de reorden y genera un pedido por proveedor;
    -- al pedido entran también los demás repuestos de ese proveedor que ya están cerca del mínimo
    PROCEDURE revisar(p_d DATE, p_tipo PLS_INTEGER) IS
        v_lins t_lins; v_ln t_lin; v_pv NUMBER; v_obj NUMBER; v_q NUMBER; v_pack NUMBER; v_pr NUMBER;
        v_t DATE; v_nped PLS_INTEGER := 0; v_trig BOOLEAN; v_cerca NUMBER;
    BEGIN
        v_pv := g_provs.FIRST;
        WHILE v_pv IS NOT NULL LOOP
            v_lins.DELETE; v_trig := FALSE;
            FOR i IN 1 .. g_np LOOP
                IF g_part(i).prov = v_pv AND g_part(i).desde <= p_d AND NOT (p_d >= g_part(i).hold_a AND p_d < g_part(i).hold_b)
                   AND (g_part(i).pend IS NULL OR g_part(i).pend <= p_d) THEN
                    v_pr := g_part(i).venta;
                    v_cerca := CASE WHEN v_pr < 400000 THEN g_part(i).minimo * 2 + 2 ELSE g_part(i).minimo + 1 END;
                    IF g_part(i).stock <= punto_reorden(i, p_tipo) THEN v_trig := TRUE; END IF;
                    IF g_part(i).stock <= GREATEST(v_cerca, punto_reorden(i, p_tipo)) AND p_tipo = 2
                       OR g_part(i).stock <= punto_reorden(i, p_tipo) THEN
                        v_obj := CASE WHEN v_pr < 50000 THEN g_part(i).minimo * 6 + 12
                                      WHEN v_pr < 400000 THEN g_part(i).minimo * 5 + 3 ELSE g_part(i).minimo + 3 END;
                        v_pack := CASE WHEN v_pr < 50000 THEN 6 WHEN v_pr < 400000 THEN 2 ELSE 1 END;
                        v_q := CEIL(GREATEST(v_obj - g_part(i).stock, 1) / v_pack) * v_pack;
                        v_ln.p := i; v_ln.cant := v_q; v_ln.precio := g_part(i).compra; v_ln.dscto := 0;
                        v_lins(v_lins.COUNT + 1) := v_ln;
                    END IF;
                END IF;
            END LOOP;
            IF v_trig AND v_lins.COUNT > 0 THEN
                -- horas crecientes dentro de la jornada: la numeración sigue el orden cronológico
                v_t := TRUNC(p_d) + (8 * 60 + 30 + v_nped * 9 + rint(0, 6)) / 1440;
                v_nped := v_nped + 1;
                crear_pedido(v_t, v_pv, v_lins);
            END IF;
            v_pv := g_provs.NEXT(v_pv);
        END LOOP;
    END revisar;

    PROCEDURE recepciones(p_d DATE) IS
        v_rid NUMBER; v_qty NUMBER;
    BEGIN
        FOR k IN 1 .. g_nped LOOP
            IF g_ped(k).estado = 'recibido' AND g_ped(k).aplicado = 0 AND TRUNC(g_ped(k).recv) = TRUNC(p_d) THEN
                FOR i IN 1 .. g_ped(k).lins.COUNT LOOP
                    IF g_w THEN
                        v_rid := g_part(g_ped(k).lins(i).p).id;
                        v_qty := g_ped(k).lins(i).cant;
                        UPDATE repuestos SET stock = stock + v_qty WHERE id = v_rid;
                    END IF;
                    g_part(g_ped(k).lins(i).p).stock := g_part(g_ped(k).lins(i).p).stock + g_ped(k).lins(i).cant;
                    g_part(g_ped(k).lins(i).p).recibido := g_part(g_ped(k).lins(i).p).recibido + g_ped(k).lins(i).cant;
                END LOOP;
                g_ped(k).aplicado := 1;
            END IF;
        END LOOP;
    END recepciones;

    -- ───────────── Cambios de precio (inflación de costos) ─────────────
    PROCEDURE cargar_eventos IS
        PROCEDURE ev(p VARCHAR2) IS
        BEGIN
            g_nev := g_nev + 1;
            g_ev(g_nev).d := TO_DATE(f(p, 1), 'YYYY-MM-DD');
            g_ev(g_nev).cod := f(p, 2);
            g_ev(g_nev).pct := TO_NUMBER(f(p, 3));
        END ev;
    BEGIN
        g_ev.DELETE; g_nev := 0;
        ev('2026-08-17|MI-P205|6');       ev('2026-08-24|NGK-BKR6E|8');     ev('2026-08-31|HP-1002|6');
        ev('2026-09-07|BRM-FD204|5');     ev('2026-09-14|MAC-48D|6');       ev('2026-09-14|FRAM-PH5796|7');
        ev('2026-09-21|MOB-5W30|7');      ev('2026-09-21|MI-AGR1846|5');    ev('2026-09-28|BSH-0281|5');
        ev('2026-09-28|MOB-15W40|6');     ev('2026-10-05|FG-LF3970|6');     ev('2026-10-05|GAT-T295|6');
        ev('2026-10-13|NGK-BKR5E|8');     ev('2026-10-13|FRP-DOT4|6');
    END cargar_eventos;

    FUNCTION redondeo(p_v NUMBER) RETURN NUMBER IS
    BEGIN
        RETURN CASE WHEN p_v < 50000 THEN ROUND(p_v / 100) * 100 ELSE ROUND(p_v / 500) * 500 END;
    END redondeo;

    PROCEDURE cambios_precio(p_d DATE) IS
        v_i PLS_INTEGER; v_nv NUMBER; v_nc NUMBER; v_ts DATE; v_k PLS_INTEGER := 0; v_hit BOOLEAN; v_rid NUMBER;
    BEGIN
        FOR e IN 1 .. g_nev LOOP
            IF g_ev(e).d = TRUNC(p_d) THEN
                v_k := v_k + 1;
                v_i := g_pcod(g_ev(e).cod);
                v_nv := redondeo(g_part(v_i).venta * (1 + g_ev(e).pct / 100));
                v_nc := redondeo(g_part(v_i).compra * (1 + g_ev(e).pct / 100));
                IF v_nv <= g_part(v_i).venta THEN v_nv := g_part(v_i).venta + 100; END IF;
                v_ts := TRUNC(p_d) + (8 * 60 + 5 + v_k * 3) / 1440;
                actividad(4, v_ts);
                IF g_w THEN
                    v_rid := g_part(v_i).id;
                    UPDATE repuestos SET precio_venta = v_nv, precio_compra = v_nc WHERE id = v_rid;
                END IF;
                -- Fila que habría escrito trg_repuestos_auditoria (sin usuario ni IP)
                aud_sys(v_ts, 'cambio_repuesto',
                        'repuesto_id=' || g_part(v_i).id || ' precio_venta:' || fnum(g_part(v_i).venta) || '->' || fnum(v_nv) ||
                        ' stock:' || g_part(v_i).stock || '->' || g_part(v_i).stock);
                -- trg_repuestos_vence_cotizaciones: las cotizaciones activas con ese repuesto quedan vencidas
                FOR k IN 1 .. g_nco LOOP
                    IF g_cot(k).estado = 'activa' THEN
                        v_hit := FALSE;
                        FOR j IN 1 .. g_cot(k).lins.COUNT LOOP
                            IF g_cot(k).lins(j).p = v_i THEN v_hit := TRUE; END IF;
                        END LOOP;
                        IF v_hit THEN g_cot(k).estado := 'vencida'; g_cot(k).upd := v_ts; END IF;
                    END IF;
                END LOOP;
                g_part(v_i).venta := v_nv;
                g_part(v_i).compra := v_nc;
            END IF;
        END LOOP;
    END cambios_precio;

    -- ───────────── Asistente NLP ─────────────
    PROCEDURE hacer_consulta(p_ts DATE) IS
        TYPE t_ent IS RECORD (tipo VARCHAR2(30), valor VARCHAR2(200));
        TYPE t_ents IS TABLE OF t_ent INDEX BY PLS_INTEGER;
        TYPE t_rec IS RECORD (p PLS_INTEGER, pun NUMBER);
        TYPE t_recs IS TABLE OF t_rec INDEX BY PLS_INTEGER;
        v_e t_ents; v_rc t_recs; v_u PLS_INTEGER; v_sel NUMBER := rnd; v_in VARCHAR2(40);
        v_c PLS_INTEGER; v_p PLS_INTEGER; v_v PLS_INTEGER; v_txt VARCHAR2(600); v_conf NUMBER; v_anio NUMBER;
        v_sus NUMBER := 0; v_util NUMBER; v_id NUMBER; v_t PLS_INTEGER; v_mk VARCHAR2(100); v_md VARCHAR2(100);
        v_n PLS_INTEGER; v_tsc TIMESTAMP; v_uidn NUMBER; v_iid NUMBER; v_cf NUMBER; v_rid NUMBER;

        PROCEDURE ent(p_tipo VARCHAR2, p_val VARCHAR2) IS
        BEGIN
            v_e(v_e.COUNT + 1).tipo := p_tipo; v_e(v_e.COUNT).valor := p_val;
        END ent;

        -- Hasta 3 repuestos compatibles con el vehículo y de la misma categoría; p_first va primero
        PROCEDURE recos(p_veh PLS_INTEGER, p_cat NUMBER, p_first PLS_INTEGER) IS
            v_n PLS_INTEGER := 0; v_dup BOOLEAN;
        BEGIN
            v_rc.DELETE;
            IF p_first > 0 THEN v_n := 1; v_rc(1).p := p_first; END IF;
            FOR v_pass IN 1 .. 2 LOOP
                FOR k IN 1 .. g_ncmp LOOP
                    EXIT WHEN v_n >= 3;
                    IF g_cmp(k).v = p_veh AND g_part(g_cmp(k).p).cat_id = p_cat
                       AND (v_pass = 2 OR g_part(g_cmp(k).p).stock > 0) THEN
                        v_dup := FALSE;
                        FOR j IN 1 .. v_n LOOP IF v_rc(j).p = g_cmp(k).p THEN v_dup := TRUE; END IF; END LOOP;
                        IF NOT v_dup THEN v_n := v_n + 1; v_rc(v_n).p := g_cmp(k).p; END IF;
                    END IF;
                END LOOP;
            END LOOP;
            FOR j IN 1 .. v_n LOOP v_rc(j).pun := ROUND(98.5 - (j - 1) * 7.5 - rnd * 3, 2); END LOOP;
        END recos;
    BEGIN
        v_u := pick_seller(p_ts);
        actividad(v_u, p_ts);
        v_in := CASE WHEN v_sel < 0.34 THEN 'buscar_repuesto' WHEN v_sel < 0.49 THEN 'consultar_precio'
                     WHEN v_sel < 0.63 THEN 'consultar_stock' WHEN v_sel < 0.78 THEN 'consultar_compatibilidad'
                     WHEN v_sel < 0.89 THEN 'recomendar_sustituto' WHEN v_sel < 0.95 THEN 'saludo_despedida'
                     ELSE 'fuera_de_dominio' END;
        v_c := rint(1, g_ncmp);
        v_p := g_cmp(v_c).p; v_v := g_cmp(v_c).v;
        v_anio := g_veh(v_v).d + rint(0, g_veh(v_v).h - g_veh(v_v).d);
        v_mk := g_veh(v_v).marca; v_md := g_veh(v_v).modelo;
        v_t := rint(1, 7);

        IF v_in = 'buscar_repuesto' THEN
            v_conf := 0.86 + rnd * 0.13;
            ent('marca', v_mk); ent('modelo', v_md);
            IF v_t = 1 THEN v_txt := 'necesito ' || g_part(v_p).termino || ' para un ' || v_mk || ' ' || v_md || ' ' || v_anio; ent('anio', v_anio);
            ELSIF v_t = 2 THEN v_txt := 'tienen ' || g_part(v_p).termino || ' para ' || v_mk || ' ' || v_md || '?';
            ELSIF v_t = 3 THEN v_txt := 'busco ' || g_part(v_p).termino || ' de ' || v_mk || ' ' || v_md || ' ' || v_anio; ent('anio', v_anio);
            ELSIF v_t = 4 THEN v_txt := 'me hace falta ' || g_part(v_p).termino || ' para el ' || v_md || ' ' || v_anio; ent('anio', v_anio);
            ELSIF v_t = 5 THEN v_txt := 'qué ' || g_part(v_p).termino || ' le sirve a un ' || v_mk || ' ' || v_md || ' ' || g_veh(v_v).motor;
            ELSIF v_t = 6 THEN v_txt := 'cliente pregunta por ' || g_part(v_p).termino || ' para su ' || v_mk || ' ' || v_md || ' ' || v_anio; ent('anio', v_anio);
            ELSE v_n := rint(2, 4); v_txt := 'necesito ' || v_n || ' ' || g_part(v_p).termino || ' para ' || v_mk || ' ' || v_md; ent('cantidad', v_n);
            END IF;
            IF rnd < 0.5 THEN ent('categoria', g_part(v_p).cat); END IF;
            recos(v_v, g_part(v_p).cat_id, v_p);
        ELSIF v_in = 'consultar_precio' THEN
            v_conf := 0.80 + rnd * 0.17;
            IF v_t <= 3 THEN
                v_txt := 'cuánto cuesta ' || g_part(v_p).termino || ' ' || g_part(v_p).codigo; ent('repuesto', g_part(v_p).codigo);
            ELSIF v_t <= 5 THEN
                v_txt := 'precio de ' || g_part(v_p).termino || ' para ' || v_mk || ' ' || v_md; ent('marca', v_mk); ent('modelo', v_md);
            ELSE
                v_txt := 'a cómo está ' || g_part(v_p).termino || ' ' || g_part(v_p).codigo; ent('repuesto', g_part(v_p).codigo);
            END IF;
            v_rc.DELETE; v_rc(1).p := v_p; v_rc(1).pun := ROUND(94 + rnd * 5, 2);
        ELSIF v_in = 'consultar_stock' THEN
            v_conf := 0.78 + rnd * 0.18;
            IF v_t <= 3 THEN
                v_txt := 'cuántas unidades quedan de ' || g_part(v_p).termino || ' ' || g_part(v_p).codigo; ent('repuesto', g_part(v_p).codigo);
            ELSIF v_t <= 5 THEN
                v_txt := 'hay en stock ' || g_part(v_p).termino || '?'; ent('categoria', g_part(v_p).cat);
            ELSE
                v_txt := 'tienen disponible el ' || g_part(v_p).codigo; ent('repuesto', g_part(v_p).codigo);
            END IF;
            v_rc.DELETE; v_rc(1).p := v_p; v_rc(1).pun := ROUND(93 + rnd * 6, 2);
        ELSIF v_in = 'consultar_compatibilidad' THEN
            v_conf := 0.82 + rnd * 0.16;
            IF rnd < 0.25 THEN   -- pareja que NO es compatible
                v_v := rint(1, g_nv_veh); v_mk := g_veh(v_v).marca; v_md := g_veh(v_v).modelo;
                v_anio := g_veh(v_v).d + rint(0, g_veh(v_v).h - g_veh(v_v).d);
                v_rc.DELETE;
            ELSE
                v_rc.DELETE; v_rc(1).p := v_p; v_rc(1).pun := ROUND(92 + rnd * 7, 2);
            END IF;
            v_txt := CASE WHEN v_t <= 4 THEN 'el ' || g_part(v_p).codigo || ' le sirve a un ' || v_mk || ' ' || v_md || ' ' || v_anio || '?'
                          ELSE 'sirve ' || g_part(v_p).termino || ' ' || g_part(v_p).codigo || ' para ' || v_mk || ' ' || v_md || '?' END;
            ent('repuesto', g_part(v_p).codigo); ent('marca', v_mk); ent('modelo', v_md); ent('anio', v_anio);
        ELSIF v_in = 'recomendar_sustituto' THEN
            v_conf := 0.74 + rnd * 0.20; v_sus := 1;
            IF rnd < 0.45 THEN   -- historia del sistema: lo que está agotado
                v_p := CASE WHEN rnd < 0.5 THEN g_pcod('90915-YZZD4') ELSE g_pcod('FG-FF5320') END;
                FOR k IN 1 .. g_ncmp LOOP IF g_cmp(k).p = v_p THEN v_v := g_cmp(k).v; EXIT; END IF; END LOOP;
                v_mk := g_veh(v_v).marca; v_md := g_veh(v_v).modelo;
                v_anio := g_veh(v_v).d + rint(0, g_veh(v_v).h - g_veh(v_v).d);
            END IF;
            v_txt := CASE WHEN v_t <= 3 THEN 'no hay ' || g_part(v_p).termino || ' original para ' || v_mk || ' ' || v_md || ' ' || v_anio || ', qué otra opción tengo'
                          WHEN v_t <= 5 THEN 'se agotó ' || g_part(v_p).termino || ', ¿qué alternativa le sirve a un ' || v_mk || ' ' || v_md || '?'
                          ELSE 'sustituto de ' || g_part(v_p).codigo || ' para ' || v_mk || ' ' || v_md END;
            ent('marca', v_mk); ent('modelo', v_md); ent('anio', v_anio); ent('repuesto', g_part(v_p).codigo);
            recos(v_v, g_part(v_p).cat_id, 0);
            -- el propio repuesto agotado no es un sustituto de sí mismo
            FOR j IN REVERSE 1 .. v_rc.COUNT LOOP
                IF v_rc(j).p = v_p THEN
                    FOR m IN j .. v_rc.COUNT - 1 LOOP v_rc(m) := v_rc(m + 1); END LOOP;
                    v_rc.DELETE(v_rc.COUNT);
                END IF;
            END LOOP;
        ELSIF v_in = 'saludo_despedida' THEN
            v_conf := 0.90 + rnd * 0.09;
            v_txt := CASE v_t WHEN 1 THEN 'hola buenos días' WHEN 2 THEN 'buenas tardes' WHEN 3 THEN 'gracias, eso es todo'
                              WHEN 4 THEN 'hola, una consulta' WHEN 5 THEN 'muchas gracias, hasta luego' WHEN 6 THEN 'buenas'
                              ELSE 'ok perfecto, gracias' END;
            v_rc.DELETE;
        ELSE
            v_conf := 0.55 + rnd * 0.35;
            v_txt := CASE v_t WHEN 1 THEN 'cuál es el clima en Bogotá hoy' WHEN 2 THEN 'quién ganó el partido de anoche'
                              WHEN 3 THEN 'recomiéndame una película para el fin de semana' WHEN 4 THEN 'cómo preparo arepas de choclo'
                              WHEN 5 THEN 'cuánto está el dólar hoy' WHEN 6 THEN 'dame un chiste'
                              ELSE 'cuál es la capital de Australia' END;
            v_rc.DELETE;
        END IF;
        IF rnd < 0.4 THEN v_txt := LOWER(v_txt); END IF;
        v_util := CASE WHEN v_in IN ('saludo_despedida', 'fuera_de_dominio') THEN NULL
                       ELSE CASE WHEN rnd < 0.72 THEN NULL WHEN rnd < 0.94 THEN 1 ELSE 0 END END;
        IF v_util IS NULL AND v_in NOT IN ('saludo_despedida', 'fuera_de_dominio') AND rnd < 0.28 THEN v_util := 1; END IF;
        g_ncons := g_ncons + 1;
        IF g_w THEN
            v_tsc := ts(p_ts);
            v_uidn := g_usr(v_u).id;
            v_iid := g_int(v_in);
            v_cf := ROUND(v_conf, 4);
            INSERT INTO consultas_asistente (usuario_id, texto_consulta, util, creado_en, intencion_id, confianza)
            VALUES (v_uidn, v_txt, v_util, v_tsc, v_iid, v_cf)
            RETURNING id INTO v_id;
            FOR j IN 1 .. v_e.COUNT LOOP
                INSERT INTO consulta_entidades (consulta_id, tipo, valor) VALUES (v_id, v_e(j).tipo, v_e(j).valor);
            END LOOP;
            FOR j IN 1 .. v_rc.COUNT LOOP
                v_rid := g_part(v_rc(j).p).id;
                INSERT INTO consulta_recomendaciones (consulta_id, repuesto_id, posicion, es_sustituto, puntaje)
                VALUES (v_id, v_rid, j, v_sus, v_rc(j).pun);
            END LOOP;
        END IF;
    END hacer_consulta;

    -- ───────────── Simulación completa ─────────────
    PROCEDURE simular(p_esc BOOLEAN) IS
        v_wtot NUMBER := 0; v_d DATE; v_n PLS_INTEGER; v_ts t_dates; v_conv t_map; v_slot t_map; v_s PLS_INTEGER;
        v_nconv PLS_INTEGER; v_wd t_nmap; v_k PLS_INTEGER; v_cum NUMBER := 0;
    BEGIN
        g_w := p_esc;
        g_seed := 20260714;
        g_nvt := 0; g_ncomp := 0; g_nanu := 0; g_nconv := 0; g_omit := 0; g_convf := 0; g_ncons := 0;
        g_cot.DELETE; g_nco := 0; g_ped.DELETE; g_nped := 0; g_aud.DELETE; g_na := 0; g_vt.DELETE;
        cargar;
        cargar_eventos;
        FOR di IN 0 .. (c_fin - c_ini) LOOP
            v_wd(di) := peso_dia(c_ini + di) * (0.80 + 0.40 * rnd);      -- ruido diario
            v_wtot := v_wtot + v_wd(di);
        END LOOP;
        v_cum := 0;

        FOR di IN 0 .. (c_fin - c_ini) LOOP
            v_d := c_ini + di;
            recepciones(v_d);
            cambios_precio(v_d);
            v_k := tipo_revision(v_d);
            IF v_k > 0 THEN revisar(v_d, v_k); END IF;

            -- Ventas del día: regulares + conversiones de cotizaciones vencidas por plazo de decisión del cliente
            v_cum := v_cum + v_wd(di);
            v_n := n_dia(c_ventas, v_cum - v_wd(di), v_cum, v_wtot);
            IF v_d = c_fin THEN v_n := GREATEST(v_n, 3); END IF;
            v_conv.DELETE; v_nconv := 0;
            FOR k IN 1 .. g_nco LOOP
                IF g_cot(k).estado = 'activa' AND g_cot(k).conv = v_d THEN
                    v_nconv := v_nconv + 1; v_conv(v_nconv) := k;
                END IF;
            END LOOP;
            v_slot.DELETE;
            horas(v_d, v_n + v_nconv, v_ts);
            FOR j IN 1 .. v_nconv LOOP
                LOOP
                    v_s := rint(1, v_n + v_nconv);
                    EXIT WHEN NOT v_slot.EXISTS(v_s);
                END LOOP;
                v_slot(v_s) := v_conv(j);
            END LOOP;
            FOR i IN 1 .. v_n + v_nconv LOOP
                IF v_slot.EXISTS(i) THEN hacer_venta(v_ts(i), v_slot(i)); ELSE hacer_venta(v_ts(i), 0); END IF;
            END LOOP;

            -- Cotizaciones nuevas
            v_n := n_dia(c_cots, v_cum - v_wd(di), v_cum, v_wtot);
            horas(v_d, v_n, v_ts);
            FOR i IN 1 .. v_n LOOP hacer_cotizacion(v_ts(i)); END LOOP;

            -- Consultas al asistente
            v_n := n_dia(c_asist, v_cum - v_wd(di), v_cum, v_wtot);
            horas(v_d, v_n, v_ts);
            FOR i IN 1 .. v_n LOOP hacer_consulta(v_ts(i)); END LOOP;

            -- Respaldos manuales del administrador
            IF v_d IN (DATE '2026-07-31', DATE '2026-08-28', DATE '2026-09-25', DATE '2026-10-16', DATE '2026-10-30') THEN
                actividad(4, v_d + 17.5 / 24);
                aud(v_d + 17.5 / 24, 4, 'crear_backup',
                    'Respaldo manual disparado: electrisys_backup_' || TO_CHAR(v_d + 22.5 / 24, 'YYYYMMDD_HH24MISS'));
            END IF;

            -- Consultas esporádicas de administración / dueño sin otra operación
            IF dow(v_d) < 6 THEN
                IF g_usr(4).act IS NULL AND rnd < 0.15 THEN actividad(4, v_d + (9 + rnd * 7) / 24); END IF;
                IF g_usr(5).act IS NULL AND rnd < (CASE WHEN TO_NUMBER(TO_CHAR(v_d, 'DD')) >= 28 THEN 0.55 ELSE 0.10 END) THEN
                    actividad(5, v_d + (9 + rnd * 7) / 24);
                END IF;
            END IF;

            -- Logins del día: uno por usuario con actividad (el JWT dura 8 horas)
            FOR u IN 1 .. 5 LOOP
                IF g_usr(u).act IS NOT NULL THEN
                    aud(GREATEST(g_usr(u).act - rint(3, 40) / 1440, v_d + 6.5 / 24), u, 'login',
                        'Login exitoso desde ' || g_usr(u).ip);
                    g_usr(u).act := NULL; g_usr(u).ip := NULL;
                END IF;
            END LOOP;
        END LOOP;
    END simular;

    -- ───────────── Cierre: cotizaciones, auditoría, intentos de login ─────────────
    PROCEDURE cerrar IS
        v_id NUMBER; v_k PLS_INTEGER; v_cid NUMBER; v_n PLS_INTEGER; v_tc TIMESTAMP; v_tu TIMESTAMP;
        v_uid NUMBER; v_rid NUMBER; v_ip VARCHAR2(45); v_ta TIMESTAMP; v_nn PLS_INTEGER;
    BEGIN
        -- Cotizaciones (ya con su estado final)
        FOR k IN 1 .. g_nco LOOP
            v_cid := CASE WHEN g_cot(k).cli > 0 THEN g_cli(g_cot(k).cli).id END;
            v_tc := ts(g_cot(k).fecha);
            v_tu := CASE WHEN g_cot(k).upd IS NOT NULL THEN ts(g_cot(k).upd) END;
            v_uid := g_usr(g_cot(k).uid).id;
            INSERT INTO cotizaciones (numero, cliente_id, usuario_id, descuento_pct, iva_pct, estado, vence_en,
                                      notas, creado_en, updated_at)
            VALUES (g_cot(k).num, v_cid, v_uid, g_cot(k).dpct, 19, g_cot(k).estado,
                    g_cot(k).vence, g_cot(k).notas, v_tc, v_tu)
            RETURNING id INTO v_id;
            FOR j IN 1 .. g_cot(k).lins.COUNT LOOP
                v_rid := g_part(g_cot(k).lins(j).p).id;
                INSERT INTO detalle_cotizaciones (cotizacion_id, repuesto_id, cantidad, precio_unit, descuento)
                VALUES (v_id, v_rid, g_cot(k).lins(j).cant, g_cot(k).lins(j).precio, g_cot(k).lins(j).dscto);
            END LOOP;
        END LOOP;

        -- Intentos de login fallidos (rate limiting)
        FOR r IN (SELECT column_value AS l FROM TABLE(sys.odcivarchar2list(
            '2026-07-22 07:58|191.104.38.206|2', '2026-08-03 08:41|181.63.20.115|1', '2026-08-19 08:05|191.104.38.206|3',
            '2026-09-02 18:22|186.84.91.7|1',    '2026-09-15 07:49|191.104.38.206|2', '2026-09-29 12:30|201.184.52.88|4',
            '2026-10-08 08:10|191.104.38.206|1', '2026-10-20 19:45|45.162.33.71|3',   '2026-10-27 09:03|181.52.147.9|2'))) LOOP
            v_ip := f(r.l, 2);
            v_nn := TO_NUMBER(f(r.l, 3));
            FOR j IN 1 .. v_nn LOOP
                v_ta := ts(TO_DATE(f(r.l, 1), 'YYYY-MM-DD HH24:MI') + (j - 1) * (25 + 7 * j) / 86400);
                INSERT INTO login_attempts (ip, created_at) VALUES (v_ip, v_ta);
            END LOOP;
        END LOOP;

        -- Auditoría: se descartan las filas que escribió el trigger durante esta carga
        -- (una por cada cambio de stock) y se insertan los eventos propios en orden cronológico
        DELETE FROM audit_log WHERE accion = 'cambio_repuesto' AND id > :b_aud;
        v_k := g_aud.FIRST;
        WHILE v_k IS NOT NULL LOOP
            v_ta := ts(g_aud(v_k).ts);
            INSERT INTO audit_log (usuario_id, accion, detalle, ip, created_at)
            VALUES (g_aud(v_k).uid, g_aud(v_k).accion, g_aud(v_k).det, g_aud(v_k).ip, v_ta);
            v_k := g_aud.NEXT(v_k);
        END LOOP;
    END cerrar;

    -- ───────────── Verificación ─────────────
    PROCEDURE pl(p VARCHAR2) IS BEGIN DBMS_OUTPUT.PUT_LINE(p); END pl;

    PROCEDURE verificar IS
        v_n NUMBER; v_m NUMBER; v_x NUMBER; v_rec NUMBER; v_ven NUMBER; v_db NUMBER; v_bad NUMBER := 0;
        v_tot NUMBER; v_id NUMBER; v_cnt VARCHAR2(4000);
        FUNCTION base(p_t VARCHAR2) RETURN NUMBER IS
            v_s PLS_INTEGER := INSTR(:b_cnt, ';' || p_t || '=');
            v_e PLS_INTEGER;
        BEGIN
            v_s := v_s + LENGTH(p_t) + 2;
            v_e := INSTR(:b_cnt, ';', v_s);
            RETURN TO_NUMBER(SUBSTR(:b_cnt, v_s, v_e - v_s));
        END base;
    BEGIN
        pl('');
        pl('================ RESUMEN POR TABLA (total / nuevas) ================');
        FOR t IN (SELECT column_value AS tn FROM TABLE(sys.odcivarchar2list(
                    'USUARIOS','PROVEEDORES','MARCAS','MODELOS','VEHICULOS','REPUESTOS','REPUESTO_COMPATIBILIDAD',
                    'CLIENTES','VENTAS','DETALLE_VENTAS','COTIZACIONES','DETALLE_COTIZACIONES','PEDIDOS',
                    'PEDIDO_DETALLE','AUDIT_LOG','LOGIN_ATTEMPTS','CONSULTAS_ASISTENTE','CONSULTA_ENTIDADES',
                    'CONSULTA_RECOMENDACIONES'))) LOOP
            EXECUTE IMMEDIATE 'SELECT COUNT(*) FROM ' || t.tn INTO v_n;
            pl(RPAD(t.tn, 28) || LPAD(v_n, 7) || '  (+' || (v_n - base(t.tn)) || ')');
        END LOOP;

        pl('');
        pl('Ventas por estado:');
        FOR r IN (SELECT estado, COUNT(*) AS n FROM ventas GROUP BY estado ORDER BY 1) LOOP
            pl('   ' || RPAD(r.estado, 12) || r.n);
        END LOOP;
        pl('Ventas por método de pago (completadas):');
        FOR r IN (SELECT metodo_pago, COUNT(*) AS n FROM ventas WHERE estado = 'completada' GROUP BY metodo_pago ORDER BY 1) LOOP
            pl('   ' || RPAD(r.metodo_pago, 14) || r.n);
        END LOOP;
        pl('Ventas completadas por vendedor:');
        FOR r IN (SELECT u.nombre, COUNT(*) AS n FROM ventas v JOIN usuarios u ON u.id = v.usuario_id
                   WHERE v.estado = 'completada' GROUP BY u.nombre ORDER BY 2 DESC) LOOP
            pl('   ' || RPAD(r.nombre, 24) || r.n);
        END LOOP;
        SELECT COUNT(*), COUNT(cliente_id) INTO v_n, v_m FROM ventas WHERE estado = 'completada';
        pl('Ventas completadas con cliente registrado: ' || v_m || ' de ' || v_n || ' (' || ROUND(100 * v_m / v_n) || ' %)');
        pl('Ventas por mes (completadas): cantidad / ingresos con IVA');
        FOR r IN (SELECT TO_CHAR(fn_fecha_local(v.creado_en), 'YYYY-MM') AS mes, COUNT(*) AS n, SUM(t.total) AS ing
                    FROM ventas v JOIN vw_totales_documento t ON t.tipo = 'venta' AND t.documento_id = v.id
                   WHERE v.estado = 'completada' GROUP BY TO_CHAR(fn_fecha_local(v.creado_en), 'YYYY-MM') ORDER BY 1) LOOP
            pl('   ' || r.mes || '  ' || LPAD(r.n, 4) || '  ' || LPAD(TO_CHAR(r.ing, 'FM999G999G999G990'), 14));
        END LOOP;
        pl('Ventas completadas por día de la semana (0 = lunes ... 6 = domingo):');
        FOR r IN (SELECT MOD(TRUNC(fn_fecha_local(creado_en)) - DATE '2026-01-05', 7) AS d, COUNT(*) AS n
                    FROM ventas WHERE estado = 'completada' GROUP BY MOD(TRUNC(fn_fecha_local(creado_en)) - DATE '2026-01-05', 7) ORDER BY 1) LOOP
            pl('   ' || r.d || '  ' || r.n);
        END LOOP;
        pl('Cotizaciones por estado:');
        FOR r IN (SELECT estado, COUNT(*) AS n FROM cotizaciones GROUP BY estado ORDER BY 1) LOOP
            pl('   ' || RPAD(r.estado, 12) || r.n);
        END LOOP;
        pl('Pedidos por estado:');
        FOR r IN (SELECT estado, COUNT(*) AS n FROM pedidos GROUP BY estado ORDER BY 1) LOOP
            pl('   ' || RPAD(r.estado, 12) || r.n);
        END LOOP;
        pl('Auditoría por acción:');
        FOR r IN (SELECT accion, COUNT(*) AS n FROM audit_log GROUP BY accion ORDER BY 2 DESC) LOOP
            pl('   ' || RPAD(r.accion, 18) || r.n);
        END LOOP;
        pl('Consultas del asistente por intención:');
        FOR r IN (SELECT i.nombre, COUNT(*) AS n FROM consultas_asistente c JOIN nlp_intenciones i ON i.id = c.intencion_id
                   GROUP BY i.nombre ORDER BY 2 DESC) LOOP
            pl('   ' || RPAD(r.nombre, 26) || r.n);
        END LOOP;
        pl('Repuestos con stock bajo o en cero (stock <= mínimo):');
        FOR r IN (SELECT codigo, stock, stock_minimo FROM vw_repuestos_stock_bajo ORDER BY stock, codigo) LOOP
            pl('   ' || RPAD(r.codigo, 16) || 'stock ' || LPAD(r.stock, 4) || '  mínimo ' || r.stock_minimo);
        END LOOP;
        pl('Generación: ventas omitidas por falta de stock = ' || g_omit || '; conversiones de cotización fallidas = '
           || g_convf || '; ventas desde cotización = ' || g_nconv);

        pl('');
        pl('================ INVARIANTES (todos deben dar OK) ================');
        -- 1. Sin stock negativo
        SELECT COUNT(*) INTO v_n FROM repuestos WHERE stock < 0;
        pl(CASE WHEN v_n = 0 THEN 'OK   ' ELSE 'FALLA' END || ' stock negativo: ' || v_n || ' repuestos');
        -- 2. Toda venta tiene al menos una línea
        SELECT COUNT(*) INTO v_n FROM ventas v WHERE NOT EXISTS (SELECT 1 FROM detalle_ventas d WHERE d.venta_id = v.id);
        pl(CASE WHEN v_n = 0 THEN 'OK   ' ELSE 'FALLA' END || ' ventas sin líneas: ' || v_n);
        SELECT COUNT(*) INTO v_n FROM cotizaciones c WHERE c.id > :b_cot
           AND NOT EXISTS (SELECT 1 FROM detalle_cotizaciones d WHERE d.cotizacion_id = c.id);
        pl(CASE WHEN v_n = 0 THEN 'OK   ' ELSE 'FALLA' END || ' cotizaciones nuevas sin líneas: ' || v_n);
        SELECT COUNT(*) INTO v_n FROM pedidos p WHERE p.id > :b_ped
           AND NOT EXISTS (SELECT 1 FROM pedido_detalle d WHERE d.pedido_id = p.id);
        pl(CASE WHEN v_n = 0 THEN 'OK   ' ELSE 'FALLA' END || ' pedidos nuevos sin líneas: ' || v_n);
        -- 3. Total de cada venta = suma de líneas + IVA 19 % (según vw_totales_documento) y = lo auditado
        v_bad := 0; v_id := g_vt.FIRST;
        WHILE v_id IS NOT NULL LOOP
            SELECT t.total INTO v_tot FROM vw_totales_documento t WHERE t.tipo = 'venta' AND t.documento_id = v_id;
            IF ABS(v_tot - g_vt(v_id)) > 0.005 THEN v_bad := v_bad + 1; END IF;
            v_id := g_vt.NEXT(v_id);
        END LOOP;
        pl(CASE WHEN v_bad = 0 THEN 'OK   ' ELSE 'FALLA' END || ' ventas cuyo total de la vista difiere del esperado: ' || v_bad
           || ' de ' || g_vt.COUNT);
        SELECT COUNT(*) INTO v_n FROM (
            SELECT v.id, v.descuento_pct, v.iva_pct, t.total,
                   (SELECT SUM(d.cantidad * d.precio_unit - d.descuento) FROM detalle_ventas d WHERE d.venta_id = v.id) AS sub
              FROM ventas v JOIN vw_totales_documento t ON t.tipo = 'venta' AND t.documento_id = v.id
             WHERE v.id > :b_ven)
         WHERE total <> sub - ROUND(sub * descuento_pct / 100, 2)
                         + ROUND((sub - ROUND(sub * descuento_pct / 100, 2)) * iva_pct / 100, 2);
        pl(CASE WHEN v_n = 0 THEN 'OK   ' ELSE 'FALLA' END
           || ' ventas con total <> suma de líneas - descuento + IVA 19 %: ' || v_n);
        -- 4. Stock calculado = stock almacenado
        v_bad := 0;
        FOR i IN 1 .. g_np LOOP
            SELECT NVL(SUM(pd.cantidad), 0) INTO v_rec FROM pedido_detalle pd JOIN pedidos p ON p.id = pd.pedido_id
             WHERE p.estado = 'recibido' AND pd.repuesto_id = g_part(i).id;
            SELECT NVL(SUM(d.cantidad), 0) INTO v_ven FROM detalle_ventas d JOIN ventas v ON v.id = d.venta_id
             WHERE v.estado = 'completada' AND d.repuesto_id = g_part(i).id;
            SELECT stock INTO v_db FROM repuestos WHERE id = g_part(i).id;
            IF g_part(i).stock0 + v_rec - v_ven <> v_db OR v_db <> g_part(i).stock THEN
                v_bad := v_bad + 1;
                pl('      descuadre ' || g_part(i).codigo || ': inicial ' || g_part(i).stock0 || ' + recibido ' || v_rec
                   || ' - vendido ' || v_ven || ' = ' || (g_part(i).stock0 + v_rec - v_ven) || ' ; base ' || v_db
                   || ' ; memoria ' || g_part(i).stock);
            END IF;
        END LOOP;
        pl(CASE WHEN v_bad = 0 THEN 'OK   ' ELSE 'FALLA' END || ' repuestos con stock almacenado <> inicial + recibido - vendido: '
           || v_bad || ' de ' || g_np);
        -- 5. Fechas dentro de 2026-07-14 .. 2026-11-01 (hora local), salvo los 3 registros de prueba conservados
        SELECT COUNT(*) INTO v_n FROM ventas WHERE id > :b_ven
           AND (fn_fecha_local(creado_en) < DATE '2026-07-14' OR fn_fecha_local(creado_en) >= DATE '2026-11-02');
        pl(CASE WHEN v_n = 0 THEN 'OK   ' ELSE 'FALLA' END || ' ventas fuera del rango de fechas: ' || v_n);
        SELECT COUNT(*) INTO v_n FROM pedidos WHERE id > :b_ped
           AND (fn_fecha_local(creado_en) < DATE '2026-07-14' OR fn_fecha_local(creado_en) >= DATE '2026-11-02');
        pl(CASE WHEN v_n = 0 THEN 'OK   ' ELSE 'FALLA' END || ' pedidos fuera del rango de fechas: ' || v_n);
        SELECT COUNT(*) INTO v_n FROM cotizaciones WHERE id > :b_cot
           AND (fn_fecha_local(creado_en) < DATE '2026-07-14' OR fn_fecha_local(creado_en) >= DATE '2026-11-02');
        pl(CASE WHEN v_n = 0 THEN 'OK   ' ELSE 'FALLA' END || ' cotizaciones fuera del rango de fechas: ' || v_n);
        SELECT COUNT(*) INTO v_n FROM audit_log WHERE id > :b_aud
           AND (fn_fecha_local(created_at) < DATE '2026-07-14' OR fn_fecha_local(created_at) >= DATE '2026-11-02');
        pl(CASE WHEN v_n = 0 THEN 'OK   ' ELSE 'FALLA' END || ' eventos de auditoría fuera del rango de fechas: ' || v_n);
        SELECT COUNT(*) INTO v_n FROM consultas_asistente
         WHERE fn_fecha_local(creado_en) < DATE '2026-07-14' OR fn_fecha_local(creado_en) >= DATE '2026-11-02';
        pl(CASE WHEN v_n = 0 THEN 'OK   ' ELSE 'FALLA' END || ' consultas del asistente fuera del rango de fechas: ' || v_n);
        -- 6. Numeración única y cronológica (contigua 1..N)
        SELECT COUNT(*) INTO v_n FROM (
            SELECT numero, LAG(numero) OVER (ORDER BY creado_en, id) AS ant FROM ventas) WHERE ant IS NOT NULL AND numero <= ant;
        SELECT COUNT(*), COUNT(DISTINCT numero), MAX(TO_NUMBER(SUBSTR(numero, 9))) INTO v_m, v_x, v_tot FROM ventas;
        pl(CASE WHEN v_n = 0 AND v_m = v_x AND v_m = v_tot THEN 'OK   ' ELSE 'FALLA' END
           || ' numeración de ventas: ' || v_m || ' filas, ' || v_x || ' números distintos, máximo ' || v_tot
           || ', desordenadas: ' || v_n);
        SELECT COUNT(*) INTO v_n FROM (
            SELECT numero, LAG(numero) OVER (ORDER BY creado_en, id) AS ant FROM pedidos) WHERE ant IS NOT NULL AND numero <= ant;
        SELECT COUNT(*), COUNT(DISTINCT numero), MAX(TO_NUMBER(SUBSTR(numero, 5))) INTO v_m, v_x, v_tot FROM pedidos;
        pl(CASE WHEN v_n = 0 AND v_m = v_x AND v_m = v_tot THEN 'OK   ' ELSE 'FALLA' END
           || ' numeración de pedidos: ' || v_m || ' filas, ' || v_x || ' números distintos, máximo ' || v_tot
           || ', desordenados: ' || v_n);
        -- 7. Sin duplicados de códigos, correos ni identificaciones
        SELECT COUNT(*) INTO v_n FROM (SELECT codigo FROM repuestos GROUP BY codigo HAVING COUNT(*) > 1);
        pl(CASE WHEN v_n = 0 THEN 'OK   ' ELSE 'FALLA' END || ' códigos de repuesto duplicados: ' || v_n);
        SELECT COUNT(*) INTO v_n FROM (SELECT LOWER(email) FROM usuarios GROUP BY LOWER(email) HAVING COUNT(*) > 1);
        pl(CASE WHEN v_n = 0 THEN 'OK   ' ELSE 'FALLA' END || ' correos de usuario duplicados: ' || v_n);
        SELECT COUNT(*) INTO v_n FROM (SELECT identificacion FROM clientes GROUP BY identificacion HAVING COUNT(*) > 1);
        pl(CASE WHEN v_n = 0 THEN 'OK   ' ELSE 'FALLA' END || ' identificaciones de cliente duplicadas: ' || v_n);
        SELECT COUNT(*) INTO v_n FROM (SELECT numero FROM cotizaciones GROUP BY numero HAVING COUNT(*) > 1);
        pl(CASE WHEN v_n = 0 THEN 'OK   ' ELSE 'FALLA' END || ' números de cotización duplicados: ' || v_n);
        -- 8. Auditoría limpia: solo los cambios de precio intencionales como cambio_repuesto
        SELECT COUNT(*) INTO v_n FROM audit_log WHERE accion = 'cambio_repuesto' AND id > :b_aud;
        pl(CASE WHEN v_n = g_nev THEN 'OK   ' ELSE 'FALLA' END || ' filas cambio_repuesto nuevas: ' || v_n
           || ' (cambios de precio programados: ' || g_nev || ')');
        -- 9. Márgenes de los repuestos nuevos y existentes
        SELECT COUNT(*) INTO v_n FROM repuestos
         WHERE id > :b_rep AND (precio_venta < precio_compra * 1.25 - 1 OR precio_venta > precio_compra * 1.60 + 1);
        pl(CASE WHEN v_n = 0 THEN 'OK   ' ELSE 'FALLA' END || ' repuestos nuevos con margen fuera de 25-60 %: ' || v_n);
    END verificar;

BEGIN
    -- Paso A: solo en memoria, para conocer cuántas ventas y pedidos habrá
    simular(FALSE);
    :n_ven := g_nvt;
    :n_ped := g_nped;
    DBMS_OUTPUT.PUT_LINE('Paso A (memoria): ' || g_nvt || ' ventas (' || g_ncomp || ' completadas, ' || g_nanu
        || ' anuladas), ' || g_nco || ' cotizaciones, ' || g_nped || ' pedidos, ' || g_ncons || ' consultas.');

    -- Registros de prueba conservados: pasan al final de la numeración (son los más recientes).
    -- Solo se cambia la columna numero (los triggers BEFORE UPDATE tocan updated_at/version).
    UPDATE ventas SET numero = 'VT-2026-' || LPAD(:n_ven + 1, 6, '0') WHERE numero = 'VT-2026-000001';
    DBMS_OUTPUT.PUT_LINE('Venta de prueba renumerada: VT-2026-000001 -> VT-2026-' || LPAD(:n_ven + 1, 6, '0')
        || ' (' || SQL%ROWCOUNT || ' fila)');
    UPDATE pedidos SET numero = 'PED-' || LPAD(:n_ped + 1, 6, '0') WHERE numero = 'PED-000001';
    DBMS_OUTPUT.PUT_LINE('Pedido de prueba renumerado: PED-000001 -> PED-' || LPAD(:n_ped + 1, 6, '0')
        || ' (' || SQL%ROWCOUNT || ' fila)');

    -- Paso B: escribe en la base en orden cronológico
    simular(TRUE);
    cerrar;
    DBMS_OUTPUT.PUT_LINE('Paso B (escritura): ' || g_nvt || ' ventas generadas.');
    verificar;
END;
/

-- ============================================================
-- 4. CIERRE: COMMIT o ROLLBACK según el argumento
-- ============================================================
DECLARE
    v_cur NUMBER;
    v_obj NUMBER;
BEGIN
    IF :modo_ok = 'COMMIT' THEN
        -- Las secuencias de numeración no se revierten con un ROLLBACK, por eso solo
        -- se avanzan aquí: el próximo registro de la aplicación seguirá a los datos de demo.
        v_obj := :n_ven + 1;
        SELECT seq_numero_venta.NEXTVAL INTO v_cur FROM dual;
        WHILE v_cur < v_obj LOOP
            SELECT seq_numero_venta.NEXTVAL INTO v_cur FROM dual;
        END LOOP;
        v_obj := :n_ped + 1;
        SELECT seq_numero_pedido.NEXTVAL INTO v_cur FROM dual;
        WHILE v_cur < v_obj LOOP
            SELECT seq_numero_pedido.NEXTVAL INTO v_cur FROM dual;
        END LOOP;
        COMMIT;
        DBMS_OUTPUT.PUT_LINE('MODO COMMIT: datos de demostración confirmados; secuencias avanzadas.');
    ELSE
        ROLLBACK;
        DBMS_OUTPUT.PUT_LINE('MODO ROLLBACK: ensayo terminado, no se guardó nada (las secuencias no se avanzaron).');
    END IF;
END;
/

-- Restaura los ajustes de SQL*Plus que cambió este script
SET DEFINE '&'
SET FEEDBACK ON

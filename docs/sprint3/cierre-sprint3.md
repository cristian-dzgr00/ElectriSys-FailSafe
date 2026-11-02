# Sprint 3 — Cierre de pendientes (Base de datos Oracle)

Fecha: 2026-10-03. Verificado en Oracle 23ai Free local (PDB `FREEPDB1`), sobre un esquema temporal
`ELECTRISYS_SC` que se creó y se eliminó al terminar; el esquema real `ELECTRISYS` no se modificó.

## Resultado por tarjeta

| Tarjeta | Estado | Evidencia |
|---|---|---|
| 3.13 Probar triggers | Hecho | `evidencia_triggers.txt`: 4 de 4 pruebas pasan |
| 3.12 Planes con volumen | Hecho | `evidencia_100k.txt`: 100 000 ventas, plan FULL vs índice en 4 consultas |
| 3.14 Tablas del asistente | Hecho | 14 carga 58 833 errores y 112 avisos; el NLP lee de Oracle con respaldo CSV |
| 3.16 Scripts re-ejecutables | Hecho (09 verificado dos veces en la BD real; 01 no se ejecutó) | 09 conserva perfil y usuarios existentes. 01 usa una ruta Linux de datafile, solo corre en el contenedor |
| 3.8 Vistas | Hecho | 07 + `vw_totales_documento`: 0 documentos descuadrados |
| 3.1 / 3.2 Normalización | Fase 1 hecha; fase 2 pendiente | 25 tablas, 0 vehículos sin `modelo_id`; la fase 2 exige cambiar el backend PHP |

## Errores reales encontrados y corregidos

1. **Orden del cargador.** `07_vistas.sql` corría antes de `10_pedidos.sql`, pero `vw_totales_documento` lee
   `pedido_detalle`, así que fallaba con ORA-00942. Ahora el orden es 10, 11, 07, 08. Además faltaba
   `11_cotizaciones_estados.sql` en el cargador.
2. **Seed de `posibles_errores` cargaba 0 filas.** `INSERT ALL` evalúa la columna IDENTITY una sola vez por
   sentencia, por lo que todas las filas recibían el mismo id (ORA-00001). Cada fila trae ahora su id
   explícito y al final el generador se reposiciona con `START WITH LIMIT VALUE` (siguiente id: 58 834).
3. **Prueba de planes no mostraba los planes.** En SQL*Plus, un `PROMPT` que termina en `-` continúa en la
   línea siguiente y se tragaba el `EXPLAIN PLAN`. Se quitaron los guiones finales.
4. **Vista inválida tras el cargado.** `vw_repuestos_compatibles` quedaba INVALID por el orden de creación.
   El script 15 termina con `DBMS_UTILITY.COMPILE_SCHEMA`; resultado: 0 objetos inválidos.

## Hallazgos de rendimiento (100 000 ventas)

| Consulta | Costo FULL | Costo con índice |
|---|---|---|
| Ventas de un cliente | 298 | 2 |
| Detalle de una venta | 157 | 3 |
| Búsqueda en `posibles_errores` | 184 | 2 |
| Ventas de los últimos 7 días | 435 | 970 |

La consulta de 7 días devuelve unas 960 filas: con ese volumen el optimizador prefiere el recorrido completo,
porque el acceso por índice cuesta más. Los índices que importan son los de búsqueda puntual.

## Qué sigue pendiente

- **Fase 2 de 3FN** (quitar `vehiculos.marca/modelo` y las columnas derivadas de los encabezados): requiere
  cambiar `VehiculoModel` y las rutas de ventas y cotizaciones del backend PHP.
- **Script 01** no se pudo probar fuera del contenedor (ruta `/opt/oracle/oradata/...`).
- Probar el cargador completo desde un contenedor vacío (criterio de terminado del sprint).

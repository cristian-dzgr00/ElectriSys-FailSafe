# Datos de demostración (`oracle/17_datos_demo.sql`)

Carga en un solo paso unos 3,5 meses de operación de **Electritorres** (2026-07-14 a 2026-11-01) para que todas las pantallas de ElectriSys tengan datos: Dashboard, Repuestos, Proveedores, Pedidos, Ventas, Cotizaciones, Clientes, Reportes, Usuarios y Auditoría.

## Cómo ejecutarlo

Conectado como `ELECTRISYS`, desde la carpeta `oracle/`:

```sql
@17_datos_demo.sql ROLLBACK   -- ensayo: carga todo, imprime el resumen y deshace
@17_datos_demo.sql COMMIT     -- carga definitiva
```

- Sin argumento, o con cualquier valor distinto de `COMMIT`, se comporta como `ROLLBACK`.
- Es **una sola transacción** y no ejecuta DDL. Cualquier error hace `ROLLBACK` y sale con código de fallo.
- El script imprime, antes de confirmar o deshacer, el conteo por tabla y los invariantes (todos deben decir `OK`).
- Con `COMMIT` también avanza `SEQ_NUMERO_VENTA` y `SEQ_NUMERO_PEDIDO` para que la próxima venta o pedido creado desde la app siga a los datos de demo. Las secuencias no se revierten con un `ROLLBACK`, por eso con ese modo no se tocan.
- Cada ensayo consume valores de las columnas identidad (los ids de las filas nuevas no empiezan en el siguiente al último existente). Es inocuo.

## Guarda de idempotencia

Si ya existe el usuario `dueno@electrisys.com` el script aborta con `ORA-20900` y un mensaje claro, sin cambiar nada. Para recargar hay que restaurar la base antes.

## Qué genera (aproximado; el resumen del script da los números exactos)

| Tabla | Nuevas | Notas |
|---|---|---|
| USUARIOS | 3 | `dueno@electrisys.com` (Andrés Felipe Torres), `laura.gomez@` y `camilo.rojas@` (vendedores). Reutilizan el hash de `admin@electrisys.com`; no se escribe ninguna clave. |
| PROVEEDORES | 5 | 13 → 18 |
| MARCAS / MODELOS / VEHICULOS | 1 / 9 / 9 | Mitsubishi, Onix, Sail, Sandero, Picanto, L200, Ranger, Yaris, TL90, MF 290 |
| REPUESTOS | 57 | 23 → 80, en las 12 categorías existentes |
| REPUESTO_COMPATIBILIDAD | 255 | 42 → 297 |
| CLIENTES | 33 | personas, talleres, ferreterías, empresas y fincas/cooperativas agro |
| VENTAS / DETALLE_VENTAS | 336 / 722 | 325 completadas y 11 anuladas; solo se cuentan las nuevas |
| COTIZACIONES / DETALLE | 45 / 113 | `activa`, `vencida` y `realizada` (13 convertidas en venta) |
| PEDIDOS / PEDIDO_DETALLE | 40 / 83 | la mayoría `recibido`; algunos `en_transito`, `solicitado` y 2 `cancelado` |
| AUDIT_LOG | ~790 | logins, `crear_venta`, `anular_venta`, pedidos, `crear_backup`, cambios de precio |
| LOGIN_ATTEMPTS | 19 | intentos fallidos repartidos en el periodo |
| CONSULTAS_ASISTENTE / ENTIDADES / RECOMENDACIONES | 150 / ~350 / ~180 | las 7 intenciones de `NLP_INTENCIONES`, con `util` en algunas |

Comportamiento del negocio simulado: más ventas de lunes a sábado (sábado más fuerte, domingo casi nulo), crecimiento de ~30 % de agosto a octubre, picos de fin de mes y quincena, festivos con poca venta, IVA 19 %, ~30 % de las ventas con cliente registrado y el resto a "Cliente general", pagos en efectivo, tarjeta y transferencia, y precios de venta que suben en algunos repuestos a lo largo del periodo.

## Modelo de stock

`stock final = stock inicial + pedidos recibidos − ventas completadas`.

- **Stock inicial**: para los 23 repuestos que ya existían es el stock que tienen al correr el script; para los nuevos es el valor con que se insertan (columna "stock inicial" de la lista del script).
- Los pedidos `recibido` suman stock en la fecha de recepción; los `solicitado`, `en_transito` y `cancelado` no lo tocan. Las ventas anuladas no consumen stock (se descuenta y se repone).
- Los pedidos salen de una política de reposición simple: revisión cada tres semanas más una revisión urgente los jueves para lo casi agotado, agrupada por proveedor. Todo se procesa en orden cronológico, así que no hay stock negativo en ningún momento.
- `90915-YZZD4` y `FG-FF5320` siguen en cero con un pedido en camino (alimentan al asistente de sustitutos). Quedan además otros repuestos por debajo del mínimo para la alerta "Stock bajo" del Dashboard.

## Cómo se evitan los efectos de los triggers

No se desactiva ningún trigger. Las filas se insertan en su estado final (venta `anulada`, pedido `recibido`, cotización `vencida`…) para que los `BEFORE UPDATE` no estampen `SYSTIMESTAMP` en `updated_at`/`recibido_en`. El trigger de auditoría de repuestos escribe una fila `cambio_repuesto` por cada movimiento de stock; el script borra solo las suyas (`id` mayor que el último previo) y las reemplaza por los eventos que la aplicación realmente produciría.

## Registros de prueba conservados

La venta anulada `VT-2026-000001` y el pedido cancelado `PED-000001` pasan al final de la numeración (son los más recientes) con un `UPDATE` de la columna `numero`; los triggers `BEFORE UPDATE` también modifican `updated_at` y `version` (ventas) de esas filas. La cotización `COT-20261101-82D089` y los usuarios existentes no se tocan.

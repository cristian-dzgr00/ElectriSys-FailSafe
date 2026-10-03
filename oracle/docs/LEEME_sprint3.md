# Sprint 3 — Base de datos Oracle (ElectriSys)

**ADVERTENCIA: estos scripts NO se han ejecutado contra un Oracle real.** Pruébalos primero en una copia de la base (o un esquema vacío). Todos están escritos para poder re-ejecutarse sin error.

## Contenido
| Archivo | Qué hace | Tarjeta |
|---|---|---|
| `07_vistas.sql` | Reemplaza el 07 original: añade `vw_totales_documento` (ventas, cotizaciones y pedidos: suma de líneas vs. total guardado) | 3.8 |
| `09_usuarios_demo_sysdba.sql` | Reemplaza el 09 original: re-ejecutable (revisa perfil/usuarios antes de crear). Ejecutar como SYSDBA | 3.16 |
| `15_normalizacion_3fn.sql` | Fase 1 de 3FN: MARCAS, MODELOS, `vehiculos.modelo_id`, trigger, vista `vw_vehiculos`, CONSULTA_ENTIDADES, CONSULTA_RECOMENDACIONES, permisos y chequeos finales | 3.1 / 3.2 |
| `12_nlp_dataset.sql`, `13_posibles_errores.sql`, `14_seed_posibles_errores.sql` | Tablas del asistente (copias de oracle_nlp) | 3.14 |
| `cargar_esquema.sh` | Cargador completo: el original + 12, 13, 14 y 15 en orden. Reemplaza el de `oracle/` | 3.11 |
| `pruebas/16_prueba_triggers.sql` | Prueba autoverificable (PASS/FAIL, termina con ROLLBACK): venta baja stock, anulación lo devuelve, stock negativo da ORA-02290, doble anulación da ORA-20002 | 3.13 |
| `pruebas/17_prueba_planes.sql` | Genera 100 000 ventas, compara plan FULL vs con índice (4 consultas + posibles_errores), mide tiempos, genera `evidencia_100k.txt` y limpia | 3.12 |
| `AGREGAR_a_cargar_esquema.txt` | Líneas añadidas al cargador (ya incluidas en `cargar_esquema.sh`) | — |
| `../Documentacion_BD_ElectriSys.docx` | ER, diccionario de datos, normalización | 3.15 |

## Cómo aplicarlos
1. Copia `07_vistas.sql` y `09_usuarios_demo_sysdba.sql` sobre los de `oracle/`.
2. Copia `15_normalizacion_3fn.sql` a `oracle/`.
3. Copia también 12, 13, 14 y el nuevo `cargar_esquema.sh` a `oracle/`.
4. Ejecuta `cargar_esquema.sh` en la copia y revisa los mensajes finales del 15: *vehículos sin modelo_id = 0* y *documentos con diferencia <> 0 = 0*.

## Alcance (fase 1)
Es compatible hacia atrás: se conservan `vehiculos.marca/modelo` y las columnas derivadas de los encabezados. La **fase 2** (eliminarlas) exige cambiar el backend PHP (`VehiculoModel`, rutas de ventas/cotizaciones) y queda para un sprint posterior.

## Pruebas (las que dan la evidencia de 3.12 y 3.13)
Con el esquema cargado, como ELECTRISYS, desde la carpeta `pruebas/`:

    sqlplus electrisys/CLAVE@//localhost:1521/freepdb1 @16_prueba_triggers.sql
    sqlplus electrisys/CLAVE@//localhost:1521/freepdb1 @17_prueba_planes.sql

Guarda `evidencia_triggers.txt` y `evidencia_100k.txt` en `oracle/planes_ejecucion/` del repo. Esas dos evidencias solo las puede producir una instancia Oracle real.

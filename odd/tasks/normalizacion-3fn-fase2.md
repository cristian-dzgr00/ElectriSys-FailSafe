# Normalización 3FN — fase 2

**Objetivo:** dejar el esquema Oracle y el backend como en `docs/sprint3/modelo_er_3fn.png` (aprobado por el usuario).
**Alcance autorizado:** repo completo; la base real `ELECTRISYS` local NO se toca (solo esquemas temporales de prueba).
**Entorno de prueba:** Oracle 23ai Free local, PDB FREEPDB1, `sqlplus "/ as sysdba"`; esquema temporal `electrisys_sc`.

## Decisiones
- Carga desde cero = cadena de migraciones: 02..05, 10..14, 15 (fase 1), 16 (fase 2), luego 06, 07, 08 reescritos al esquema nuevo.
- `ventas`/`cotizaciones`: `descuento_pct`, `iva_pct` reemplazan `subtotal/descuento/impuesto/total`. Totales en `vw_totales_documento`.
- Detalles y `repuesto_compatibilidad`: PK compuesta, sin `id` ni `subtotal`.
- `consultas_asistente`: `intencion_id` FK a `nlp_intenciones`; JSON fuera; se conserva `confianza` (dato que hoy viaja en el JSON).
- `posibles_errores(_avisos)`: `marca_id/modelo_id/categoria_id` (exactamente uno según `tipo`) reemplazan `correcto`.

## Tareas
- [ ] T1 Oracle: `16_normalizacion_3fn_fase2.sql`, reescribir 06/07/08, cargador, pruebas 16/17, volumen. Probar en esquema temporal con datos heredados.
- [ ] T2 Backend PHP, frontend, NLP Python (`repositorio_oracle.py`), exportador de feedback.
- [ ] T3 Documentación (`docs/sprint3`, `oracle/docs`) y Trello.

## Verificación
Sección a completar con la evidencia observada.

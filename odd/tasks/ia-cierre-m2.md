# Feature: ia-cierre-m2

## Objetivo
Dejar el componente de IA (asistente NLP) como lo describen el informe y las diapositivas del curso «Aplicación de la IA» (entrega M2, `Avance2_IA`): cifras vigentes y únicas, evaluación sólida y las funciones prometidas en los sprints 7 a 9 funcionando.

## Alcance (pedido del usuario, 2026-11-02)
Incluye: puntos 1, 2 y 3 del análisis previo.
1. **Cifras desactualizadas:** reentrenar y reevaluar con el dataset vigente (374 frases) y dejar una única fuente de cifras en el repo.
2. **Lo prometido y pendiente:** RF-11 (cantidad sugerida en Pedidos), RF-12 («También suelen llevar»), aviso «¿Quisiste decir…?», pedir aclaración si falta la marca, búsqueda por categoría como respaldo con aviso de compatibilidad no confirmada, advertencia de datos personales, sinónimos de categoría en el NER, evaluación de una capa oculta, casos límite de los endpoints nuevos.
3. **Evaluación débil:** conjunto de prueba limpio, criterios C3 y C4, sesgo por nombres de vehículo, NER y recomendador con muestras mayores, evaluación no circular del agente de errores, backtesting de demanda y reglas de asociación.

**Fuera de alcance por ahora:** informe de Word, presentaciones, manual de uso (documentación). La prueba de uso con vendedores reales queda pendiente de decisión del usuario.

## Reglas de trabajo
- Cifras honestas: si un criterio no se cumple, se reporta tal cual.
- Los conjuntos de prueba se redactan y **congelan antes** de ajustar nada con ellos; no se usan para crear diccionarios ni sinónimos.
- Sin push sin autorización explícita. Sin cambiar contraseñas de usuarios.
- Rama: `feature/ia-cierre-m2` (desde `main`).

## Decisión del usuario (2026-11-02): ampliar, no eliminar
- **No se elimina ninguna frase de entrenamiento ni ninguna fila de la tabla de errores** (tampoco duplicados normalizados ni errores con dígitos). Se **amplía al máximo** posible: más frases por intención y más errores de escritura (marcas, modelos y categorías).
- Condiciones para que ampliar no invalide la evaluación:
  1. Las frases y errores nuevos se escriben **sin leer** los conjuntos congelados `eval/holdout_*_v2.*`; después se verifica por script que no coincidan (si coinciden, se descarta la **nueva**, nunca la del holdout).
  2. Las frases nuevas deben ser genuinamente variadas, no plantillas con el vehículo cambiado: de lo contrario la validación cruzada se infla por casi-duplicados entre particiones. Se reporta además una validación cruzada agrupada para detectarlo.
- **Estilo de las frases nuevas (pedido del usuario):** frases que un vendedor **podría escribir de verdad** en el mostrador: cortas y directas, con abreviaturas y jerga colombiana ("pa", "xfa", "cuanto vale", "tiene", "me regala", "mi llave"), sin tildes a veces, con el vehículo dicho de forma coloquial ("el spark", "la hilux", "un logan 2015"), con errores leves de tipeo, dos o tres datos juntos (parte + vehículo + año), preguntas sueltas de precio o stock y saludos/despedidas informales. Evitar frases de manual o excesivamente formales.
- Consecuencia: el dataset ya no es de 374 frases; todas las cifras se recalculan con el tamaño final.

## Tareas
- [ ] IA-1 Modelo de intención: limpieza del dataset, reentrenamiento, baselines, capa oculta, sesgo, C3/C4, y una sola fuente de cifras en `nlp-service/eval/*.json`. Ruta: delegada (varios archivos + lectura de código que prepara la escritura).
- [ ] IA-2 Conjuntos de prueba independientes: holdout de intención, NER, recomendador y errores de escritura realistas. Ruta: delegada.
- [ ] IA-3 Backtesting de demanda (MAE/MAPE frente a línea base) y de reglas de asociación con las ventas de demostración. Ruta: delegada.
- [ ] IA-4 Funciones prometidas en backend y frontend (RF-11, RF-12, aclaraciones, respaldo por categoría, advertencia de datos). Ruta: delegada.
- [ ] IA-5 Redespliegue en las VMs de Oracle y pruebas de punta a punta en el navegador. Ruta: inline (despliegue ya conocido).
- [ ] IA-6 Commits por unidad de trabajo y PR (sin push sin permiso).

## Criterios de aceptación
- Un único conjunto de cifras vigentes, reproducible con comandos documentados en los scripts de `eval/`.
- Suite de pruebas del NLP y del backend en verde; el CI de GitHub en verde.
- Las funciones prometidas visibles en el sitio y probadas en el navegador.

## Progreso (estado final, 2026-11-02)
- [x] IA-1 Modelo: LR C=15 conservada (la capa oculta MLP quedó ~2 puntos de F1 peor en CV normal y agrupada, 30-100 veces más lenta), marcador `<vehiculo>` (+0,01 F1, p≈0,02), umbral 0,40 elegido por CV, tests ya no pisan el modelo, `eval/generar_cifras.py` produce `eval/cifras_vigentes.json` (fuente única).
- [x] IA-2 Conjuntos congelados (huellas en `eval/CONGELADO.txt`, comprobadas intactas) y "después" medido una sola vez (NER diagnóstico adicional: 2 veces). Intención 0,802 → 0,912; NER categoría 0,608 → 0,984; recomendador completo P@1 0,537 → 0,927; errores fuera de tabla 0,739 → 0,939. NER `marca` 1,000 → 0,896 por la inferencia de marca (decisión del usuario pendiente).
- [x] IA-3 Backtests: demanda (iguala al promedio histórico, mejor que ingenuo y promedio de 4 semanas) y asociación (supera al azar; no supera a «más vendidos»). Datos sintéticos de 16 semanas.
- [x] IA-4 Funciones del sitio: RF-11, RF-12, «¿Quisiste decir…?», aclaración sin marca, respaldo por categoría con aviso, advertencia y enmascarado de datos personales; probadas en navegador salvo el botón «Usar cantidad sugerida» (no apareció para el producto probado).
- [x] IA-5 Redespliegue en las 2 VMs (tabla de errores nueva en el volumen `nlp_errores`: 109.277 filas). Defectos hallados en producción y corregidos: búsqueda de repuestos sensible a mayúsculas/tildes (Oracle) y registro del asistente roto por la fase 2 de 3FN (`ORA-00904`; ahora 150→152 consultas guardadas, texto enmascarado, feedback OK).
- Datos: `intents_dataset.csv` 374 → 2.551 frases; tabla de errores 58.833 → 109.277 filas (nada eliminado).
- Pendiente: criterio C3 (recall `recomendar_sustituto` 0,75 frente a 0,90) no se cumple; C4 cumple sin margen en CV agrupada; informe y presentaciones (fuera de alcance de esta etapa); prueba de uso con vendedores reales; frases reales para el conjunto de prueba; `vitest` en el CI.
- 2026-11-02 (inicio): plan creado, rama creada.

## Dudas abiertas para el usuario
- Frases de vendedores reales para el conjunto de prueba (si no hay, las redacto yo y se declara en el informe que no son reales).
- Prueba de uso con vendedores (tiempo de búsqueda con y sin asistente): ¿se prepara la medición?

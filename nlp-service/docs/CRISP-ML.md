# CRISP-ML(Q) aplicado al asistente NLP de ElectriSys

CRISP-ML(Q) organiza un proyecto de aprendizaje automático en fases y exige, en cada una, identificar los riesgos de calidad y cómo se controlan (la «Q»). Este documento dice **dónde está cada fase en el repositorio**. La evidencia ejecutada (gráficas, métricas, errores) está en el cuaderno:

> **`nlp-service/notebooks/asistente_nlp.ipynb`**. Todas las cifras de este documento salen de ese cuaderno (ejecución del 2026-09-29). El cuaderno no modifica archivos del proyecto: entrena en memoria, escribe solo en `notebooks/salida/` (la base SQLite de trabajo y el script `12_dataset_nlp_oracle.sql`) y al final verifica con SHA-256 que `models/`, `eval/`, el dataset y `oracle/*.sql` quedaron intactos.

## Mapa de fases a archivos

| Fase | Qué hay | Archivos del proyecto | Cuaderno |
|---|---|---|---|
| 1. Comprensión del negocio | Problema (sustituto de un repuesto agotado), objetivo, restricciones (sin modelos de lenguaje externos, presupuesto cero, explicable), criterios de éxito C1-C8 y tabla de riesgos | `docs/asistente-nlp.md` (raíz del repo) · `backend/src/patterns/observer/GestorAsistente.php` (tiempo límite de 5 s) | §1 |
| 2. Comprensión de los datos | Flujo de entrada y salida; construcción del dataset (65 → 374 frases); carga en la base de datos (réplica SQLite de Oracle, tablas `nlp_intenciones`, `nlp_frases`, `nlp_predicciones`); descripción y gráficas de la base; 374 frases en 7 intenciones (50-56 por clase), sin nulos ni duplicados exactos; longitud, media, mediana y moda, casi-duplicados, palabras características (χ²), peso de la negación | `data/intents_dataset.csv` · `tests/test_dataset.py` · `oracle/02_ddl_tablas.sql` · `oracle/05_seed.sql` | §2 |
| 3. Preparación de los datos | Normalización, tokenización y stopwords que conservan la negación; partición (validación cruzada + holdout); chequeo automático de fuga | `app/preprocessing.py` · `eval/holdout_intent.csv` · `eval/holdout_ner.json` | §3 |
| 4. Modelado | Intención: TF-IDF de unigramas + regresión logística (`C=15`, `liblinear`), umbral 0.35. Entidades: reglas + RapidFuzz. Sustitutos: TF-IDF + coseno (patrón Strategy). Comparación de 7 configuraciones + línea base | `app/intent/train.py` (`_construir_pipeline`) · `app/intent/classifier.py` · `app/ner/extractor.py` · `app/ner/dictionary.py` · `app/recommender/` | §4 |
| 5. Evaluación | Holdout, matrices de confusión, errores, barrido del umbral, NER por campo, recomendador, latencia, resumen frente a criterios | `eval/eval_intent.py` · `eval/eval_ner.py` · `eval/eval_recomendador.py` · `eval/resultados_*.json` · `docs/evaluacion.md` (desactualizado, ver pendientes) | §5 |
| 6. Despliegue | FastAPI en Docker; backend PHP como único cliente (`X-Internal-Key`, JWT de servicio de rol vendedor, 300 caracteres, 20 consultas/min); demostración con consultas | `app/main.py` · `app/pipeline.py` · `app/config.py` · `Dockerfile` · `docker/docker-compose*.yml` · `backend/src/routes/asistente.php` | §6 |
| 7. Monitoreo y mantenimiento | Registro de consultas, calificación útil/no útil, exportación para curación manual, líneas base y alertas sugeridas | `eval/exportar_feedback.py` · tabla `consultas_asistente` (columna `util`) · `database/schema_v4_migration_feedback.sql` | §7 |

## Resultados principales

**Clasificador de intención** (configuración del proyecto):

| Evidencia | Resultado | Confiabilidad |
|---|---|---|
| F1 macro, validación cruzada estratificada 5 partes × 10 repeticiones | **0.820 ± 0.037** | La más confiable: 374 frases |
| Accuracy con umbral, validación cruzada | 0.807 | Ídem |
| Accuracy con umbral, holdout limpio (27 frases) | 0.926, IC 95 % [0.77, 0.98] | Optimista: holdout contaminado (ver riesgos) |
| Línea base trivial (clase más frecuente), F1 macro | 0.037 | — |

Comparación de configuraciones (diferencia de F1 frente a la del proyecto, mismas 50 particiones): bigramas −0.089 (pierden en 50/50), `C=1` −0.034 (y manda el 73 % de las consultas al fallback), Naive Bayes −0.189, `class_weight="balanced"` +0.003, `C=100` +0.009 (gana 31/50, no concluyente). **Se mantiene la configuración del proyecto.**

**Criterios de éxito** (fijados en §1 del cuaderno; el repositorio no tenía metas formales):

| ID | Criterio | Meta | Resultado | ¿Cumple? |
|---|---|---|---|---|
| C1 | F1 macro en validación cruzada | ≥ 0.80 | 0.820 | Sí |
| C2 | Accuracy en holdout limpio | ≥ 0.80 | 0.926 | Sí, pero su IC baja a 0.77 |
| C3 | Recall de `recomendar_sustituto` (CV) | ≥ 0.90 | 0.804 | **No** |
| C4 | Frases fuera de dominio tratadas como negocio (CV) | ≤ 15 % | 32 % | **No** |
| C5 | Precisión global del NER | ≥ 0.90 | 1.000 (12 casos) | Sí, con muestra mínima |
| C6 | Precisión@3 del recomendador | ≥ 0.80 | 1.000 (6 casos) | Sí, no concluyente |
| C7 | Latencia p95 intención + NER | < 100 ms | 1.7-2.7 ms (varía por corrida; sin contar el backend) | Sí |
| C8 | Ventaja sobre la línea base (F1) | ≥ +50 pts | +78.4 pts | Sí |

## Riesgos de calidad

| # | Riesgo | Mitigación en el proyecto | Qué mostró el cuaderno |
|---|---|---|---|
| R1 | Dataset pequeño escrito por el equipo | Validación cruzada + holdout + feedback | El modelo aprendió **sesgos por nombres de vehículo**: 24 de 29 tokens de vehículo pesan > 1 hacia una intención («hilux» → `recomendar_sustituto`, 3.91). «¿Hay filtro de aceite para Hilux 2.7?» sale como sustituto sin decir «no» |
| R2 | Fuga entre entrenamiento y prueba | Chequeo automático (cuaderno §3.3) | 1 frase idéntica en ambos conjuntos, y el dataset se amplió con vocabulario de los errores del holdout (cobertura de su vocabulario 75.8 % → 91.4 %) |
| R3 | Inventar una intención ante una frase ajena | Umbral de confianza 0.35 | El umbral atrapa **una sola** frase fuera de dominio más que no tenerlo; los errores graves («¿Cuánto falta para navidad?» → precio, 0.88) tienen confianza alta |
| R4 | Perder la negación | Stopwords sin «no», «sin», «ni», «nunca», «tampoco» | Confirmado: la negación está en el 58.9 % de las frases de sustituto y `no` es su palabra de mayor peso |
| R5 | Errores de tipeo en vehículos | RapidFuzz (umbrales 85 / 88) | «toyta» → Toyota funciona |
| R6 | Categorías sin parecido ortográfico | `SINONIMOS_CATEGORIA` | Funciona, pero se creó para los 2 errores del propio holdout del NER: esa parte de la métrica está sobreajustada |
| R7 | El modelo servido no corresponde al dataset | — (no había control) | `models/intent_classifier.pkl` tiene 194 términos (dataset viejo de 65 frases) frente a 502 del actual; coincide solo en el 75 % de las predicciones del holdout. El `Dockerfile` lo copia tal cual |
| R8 | Caída del backend o del microservicio | Tiempos límite, `BackendNoDisponibleError`, 503 controlado | Revisado en código, no se prueba en el cuaderno |
| R9 | Degradación con el uso real | Registro, útil/no útil, `exportar_feedback.py` | Sin datos reales disponibles; el cuaderno deja las líneas base para las alertas |

## Documentos y artefactos desactualizados

| Archivo | Qué dice | Realidad actual |
|---|---|---|
| `docs/evaluacion.md` | Accuracy 0.821 sobre el holdout, «~65 ejemplos», errores con «bodega», «chao», «wifi» | Dataset de 374 frases; CV 0.807, holdout limpio 0.926; esos errores ya no ocurren porque sus palabras se agregaron al dataset |
| `models/metrics_intent.json` | 65 ejemplos, accuracy CV 0.338 | Corresponde al dataset viejo |
| Comentario de `_construir_pipeline()` en `app/intent/train.py` | Bigramas + `balanced` daban probabilidades «~0.20» con «~60 ejemplos» | Hoy su confianza media es 0.58; siguen rindiendo peor (−0.088 de F1) |
| Comentarios de `tests/test_intent.py` | «~60 ejemplos», accuracy CV «~0.30-0.35» | CV 0.807 |

## Pendientes (no aplicados por el cuaderno)

**Críticos**

1. **Reentrenar el modelo** (`python -m app.intent.train`) y agregar `RUN python -m app.intent.train` al `Dockerfile` después de `COPY data ./data`, para que el modelo servido siempre salga del dataset versionado.
2. **Quitar «¿Cuál es tu color favorito?» de `eval/holdout_intent.csv`** (está también en el dataset) o reemplazarla por una frase nueva.
3. **Congelar un holdout nuevo** (idealmente con frases de vendedores reales, ~20 por clase) y no volver a usarlo para decidir qué agregar al dataset.

**Mejoras del modelo (atacan C3 y C4)**

4. Agregar a `recomendar_sustituto` frases sin negación explícita («se me acabaron…», «ya no queda…»).
5. Agregar a `fuera_de_dominio` frases ajenas que usen palabras del negocio («¿cuánto falta para…?», «¿tienen parqueadero?»).
6. Probar reemplazar marca y modelo detectados por el NER con un marcador (`<vehiculo>`) antes de clasificar, para quitar el sesgo por vehículos; comparar con validación cruzada.
7. Quitar uno de cada par que queda idéntico tras preprocesar («Buenas» / «buenas como estas»; las dos variantes de «¿Tienen (la) correa poly-v…?») y ampliar `tests/test_dataset.py` para detectarlos.

**Mantenimiento**

8. Actualizar `docs/evaluacion.md`, `models/metrics_intent.json` (se regenera al reentrenar) y los comentarios de `train.py` y `test_intent.py`.
9. Hacer que `tests/test_intent.py` entrene en un directorio temporal: hoy su *fixture* llama a `entrenar()` y **sobrescribe el modelo real** cada vez que se corre `pytest`.
10. `eval/eval_intent.py` llama a `predecir_intencion` dos veces por frase; basta una.
11. Volver a correr `eval/eval_recomendador.py` contra el catálogo actual en Oracle (los resultados guardados son del 2026-09-05 y todos sus casos tienen 3 candidatos o menos, así que la precisión@3 no discrimina).
12. Ejecutar por primera vez el ciclo de mejora con feedback real (cuaderno §7.2) y comparar contra las líneas base.

## Cómo volver a ejecutar el cuaderno

El cuaderno necesita las dependencias de `requirements.txt` más `matplotlib` e `ipykernel`. En Windows, si el proyecto está en una ruta larga (p. ej. dentro de OneDrive), `pip install ipykernel` puede fallar por la longitud de ruta; en ese caso, cree el entorno virtual en una ruta corta:

```bash
python -m venv C:\nlpnb-venv
C:\nlpnb-venv\Scripts\python -m pip install -r nlp-service/requirements.txt matplotlib ipykernel
```

Luego abra `nlp-service/notebooks/asistente_nlp.ipynb` con ese intérprete y ejecute todas las celdas (tarda menos de un minuto). No necesita el backend.

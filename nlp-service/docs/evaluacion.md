# Evaluación del Asistente NLP

Métricas medidas el 2026-09-05 contra un **set de prueba independiente**
(`eval/holdout_*.{csv,json}`) — frases nunca vistas por el modelo, escritas
con una redacción distinta a `data/intents_dataset.csv`. A diferencia de la
validación cruzada de la Sprint 3 (que reparte el mismo dataset chico de
~65 ejemplos en folds de ~2 ejemplos por clase), esto mide generalización
real y da números mucho más representativos de uso real.

Reproducible con:
```bash
python -m eval.eval_intent        # no necesita nada externo
python -m eval.eval_ner           # no necesita nada externo
python -m eval.eval_recomendador  # necesita BACKEND_URL levantado con el seed cargado
```
Cada script guarda su detalle en `eval/resultados_*.json`.

## 1. Clasificación de intención

28 ejemplos nuevos (4 por clase), nunca usados en entrenamiento.

| Métrica | Valor |
|---|---|
| Accuracy | **0.821** |
| F1 macro | **0.813** |
| Confianza promedio | 0.550 |

| Intención | Precision | Recall | F1 |
|---|---|---|---|
| recomendar_sustituto | 1.00 | 1.00 | 1.00 |
| consultar_compatibilidad | 1.00 | 1.00 | 1.00 |
| consultar_precio | 0.80 | 1.00 | 0.89 |
| buscar_repuesto | 0.67 | 1.00 | 0.80 |
| fuera_de_dominio | 0.60 | 0.75 | 0.67 |
| consultar_stock | 1.00 | 0.50 | 0.67 |
| saludo_despedida | 1.00 | 0.50 | 0.67 |

**Interpretación:** la intención central del proyecto (`recomendar_sustituto`)
y `consultar_compatibilidad` generalizan perfectamente. Las fallas (5/28)
son consistentes con un dataset todavía chico (~9 ejemplos/clase):
- *"Dime si hay suficientes bujías Bosch en **bodega**"* → clasificado como
  `fuera_de_dominio`: "bodega" como sinónimo de stock no aparece en el
  dataset de entrenamiento.
- *"Chao, que estés bien"* → `fuera_de_dominio`: el dataset solo tiene
  despedidas con "hasta luego"/"nos vemos", no "chao".
- *"¿Tienen **wifi** para clientes?"* → `buscar_repuesto`: el patrón
  "¿Tienen...?" está fuertemente asociado a esa clase en el entrenamiento,
  y "wifi" no tiene señal léxica que lo contrarreste.

**Mejora esperada:** estos tres errores se resuelven agregando variantes
como las de arriba a `data/intents_dataset.csv` — no son fallas
estructurales del pipeline, son huecos de vocabulario cubribles con más
ejemplos (ver sección "Próximos pasos" abajo).

## 2. Extracción de entidades (NER)

12 casos anotados a mano, incluyendo un caso con error de tipeo ("toyta")
y uno sin ningún vehículo mencionado (para probar que no inventa datos).

| Precisión global | **0.950** |
|---|---|

| Campo | Precisión | Evaluados |
|---|---|---|
| marca | 1.00 | 11 |
| modelo | 1.00 | 11 |
| año | 1.00 | 5 |
| motor | 1.00 | 2 |
| combustible | 1.00 | 3 |
| código | 1.00 | 2 |
| categoría | 0.67 | 6 |

**Interpretación:** marca/modelo/año/motor/combustible/código (los campos
que realmente maneja la búsqueda de compatibilidad) son 100% exactos, con
tolerancia a errores de tipeo confirmada ("toyta" → "Toyota"). El único
punto débil es **categoría**, y por una razón estructural, no un bug:

- *"correa de distribucion"* no matcheó "Correas y Bandas" — singular vs.
  plural más una categoría de tres palabras es un caso límite del fuzzy
  matching actual.
- *"bujias"* no matcheó "Encendido" — este caso **no es corregible con
  fuzzy matching**: "bujía" y "encendido" son palabras completamente
  distintas, relacionadas solo por significado (una bujía enciende el
  motor), no por ortografía. Ningún algoritmo de similitud de caracteres
  puede tender ese puente; se necesitaría un diccionario de sinónimos por
  categoría o un enfoque semántico (embeddings).

Esto no compromete la funcionalidad principal (recomendar sustitutos por
vehículo), porque esa búsqueda depende de marca+modelo, no de categoría —
categoría es un filtro adicional opcional.

## 3. Motor de recomendación (precisión@k)

6 consultas contra el catálogo semilla real (`database/seed_vehiculos.sql`),
vía el backend PHP en vivo — mide la cadena completa NER → búsqueda de
candidatos → ranking TF-IDF/coseno.

| Métrica | Valor |
|---|---|
| Precisión@1 | **1.000** |
| Precisión@3 | **1.000** |

Los 6/6 casos acertaron, incluyendo el caso central del proyecto (filtro de
aceite Toyota agotado → recomienda HP-1002 y M1-102, excluyendo
correctamente el original sin stock).

**Limitación honesta:** el catálogo semilla es intencionalmente chico (15
repuestos) y solo tiene **un** caso real de "varios sustitutos posibles
para un producto agotado" (los filtros de aceite Toyota). El resto de
categorías (batería, bujía, correa) solo tienen una opción sembrada, así
que en esos casos precisión@k mide "¿encontró el único candidato posible?"
más que "¿lo rankeó por encima de alternativas peores?". Con un catálogo
real más grande esta métrica sería más informativa — dejarlo anotado para
cuando el negocio cargue su inventario real.

## Próximos pasos (para cuando se amplíe el dataset)

1. Agregar a `data/intents_dataset.csv` variantes con sinónimos coloquiales
   detectados aquí: "bodega" (stock), "chao" (despedida), evitar que todo
   "¿Tienen...?" se asocie ciegamente a `buscar_repuesto`.
2. Si categoría importa más adelante (ej. para el fallback de "sin
   compatibilidad exacta"), agregar un diccionario chico de sinónimos por
   categoría (`bujía/bujías → Encendido`, `correa/correas → Correas y
   Bandas`) en `app/ner/extractor.py`.
3. Re-correr `python -m eval.eval_intent` después de ampliar el dataset y
   comparar contra estos números como línea base.

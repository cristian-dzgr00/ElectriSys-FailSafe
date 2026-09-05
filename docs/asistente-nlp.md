# Asistente Inteligente basado en NLP para Recomendación de Repuestos

Proyecto de la materia "Aplicación de la Inteligencia Artificial". Documento
de arquitectura para la sustentación — no repite lo que ya está en el
código, explica las decisiones y el porqué.

## El problema

Un vendedor está atendiendo a un cliente que pide un repuesto específico
para su vehículo. El repuesto está agotado. Antes de este proyecto, el
vendedor tenía que saber de memoria (o buscar manualmente) qué otro
producto del inventario podía servir como sustituto. El asistente resuelve
esto: el vendedor escribe la situación en lenguaje natural y el sistema
responde con sustitutos reales, tomados del inventario y filtrados por
compatibilidad real con el vehículo del cliente.

**Requisito explícito de la materia:** no puede ser una integración con un
LLM externo (eso no demuestra aplicación de las técnicas de IA vistas en
el curso). Todo el procesamiento de lenguaje —clasificación, extracción de
entidades, ranking— es un pipeline propio, entrenado/construido sobre datos
del negocio, corriendo localmente.

## Arquitectura: tres componentes

```
┌─────────────┐   1. "no hay filtro de aceite    ┌──────────────────┐
│  Frontend    │      para Hilux 2.7 2024..."     │  Backend PHP      │
│  React       │ ────────────────────────────────>│  (Slim)           │
│  (Ventas.jsx)│   POST /api/asistente/consultar  │                    │
└─────────────┘   (JWT del vendedor)              │  asistente.php:    │
                                                    │  - valida input    │
       ▲                                           │  - rate limiting   │
       │ 5. respuesta + tarjetas                   │  - GestorAsistente │
       │    de sustitutos                          └─────────┬──────────┘
       │                                                      │
       │                                    2. POST /nlp/consultar
       │                                       (X-Internal-Key)
       │                                                      ▼
       │                                           ┌──────────────────┐
       │                                           │  Microservicio    │
       └───────────────────────────────────────────│  Python (FastAPI) │
                                                     │  nlp-service/     │
                                                     │                    │
                                                     │  intención → NER   │
                                                     │  → candidatos      │
                                                     │  → ranking → NLG   │
                                                     └─────────┬──────────┘
                                                               │
                                          3. GET /api/vehiculos/marcas,
                                             /api/repuestos/buscar-compatibles
                                             (JWT autofirmado, mismo JWT_SECRET)
                                                               │
                                                               ▼
                                                     ┌──────────────────┐
                                                     │  Backend PHP      │
                                                     │  (vía "frontend"/ │
                                                     │  nginx — ver nota)│
                                                     └─────────┬──────────┘
                                                               │
                                          4. SELECT ... FROM repuestos
                                             JOIN repuesto_compatibilidad
                                             JOIN vehiculos
                                                               ▼
                                                     ┌──────────────────┐
                                                     │  MySQL             │
                                                     └──────────────────┘
```

**Por qué dos saltos al backend (2 y 3) en vez de uno:** el microservicio
no tiene acceso directo a la base de datos — todo pasa por la API del
backend PHP, que ya tiene la lógica de negocio (qué es "compatible", qué
tiene stock, permisos). Esto evita duplicar reglas de negocio en dos
lenguajes distintos.

### 1. Base de datos (`database/schema_v3_migration_nlp.sql`)

Tres tablas nuevas sobre el esquema existente:
- **`vehiculos`**: marca, modelo, **rango** de años (`anio_desde`/`anio_hasta`,
  no un año único — un repuesto real aplica a varios años de un modelo),
  motor, combustible.
- **`repuesto_compatibilidad`**: puente N:N entre `repuestos` y `vehiculos`.
- **`consultas_asistente`**: log de cada consulta (texto, intención
  detectada, entidades, respuesta) — alimentada por el patrón Observer, no
  por la ruta HTTP directamente (ver más abajo).

### 2. Backend PHP (`backend/src/routes/asistente.php` + `vehiculos.php` + extensiones a `repuestos.php`)

- `POST /api/asistente/consultar`: único endpoint nuevo de cara al
  frontend. Valida input, aplica rate limiting (20/min por usuario), y
  delega en `GestorAsistente`.
- `GET /api/repuestos/buscar-compatibles`, `GET/POST/DELETE
  /api/repuestos/{id}/compatibilidad`, `GET /api/vehiculos/*`: rutas de
  catálogo que **el microservicio** consume para saber qué existe
  realmente en inventario.

**Patrón Observer reutilizado** (no reinventado): `GestorAsistente` +
`AsistenteLogObserver` siguen exactamente la misma estructura que
`GestorVentas` + `AuditLogObserver` (que ya auditaba las ventas). El
Subject hace el trabajo (llamar al microservicio) y notifica a los
Observers al terminar; si el registro en `consultas_asistente` falla, la
respuesta al vendedor no se ve afectada — mismo principio de
desacoplamiento que ya regía en el sistema de ventas.

### 3. Microservicio de NLP (`nlp-service/`, Python + FastAPI)

Pipeline en `app/pipeline.py`, cada paso es un módulo independiente y
testeable por separado:

| Paso | Módulo | Técnica |
|---|---|---|
| Preprocesamiento | `app/preprocessing.py` | normalización ES, tokenización, stopwords (sin negaciones) |
| Clasificación de intención | `app/intent/` | TF-IDF (unigramas) + regresión logística, entrenado con `data/intents_dataset.csv` |
| Extracción de entidades | `app/ner/` | reglas (regex) + fuzzy matching (rapidfuzz) contra un diccionario que se sincroniza con la BD real |
| Motor de recomendación | `app/recommender/` | TF-IDF + similitud coseno sobre candidatos ya filtrados por compatibilidad |
| Generación de respuesta | `app/nlg/templates.py` | plantillas por intención, sin LLM |

**Por qué TF-IDF + coseno y no embeddings:** para un catálogo del tamaño de
una tienda de repuestos (decenas/cientos de productos), TF-IDF es rápido,
no requiere descargar modelos pesados, y es completamente explicable en la
sustentación ("por qué recomendó esto" se puede mostrar como superposición
de palabras). Queda aislado detrás de una interfaz (`EstrategiaSimilitud`,
patrón **Strategy** — la misma idea que ya usa `DiscountStrategy` en el
backend PHP para el cálculo de descuentos) para poder cambiarlo por
embeddings más adelante sin tocar el resto del pipeline.

**Por qué la clasificación de intención usa regresión logística y no algo
más sofisticado:** con un dataset de ~65-90 ejemplos, un modelo simple con
buena regularización generaliza mejor y es interpretable — se probó
empíricamente (ver `docs/evaluacion.md`) que una configuración con
bigramas y balanceo de clases producía probabilidades demasiado "planas" y
el umbral de confianza descartaba predicciones correctas.

**Autenticación entre servicios:**
- Backend → microservicio: header `X-Internal-Key` (mismo patrón que ya
  usaba `WS_NOTIFY_KEY` para el servidor de WebSocket).
- Microservicio → backend: el microservicio **firma su propio JWT** con el
  mismo `JWT_SECRET` que usa `JwtMiddleware` — no necesita hacer login ni
  que un humano genere un token a mano. Esto es un atajo pragmático (no un
  mecanismo de cuentas de servicio completo); para un sistema en
  producción real valdría la pena un usuario de servicio dedicado con
  permisos acotados.

## Flujo de datos para el ejemplo del enunciado

1. Vendedor escribe: *"No hay filtro de aceite original de Toyota para
   Hilux 2.7 gasolina 2024, ¿qué recomiendo?"*
2. Backend valida, registra el intento (rate limit), llama al
   microservicio.
3. Microservicio clasifica intención → `recomendar_sustituto` (confianza
   ~0.65). Extrae entidades → marca=Toyota, modelo=Hilux, año=2024,
   motor=2.7, combustible=gasolina, categoría=Filtros.
4. Llama a `GET /api/repuestos/buscar-compatibles?marca=Toyota&modelo=Hilux&...`
   → el backend devuelve los repuestos compatibles con ese vehículo,
   incluido el filtro original (`90915-YZZD4`, stock 0).
5. Se filtran los que tienen stock > 0 → quedan `HP-1002` y `M1-102`.
6. Se rankean por similitud textual contra la consulta original.
7. Plantilla NLG arma: *"Puedes recomendar el repuesto 'HP-1002' de K&N
   Filtros o 'M1-102' de Mobil 1 Distribuidora — posibles sustitutos para
   Toyota Hilux 2.7 gasolina 2024."*
8. El backend recibe la respuesta, la registra en `consultas_asistente`
   (Observer), y se la devuelve al frontend.
9. El frontend muestra el texto y una tarjeta por sustituto (código,
   nombre, proveedor, stock, precio).

## Cómo levantar todo

### Con Docker (`docker compose up`)

```bash
./tls/generate-certs.sh          # PKI para mTLS (paso previo, una sola vez)
docker compose -f docker/docker-compose.yml up -d --build
```

Levanta: `mysql-primary`/`mysql-replica`, `backend-a`/`backend-b`,
`websocket-server`, `nlp-service`, `frontend` (nginx). El seed de
vehículos/repuestos automotrices (`database/seed_vehiculos.sql`) se carga
automáticamente en un volumen nuevo.

### Desarrollo local sin Docker (lo que se usó para validar cada sprint)

```bash
# Backend (necesita 2 instancias si se prueba la integración completa:
# el "php -S" de un solo hilo de Windows se autobloquea si el
# microservicio le llama de vuelta al mismo proceso)
cd backend && php -S 127.0.0.1:8099 -t public public/index.php

# Microservicio
cd nlp-service && venv/Scripts/activate && uvicorn app.main:app --port 8103

# Frontend
cd frontend && npm run dev
```

## Validación real con `docker compose up`

Validado de punta a punta el 2026-09-05 contra un volumen de MySQL
genuinamente nuevo (no reutilizando datos viejos): todas las imágenes
compilan, todos los healthchecks pasan, y el caso del enunciado responde
correctamente vía `http://localhost/api/asistente/consultar` a través de
nginx → backend PHP → microservicio → backend PHP → MySQL, registrando la
consulta en `consultas_asistente`.

**Bug real encontrado y corregido en esta validación:** `Database.php`
combinaba las opciones de PDO con las opciones mTLS usando `array_merge()`.
Como esas claves son las constantes `PDO::*` (enteros), `array_merge()` las
reindexa secuencialmente en vez de preservarlas — por coincidencia
posicional, el valor de `SSL_VERIFY_SERVER_CERT` terminaba en la posición
de `PDO::ATTR_CASE`, y PDO lo interpretaba como `PDO::CASE_UPPER`: **todas
las columnas de la base de datos volvían en MAYÚSCULAS con mTLS activo**,
rompiendo el login y cualquier acceso a `$row['columna']` en minúscula —
prácticamente toda la aplicación. Nunca se detectó antes porque ningún
sprint anterior había probado con certificados TLS reales. Se corrigió
cambiando `array_merge($options, $tlsOptions)` por `$options + $tlsOptions`,
con una prueba de regresión en `backend/tests/DatabaseTlsOptionsTest.php`.

**Problema distinto, no corregido (fuera de alcance de este proyecto):**
con la combinación de opciones ya corregida, el handshake mTLS entre el
backend y MySQL falla de verdad (`SSL routines::tlsv1 alert unknown ca`) —
la configuración TLS/mTLS es un módulo aparte de la materia de Sistemas
Distribuidos, no del asistente NLP, y nunca se había probado end-to-end en
este repositorio (los certificados ni siquiera estaban generados). Para
validar el asistente se usó el modo "sin TLS" que el propio código ya
soporta como fallback documentado (`TlsConfig::getMysqlPdoOptions()`
devuelve `[]` si no encuentra certificados). Quien retome el módulo de
mTLS debería revisar la configuración de verificación de certificados de
cliente en `tls/mysql/mysql-ssl.cnf`.

## Evaluación

Ver [`nlp-service/docs/evaluacion.md`](../nlp-service/docs/evaluacion.md)
para las métricas completas (accuracy/F1 de intención sobre un set de
prueba independiente, precisión de NER por campo, precisión@k del
recomendador) con interpretación de errores y próximos pasos.

## Historial de sprints

| Sprint | Entregable |
|---|---|
| 0 | Esquema de BD (vehículos, compatibilidad) + seed de datos automotrices |
| 1 | CRUD de vehículos/compatibilidad en el backend |
| 2 | Esqueleto del microservicio + dataset de intención + preprocesamiento |
| 3 | Clasificación de intención + NER híbrido |
| 4 | Motor de recomendación (TF-IDF+coseno) + generación de respuesta |
| 5 | Integración backend↔microservicio (Observer, autenticación, Docker) |
| 6 | Frontend: botón flotante + chat, formulario de compatibilidad |
| 7 | Rate limiting + checklist de casos límite |
| 8 | Evaluación final + esta documentación |

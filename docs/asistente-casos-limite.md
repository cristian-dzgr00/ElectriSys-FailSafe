# Asistente NLP — Checklist de endurecimiento (Sprint 7)

Batería de casos límite de `POST /api/asistente/consultar`, validada en vivo
contra el stack real (MySQL + 2 instancias del backend + microservicio) el
2026-09-05. Objetivo: ningún caso debe producir un error 500 sin manejar ni
colgar al vendedor en plena venta.

| # | Caso | Esperado | Obtenido |
|---|------|----------|----------|
| 1 | Texto vacío (`""`) | 400, mensaje claro | ✅ `400` — "El texto de la consulta es obligatorio" |
| 2 | Texto de 1000 caracteres | 400, mensaje claro | ✅ `400` — "La consulta no puede superar 300 caracteres" |
| 3 | Sin marca/modelo mencionados ("no hay filtro de aceite, que recomiendo") | 200, pide aclarar el vehículo | ✅ `200` — "No logré identificar la marca y el modelo..." |
| 4 | Vehículo inexistente en catálogo ("Lamborghini Aventador 2024") | 200, mismo mensaje que el caso 3 (fuzzy match no debe inventar una marca) | ✅ `200` — marca/modelo quedan `null`, no hay falso positivo |
| 5 | Microservicio de NLP caído por completo | 503 rápido (no colgado), mensaje claro | ✅ `503` en 2.1s — "El asistente no está disponible en este momento..." |
| 6 | Backend caído *desde la perspectiva del microservicio* (nlp-service no puede consultar el catálogo) | 200, mensaje de "no pude consultar el catálogo", sin perder la intención/entidades ya extraídas | ✅ `200` — intención y entidades correctas, `sugerencias: []`, aviso claro |
| 7 | Sin JWT | 401 | ✅ `401` — "Token no proporcionado" |
| 8 | Rate limiting: 21 consultas en <1 minuto del mismo usuario | Las primeras 20 pasan, la 21+ recibe 429 con `Retry-After` | ✅ peticiones 1-20 → `200`; 21-22 → `429` con `Retry-After: 60` |

## Decisiones de diseño

- **Rate limiting por `usuario_id`, no por IP** (a diferencia del login): varios
  vendedores de la misma tienda comparten IP; limitar por usuario evita que
  uno sature al microservicio sin bloquear a sus compañeros.
- **Reutiliza la tabla `consultas_asistente`** (ya poblada por
  `AsistenteLogObserver`) en vez de crear una tabla nueva solo para contar
  intentos — ventana deslizante de 1 minuto vía
  `creado_en > NOW() - INTERVAL 1 MINUTE`.
- **Límite generoso (20/min):** suficiente para uso normal en mostrador, alto
  para que un vendedor legítimo nunca lo note, bajo para frenar un abuso
  claro (flood accidental o intencional).
- Si la propia verificación del límite falla (ej. BD caída), **no se bloquea
  al vendedor** — se prioriza que el asistente siga intentando responder
  sobre una protección que en ese momento no se puede confirmar.

## Cosas ya cubiertas por sprints anteriores (no repetidas aquí)

- **X-Internal-Key** protege `/nlp/consultar` de llamadas directas no
  autorizadas dentro de la red — probado en el Sprint 5
  (`nlp-service/tests/test_main.py`).
- **CSP** (`connect-src 'self'`): el frontend nunca llama directo al
  microservicio, solo vía `/api/asistente/consultar` del backend (mismo
  origen) — confirmado sin errores de consola en la prueba de navegador del
  Sprint 6.
- **Timeout del frontend no cuelga la UI**: `services/api.js` tiene
  `timeout: 10000` (10s), por encima del `CURLOPT_TIMEOUT` de 5s que usa
  `GestorAsistente.php` — el vendedor siempre ve la respuesta (o el error)
  del backend antes de que el propio navegador se rinda.
- **Datos en `consultas_asistente`**: solo texto de la consulta e
  intención/entidades/respuesta — mismo nivel de sensibilidad que
  `audit_log` (datos operativos internos, no PII de clientes).

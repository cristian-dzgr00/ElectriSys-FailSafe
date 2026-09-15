# ElectriSys POS

**Sistema de punto de venta (POS) para repuestos automotrices y de maquinaria agrícola**, con un asistente de recomendación basado en Procesamiento de Lenguaje Natural (proyecto de la materia *Aplicación de la Inteligencia Artificial*) y una infraestructura distribuida (proyecto de la materia *Sistemas Distribuidos*): réplica de base de datos, mTLS, VPN, Kubernetes/Istio, observabilidad y análisis de red.

## Arquitectura

```
┌──────────────┐   HTTP    ┌──────────────┐  FastCGI/mTLS  ┌──────────────┐
│  Frontend     │──────────▶│   nginx       │───────────────▶│  Backend PHP  │
│  React + Vite │           │  (frontend)   │                │  (Slim, x2)   │
└──────────────┘           └──────┬───────┘                └───────┬───────┘
                                   │ /ws                            │
                                   ▼                                │
                          ┌──────────────┐                          │
                          │  WebSocket    │                          │
                          │  (Node.js)    │                          │
                          └──────────────┘                          │
                                                                     ▼
┌──────────────┐   JWT autofirmado    ┌──────────────┐     ┌──────────────┐
│ Microservicio │◀─────────────────────│  Backend PHP  │────▶│  Oracle 23ai  │
│ NLP (FastAPI) │   X-Internal-Key     │  /asistente   │     │  Free         │
└──────────────┘─────────────────────▶└──────────────┘     └──────────────┘
```

El asistente NLP (intención → entidades → recomendación → respuesta) está documentado en detalle en [`docs/asistente-nlp.md`](docs/asistente-nlp.md).

## Estructura del repositorio

```
Electrisys/
├── backend/              PHP (Slim) — API REST, patrones Observer/Strategy
├── frontend/             React + Vite — POS y asistente flotante
├── nlp-service/          Python (FastAPI) — clasificación de intención, NER, recomendador
├── database/             histórico MySQL (archivado — ver Oracle abajo)
├── oracle/               esquema real (Oracle 23ai): DDL, PL/SQL, triggers, vistas, roles, backup
├── docker/               docker-compose.yml y Dockerfiles de cada servicio
├── websocket-server/     Node.js — notificaciones en tiempo real
├── k8s/                  Manifiestos Kubernetes (Istio, network policies, HPA, monitoring)
├── monitoring/           Prometheus + Grafana (stack local)
├── network-analysis/     Capturas y perfiles Wireshark para análisis de protocolos
├── tls/                  Generación de PKI interna para mTLS
├── vpn/                  Configuración WireGuard
├── nginx/                Configuración del proxy inverso
└── docs/                 Documentación de arquitectura y evaluación
```

## Stack

- **Backend:** PHP 8.2, Slim Framework 4, oci8 (Oracle Instant Client), JWT (firebase/php-jwt)
- **Frontend:** React 18, Vite, axios, lucide-react
- **Microservicio NLP:** Python 3.11, FastAPI, scikit-learn (TF-IDF + regresión logística), rapidfuzz, pandas
- **Base de datos:** Oracle Database 23ai Free — instancia única (sin réplica: Oracle Free no soporta Data Guard/RAC, son features Enterprise). PL/SQL: packages `pkg_ventas`/`pkg_reportes`, triggers de stock/auditoría, vistas de reporte — ver [`oracle/docs/migracion-oracle.md`](oracle/docs/migracion-oracle.md)
- **Tiempo real:** Node.js + WebSocket
- **Infraestructura:** Docker Compose, Kubernetes, Istio, WireGuard, stunnel (mTLS), Prometheus/Grafana

## Requisitos

- Docker Desktop (o Docker Engine + Compose v2)
- Para desarrollo sin Docker: PHP 8.2+ con la extensión `oci8` (requiere Oracle Instant Client), Composer, Node.js 20+, Python 3.11+, Oracle Database 23ai Free

## Inicio rápido

Primero, crear el archivo de secretos (solo la primera vez). No está en el
repositorio: antes los secretos venían escritos como valores por defecto
dentro de `docker-compose.yml`, lo que equivalía a publicarlos.

```bash
cp docker/.env.example docker/.env
# editar docker/.env y reemplazar cada valor (el archivo trae los comandos
# para generarlos, p. ej. openssl rand -base64 64)
```

```bash
docker compose -f docker/docker-compose.yml up -d --build
```

Si falta algún secreto, Compose aborta indicando exactamente cuál.

Esto levanta Oracle 23ai Free, 2 instancias del backend, el microservicio de NLP, el WebSocket server y el frontend. El arranque inicial de Oracle tarda 1-2 minutos (más que MySQL).

**Carga del esquema (todavía manual — ver "Estado conocido" abajo):** una vez que `oracle-db` esté `healthy`, cargar el esquema desde `oracle/02_ddl_tablas.sql` en adelante (`01_usuario_y_esquema.sql` se salta: la imagen `gvenzl/oracle-free` ya crea el usuario `electrisys` vía las variables `APP_USER`/`APP_USER_PASSWORD`), conectado como ese usuario contra `//localhost:1521/FREEPDB1`.

Verificar:

```
Frontend / POS:        http://localhost
API:                    http://localhost/api/health
WebSocket:              http://localhost:8080/health
```

Login de prueba:

| Usuario | Email | Contraseña |
|---|---|---|
| Administrador | `admin@electrisys.com` | `password` |
| Vendedor | `vendedor@electrisys.com` | `password` |
| Dueño | `dueno@electrisys.com` | `password` |

### Probar el asistente

En la vista **Ventas**, abrir el botón flotante (esquina inferior derecha) y escribir, por ejemplo:

> *"No hay filtro de aceite original de Toyota para Hilux 2.7 gasolina 2024, ¿qué recomiendo?"*

### Desarrollo local sin Docker

```bash
# Backend
cd backend && composer install && php -S localhost:8099 -t public public/index.php

# Microservicio NLP
cd nlp-service && python -m venv venv && venv/Scripts/activate
pip install -r requirements.txt && uvicorn app.main:app --port 8103

# Frontend
cd frontend && npm install && npm run dev
```

## Pruebas

```bash
cd backend && composer test        # PHPUnit — 16 pruebas
cd nlp-service && pytest tests/    # pytest — 84 pruebas
```

Evaluación cuantitativa del asistente (accuracy de intención, precisión de NER, precisión@k del recomendador): [`nlp-service/docs/evaluacion.md`](nlp-service/docs/evaluacion.md).

## Documentación

| Documento | Contenido |
|---|---|
| [`docs/asistente-nlp.md`](docs/asistente-nlp.md) | Arquitectura del asistente NLP, decisiones de diseño, flujo de datos completo |
| [`docs/asistente-casos-limite.md`](docs/asistente-casos-limite.md) | Checklist de resiliencia (rate limiting, fallos del microservicio/backend, validaciones) |
| [`nlp-service/docs/evaluacion.md`](nlp-service/docs/evaluacion.md) | Métricas del modelo de intención, NER y recomendador sobre un set de prueba independiente |
| [`ESTRUCTURA.md`](ESTRUCTURA.md) | Historial de cambios de la infraestructura distribuida (mTLS, VPN, Istio, monitoreo, análisis de red) |
| [`oracle/docs/migracion-oracle.md`](oracle/docs/migracion-oracle.md) | Migración de MySQL a Oracle 23ai — hoy el motor real de la app (no solo el ejercicio académico original): PL/SQL, triggers, vistas, roles/privilegios, evidencia real de `EXPLAIN PLAN` y backup/recovery con Data Pump |

## Estado conocido / limitaciones

- **TLS entre backend y Oracle:** diferido, igual que ya pasaba con el mTLS de MySQL (nunca se validó de punta a punta en producción real). Oracle usa Wallets, un mecanismo distinto a los certificados PEM sueltos — no se abordó en esta migración. Conexión sin TLS dentro de la red interna de Docker/K8s.
- **Sin réplica de base de datos:** Oracle Database 23ai **Free** no soporta Data Guard/RAC (son features Enterprise) — a diferencia del MySQL primary+réplica que tenía el proyecto antes, hoy es una sola instancia. `Database::isWritable()`/failover automático se retiraron del backend por este motivo.
- **Carga del esquema Oracle:** todavía manual al crear el contenedor por primera vez (ver "Inicio rápido" arriba) — falta automatizarla vía el mecanismo de init-scripts de la imagen `gvenzl/oracle-free`.
- **Kubernetes/monitoreo para Oracle:** los manifiestos de `k8s/` (`mysql-primary.yaml`, etc.) y el exporter de Prometheus (`mysqld-exporter`) todavía apuntan a MySQL — pendientes de migrar al equivalente Oracle.
- **`database/`:** queda como referencia histórica del esquema MySQL original — ya no lo usa la aplicación ni `docker-compose.yml`. El esquema real vive en `oracle/`.
- **VPN/rutas de administración:** `/api/usuarios` y `/api/auditlog` requieren estar en la subred WireGuard (`10.100.0.0/24`); en desarrollo local (`127.0.0.1`, `172.29.0.1`) se permiten automáticamente.
- **Dataset de intención del asistente:** ~90 ejemplos; suficiente para una demo sólida (82% accuracy en un set de prueba independiente), pero se beneficiaría de ampliarse — ver "Próximos pasos" en `nlp-service/docs/evaluacion.md`.
- **Kubernetes/Istio:** los manifiestos en `k8s/` no se han validado contra un clúster real en este entorno.

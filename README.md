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
- **Base de datos:** Oracle Autonomous AI Database (Always Free) en Oracle Cloud, conexión mTLS con wallet — instancia única (sin réplica: el nivel gratuito no ofrece Data Guard/RAC). La imagen `gvenzl/oracle-free` queda solo como opción local (perfil `local` de Compose). PL/SQL: packages `pkg_ventas`/`pkg_reportes`, triggers de stock/auditoría, vistas de reporte — ver [`oracle/docs/migracion-oracle.md`](oracle/docs/migracion-oracle.md)
- **Tiempo real:** Node.js + WebSocket
- **Infraestructura:** Docker Compose, Kubernetes, Istio, WireGuard, stunnel (mTLS), Prometheus/Grafana

## Requisitos

- Docker Desktop (o Docker Engine + Compose v2)
- El wallet de la Autonomous Database (`Wallet_ELECTRISYS.zip`, se descarga desde la consola de Oracle Cloud; nunca se sube al repositorio)
- Para desarrollo sin Docker: PHP 8.2+ con la extensión `oci8` (requiere Oracle Instant Client), Composer, Node.js 20+, Python 3.11+

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

Esto levanta 2 instancias del backend, el microservicio de NLP, el WebSocket server y el frontend, conectados a la Autonomous Database de Oracle Cloud. Antes hay que preparar el wallet (una sola vez): `docker\preparar_wallet.ps1 -WalletZip "C:\ruta\Wallet_ELECTRISYS.zip"`, y poner `DB_PASS` (clave del usuario `ELECTRISYS`) en `docker/.env`. El contenedor `oracle-db` (perfil `local`) ya no arranca por defecto; usarlo exigiría volver a apuntar las variables `DB_*` del backend en `docker-compose.yml`.

**Carga del esquema en la nube (una sola vez por base):** `oracle\cargar_esquema_cloud.ps1 -WalletZip "C:\ruta\Wallet_ELECTRISYS.zip"` crea el usuario `ELECTRISYS` y corre los scripts `02`–`15`, paquetes, vistas, roles y el paquete de respaldo. Detalles, red y servidores en [`oracle/docs/despliegue-oracle-cloud.md`](oracle/docs/despliegue-oracle-cloud.md).

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
| [`docs/despliegue-produccion.md`](docs/despliegue-produccion.md) | Despliegue actual en Oracle Cloud (Always Free): 2 VMs + Autonomous Database, HTTPS con Let's Encrypt, DuckDNS, operación y límites |
| [`oracle/docs/despliegue-oracle-cloud.md`](oracle/docs/despliegue-oracle-cloud.md) | Detalle de la base en Oracle Cloud: wallet, carga del esquema, red, VMs, seguridad |
| [`oracle/docs/migracion-oracle.md`](oracle/docs/migracion-oracle.md) | Migración de MySQL a Oracle 23ai — hoy el motor real de la app (no solo el ejercicio académico original): PL/SQL, triggers, vistas, roles/privilegios, evidencia real de `EXPLAIN PLAN` y backup/recovery con Data Pump |

## Estado conocido / limitaciones

- **TLS entre backend y Oracle:** resuelto en la nube. La Autonomous Database exige mTLS y el backend se conecta con el wallet (`docker/wallet`, fuera del repositorio). El stunnel entre nginx y PHP-FPM sigue sin certificados en este despliegue (`PHP-FPM sin mTLS`), pero ambos comparten la red privada de Docker.
- **Sin réplica de base de datos:** Oracle Database 23ai **Free** no soporta Data Guard/RAC (son features Enterprise) — a diferencia del MySQL primary+réplica que tenía el proyecto antes, hoy es una sola instancia. `Database::isWritable()`/failover automático se retiraron del backend por este motivo.
- **Carga del esquema Oracle:** se hace una vez con `oracle/cargar_esquema_cloud.ps1`; no es idempotente (en una base ya cargada falla con `ORA-00955` a propósito).
- **Respaldos:** la base usa los respaldos automáticos de Autonomous Database (retención 60 días, visibles en la consola de Oracle). La pantalla "Respaldos" lista los `.dmp` de Data Pump leyendo el directorio de la base (`DBMS_CLOUD.LIST_FILES`). Usuarios, Respaldos y Auditoría se pueden ver sin VPN, pero las acciones que modifican algo ("Respaldar ahora", crear/editar/eliminar usuarios) exigen la VPN WireGuard (no desplegada en la nube; ver el túnel SSH en `docs/despliegue-produccion.md`) y la interfaz lo explica con una ventana.
- **Monitoreo en la nube:** Prometheus/Grafana no se desplegaron (las VMs gratuitas tienen 1 GB de RAM). En su lugar, `docker/vigilante-oracle.sh` corre por cron cada 30 min: comprueba `/api/health`, reinicia los contenedores si caen y mantiene activa la base (Oracle detiene una Always Free tras 7 días sin conexiones SQL).
- **Kubernetes/monitoreo para Oracle:** los manifiestos de `k8s/` (`mysql-primary.yaml`, etc.) y el exporter de Prometheus (`mysqld-exporter`) todavía apuntan a MySQL — pendientes de migrar al equivalente Oracle.
- **`database/`:** queda como referencia histórica del esquema MySQL original — ya no lo usa la aplicación ni `docker-compose.yml`. El esquema real vive en `oracle/`.
- **VPN/rutas de administración:** `/api/usuarios` y `/api/auditlog` requieren estar en la subred WireGuard (`10.100.0.0/24`); en desarrollo local (`127.0.0.1`, `172.29.0.1`) se permiten automáticamente.
- **Dataset de intención del asistente:** ~90 ejemplos; suficiente para una demo sólida (82% accuracy en un set de prueba independiente), pero se beneficiaría de ampliarse — ver "Próximos pasos" en `nlp-service/docs/evaluacion.md`.
- **Kubernetes/Istio:** los manifiestos en `k8s/` no se han validado contra un clúster real en este entorno.

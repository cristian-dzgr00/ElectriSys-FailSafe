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
│ Microservicio │◀─────────────────────│  Backend PHP  │────▶│  MySQL        │
│ NLP (FastAPI) │   X-Internal-Key     │  /asistente   │     │ primary+réplica│
└──────────────┘─────────────────────▶└──────────────┘     └──────────────┘
```

El asistente NLP (intención → entidades → recomendación → respuesta) está documentado en detalle en [`docs/asistente-nlp.md`](docs/asistente-nlp.md).

## Estructura del repositorio

```
Electrisys/
├── backend/              PHP (Slim) — API REST, patrones Observer/Strategy
├── frontend/             React + Vite — POS y asistente flotante
├── nlp-service/          Python (FastAPI) — clasificación de intención, NER, recomendador
├── database/             schema.sql, migraciones, seeds (catálogo real de repuestos)
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

- **Backend:** PHP 8.2, Slim Framework 4, PDO/MySQL, JWT (firebase/php-jwt)
- **Frontend:** React 18, Vite, axios, lucide-react
- **Microservicio NLP:** Python 3.11, FastAPI, scikit-learn (TF-IDF + regresión logística), rapidfuzz, pandas
- **Base de datos:** MySQL 8.0 (primary + réplica)
- **Tiempo real:** Node.js + WebSocket
- **Infraestructura:** Docker Compose, Kubernetes, Istio, WireGuard, stunnel (mTLS), Prometheus/Grafana

## Requisitos

- Docker Desktop (o Docker Engine + Compose v2)
- Para desarrollo sin Docker: PHP 8.2+, Composer, Node.js 20+, Python 3.11+, MySQL 8.0

## Inicio rápido

```bash
docker compose -f docker/docker-compose.yml up -d --build
```

Esto levanta MySQL (primary + réplica), 2 instancias del backend, el microservicio de NLP, el WebSocket server y el frontend, y carga automáticamente el catálogo real de repuestos (autopartes + maquinaria agrícola) la primera vez que se crea el volumen.

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

## Estado conocido / limitaciones

- **mTLS entre backend y MySQL:** los certificados no vienen generados (`tls/generate-certs.sh` debe correrse aparte); aun generándolos, el handshake mTLS actualmente falla en validación de certificado — pendiente de revisión en `tls/mysql/mysql-ssl.cnf`. El sistema funciona correctamente en modo sin TLS (fallback automático).
- **VPN/rutas de administración:** `/api/usuarios` y `/api/auditlog` requieren estar en la subred WireGuard (`10.100.0.0/24`); en desarrollo local (`127.0.0.1`, `172.29.0.1`) se permiten automáticamente.
- **Dataset de intención del asistente:** ~90 ejemplos; suficiente para una demo sólida (82% accuracy en un set de prueba independiente), pero se beneficiaría de ampliarse — ver "Próximos pasos" en `nlp-service/docs/evaluacion.md`.
- **Kubernetes/Istio:** los manifiestos en `k8s/` no se han validado contra un clúster real en este entorno.

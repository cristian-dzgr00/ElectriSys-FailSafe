# Estructura del proyecto ElectriSys

```
electrisys/
│
├── .gitignore                          [EDITADO]  agrega tls/ y captures/
│
├── backend/
│   ├── .env                            [EDITADO]  + WS_NOTIFY_KEY
│   ├── public/
│   │   └── index.php                   [EDITADO]  + VpnMiddleware en rutas admin
│   │                                              + WebSocketObserver registrado
│   └── src/
│       ├── config/
│       │   └── TlsConfig.php           [NUEVO]    Lee certs TLS para PDO mTLS
│       ├── middlewares/
│       │   ├── JwtMiddleware.php       (sin cambios)
│       │   ├── RoleMiddleware.php      (sin cambios)
│       │   └── VpnMiddleware.php       [NUEVO]    Restringe admin a IPs VPN
│       ├── models/
│       │   ├── Database.php            [EDITADO]  + TlsConfig para mTLS MySQL
│       │   └── VentaModel.php          (sin cambios)
│       ├── patterns/
│       │   ├── observer/
│       │   │   ├── AuditLogObserver.php   (sin cambios)
│       │   │   ├── GestorVentas.php       (sin cambios)
│       │   │   ├── VentaObserver.php      (sin cambios)
│       │   │   ├── VentaSubject.php       (sin cambios)
│       │   │   └── WebSocketObserver.php  [NUEVO]  Notifica al WS server
│       │   └── strategy/               (sin cambios)
│       └── routes/
│           ├── ventas.php              [EDITADO]  Usa GestorVentas con Observer
│           └── ... (resto sin cambios)
│
├── docker/
│   ├── docker-compose.yml             [EDITADO]  + websocket-server
│   │                                             + volumenes TLS en backends
│   │                                             + MySQL con flags SSL
│   ├── Dockerfile.backend             [EDITADO]  + stunnel instalado
│   ├── Dockerfile.frontend            (sin cambios)
│   └── entrypoint-backend.sh          [NUEVO]    Arranca stunnel + PHP-FPM
│
├── frontend/
│   ├── package.json                   [EDITADO]  versión bump a 2.0.0
│   └── src/
│       ├── components/
│       │   └── NotificationBell.jsx   [NUEVO]    Campana WS en tiempo real
│       ├── hooks/
│       │   └── useWebSocket.js        [NUEVO]    Hook WS con reconexión auto
│       └── pages/
│           └── Dashboard.jsx          [EDITADO]  + NotificationBell en header
│                                                  + useWebSocket para live updates
│
├── k8s/
│   ├── (ambassador-mapping.yaml)      [ELIMINADO] reemplazado por k8s/istio/gateway.yaml
│   ├── backend-deployment.yaml        [EDITADO]  + volumeMount TLS + annotations Prometheus
│   ├── backend-service.yaml           (sin cambios)
│   ├── configmap.yaml                 (sin cambios)
│   ├── frontend-deployment.yaml       (sin cambios)
│   ├── hpa.yaml                       (sin cambios)
│   ├── mysql-backup-cronjob.yaml      (sin cambios)
│   ├── mysql-primary.yaml             (sin cambios)
│   ├── mysql-replica.yaml             (sin cambios)
│   ├── namespace.yaml                 [EDITADO]  + istio-injection: enabled
│   ├── secrets-external.yaml          (sin cambios)
│   ├── secrets.yaml                   [EDITADO]  + WS_NOTIFY_KEY + GRAFANA_PASSWORD
│   ├── websocket-deployment.yaml      [NUEVO]    Deployment WS Node.js
│   ├── websocket-service.yaml         [NUEVO]    Service ClusterIP para WS
│   │
│   ├── istio/                         [NUEVO — módulo 3]
│   │   ├── istio-operator.yaml        Configuración de instalación Istio
│   │   ├── gateway.yaml               Punto de entrada HTTP/HTTPS
│   │   ├── virtual-service.yaml       Canary 90/10 + retries
│   │   ├── destination-rule.yaml      Circuit breaker + subsets
│   │   ├── peer-authentication.yaml   mTLS STRICT en todo el namespace
│   │   ├── request-authentication.yaml Validación JWT a nivel Istio
│   │   └── telemetry.yaml             Trazas Jaeger + métricas Prometheus
│   │
│   ├── monitoring/                    [NUEVO — módulo 1]
│   │   ├── prometheus-deployment.yaml Prometheus + ConfigMap + Service
│   │   ├── grafana-deployment.yaml    Grafana + Service
│   │   └── servicemonitor.yaml        ServiceMonitor para Prometheus Operator
│   │
│   ├── network-policies/              [NUEVO — módulo 2]
│   │   ├── deny-all.yaml              Bloquea todo el tráfico por defecto
│   │   ├── allow-frontend-to-backend.yaml  Nginx → PHP-FPM :9000
│   │   ├── allow-backend-to-mysql.yaml     Backend → MySQL :3306
│   │   ├── allow-ingress.yaml              Tráfico externo → frontend :80
│   │   └── allow-prometheus-scrape.yaml    Prometheus → exporters
│   │
│   ├── tls/                           [NUEVO — módulo 4]
│   │   └── tls-secret.yaml            Generado por generate-certs.sh
│   │
│   └── vpn/                           [NUEVO — módulo 5]
│       ├── wireguard-deployment.yaml  Deployment WireGuard en K8s
│       └── wireguard-service.yaml     Service LoadBalancer UDP :51820
│
├── monitoring/                        [NUEVO — módulo 1]
│   ├── prometheus.yml                 Configuración de scraping
│   ├── alert_rules.yml                Alertas de red y disponibilidad
│   ├── docker-compose.monitoring.yml  Stack local Prometheus+Grafana
│   └── grafana/
│       ├── datasources/
│       │   └── prometheus.yml         Datasource auto-configurado
│       └── dashboards/
│           └── electrisys.json        Dashboard de red y rendimiento
│
├── network-analysis/                  [NUEVO — módulo 6]
│   ├── README.md                      Guía de captura y análisis OSI
│   ├── captures/
│   │   └── .gitkeep                   (los .pcap se ignoran por .gitignore)
│   ├── scripts/
│   │   ├── capture-login.sh           TCP handshake + JWT en headers
│   │   ├── capture-api.sh             Peticiones REST completas
│   │   ├── capture-mysql.sh           Protocolo wire MySQL
│   │   └── capture-replication.sh     Binlog Primary→Replica
│   └── wireshark-profile/
│       └── electrisys.lua             Disector Lua para JWTs
│
├── nginx/
│   └── nginx.conf                     [EDITADO]  + /stub_status (Prometheus)
│                                                  + /ws proxy (WebSocket)
│                                                  + geo $is_vpn_client
│                                                  + restricción VPN en admin
│                                                  + fastcgi → stunnel (mTLS)
│
├── tls/                               [NUEVO — módulo 4]
│   ├── generate-certs.sh              Genera PKI completa (CA + 3 certs)
│   ├── ca/                            (generado por el script)
│   ├── mysql/
│   │   └── mysql-ssl.cnf              Config SSL para mysqld
│   ├── nginx/                         (generado por el script)
│   ├── php-fpm/                       (generado por el script)
│   └── stunnel/
│       ├── nginx-to-fpm.conf          Stunnel cliente (Nginx)
│       └── fpm-listener.conf          Stunnel servidor (PHP-FPM)
│
└── vpn/                               [NUEVO — módulo 5]
    ├── wg0.conf                       Config servidor WireGuard
    ├── client-template.conf           Plantilla para clientes
    └── setup-wireguard.sh             Script de instalación en Ubuntu
```

## Resumen de cambios

| | Nuevos | Editados | Eliminados |
|---|---|---|---|
| Backend PHP | 3 | 3 | 0 |
| Frontend React | 2 | 2 | 0 |
| Kubernetes | 16 | 4 | 1 |
| Docker | 1 | 2 | 0 |
| Infraestructura nueva | 18 | 0 | 0 |
| **Total** | **40** | **11** | **1** |

## Orden de aplicación recomendado

1. `./tls/generate-certs.sh` — generar PKI primero
2. `kubectl apply -f k8s/namespace.yaml` — habilitar Istio injection
3. `istioctl install -f k8s/istio/istio-operator.yaml`
4. **`./k8s/crear-configmaps-sql.sh`** — esquema, seeds y script de
   replicación como ConfigMaps. **Antes de aplicar los Deployments de
   MySQL**: sin esto la base arranca sin tablas y la réplica no replica.
5. `kubectl apply -f k8s/network-policies/` — segmentar red
6. `kubectl apply -f k8s/istio/` — service mesh
7. `kubectl apply -f k8s/monitoring/` — observabilidad
8. `kubectl apply -f k8s/tls/` + `k8s/vpn/` + `k8s/websocket-*.yaml`
9. `docker compose -f docker/docker-compose.yml -f monitoring/docker-compose.monitoring.yml up`

> El canary 90/10 ya no está en Istio: vive en el `upstream php_backend`
> de `nginx/nginx.conf` (pesos 9 y 1). Istio no puede dividir tráfico
> sobre el puerto 9000 porque habla FastCGI, no HTTP.

---

# Entrega: 5 features nuevas (inventario en vivo, pedidos, IA, backups, despliegue)

Todo lo de arriba corresponde a la entrega de infraestructura (mTLS, VPN,
Istio) y se mantiene. Lo que sigue son los archivos que agrega o toca esta
entrega. El motor de base de datos es **solo Oracle 23ai**: cualquier
referencia a MySQL en las secciones anteriores es del diseño descartado.

## Sprint 1 — Inventario en tiempo real

```
backend/src/models/VentaModel.php            [EDITADO]  + stockDe(), itemsDeVenta()
backend/src/patterns/observer/
  ├── GestorVentas.php                       [EDITADO]  emite 'stock_actualizado'
  ├── WebSocketObserver.php                  [EDITADO]  caso stock_actualizado (incluye
  │                                                     al vendedor) + payload genérico
  └── AuditLogObserver.php                   [EDITADO]  ignora 'stock_actualizado'
frontend/src/pages/Repuestos.jsx             [EDITADO]  stock en vivo + resalte + En vivo/Offline
frontend/src/pages/Dashboard.jsx             [EDITADO]  callback del WS en useCallback
                                                        (antes reconectaba en cada render)
```

frontend/src/components/NotificationBell.jsx [NUEVO]  campana en tiempo real;
                                                     filtra stock_actualizado
frontend/src/components/Navbar.jsx           [EDITADO] monta la campana

> El prompt asumía que `NotificationBell.jsx` ya existía; no era así: la
> campana nunca se había construido (`Bell` estaba importado sin usar en
> `Dashboard.jsx`). Se creó como componente propio en el Navbar, para que
> escuche el WebSocket desde cualquier vista.

## Sprint 2 — Pedidos a proveedor

Un "pedido" acá es una **orden de compra a un proveedor**, no un encargo de
cliente: el stock **sube al recibir**, no se reserva al crear.

```
oracle/10_pedidos.sql                        [NUEVO]  tablas, índices, 3 triggers, GRANTs
backend/src/models/PedidoModel.php           [NUEVO]  listar/buscar/crear/cambiarEstado/cancelar
backend/src/patterns/observer/GestorPedidos.php [NUEVO] Subject que reusa los Observers de ventas
backend/src/routes/pedidos.php               [NUEVO]  REST + RoleMiddleware(admin,dueno)
backend/public/index.php                     [EDITADO] registra pedidos.php
frontend/src/services/pedidosService.js      [NUEVO]
frontend/src/pages/Pedidos.jsx               [NUEVO]  tabla, filtros, modal, estados en vivo
frontend/src/App.jsx                         [EDITADO] ruta /pedidos + PrivateRoute roles={[...]}
frontend/src/components/Sidebar.jsx          [EDITADO] ítem Pedidos (admin y dueño)
frontend/src/components/BuscadorRepuesto.jsx [EDITADO] prop campoPrecio (compra vs venta)
frontend/src/components/Tooltip.jsx          [EDITADO] tooltips de los estados de pedido
```

## Sprint 3 — IA sobre el catálogo (modelo propio, sin LLM externo)

```
nlp-service/app/recommender/similares.py     [NUEVO]  productos relacionados (TF-IDF + coseno)
nlp-service/app/demanda/forecast.py          [NUEVO]  promedio móvil ponderado -> señal
nlp-service/app/recommender/client_backend.py [EDITADO] obtener_repuesto(), obtener_demanda()
nlp-service/app/main.py                      [EDITADO] GET /recomendaciones/{id}
                                                       GET /prediccion-demanda/{id}
                                                       GET /prediccion-demanda?ids= (lote)
nlp-service/tests/test_recomendaciones.py    [NUEVO]  12 tests de los modelos
nlp-service/tests/test_endpoints_ia.py       [NUEVO]  10 tests HTTP de los endpoints
backend/src/routes/repuestos.php             [EDITADO] GET /{id}/demanda + proxy /{id}/recomendaciones
                                                       GET /demanda/lote  (serie de N repuestos en 1 consulta)
                                                       GET /demanda/senales (proxy del lote)
frontend/src/pages/Repuestos.jsx             [EDITADO] sección "Sugerencias" en el modal
                                                       + badge de rotación en la tabla
frontend/src/services/ventasService.js       [EDITADO] repuestosService.recomendaciones()
                                                       + senalesDemanda(ids)
```

## Sprint 4 — Respaldos y recuperación

```
oracle/backup/10_directorio_backup_sysdba.sql [EDITADO] ruta Linux del volumen persistente
oracle/backup/backup_logico.sh                [EDITADO] credenciales por env + retención
oracle/backup/restaurar_logico.sh             [EDITADO] credenciales por env + procedimiento
oracle/backup/cron_backup.sh                  [NUEVO]  planificador diario (2 AM)
oracle/backup/11_pkg_backup_plsql.sql         [NUEVO]  pkg_backup con DBMS_DATAPUMP
oracle/cargar_esquema.sh                      [NUEVO]  carga el esquema en orden y con el usuario correcto
oracle/backup/12_recompilar_invalidos.sql     [NUEVO]  recompila lo que el impdp invalida
oracle/01_usuario_y_esquema.sql               [EDITADO] contraseña por parámetro (ya no versionada)
                                                        + re-ejecutable si el usuario/tablespace ya existen
oracle/docs/migracion-oracle.md               [EDITADO] credencial de ejemplo -> $DB_PASS
.dockerignore                                 [NUEVO]  contexto de build: 52MB -> 21MB
docker/docker-compose.backup.yml              [NUEVO]  servicio oracle-backup + volumen persistente
backend/src/routes/admin_backup.php           [NUEVO]  GET/POST /api/admin/backups (tras VPN)
frontend/src/pages/Backups.jsx                [NUEVO]  vista de respaldos (admin y dueño)
frontend/src/services/backupsService.js       [NUEVO]
```

k8s/oracle-backup-cronjob.yaml                [NUEVO]  CronJob 02:00 + PVC
k8s/oracle-restore-job.yaml                   [NUEVO]  Job manual de restauración
k8s/secrets.yaml                              [EDITADO] claves DB_* de Oracle

> El despliegue de producción es **Docker Compose**; los manifiestos de
> Kubernetes quedan para el entorno del curso. Ojo: `k8s/` todavía no tiene
> ningún manifiesto de Oracle (los `mysql-*.yaml` son del diseño
> descartado), así que el CronJob asume un Service `oracle-db` que hay que
> desplegar antes. Y el PVC debe montarse TAMBIÉN en el pod de Oracle:
> Data Pump escribe del lado del servidor, no del cliente.

## Sprint 5 — Despliegue

```
docs/despliegue-produccion.md                 [NUEVO]  guía completa (DuckDNS, Droplet, TLS, humo)
nginx/locations-electrisys.conf               [NUEVO]  rutas compartidas HTTP/HTTPS
nginx/nginx.prod.conf                         [NUEVO]  server 443 + redirect 80 + ACME
nginx/nginx.conf                              [EDITADO] incluye el archivo de rutas
docker/docker-compose.prod.yml                [NUEVO]  TLS, cierra puertos internos, APP_ENV
docker/Dockerfile.frontend                    [EDITADO] copia el archivo de rutas
docker/docker-compose.yml                     [EDITADO] monta oracle/ en /scripts, rutas nginx
docker/.env.example                           [EDITADO] DOMINIO, BACKUP_AL_ARRANCAR
backend/.env.example                          [EDITADO] BACKUP_PATH
.github/workflows/ci-cd.yml                   [EDITADO] fuera MySQL, + job test-nlp,
                                                        deploy k8s condicionado
```

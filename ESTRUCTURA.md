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

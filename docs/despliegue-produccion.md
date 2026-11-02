# Despliegue en producción — ElectriSys POS

Guía del despliegue actual: **Oracle Cloud (nivel Always Free) + dominio DuckDNS + HTTPS de Let's Encrypt**. Costo: USD 0.

> Esta guía reemplaza a la versión anterior, que describía un Droplet de DigitalOcean con Oracle en un contenedor. La base de datos ya no corre en Docker: es una **Autonomous AI Database** gestionada por Oracle.

Sitio en producción: https://electrisys.duckdns.org

---

## 1. Arquitectura

```
Navegador ──▶ electrisys.duckdns.org (DuckDNS) ──▶ IP pública de la VM web
                                                     │
        VM web  (E2.1.Micro)                         ▼
        nginx :80/:443 ──▶ backend-a / backend-b (PHP-FPM) ──mTLS + wallet──▶ Autonomous AI Database
                      └──▶ websocket-server (Node)                              (ELECTRISYS, us-ashburn-1)
                                  │
        VM nlp  (E2.1.Micro)      │ red privada de la VCN (8000 / 8081)
        nlp-service (FastAPI) ◀───┘
```

| Pieza | Dónde | Archivo de Compose |
|---|---|---|
| nginx + frontend, 2 backends PHP, WebSocket | VM `electrisys-web` | `docker-compose.yml` + `docker-compose.prod.yml` + `docker-compose.oracle-web.yml` |
| Microservicio NLP | VM `electrisys-nlp` | `docker-compose.nlp.yml` (independiente) |
| Base de datos | Autonomous AI Database `ELECTRISYS` | — (se carga con `oracle/cargar_esquema_cloud.ps1`) |

Por qué dos VMs `VM.Standard.E2.1.Micro` (x86, 1 GB): las instancias Ampere A1 del nivel gratuito respondían `Out of host capacity` en los tres dominios de disponibilidad de Ashburn, y el stack completo no cabe en una sola VM de 1 GB. Si hubiera capacidad A1 (máximo gratuito: 2 OCPU / 12 GB), todo cabe en una VM y el `Dockerfile.backend` ya soporta arm64.

---

## 2. Cuentas y herramientas

| Qué | Para qué |
|---|---|
| Cuenta de Oracle Cloud (región home `us-ashburn-1`) | Base, VMs y red. Los recursos Always Free **solo** se crean en la región home |
| Cuenta de [DuckDNS](https://www.duckdns.org) | Subdominio `electrisys` y su token |
| Docker Desktop (equipo de desarrollo) | Construir las imágenes `linux/amd64` |
| OCI CLI (opcional) | Crear la red y las VMs por línea de comandos; también se puede hacer en la consola web |
| SQL*Plus + el wallet | Cargar y verificar la base |

---

## 3. Base de datos

Ver [`oracle/docs/despliegue-oracle-cloud.md`](../oracle/docs/despliegue-oracle-cloud.md): descarga del wallet, `cargar_esquema_cloud.ps1` y notas de conexión. Resumen:

- Servicio de conexión: `electrisys_tp` (mTLS con wallet).
- El wallet va en `docker/wallet/` (lo prepara `docker/preparar_wallet.ps1`; está ignorado por Git).
- `DB_PASS` en `docker/.env` es la clave del usuario `ELECTRISYS`.

---

## 4. Red en Oracle Cloud

Una VCN (`10.0.0.0/16`) con internet gateway, ruta por defecto a ese gateway y una subred pública. En la *security list* de la subred:

| Puerto | Origen | Para qué |
|---|---|---|
| 22 | `0.0.0.0/0` | SSH |
| 80, 443 | `0.0.0.0/0` | HTTP (redirección y desafío ACME) y HTTPS |
| 8000, 8081 | `10.0.0.0/16` | Solo entre las VMs: NLP y retorno del NLP al backend |

**Ojo con el firewall del propio Ubuntu:** la imagen de Oracle trae reglas `iptables` que solo dejan pasar el 22, así que abrir la security list no basta. `docker/preparar-vm-oracle.sh` abre los puertos y los persiste.

---

## 5. Preparar las VMs

Crear dos instancias `VM.Standard.E2.1.Micro` con Ubuntu 22.04, IP pública, disco de 50 GB y tu llave SSH. En el dominio de disponibilidad que ofrezca el shape gratuito (en Ashburn, AD-2).

En cada VM (con `scp` del script y luego, por SSH):

```bash
# VM web: abre 80 y 443
bash preparar-vm-oracle.sh "80 443"
# VM nlp: abre 8000 solo a la red privada
bash preparar-vm-oracle.sh "8000@10.0.0.0/16"
```

El script crea 2 GB de swap (imprescindible con 1 GB de RAM), abre y persiste el firewall e instala Docker.

---

## 6. Dominio (DuckDNS)

1. En duckdns.org, crear el subdominio y apuntarlo a la IP pública de la **VM web**.
2. La IP pública de Oracle es fija mientras la instancia exista, así que no hace falta el actualizador periódico. Si se recrea la VM, actualizar la IP en el panel o con:

```bash
curl "https://www.duckdns.org/update?domains=SUBDOMINIO&token=TOKEN&ip=NUEVA_IP"   # responde OK
```

3. Verificar que resuelve antes de pedir el certificado: `dig +short SUBDOMINIO.duckdns.org`.

---

## 7. Imágenes y archivos

Compilar el frontend dentro de 1 GB de RAM falla por falta de memoria, así que **las imágenes se construyen en el equipo de desarrollo** y se suben ya hechas:

```powershell
cd docker
$env:DOMINIO="electrisys.duckdns.org"; $env:NLP_HOST="10.0.0.11"; $env:WEB_PRIVATE_IP="10.0.0.32"
$env:DOCKER_DEFAULT_PLATFORM="linux/amd64"
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.oracle-web.yml build backend-a websocket-server frontend
docker compose -f docker-compose.nlp.yml build        # requiere BACKEND_URL, NLP_BIND_IP en el entorno
docker save electrisys/backend:oracle electrisys/websocket:oracle electrisys/frontend:oracle -o img_web.tar
docker save electrisys/nlp:oracle -o img_nlp.tar
```

Subir cada `.tar` a su VM y cargarlo con `docker load -i`. Luego subir el código (`backend/`, `nginx/`, `tls/stunnel/`, `docker/` con el wallet) a `~/electrisys/`. **No subir** `tls/ca/ca.key` ni otras llaves privadas.

Crear `docker/.env` en cada VM (modo `600`), con los secretos del proyecto más:

| VM | Variables extra |
|---|---|
| web | `DB_PASS`, `DOMINIO`, `NLP_HOST` (IP privada del NLP), `WEB_PRIVATE_IP` (IP privada de la web) |
| nlp | `JWT_SECRET` y `NLP_INTERNAL_KEY` (idénticos a los de la web), `BACKEND_URL=http://<IP privada web>:8081`, `NLP_BIND_IP` |

> `JWT_SECRET` debe ser el mismo en backend, WebSocket y NLP. Si divergen, el login funciona pero el WebSocket y el asistente fallan sin un error claro.

---

## 8. Certificado HTTPS

Con el dominio ya resolviendo y el puerto 80 libre (antes de levantar nginx):

```bash
sudo apt-get install -y certbot && sudo mkdir -p /var/www/certbot
sudo certbot certonly --standalone -d SUBDOMINIO.duckdns.org --agree-tos --register-unsafely-without-email --non-interactive
```

Para que la renovación funcione con nginx ocupando el puerto 80, pasar el autenticador a `webroot` y agregar el hook que recarga nginx:

```bash
# /etc/letsencrypt/renewal/SUBDOMINIO.duckdns.org.conf
authenticator = webroot
webroot_path = /var/www/certbot,
[[webroot_map]]
SUBDOMINIO.duckdns.org = /var/www/certbot

# /etc/letsencrypt/renewal-hooks/deploy/recargar-nginx.sh  (chmod +x)
cd /home/ubuntu/electrisys/docker && docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.oracle-web.yml exec -T frontend nginx -s reload
```

Probar con `sudo certbot renew --dry-run --no-random-sleep-on-renew` (sin esa opción espera un retardo aleatorio de unos 4 minutos y parece colgado).

El dominio también debe estar en `nginx/nginx.prod.conf` (`server_name` y rutas del certificado).

---

## 9. Levantar los servicios

```bash
# VM web
cd ~/electrisys/docker
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.oracle-web.yml \
  up -d --no-build backend-a backend-b websocket-server frontend

# VM nlp
cd ~/electrisys/docker && docker compose -f docker-compose.nlp.yml up -d --no-build
```

Todos los servicios tienen `restart: unless-stopped` y Docker arranca con el sistema: tras un reinicio de la VM el sitio vuelve solo (probado: ~90 s la web, ~105 s el NLP).

---

## 10. Verificación

Comprobaciones automatizadas desde fuera (todas pasan en producción):

| # | Qué | Resultado esperado |
|---|---|---|
| 1 | `curl -I https://DOMINIO/` | 200 y certificado válido; `http://` responde 301 a HTTPS |
| 2 | `GET /api/health` | `status: ok` y `db.status: ok` |
| 3 | Login como administrador | Devuelve token y entra al dashboard |
| 4 | Registrar una venta | Stock del repuesto baja en 1 y el IVA (19 %) es correcto |
| 5 | **Inventario en vivo** | Con dos sesiones abiertas en *Repuestos*, la venta de una baja el stock en la otra **sin recargar**; indicador "En vivo" |
| 6 | Anular la venta | Estado "Anulada" y el stock vuelve a subir en ambas sesiones |
| 7 | Crear y cancelar un pedido a proveedor | El stock no cambia hasta marcarlo "recibido" |
| 8 | Asistente (chat) | Consulta "pastillas de freno para un Chevrolet Spark" devuelve intención, entidades y sugerencias del catálogo |
| 9 | Reinicio de cada VM | Los servicios vuelven solos |

---

## 11. Operación

- **Vigilante:** `docker/vigilante-oracle.sh`, por cron cada 30 minutos en la VM web (`*/30 * * * * /home/ubuntu/electrisys/docker/vigilante-oracle.sh`). Consulta `/api/health`, reinicia los contenedores si no responde y registra el NLP. Escribe en `~/electrisys/vigilante.log`. Como `/api/health` ejecuta SQL contra la base, también evita que Oracle la detenga por inactividad.
- **Actualizar:** reconstruir las imágenes en el equipo de desarrollo, subirlas y repetir `docker load` + `docker compose ... up -d --no-build`.
- **Respaldos:** los hace Oracle automáticamente (Autonomous Database, retención 60 días; se ven en la consola). La pantalla "Respaldos" de la app exige la VPN WireGuard, que **no** está desplegada en la nube.
- **Monitoreo:** Prometheus y Grafana no se desplegaron (no caben en 1 GB). El vigilante cubre disponibilidad básica; las métricas de la base están en la consola de Oracle (*Performance Hub*).

---

## 11.1 Entrar a Usuarios y Respaldos (rutas de administración)

Las pantallas **Usuarios**, **Respaldos** y **Auditoría** se pueden **ver** sin VPN: el backend permite únicamente los `GET` de sus listados, siempre con la sesión iniciada. Cualquier acción que modifique algo (crear, editar o desactivar usuarios, «Respaldar ahora», descargar la exportación CSV) exige que la petición llegue desde la red VPN `10.100.0.0/24` o desde una IP interna (`VpnMiddleware`). Fuera de ella la interfaz muestra la ventana «Acceso por VPN requerido» y la API responde 403 con `code: VPN_REQUIRED`. Es el comportamiento diseñado, no una falla. El frontend sabe si está en la VPN consultando `GET /api/vpn/estado`.

No existe otra dirección web: es **el mismo sitio, el mismo backend y la misma base**. Solo cambia por dónde llega la petición. Como WireGuard no está desplegado, la forma de entrar es un **túnel SSH** hacia la VM web:

```powershell
ssh -i $env:USERPROFILE\.ssh\electrisys_oracle -N -L 8443:127.0.0.1:443 ubuntu@IP_PUBLICA_VM_WEB
```

Dejar esa ventana abierta y abrir **https://localhost:8443**. El navegador avisa que el certificado no coincide (es el de `electrisys.duckdns.org`): *Avanzado → Continuar*. Iniciar sesión con un usuario administrador. Todo lo que se cambie ahí queda en la misma base y se ve en el sitio normal.

Verificado en producción: por el túnel, Usuarios lista a los usuarios y Respaldos carga sin errores; "Respaldar ahora" genera un `.dmp` y su `.log` en `ELECTRISYS_BACKUP_DIR` (dentro del servidor de la base). La pantalla Respaldos los lista leyendo ese directorio con `DBMS_CLOUD.LIST_FILES`, lo que requiere una sola vez `GRANT EXECUTE ON DBMS_CLOUD TO electrisys` (script `oracle/backup/12_listado_backups_cloud.sql`, lo corre `ADMIN`). Los `.dmp` no se descargan desde la web: contienen hashes de contraseñas.

Desplegar WireGuard (`vpn/setup-wireguard.sh`) es la alternativa para dar acceso a más personas: exige abrir el puerto UDP 51820 en la security list y en `iptables`, e instalar el cliente WireGuard en cada equipo.

---

## 12. Límites del nivel gratuito

Según la documentación de Oracle (ver `oracle/docs/despliegue-oracle-cloud.md`):

- **Autonomous Database Always Free:** se **detiene sola tras 7 días de inactividad** (sin conexiones SQL ni uso de CPU) conservando los datos; se arranca con *Start* en la consola. Si permanece detenida o inactiva **90 días acumulados**, puede ser eliminada de forma permanente.
- **VMs Always Free:** Oracle puede reclamar las inactivas. Se consideran inactivas si, durante 7 días, el percentil 95 de CPU y el uso de red son ambos menores al 20 % (en A1 también la memoria). Una VM Micro con poco tráfico puede cumplir ese criterio: conviene revisar el correo de la cuenta de Oracle.
- Los recursos Always Free solo existen en la región home de la tenancy.

---

## Problemas frecuentes

| Síntoma | Causa probable |
|---|---|
| El sitio no responde pero la VM está encendida | `iptables` de la VM sin los puertos 80/443 (la security list sola no alcanza) |
| certbot: "Challenge failed" | DuckDNS aún no apunta a la IP, o el puerto 80 está ocupado/cerrado |
| `certbot renew --dry-run` parece colgado | Retardo aleatorio de ~4 min; usar `--no-random-sleep-on-renew` |
| `/api/health` con `db.status: error` | Base detenida por inactividad (usar *Start* en la consola de Oracle) o wallet/`DB_PASS` incorrectos |
| Indicador **Offline** en Repuestos | `JWT_SECRET` distinto entre servicios, o el bloque `/ws` de nginx no quedó incluido |
| El asistente no responde | NLP caído o `NLP_HOST`/`BACKEND_URL` mal puestos; ver `docker logs es_nlp_service` |
| La VM mata contenedores por falta de memoria | Falta el swap de 2 GB (`preparar-vm-oracle.sh`) |
| `Out of host capacity` al crear una VM A1 | Sin capacidad ARM en la región; usar `E2.1.Micro` o reintentar más tarde |

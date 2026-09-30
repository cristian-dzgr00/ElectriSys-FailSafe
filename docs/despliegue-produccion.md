# Despliegue en producción — ElectriSys POS

Guía paso a paso para poner el POS en línea en un Droplet de DigitalOcean con
dominio DuckDNS y HTTPS de Let's Encrypt. Pensada para que cualquiera del
equipo pueda ejecutarla sin haber participado del desarrollo.

**Stack desplegado:** Oracle 23ai Free + 2 backends PHP + websocket-server +
nlp-service + frontend/NGINX, todo con Docker Compose. Kubernetes **no** se
usa en este despliegue (los manifiestos de `k8s/` quedan para el ejercicio de
la materia).

---

## 0. Antes de empezar

Vas a necesitar:

- Una cuenta de DigitalOcean con el crédito del [GitHub Student Developer
  Pack](https://education.github.com/pack) ya aplicado.
- Una cuenta de [DuckDNS](https://www.duckdns.org) (login con GitHub).
- Acceso SSH y el repositorio clonable desde el servidor.

Tiempo estimado: 45–60 minutos la primera vez.

---

## 1. Crear el Droplet

En el panel de DigitalOcean: **Create → Droplets**.

| Opción | Valor |
|---|---|
| Imagen | Marketplace → **Docker on Ubuntu** (trae Docker + Compose listos) |
| Plan | Basic, **4 GB RAM / 2 vCPU** mínimo (8 GB si el presupuesto lo permite) |
| Región | La más cercana al negocio |
| Autenticación | Clave SSH (no contraseña) |

> **Por qué 4 GB como mínimo:** Oracle 23ai Free solo, en reposo, ronda los
> 1.5–2 GB. Con 2 GB totales el contenedor de la base arranca y muere por OOM
> a mitad de la carga inicial de los scripts, y el síntoma —un healthcheck que
> nunca pasa— no dice que faltó memoria.

Anotá la **IP pública** que te asigna.

---

## 2. Dominio en DuckDNS

1. Entrá a duckdns.org, creá el subdominio (ej. `electrisys-pos`) y apuntalo a
   la IP del Droplet.
2. Copiá tu **token** del dashboard.
3. En el Droplet, instalá el actualizador oficial para que el registro no
   quede desactualizado si DigitalOcean cambia la IP:

```bash
mkdir -p ~/duckdns
cat > ~/duckdns/duck.sh <<'EOF'
echo url="https://www.duckdns.org/update?domains=TU-SUBDOMINIO&token=TU-TOKEN&ip=" \
  | curl -k -o ~/duckdns/duck.log -K -
EOF
chmod 700 ~/duckdns/duck.sh
~/duckdns/duck.sh && cat ~/duckdns/duck.log   # debe decir OK

# cada 5 minutos
(crontab -l 2>/dev/null; echo "*/5 * * * * ~/duckdns/duck.sh >/dev/null 2>&1") | crontab -
```

4. **Verificá la resolución antes de seguir.** Si esto no devuelve la IP del
   Droplet, certbot va a fallar y el error no va a mencionar el DNS:

```bash
dig +short TU-SUBDOMINIO.duckdns.org
```

---

## 3. Firewall

Desde el panel de DigitalOcean (**Networking → Firewalls**) o con `doctl`:

| Dirección | Puerto | Origen |
|---|---|---|
| Entrada | 22 (SSH) | Tu IP, o la red del equipo |
| Entrada | 80 (HTTP) | Todas — lo necesita Let's Encrypt |
| Entrada | 443 (HTTPS) | Todas |

**Todo lo demás cerrado.** En particular el **1521/1522 de Oracle**: el backend
le habla a la base por la red interna de Docker, nunca por la IP pública. El
override `docker-compose.prod.yml` además deja de publicar esos puertos, así
que quedan dos capas y no una.

---

## 4. Clonar y configurar

```bash
git clone <URL-del-repo> electrisys && cd electrisys

cp docker/.env.example  docker/.env
cp backend/.env.example backend/.env
```

Editá `docker/.env` y reemplazá **todos** los valores `CAMBIAR_…` por secretos
generados de verdad:

```bash
openssl rand -base64 64   # JWT_SECRET
openssl rand -hex 32      # WS_NOTIFY_KEY
openssl rand -hex 32      # NLP_INTERNAL_KEY
openssl rand -base64 24   # ORACLE_PASSWORD y DB_PASS (uno distinto cada uno)
openssl rand -base64 24   # GRAFANA_PASSWORD
```

Y poné tu dominio:

```dotenv
DOMINIO=TU-SUBDOMINIO.duckdns.org
```

> `JWT_SECRET` tiene que ser el **mismo** para backend, websocket-server y
> nlp-service — por eso los tres lo toman de `docker/.env` y no de sus propios
> archivos. Si divergen, la sesión inicia pero el WebSocket rechaza la conexión
> y el asistente deja de responder, sin un error que lo explique.

Ninguno de los dos `.env` se sube al repositorio (`.gitignore` los cubre).
Verificalo antes de commitear cualquier cosa: `git status --short`.

Ajustá el dominio en la config de NGINX de producción:

```bash
sed -i "s/electrisys-pos.duckdns.org/TU-SUBDOMINIO.duckdns.org/g" nginx/nginx.prod.conf
```

---

## 5. Certificado HTTPS

Primera emisión, con el puerto 80 libre (todavía no levantaste el stack):

```bash
sudo apt-get update && sudo apt-get install -y certbot
sudo mkdir -p /var/www/certbot

sudo certbot certonly --standalone \
  -d TU-SUBDOMINIO.duckdns.org \
  --agree-tos -m TU-CORREO --no-eff-email
```

Queda en `/etc/letsencrypt/live/TU-SUBDOMINIO.duckdns.org/`, que es lo que monta
el contenedor de nginx.

**Renovación automática** (los certificados vencen a los 90 días). El paquete de
Ubuntu ya instala un systemd timer; lo que falta es que nginx recargue el
certificado nuevo y que la validación no choque con el puerto 80 ocupado:

```bash
sudo mkdir -p /etc/letsencrypt/renewal-hooks/deploy
sudo tee /etc/letsencrypt/renewal-hooks/deploy/recargar-nginx.sh >/dev/null <<'EOF'
#!/bin/sh
cd /root/electrisys/docker && docker compose exec -T frontend nginx -s reload
EOF
sudo chmod +x /etc/letsencrypt/renewal-hooks/deploy/recargar-nginx.sh

# renovar en modo webroot: no necesita el puerto 80 libre, lo sirve nginx
sudo certbot certonly --webroot -w /var/www/certbot \
  -d TU-SUBDOMINIO.duckdns.org --force-renewal --dry-run
```

Ajustá la ruta `/root/electrisys` si clonaste en otro lado. Comprobá el timer
con `systemctl list-timers | grep certbot`.

---

## 6. Levantar el stack

```bash
cd docker
docker compose -f docker-compose.yml \
               -f docker-compose.backup.yml \
               -f docker-compose.prod.yml up -d
```

El **primer arranque de Oracle tarda varios minutos**: la imagen crea la base y
corre todos los scripts de `oracle/`. Seguilo con:

```bash
docker compose logs -f oracle-db          # esperá "DATABASE IS READY TO USE"
docker compose ps                          # todos healthy
```

Si es una instalación desde cero, los scripts `01`–`09` se cargan solos. Los
dos que **no** están en esa carga automática hay que correrlos a mano una vez:

```bash
# tablas de pedidos a proveedor (Sprint 2)
docker compose exec -T oracle-db sqlplus -S \
  electrisys/"$DB_PASS"@//localhost:1521/freepdb1 < ../oracle/10_pedidos.sql

# DIRECTORY de Data Pump — requiere SYSDBA
docker compose exec -T oracle-db sqlplus -S / as sysdba \
  < ../oracle/backup/10_directorio_backup_sysdba.sql

# package de respaldo bajo demanda
docker compose exec -T oracle-db sqlplus -S \
  electrisys/"$DB_PASS"@//localhost:1521/freepdb1 < ../oracle/backup/11_pkg_backup_plsql.sql
```

### Monitoreo

```bash
docker compose -f docker-compose.yml \
               -f ../monitoring/docker-compose.monitoring.yml up -d
```

Grafana no debe quedar expuesto: entrá por un túnel SSH
(`ssh -L 3000:localhost:3000 root@IP`) en vez de abrir el puerto en el firewall.

---

## 7. Datos: arrancar limpio o migrar

- **Limpio:** no hagas nada, `oracle/05_seed.sql` ya cargó los datos de ejemplo.
- **Migrando desde desarrollo:** usá el flujo de respaldo, no copies archivos
  `.sql` a mano. En la máquina de origen generá el dump con
  `oracle/backup/backup_logico.sh`, copialo al Droplet con `scp` dentro del
  volumen de respaldos, y restauralo siguiendo el procedimiento del encabezado
  de `oracle/backup/restaurar_logico.sh`. Probalo primero contra un esquema de
  staging.

---

## 8. Prueba de humo

Con `https://TU-SUBDOMINIO.duckdns.org` ya en línea, verificá **a mano**:

| # | Qué | Cómo |
|---|---|---|
| 1 | Candado válido | El navegador no debe advertir nada; el emisor es Let's Encrypt, no un certificado autofirmado |
| 2 | Login y venta | Entrá, registrá una venta, comprobá que el stock baja |
| 3 | **Inventario en vivo** | Dos navegadores distintos con dos usuarios, ambos en *Repuestos*. Registrá una venta en uno: el stock del otro baja en menos de 2 s, sin recargar, y el indicador dice **En vivo** (es `wss://`) |
| 4 | Anulación | Anulá esa venta: el stock vuelve a subir en ambos |
| 5 | **Pedidos** | Como admin, creá un pedido a proveedor, marcalo *recibido*: el stock sube y se propaga a *Repuestos* |
| 6 | **Sugerencias de IA** | Abrí un repuesto: aparecen productos relacionados y la señal de reabastecimiento |
| 7 | **Respaldo** | Conectado a la VPN, entrá a *Respaldos* → "Respaldar ahora". El `.dmp` aparece en la lista a los pocos segundos |
| 8 | Respaldo automático | `docker compose logs oracle-backup` debe mostrar el próximo backup programado |

Si el paso 3 falla pero el resto anda, mirá `docker compose logs websocket-server`
y confirmá que `JWT_SECRET` es idéntico en los tres servicios.

---

## 9. Actualizar el sistema desplegado

```bash
cd ~/electrisys && git pull
cd docker && docker compose -f docker-compose.yml \
                            -f docker-compose.backup.yml \
                            -f docker-compose.prod.yml up -d --build
```

Antes de una actualización que toque la base, dispará un respaldo manual desde
la vista *Respaldos*.

---

## Problemas frecuentes

| Síntoma | Causa probable |
|---|---|
| certbot: "Challenge failed for domain" | El DNS de DuckDNS todavía no resuelve a la IP, o el puerto 80 está ocupado/cerrado |
| La página carga pero el indicador dice **Offline** | `JWT_SECRET` distinto entre servicios, o el bloque `/ws` de nginx no quedó incluido |
| `oracle-db` reiniciándose en bucle | Memoria insuficiente: el Droplet de 2 GB no alcanza |
| Sin sugerencias en Repuestos | `nlp-service` caído — la vista sigue funcionando; revisá `docker compose logs nlp-service` |
| *Respaldos* responde 403 | Esa sección exige estar dentro de la VPN WireGuard (ver `vpn/`) |
| El `.dmp` no aparece nunca | El `DIRECTORY` de Oracle apunta a una ruta que el volumen no monta — revisá el paso 6 |

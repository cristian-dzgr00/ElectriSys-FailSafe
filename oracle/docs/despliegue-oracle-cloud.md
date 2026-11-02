# Despliegue de la base de datos en Oracle Cloud

Base: Autonomous AI Database (Always Free), región US East (Ashburn), nombre `ELECTRISYS`, tipo Transaction Processing.
Servicios disponibles: `electrisys_high`, `_medium`, `_low`, `_tp`, `_tpurgent` (conexión mTLS con wallet).

## Carga del esquema
1. Descargar el wallet (Database connection → Download wallet) y guardarlo FUERA del repositorio.
2. Desde la carpeta `oracle`: `.\cargar_esquema_cloud.ps1 -WalletZip "C:\ruta\Wallet_ELECTRISYS.zip"`
3. El script pide la clave de `ADMIN` y define la de `ELECTRISYS`; deja el log en `oracle/logs/`.

Scripts propios de la nube: `01_usuario_y_esquema_cloud.sql`, `09_usuarios_demo_cloud.sql`, `backup/10_directorio_backup_cloud.sql`. Los demás (02–08, 10–16, backup/11) se reutilizan sin cambios.

## Conexión de la aplicación
Definir en el `.env` del backend `DB_WALLET_DIR` y `DB_TNS_ALIAS` (ver `.env.example`). El `sqlnet.ora` del wallet debe tener `DIRECTORY` apuntando a la carpeta donde queda el wallet en el servidor/contenedor. Requiere Oracle Instant Client 19 o superior en la imagen de PHP.

## Servidores de la aplicación (Oracle Cloud Always Free)
La aplicación corre en dos VMs `VM.Standard.E2.1.Micro` (x86, 1 GB, gratis) de la misma tenancy, en la misma región que la base (us-ashburn-1). Se usan Micro y no Ampere A1 porque A1 devolvía `Out of host capacity` en los tres dominios de disponibilidad de Ashburn.

| VM | Corre | Archivo compose |
|---|---|---|
| `electrisys-web` | nginx (HTTPS), `backend-a`, `backend-b`, WebSocket | `docker-compose.yml` + `.prod.yml` + `.oracle-web.yml` |
| `electrisys-nlp` | microservicio NLP | `docker-compose.nlp.yml` |

- **Red:** una VCN `electrisys-vcn` (10.0.0.0/16) con subred pública. La security list abre 22/80/443 al exterior y 8000/8081 solo dentro de la VCN. Además el firewall de Ubuntu de Oracle (`iptables`) solo deja pasar el 22 por defecto, así que 80/443 se abren a mano (y se persisten en `/etc/iptables/rules.v4`).
- **Memoria:** cada VM tiene 2 GB de swap (`/swapfile`). Las imágenes se construyen en el equipo de desarrollo (`DOCKER_DEFAULT_PLATFORM=linux/amd64`) y se suben con `docker save`/`docker load`: compilar el frontend en 1 GB falla por OOM.
- **Variables extra en `docker/.env`:** `DOMINIO`, `DB_PASS` (clave de `ELECTRISYS`), y según la VM `NLP_HOST` y `WEB_PRIVATE_IP` (web) o `BACKEND_URL` y `NLP_BIND_IP` (nlp).
- **HTTPS:** Let's Encrypt con certbot en la VM web. La renovación usa el modo `webroot` (`/var/www/certbot`) porque nginx ocupa el puerto 80, y el hook `/etc/letsencrypt/renewal-hooks/deploy/recargar-nginx.sh` recarga nginx.
- **DuckDNS:** `electrisys.duckdns.org` apunta a la IP pública de `electrisys-web` (fija mientras la instancia exista).
- **Vigilante:** `docker/vigilante-oracle.sh` corre por cron cada 30 min en la VM web. Consulta `/api/health` (ejecuta `SELECT 1` en la base, lo que evita la parada por inactividad), reinicia los contenedores si caen y deja el registro en `~/electrisys/vigilante.log`.
- **Guía completa del despliegue:** `docs/despliegue-produccion.md`.

Reiniciar el servicio en la VM web:
```bash
cd ~/electrisys/docker
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.oracle-web.yml up -d --no-build backend-a backend-b websocket-server frontend
```
En la VM NLP: `docker compose -f docker-compose.nlp.yml up -d --no-build`.

## Seguridad
Nunca subir el wallet, las claves de `ADMIN`/`ELECTRISYS` ni la carpeta `logs/` al repositorio.
Los usuarios de demostración (`admin@electrisys.com` / `password`) siguen activos: cambiar sus claves antes de dejar el sitio abierto al público.

## Límites del nivel gratuito a tener en cuenta
- Los recursos Always Free solo se crean en la región home de la tenancy (aquí us-ashburn-1).
- Una Autonomous Database Always Free se detiene tras 7 días sin actividad; las instancias Always Free inactivas pueden ser reclamadas por Oracle.

## Limitaciones conocidas
- Data Pump en Autonomous deja los `.dmp` dentro del servidor de la base; el listado de respaldos del backend (`BACKUP_PATH`) no los ve. Para sacarlos hay que copiarlos a Object Storage.

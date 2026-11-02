# Feature: despliegue-oracle-cloud

## Objetivo
Base de datos en Oracle Cloud (Autonomous AI Database, Always Free, us-ashburn-1) y la app publicada en https://electrisys.duckdns.org funcionando, sin costo.

## Problema
- La suscripción Azure for Students quedó `Disabled` (crédito agotado): `electrisys-vm` desasignada y el sitio sin respuesta.
- Decisión del usuario (2026-11-01): mover el servidor a Oracle Cloud Always Free, costo USD 0, base en Oracle Cloud.
- Ampere A1 devolvió `Out of host capacity` en los 3 AD de Ashburn (4 rondas, ~1 h). Se pasó a dos VMs `E2.1.Micro`.

## Alcance autorizado
- Oracle Cloud tenancy `dzgrcristian31`: VCN, subred, reglas, VMs (sesión `oci` perfil `electrisys`).
- Cargar/verificar el esquema en ELECTRISYS; clave definida por el usuario.
- Repuntar DuckDNS (token del usuario, guardado fuera del repo en `~/.electrisys-secrets`).
- Azure: solo lectura.

## Tareas
- [x] T1 `Dockerfile.backend` compatible con amd64 y arm64. Evidencia: build amd64 OK y `php -m` lista `oci8`; URLs ARM verificadas (HEAD 200). La rama arm64 no se ejercitó (no hubo VM A1).
- [x] T2 Infraestructura Oracle: VCN `electrisys-vcn`, IGW, subred pública, security list 22/80/443 + 8000/8081 solo VCN; VMs `electrisys-web` (150.136.165.160, 10.0.0.32) y `electrisys-nlp` (129.80.120.49, 10.0.0.11), Ubuntu 22.04, 2 GB swap, iptables 80/443 y Docker. Ruta: inline.
- [x] T3 Esquema en ELECTRISYS: ya estaba cargado desde 2026-10-31 (27 tablas, 3 paquetes, 0 inválidos, fase 2 de 3FN aplicada). Verificado con sqlplus + wallet; no se recargó. `cargar_esquema_cloud.ps1` acepta claves por entorno y envía a sqlplus sin BOM.
- [x] T4 Despliegue: imágenes amd64 construidas en el equipo de desarrollo y cargadas por `docker save/load`; `docker-compose.oracle-web.yml` y `docker-compose.nlp.yml` nuevos; wallet y `.env` en cada VM.
- [x] T5 DuckDNS apunta a 150.136.165.160; certificado Let's Encrypt emitido (vence 2027-01-31); renovación webroot + hook probada con `certbot renew --dry-run`.
- [x] T6 Verificación de punta a punta (2026-11-01 ~20:40): `https://electrisys.duckdns.org/` 200 desde fuera, redirección HTTP→HTTPS 301, certificado válido (`ssl_verify_result=0`), `/api/health` con db ok (7,5 ms), login `admin@electrisys.com`, `GET /api/repuestos` 200, `POST /api/asistente/consultar` devuelve intención, entidades y sugerencias (NLP en otra VM y llamada de vuelta por 8081), `wss://…/ws` conecta con subprotocolo `bearer`.
- [x] T7 Documentado en `oracle/docs/despliegue-oracle-cloud.md` y `docker/.env.example`.

## Fase 2 (pedido del usuario, 2026-11-01)
- [x] T8 Pruebas funcionales en navegador real (Playwright headless 1.49.1, scripts fuera del repo). Evidencia 2026-11-01: login admin y vendedor; dashboard con 23 productos y 12 clientes; menú y 4 pantallas sin errores de API; indicador "En vivo" en Repuestos/Pedidos; venta VT-2026-000001 por $ 17.850 (15.000 + IVA 19 %) con stock 60→59 en otra sesión sin recargar; anulación con stock 59→60 en vivo; pedido PED-000001 creado (stock sin cambio) y cancelado; asistente (chat) responde con "Pastillas de freno"/"Brembo" vía la VM del NLP. Datos de prueba: venta Anulada y pedido Cancelado quedan como registros históricos (stock neto sin cambio). No probado: cotizaciones (solo carga), clientes, reportes, usuarios.
- [x] T9 Vigilante `docker/vigilante-oracle.sh` por cron cada 30 min en la VM web (OK api+db / OK nlp en el log; `/api/health` ejecuta `SELECT 1 FROM dual`, verificado en `backend/src/routes/health.php`). Grafana/Prometheus descartados: no caben en 1 GB.
- [x] T10 Respaldos: decisión = usar los respaldos automáticos de Autonomous Database (retención 60 días, visibles en la consola). La pantalla "Respaldos" queda detrás de la VPN por diseño (WireGuard no desplegado); documentado en README y `docs/despliegue-produccion.md`. No se cambió código.
- [x] T11 Reinicio por `sudo reboot` (la sesión OCI había vencido): web volvió sola en ~92 s y el NLP en ~105 s; contenedores, swap, `iptables` y cron intactos; el vigilante reporta OK.
- [x] T12 `docs/despliegue-produccion.md` reescrito (Oracle Cloud, 2 VMs, DuckDNS, límites) y README actualizado. Ruta: inline (solo documentación; el contexto del despliegue ya estaba en la sesión, delegar exigía reexplicarlo todo).
- [x] T13 Commits convencionales de la migración, sin push y sin `Claude outputs/oracle_cloud.zip` (ver commits abajo).

## Criterios de aceptación
Cumplidos: el sitio responde 200, la API autentica y lee de ELECTRISYS en la nube, el NLP responde, HTTPS válido.

## Pendiente / riesgos
- Cambios sin commitear: este feature convive con trabajo previo del usuario en el árbol (modelos PHP, scripts `oracle/*_cloud*`, `docker-compose.yml`). No se commiteó nada sin pedirlo.
- Usuarios demo (`admin@electrisys.com` / `password`) siguen activos en un sitio público.
- No se probó un reinicio de las VMs (Docker habilitado y `restart: unless-stopped` configurados).
- Autonomous Always Free se detiene tras 7 días sin uso; instancias Always Free inactivas pueden reclamarse.
- Respaldos Data Pump en Autonomous: el listado del backend (`BACKUP_PATH`) no los ve.

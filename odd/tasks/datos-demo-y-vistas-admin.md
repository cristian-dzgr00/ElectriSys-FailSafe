# Feature: datos-demo-y-vistas-admin

## Objetivo
1. La base en Oracle Cloud debe parecer usada durante ~3,5 meses: datos realistas en **todas** las vistas y más productos.
2. Las vistas **Usuarios**, **Respaldos** y **Auditoría** se pueden *ver* sin VPN, pero cualquier acción que modifique algo (crear/editar/eliminar usuario, "Respaldar ahora", descargar exportación) muestra una ventana emergente que explica que se necesita entrar por un túnel VPN.
3. La pantalla Respaldos deja de mostrar el texto engañoso (servicio `oracle-backup`, respaldo nocturno propio) y lista los `.dmp` reales generados en la base.

## Problema / por qué
- El usuario revisó el sitio y vio pocos datos (la nube se cargó el 2026-10-31 solo con la siembra del proyecto; los datos anteriores del usuario siguen en el volumen local `docker_oracle_data`, no se tocaron).
- Hoy `/api/usuarios`, `/api/admin/backups` y la auditoría devuelven 403 fuera de la VPN, así que las pantallas se ven rotas para quien no está en el túnel.

## Alcance autorizado
- Escribir datos de demostración en el esquema ELECTRISYS (ADB en la nube), conservando lo existente (incluidos los datos de prueba: VT-2026-000001, PED-000001, COT-20261101-82D089).
- Cambios en `backend/` y `frontend/` descritos arriba, reconstrucción de imágenes y despliegue en las dos VMs.
- Sin cambiar contraseñas de usuarios existentes (el usuario quiere conservarlas: `password`). Usuarios nuevos usan el mismo hash.
- **Sin push** a GitHub.

## Decisiones
- Acceso de solo lectura sin VPN: `GET /api/usuarios`, `GET /api/admin/backups` (listado) y el listado de auditoría. Todo lo demás de esas rutas sigue exigiendo VPN. La exportación CSV (`/exportar-csv`) sigue exigiendo VPN porque contiene datos de negocio.
- El frontend sabe si está en VPN por un endpoint `GET /api/vpn/estado` (requiere JWT) y abre el modal **antes** de mostrar formularios.
- Recomendación aceptada para Respaldos: listar los `.dmp` con `DBMS_CLOUD.LIST_FILES('ELECTRISYS_BACKUP_DIR')` (requiere `GRANT EXECUTE ON DBMS_CLOUD` a ELECTRISYS, lo corre ADMIN).

## Tareas
- [x] D1 Backend + frontend: acceso de solo lectura, endpoint de estado VPN, modal VPN en Usuarios/Respaldos, pantalla Respaldos veraz y con listado desde la base. Ruta: **delegada** a un escritor (≥2 archivos no triviales; el contexto de la sesión supera el respaldo de ~150k tokens). Evidencia: PHPUnit RED→GREEN (11 pruebas del middleware; suite completa 26 pruebas / 55 aserciones con el repo montado), `php -l` OK, `npm run build` OK; revisión puntual del padre sobre la lista de rutas abiertas (solo GET, 3 rutas exactas, regex ancladas); desplegado y probado en navegador: sin VPN, Usuarios lista 2 filas sin errores y Nuevo/Editar/Desactivar abren el modal "Acceso por VPN requerido" sin abrir formulario; Respaldos sin textos viejos y "Respaldar ahora" abre el modal; por túnel SSH "Nuevo usuario" abre el formulario sin modal. Auditoría: no tiene botones que modifiquen (solo recargar, filtros y paginación), carga sin VPN por la lista abierta `GET /api/audit-log`; falta probarla con el usuario dueño (se crea en D2). **Pendiente de autorización del usuario:** `GRANT EXECUTE ON DBMS_CLOUD TO electrisys` (script `oracle/backup/12_listado_backups_cloud.sql`); el sistema bloqueó el comando y no se reintentó. Mientras tanto Respaldos muestra el aviso neutral "No se pudo leer el listado de respaldos de la base."
- [ ] D2 Datos demo: `oracle/17_datos_demo.sql` (PL/SQL determinista, una transacción) + usuarios nuevos (dueño y vendedores) + más repuestos, proveedores, clientes, ventas, cotizaciones, pedidos, auditoría, consultas del asistente. Ruta: **delegada** (lectura de esquema y triggers que prepara la escritura).
- [ ] D3 Reconstruir imágenes (frontend) y subir backend/frontend a las VMs; ejecutar `GRANT` y el script de datos.
- [ ] D4 Pruebas en navegador: todas las vistas con datos; Usuarios/Respaldos/Auditoría con y sin túnel; modal VPN; usuario dueño.
- [ ] D5 Documentación y commits (sin push).

## Criterios de aceptación
- Sitio normal: Usuarios lista usuarios sin error; al pulsar Nuevo/Editar/Eliminar aparece el modal VPN. Respaldos lista archivos y los botones muestran el modal. Auditoría (rol dueño) carga y no tiene acciones de edición.
- Por el túnel SSH: las mismas acciones funcionan (sin modal).
- Cada vista principal (Dashboard, Repuestos, Proveedores, Pedidos, Ventas, Cotizaciones, Clientes, Reportes, Usuarios, Respaldos, Auditoría) muestra datos de ~3,5 meses; el stock es coherente con ventas y pedidos recibidos.

## Progreso
- 2026-11-02: tareas definidas; sin cambios de código todavía.

## Próximo paso
D1.

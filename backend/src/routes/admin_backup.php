<?php
use Psr\Http\Message\ResponseInterface as Response;
use Psr\Http\Message\ServerRequestInterface as Request;
use App\models\Database;
use App\middlewares\RoleMiddleware;
use App\patterns\observer\AuditLogObserver;

/**
 * Administración de respaldos.
 *
 * Se registra en el grupo que ya lleva VpnMiddleware + JwtMiddleware (el
 * mismo que usuarios y auditoría): los respaldos contienen TODA la base —
 * clientes, ventas, hashes de contraseñas— así que disparar uno o exportar
 * datos solo es posible desde la VPN. Fuera de la VPN, VpnMiddleware deja
 * pasar únicamente el listado (GET /admin/backups). Encima va
 * RoleMiddleware(['admin','dueno']) por ruta.
 *
 * Los respaldos automáticos los hace Oracle Autonomous Database (60 días,
 * visibles en la consola de Oracle Cloud). Estos endpoints sirven para ver
 * los exports de Data Pump que hay y disparar uno manual antes de una
 * operación riesgosa.
 */

/** Carpeta donde Data Pump escribe los dumps, vista desde el backend. */
function backupPath(): string
{
    return rtrim($_ENV['BACKUP_PATH'] ?? '/opt/oracle/backups/electrisys', '/\\');
}

/** Formatea un tamaño en bytes igual que el listado del volumen local. */
function tamanoLegible(int $bytes): string
{
    return $bytes >= 1048576
        ? round($bytes / 1048576, 1) . ' MB'
        : max(1, (int) round($bytes / 1024)) . ' KB';
}

/**
 * Lista los .dmp del directorio Oracle ELECTRISYS_BACKUP_DIR con
 * DBMS_CLOUD.LIST_FILES. Es lo que se usa cuando el backend no tiene la
 * carpeta de respaldos montada (Autonomous Database: los archivos viven en el
 * servidor de la base, no en este contenedor). Requiere
 * oracle/backup/12_listado_backups_cloud.sql (GRANT EXECUTE ON DBMS_CLOUD).
 *
 * @return array<int,array<string,mixed>>
 */
function listarBackupsOracle(): array
{
    $db = Database::getConnection();
    $filas = $db->query(
        "SELECT object_name, bytes, "
        . "TO_CHAR(SYS_EXTRACT_UTC(last_modified), 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"') AS last_modified "
        . "FROM DBMS_CLOUD.LIST_FILES('ELECTRISYS_BACKUP_DIR')"
    )->fetchAll();

    $backups = [];
    foreach ($filas as $fila) {
        $nombre = (string) ($fila['object_name'] ?? '');
        if (!preg_match('/\.dmp$/i', $nombre)) {
            continue;
        }
        $bytes = (int) ($fila['bytes'] ?? 0);
        $ts    = strtotime((string) ($fila['last_modified'] ?? ''));
        $backups[] = [
            'archivo' => $nombre,
            'bytes'   => $bytes,
            'tamano'  => tamanoLegible($bytes),
            'fecha'   => date('c', $ts !== false ? $ts : 0),
        ];
    }
    return $backups;
}

// GET /api/admin/backups — respaldos disponibles
$group->get('/admin/backups', function (Request $req, Response $res) {
    $path = backupPath();

    // Sin la carpeta montada (caso de Autonomous Database) se lista el
    // directorio Oracle por SQL. Si eso falla (p. ej. falta el GRANT sobre
    // DBMS_CLOUD) se responde 200 con lista vacía y un mensaje neutro: la
    // vista tiene que seguir ofreciendo el botón de respaldo manual, que no
    // depende del listado.
    if (!is_dir($path) || !is_readable($path)) {
        $backups = [];
        $mensaje = null;
        try {
            $backups = listarBackupsOracle();
            usort($backups, fn($a, $b) => strcmp($b['fecha'], $a['fecha']));
        } catch (\Throwable $e) {
            error_log('[ElectriSys][Backup] No se pudo listar ELECTRISYS_BACKUP_DIR: ' . $e->getMessage());
            $mensaje = 'No se pudo leer el listado de respaldos de la base.';
        }

        $payload = [
            'data'      => $backups,
            'accesible' => $mensaje === null,
            'ruta'      => 'ELECTRISYS_BACKUP_DIR',
        ];
        if ($mensaje !== null) {
            $payload['mensaje'] = $mensaje;
        }
        $res->getBody()->write(json_encode($payload));
        return $res->withHeader('Content-Type', 'application/json');
    }

    $backups = [];
    foreach (scandir($path) ?: [] as $archivo) {
        // Oracle escribe los dumps en MAYÚSCULAS en algunas plataformas y en
        // minúsculas en otras — la comparación va sin distinguir mayúsculas.
        if (!preg_match('/\.dmp$/i', $archivo)) {
            continue;
        }
        $completo = $path . DIRECTORY_SEPARATOR . $archivo;
        $bytes    = (int) @filesize($completo);
        $backups[] = [
            'archivo'  => $archivo,
            'bytes'    => $bytes,
            'tamano'   => tamanoLegible($bytes),
            'fecha'    => date('c', (int) @filemtime($completo)),
        ];
    }

    // Más reciente primero: es el que se usaría en una restauración.
    usort($backups, fn($a, $b) => strcmp($b['fecha'], $a['fecha']));

    $res->getBody()->write(json_encode([
        'data'      => $backups,
        'accesible' => true,
        'ruta'      => $path,
    ]));
    return $res->withHeader('Content-Type', 'application/json');
})->add(new RoleMiddleware(['admin', 'dueno']));

// GET /api/admin/backups/exportar-csv — exporta los datos de negocio
//
// Esto NO es el .dmp de Oracle: ese sigue sin poder bajarse por el
// navegador porque contiene toda la base, incluidos los hashes de
// contraseñas (ver la nota en frontend/src/pages/Backups.jsx). Este
// endpoint arma, al vuelo, un .zip con un .csv por tabla de negocio para
// que el dueño/admin pueda revisar o archivar los datos fuera del sistema.
// De "usuarios" se listan las columnas explícitamente para excluir
// "password"; "login_attempts" se omite del todo por no aportar valor de
// negocio y ser puramente de seguridad.
$group->get('/admin/backups/exportar-csv', function (Request $req, Response $res) {
    $db = Database::getConnection();

    $tablas = [
        'roles'                   => null,
        'usuarios'                => ['id', 'nombre', 'email', 'rol_id', 'activo', 'creado_en', 'updated_at', 'deleted_at'],
        'proveedores'             => null,
        'categorias'              => null,
        'repuestos'               => null,
        'clientes'                => null,
        'ventas'                  => null,
        'detalle_ventas'          => null,
        'cotizaciones'            => null,
        'detalle_cotizaciones'    => null,
        'pedidos'                 => null,
        'pedido_detalle'          => null,
        'vehiculos'               => null,
        'repuesto_compatibilidad' => null,
        'consultas_asistente'     => null,
        'audit_log'               => null,
    ];

    $tmp = tempnam(sys_get_temp_dir(), 'electrisys_export_');
    $zip = new \ZipArchive();
    $zip->open($tmp, \ZipArchive::OVERWRITE);

    foreach ($tablas as $tabla => $columnas) {
        $select = $columnas ? implode(',', $columnas) : '*';
        try {
            $filas = $db->query("SELECT {$select} FROM {$tabla}")->fetchAll();
        } catch (\Throwable $e) {
            error_log("[ElectriSys][Export] No se pudo leer {$tabla}: " . $e->getMessage());
            continue;
        }

        $csv = fopen('php://temp', 'r+');
        if ($filas) {
            fputcsv($csv, array_keys($filas[0]));
            foreach ($filas as $fila) {
                fputcsv($csv, $fila);
            }
        } elseif ($columnas) {
            fputcsv($csv, $columnas);
        }
        rewind($csv);
        $zip->addFromString("{$tabla}.csv", stream_get_contents($csv));
        fclose($csv);
    }

    $zip->close();
    $contenido = file_get_contents($tmp);
    unlink($tmp);

    $nombre = 'electrisys_export_' . date('Ymd_His') . '.zip';
    $user   = $req->getAttribute('user');
    (new AuditLogObserver())->actualizar('exportar_datos', [
        'usuario_id' => (int) ($user['sub'] ?? $user['id'] ?? 0),
        'detalle'    => "Exportación CSV de datos de negocio: {$nombre}",
        'ip'         => $req->getServerParams()['REMOTE_ADDR'] ?? '',
    ]);

    $res->getBody()->write($contenido);
    return $res->withHeader('Content-Type', 'application/zip')
               ->withHeader('Content-Disposition', "attachment; filename=\"{$nombre}\"")
               ->withHeader('Content-Length', (string) strlen($contenido));
})->add(new RoleMiddleware(['admin', 'dueno']));

// POST /api/admin/backups — dispara un respaldo manual
$group->post('/admin/backups', function (Request $req, Response $res) {
    $user = $req->getAttribute('user');
    $ip   = $req->getServerParams()['REMOTE_ADDR'] ?? '';

    try {
        // pkg_backup.exportar_esquema usa DBMS_DATAPUMP: el export lo corre
        // la base, no este proceso. El backend no tiene (ni necesita) el
        // cliente expdp ni acceso al socket de Docker.
        // Ver oracle/backup/11_pkg_backup_plsql.sql.
        $conn = Database::getConnection()->raw();
        $stmt = oci_parse($conn, "BEGIN :nombre := pkg_backup.exportar_esquema(); END;");
        $nombre = '';
        oci_bind_by_name($stmt, ':nombre', $nombre, 120);
        if (!@oci_execute($stmt)) {
            $e = oci_error($stmt);
            throw new \RuntimeException($e['message'] ?? 'Error desconocido al lanzar Data Pump');
        }

        // Se reutiliza el Observer de auditoría en vez de hacer el INSERT a
        // mano: la forma de auditar (tabla, columnas, manejo de errores) vive
        // en un solo lugar. No se arma un Subject porque acá no hay varios
        // observadores ni una operación de negocio compuesta que notificar,
        // solo el registro de quién disparó el respaldo.
        (new AuditLogObserver())->actualizar('crear_backup', [
            'usuario_id' => (int)($user['sub'] ?? $user['id'] ?? 0),
            'detalle'    => "Respaldo manual disparado: {$nombre}",
            'ip'         => $ip,
        ]);

        // 202 y no 201: el job de Data Pump corre en segundo plano, el .dmp
        // todavía no existe cuando esta respuesta sale.
        $res->getBody()->write(json_encode([
            'success' => true,
            'archivo' => $nombre,
            'mensaje' => 'Respaldo iniciado. El archivo aparecerá en la lista al terminar.',
        ]));
        return $res->withStatus(202)->withHeader('Content-Type', 'application/json');
    } catch (\Throwable $e) {
        error_log('[ElectriSys][Backup] ' . $e->getMessage());
        $res->getBody()->write(json_encode(['error' => 'No se pudo iniciar el respaldo']));
        return $res->withStatus(500)->withHeader('Content-Type', 'application/json');
    }
})->add(new RoleMiddleware(['admin', 'dueno']));

<?php
/**
 * auditlog.php — Ruta de Auditoría
 * Solo accesible para usuarios con rol 'dueno'.
 */

use Psr\Http\Message\ResponseInterface as Response;
use Psr\Http\Message\ServerRequestInterface as Request;
use App\models\Database;

// GET /api/audit-log
$group->get('/audit-log', function (Request $req, Response $res) {
    $user = $req->getAttribute('user');

    // Solo el dueño puede ver el log
    if (($user['rol'] ?? '') !== 'dueno') {
        $res->getBody()->write(json_encode(['error' => 'Acceso denegado']));
        return $res->withStatus(403)->withHeader('Content-Type', 'application/json');
    }

    $params = $req->getQueryParams();
    $orden  = in_array($params['orden'] ?? '', ['ASC', 'DESC'], true)
              ? $params['orden'] : 'DESC';
    $accion = trim($params['accion'] ?? '');
    $usuario_id = isset($params['usuario_id']) && ctype_digit((string)$params['usuario_id'])
                  ? (int)$params['usuario_id'] : null;
    $desde  = trim($params['desde'] ?? '');
    $hasta  = trim($params['hasta'] ?? '');
    $page   = max(1, (int)($params['page']  ?? 1));
    $limit  = min(100, max(1, (int)($params['limit'] ?? 20)));
    $offset = ($page - 1) * $limit;

    $where  = ['1=1'];
    $bind   = [];

    if ($accion !== '') {
        $where[] = 'a.accion = ?';
        $bind[]  = $accion;
    }
    if ($usuario_id !== null) {
        $where[] = 'a.usuario_id = ?';
        $bind[]  = $usuario_id;
    }
    if ($desde !== '') {
        $where[] = 'DATE(a.created_at) >= ?';
        $bind[]  = $desde;
    }
    if ($hasta !== '') {
        $where[] = 'DATE(a.created_at) <= ?';
        $bind[]  = $hasta;
    }

    $whereStr = implode(' AND ', $where);

    try {
        $db = Database::getConnection();

        // Total
        $countStmt = $db->prepare(
            "SELECT COUNT(*) FROM audit_log a WHERE $whereStr"
        );
        $countStmt->execute($bind);
        $total = (int) $countStmt->fetchColumn();

        // Filas
        $stmt = $db->prepare("
            SELECT
                a.id,
                a.accion,
                a.detalle,
                a.ip,
                a.created_at,
                u.nombre   AS usuario_nombre,
                u.email    AS usuario_email,
                r.nombre   AS usuario_rol
            FROM audit_log a
            LEFT JOIN usuarios u ON a.usuario_id = u.id
            LEFT JOIN roles r    ON u.rol_id = r.id
            WHERE $whereStr
            ORDER BY a.created_at $orden
            LIMIT ? OFFSET ?
        ");
        $stmt->execute([...$bind, $limit, $offset]);
        $rows = $stmt->fetchAll();

        // Acciones distintas para el filtro
        $accionesStmt = $db->query("SELECT DISTINCT accion FROM audit_log ORDER BY accion");
        $acciones = $accionesStmt->fetchAll(\PDO::FETCH_COLUMN);

        // Usuarios que tienen registros
        $usuariosStmt = $db->query("
            SELECT DISTINCT u.id, u.nombre
            FROM audit_log a
            JOIN usuarios u ON a.usuario_id = u.id
            ORDER BY u.nombre
        ");
        $usuarios = $usuariosStmt->fetchAll();

        $res->getBody()->write(json_encode([
            'data'     => $rows,
            'total'    => $total,
            'page'     => $page,
            'limit'    => $limit,
            'acciones' => $acciones,
            'usuarios' => $usuarios,
        ]));
        return $res->withHeader('Content-Type', 'application/json');

    } catch (\Throwable $e) {
        error_log('[ElectriSys] Error en audit-log: ' . $e->getMessage());
        $res->getBody()->write(json_encode(['error' => 'Error al obtener el log de auditoría']));
        return $res->withStatus(500)->withHeader('Content-Type', 'application/json');
    }
});
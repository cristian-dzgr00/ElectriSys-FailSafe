<?php
use Psr\Http\Message\ResponseInterface as Response;
use Psr\Http\Message\ServerRequestInterface as Request;
use App\models\Database;
use App\middlewares\RoleMiddleware;

function proveedoresDB() { return Database::getConnection(); }

function validarProveedor(array $b): ?string {
    if (empty(trim($b['nombre'] ?? '')))  return 'El nombre del proveedor es obligatorio';
    if (strlen(trim($b['nombre'])) > 150) return 'El nombre no puede superar 150 caracteres';
    if (!empty($b['email']) && !filter_var($b['email'], FILTER_VALIDATE_EMAIL))
                                          return 'El formato del email no es válido';
    if (!empty($b['telefono']) && !ctype_digit($b['telefono']))
                                          return 'El teléfono solo puede contener números';
    return null;
}

// GET /api/proveedores — paginación real
$group->get('/proveedores', function (Request $req, Response $res) {
    $p     = $req->getQueryParams();
    $page  = max(1, (int)($p['page']  ?? 1));
    $limit = min(100, max(1, (int)($p['limit'] ?? 15)));
    $off   = ($page - 1) * $limit;
    $q     = '%' . trim($p['q'] ?? '') . '%';

    $db   = proveedoresDB();
    $stmt = $db->prepare("
        SELECT p.*, COUNT(*) OVER() AS total_filas FROM proveedores p
        WHERE activo=1 AND (nombre LIKE ? OR contacto LIKE ? OR email LIKE ?)
        ORDER BY nombre OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
    ");
    $stmt->execute([$q, $q, $q, $off, $limit]);
    $rows  = $stmt->fetchAll();
    $total = (int) ($rows[0]['total_filas'] ?? 0);
    foreach ($rows as &$fila) { unset($fila['total_filas']); }
    unset($fila);

    $res->getBody()->write(json_encode(['data' => $rows, 'total' => $total, 'page' => $page]));
    return $res->withHeader('Content-Type', 'application/json');
});

// GET /api/proveedores/{id} — para el popup de contacto en pedidos, etc.
// No filtra por activo=1: un pedido histórico puede apuntar a un proveedor
// ya desactivado y sus datos de contacto siguen siendo válidos de mostrar.
$group->get('/proveedores/{id}', function (Request $req, Response $res, array $args) {
    if (!ctype_digit((string)$args['id'])) {
        $res->getBody()->write(json_encode(['error' => 'ID inválido']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }
    $stmt = proveedoresDB()->prepare("SELECT * FROM proveedores WHERE id = ?");
    $stmt->execute([(int)$args['id']]);
    $prov = $stmt->fetch();
    if (!$prov) {
        $res->getBody()->write(json_encode(['error' => 'Proveedor no encontrado']));
        return $res->withStatus(404)->withHeader('Content-Type', 'application/json');
    }
    $res->getBody()->write(json_encode(['data' => $prov]));
    return $res->withHeader('Content-Type', 'application/json');
});

// POST /api/proveedores
$group->post('/proveedores', function (Request $req, Response $res) {
    $b = (array) $req->getParsedBody();
    if ($err = validarProveedor($b)) {
        $res->getBody()->write(json_encode(['error' => $err]));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }
    try {
        $db = proveedoresDB();
        $stmt = $db->prepare("INSERT INTO proveedores (nombre,contacto,telefono,email,direccion) VALUES (?,?,?,?,?) RETURNING id INTO :out_id");
        $nuevoId = 0;
        $stmt->bindOut(':out_id', $nuevoId);
        $stmt->execute([
               trim($b['nombre']),
               trim($b['contacto'] ?? '') ?: null,
               trim($b['telefono'] ?? '') ?: null,
               strtolower(trim($b['email'] ?? '')) ?: null,
               trim($b['direccion'] ?? '') ?: null,
           ]);
        $res->getBody()->write(json_encode(['success' => true, 'id' => (int) $nuevoId]));
        return $res->withStatus(201)->withHeader('Content-Type', 'application/json');
    } catch (\Throwable $e) {
        error_log('[ElectriSys] Error creando proveedor: ' . $e->getMessage());
        $res->getBody()->write(json_encode(['error' => 'No se pudo guardar el proveedor']));
        return $res->withStatus(500)->withHeader('Content-Type', 'application/json');
    }
})->add(new RoleMiddleware(['admin']));

// PUT /api/proveedores/{id}
$group->put('/proveedores/{id}', function (Request $req, Response $res, array $args) {
    if (!ctype_digit((string)$args['id'])) {
        $res->getBody()->write(json_encode(['error' => 'ID inválido']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }
    $b = (array) $req->getParsedBody();
    if ($err = validarProveedor($b)) {
        $res->getBody()->write(json_encode(['error' => $err]));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }
    proveedoresDB()->prepare("
        UPDATE proveedores SET nombre=?,contacto=?,telefono=?,email=?,direccion=? WHERE id=? AND activo=1
    ")->execute([
        trim($b['nombre']),
        trim($b['contacto'] ?? '') ?: null,
        trim($b['telefono'] ?? '') ?: null,
        strtolower(trim($b['email'] ?? '')) ?: null,
        trim($b['direccion'] ?? '') ?: null,
        (int)$args['id'],
    ]);
    $res->getBody()->write(json_encode(['success' => true]));
    return $res->withHeader('Content-Type', 'application/json');
})->add(new RoleMiddleware(['admin']));

// DELETE /api/proveedores/{id} — soft delete
$group->delete('/proveedores/{id}', function (Request $req, Response $res, array $args) {
    if (!ctype_digit((string)$args['id'])) {
        $res->getBody()->write(json_encode(['error' => 'ID inválido']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }
    proveedoresDB()->prepare("UPDATE proveedores SET activo=0, deleted_at=SYSTIMESTAMP WHERE id=?")
                  ->execute([(int)$args['id']]);
    $res->getBody()->write(json_encode(['success' => true]));
    return $res->withHeader('Content-Type', 'application/json');
})->add(new RoleMiddleware(['admin']));

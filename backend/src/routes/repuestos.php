<?php
use Psr\Http\Message\ResponseInterface as Response;
use Psr\Http\Message\ServerRequestInterface as Request;
use App\models\Database;
use App\models\VehiculoModel;

function repuestosDB() { return Database::getConnection(); }

// GET /api/repuestos
$group->get('/repuestos', function (Request $req, Response $res) {
    $p     = $req->getQueryParams();
    $page  = max(1, (int)($p['page']  ?? 1));
    $limit = min(100, max(1, (int)($p['limit'] ?? 15)));
    $off   = ($page - 1) * $limit;
    $q     = '%' . trim($p['q'] ?? '') . '%';

    $db    = repuestosDB();
    $total = (int) $db->prepare("
        SELECT COUNT(*) FROM repuestos r
        LEFT JOIN categorias c ON r.categoria_id = c.id
        WHERE r.activo = 1 AND (r.nombre LIKE ? OR r.codigo LIKE ? OR c.nombre LIKE ?)
    ")->execute([$q,$q,$q]) ? $db->query("SELECT FOUND_ROWS()")->fetchColumn() : 0;

    // Re-query con SQL_CALC_FOUND_ROWS
    // Busca también por categoría (c.nombre LIKE) — lo usa el microservicio
    // NLP para el fallback de "sin compatibilidad exacta, buscar por categoría".
    $stmt = $db->prepare("
        SELECT SQL_CALC_FOUND_ROWS r.*, c.nombre AS categoria
        FROM repuestos r
        LEFT JOIN categorias c ON r.categoria_id = c.id
        WHERE r.activo = 1 AND (r.nombre LIKE ? OR r.codigo LIKE ? OR c.nombre LIKE ?)
        ORDER BY r.nombre
        LIMIT ? OFFSET ?
    ");
    $stmt->execute([$q, $q, $q, $limit, $off]);
    $rows  = $stmt->fetchAll();
    $total = (int) $db->query("SELECT FOUND_ROWS()")->fetchColumn();

    $res->getBody()->write(json_encode(['data' => $rows, 'total' => $total, 'page' => $page]));
    return $res->withHeader('Content-Type', 'application/json');
});

// GET /api/repuestos/buscar-compatibles?marca=&modelo=&anio=&motor=&combustible=&categoria=
// Registrada ANTES de /repuestos/{id}: si fuera después, Slim/FastRoute la capturaría
// como {id}="buscar-compatibles" (ambas son rutas de un solo segmento bajo /repuestos).
// La usará el microservicio NLP (Sprint 4) para obtener candidatos de sustitución.
$group->get('/repuestos/buscar-compatibles', function (Request $req, Response $res) {
    $p      = $req->getQueryParams();
    $marca  = trim($p['marca']  ?? '');
    $modelo = trim($p['modelo'] ?? '');
    if ($marca === '' || $modelo === '') {
        $res->getBody()->write(json_encode(['error' => 'marca y modelo son obligatorios']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }

    $where  = ['r.activo = 1', 'v.marca = ?', 'v.modelo = ?'];
    $params = [$marca, $modelo];

    if (!empty($p['anio']) && ctype_digit((string)$p['anio'])) {
        $where[]  = '? BETWEEN v.anio_desde AND v.anio_hasta';
        $params[] = (int) $p['anio'];
    }
    if (!empty($p['motor'])) {
        $where[]  = 'v.motor = ?';
        $params[] = trim($p['motor']);
    }
    if (!empty($p['combustible'])) {
        $where[]  = 'v.combustible = ?';
        $params[] = trim($p['combustible']);
    }
    if (!empty($p['categoria'])) {
        $where[]  = 'c.nombre LIKE ?';
        $params[] = '%' . trim($p['categoria']) . '%';
    }

    $stmt = repuestosDB()->prepare("
        SELECT DISTINCT r.id, r.codigo, r.nombre, r.descripcion, r.stock, r.precio_venta,
               c.nombre AS categoria, pr.nombre AS proveedor
        FROM repuesto_compatibilidad rc
        JOIN vehiculos  v  ON v.id = rc.vehiculo_id
        JOIN repuestos  r  ON r.id = rc.repuesto_id
        LEFT JOIN categorias  c  ON c.id  = r.categoria_id
        LEFT JOIN proveedores pr ON pr.id = r.proveedor_id
        WHERE " . implode(' AND ', $where) . "
        ORDER BY r.nombre
    ");
    $stmt->execute($params);
    $res->getBody()->write(json_encode(['data' => $stmt->fetchAll()]));
    return $res->withHeader('Content-Type', 'application/json');
});

// GET /api/repuestos/{id}
$group->get('/repuestos/{id}', function (Request $req, Response $res, array $args) {
    if (!ctype_digit((string)$args['id'])) {
        $res->getBody()->write(json_encode(['error' => 'ID inválido']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }
    $stmt = repuestosDB()->prepare("SELECT r.*, c.nombre AS categoria FROM repuestos r LEFT JOIN categorias c ON r.categoria_id=c.id WHERE r.id=? AND r.activo=1");
    $stmt->execute([(int)$args['id']]);
    $row = $stmt->fetch();
    if (!$row) {
        $res->getBody()->write(json_encode(['error' => 'Repuesto no encontrado']));
        return $res->withStatus(404)->withHeader('Content-Type', 'application/json');
    }
    $res->getBody()->write(json_encode(['data' => $row]));
    return $res->withHeader('Content-Type', 'application/json');
});

// GET /api/repuestos/{id}/compatibilidad — vehículos compatibles con este repuesto
$group->get('/repuestos/{id}/compatibilidad', function (Request $req, Response $res, array $args) {
    if (!ctype_digit((string)$args['id'])) {
        $res->getBody()->write(json_encode(['error' => 'ID inválido']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }
    $stmt = repuestosDB()->prepare("
        SELECT v.* FROM repuesto_compatibilidad rc
        JOIN vehiculos v ON v.id = rc.vehiculo_id
        WHERE rc.repuesto_id = ?
        ORDER BY v.marca, v.modelo, v.anio_desde
    ");
    $stmt->execute([(int)$args['id']]);
    $res->getBody()->write(json_encode(['data' => $stmt->fetchAll()]));
    return $res->withHeader('Content-Type', 'application/json');
});

// POST /api/repuestos/{id}/compatibilidad
// Body: {vehiculo_id} para reusar un vehículo existente, o
// {marca, modelo, anio_desde, anio_hasta, motor, combustible} para crear uno nuevo (o reusarlo si ya existe).
$group->post('/repuestos/{id}/compatibilidad', function (Request $req, Response $res, array $args) {
    if (!ctype_digit((string)$args['id'])) {
        $res->getBody()->write(json_encode(['error' => 'ID inválido']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }
    $repuestoId = (int) $args['id'];
    $db = repuestosDB();

    $stmt = $db->prepare("SELECT id FROM repuestos WHERE id = ? AND activo = 1");
    $stmt->execute([$repuestoId]);
    if (!$stmt->fetchColumn()) {
        $res->getBody()->write(json_encode(['error' => 'Repuesto no encontrado']));
        return $res->withStatus(404)->withHeader('Content-Type', 'application/json');
    }

    $b = (array) $req->getParsedBody();
    $vehiculos = new VehiculoModel();

    if (!empty($b['vehiculo_id'])) {
        if (!ctype_digit((string)$b['vehiculo_id']) || !$vehiculos->buscarPorId((int)$b['vehiculo_id'])) {
            $res->getBody()->write(json_encode(['error' => 'vehiculo_id inválido o inexistente']));
            return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
        }
        $vehiculoId = (int) $b['vehiculo_id'];
    } else {
        if ($err = VehiculoModel::validar($b)) {
            $res->getBody()->write(json_encode(['error' => $err]));
            return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
        }
        $vehiculoId = $vehiculos->buscarOcrear($b);
    }

    $db->prepare("INSERT IGNORE INTO repuesto_compatibilidad (repuesto_id, vehiculo_id) VALUES (?, ?)")
        ->execute([$repuestoId, $vehiculoId]);

    $res->getBody()->write(json_encode(['success' => true, 'vehiculo' => $vehiculos->buscarPorId($vehiculoId)]));
    return $res->withStatus(201)->withHeader('Content-Type', 'application/json');
});

// DELETE /api/repuestos/{id}/compatibilidad/{vehiculo_id}
$group->delete('/repuestos/{id}/compatibilidad/{vehiculo_id}', function (Request $req, Response $res, array $args) {
    if (!ctype_digit((string)$args['id']) || !ctype_digit((string)$args['vehiculo_id'])) {
        $res->getBody()->write(json_encode(['error' => 'ID inválido']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }
    $stmt = repuestosDB()->prepare("DELETE FROM repuesto_compatibilidad WHERE repuesto_id = ? AND vehiculo_id = ?");
    $stmt->execute([(int)$args['id'], (int)$args['vehiculo_id']]);
    if ($stmt->rowCount() === 0) {
        $res->getBody()->write(json_encode(['error' => 'Esa compatibilidad no existe']));
        return $res->withStatus(404)->withHeader('Content-Type', 'application/json');
    }
    $res->getBody()->write(json_encode(['success' => true]));
    return $res->withHeader('Content-Type', 'application/json');
});

function validarRepuesto(array $b): ?string {
    if (empty(trim($b['nombre'] ?? '')))              return 'El nombre del repuesto es obligatorio';
    if (strlen(trim($b['nombre'])) > 200)             return 'El nombre no puede superar 200 caracteres';
    if (!isset($b['precio_venta']) || !is_numeric($b['precio_venta']) || $b['precio_venta'] <= 0)
                                                       return 'El precio de venta debe ser mayor a $0';
    if (isset($b['precio_compra']) && $b['precio_compra'] < 0)
                                                       return 'El precio de compra no puede ser negativo';
    if (isset($b['stock']) && (int)$b['stock'] < 0)   return 'El stock no puede ser negativo';
    if (isset($b['stock_minimo']) && (int)$b['stock_minimo'] < 0) return 'El stock mínimo no puede ser negativo';
    return null;
}

// POST /api/repuestos
$group->post('/repuestos', function (Request $req, Response $res) {
    $b = (array) $req->getParsedBody();
    if ($err = validarRepuesto($b)) {
        $res->getBody()->write(json_encode(['error' => $err]));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }
    try {
        $db = repuestosDB();
        $db->prepare("
            INSERT INTO repuestos (nombre, codigo, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
            VALUES (:nombre, :codigo, :descripcion, :categoria_id, :proveedor_id, :precio_compra, :precio_venta, :stock, :stock_minimo)
        ")->execute([
            ':nombre'       => trim($b['nombre']),
            ':codigo'       => trim($b['codigo'] ?? ''),
            ':descripcion'  => trim($b['descripcion'] ?? ''),
            ':categoria_id' => $b['categoria_id'] ?: null,
            ':proveedor_id' => $b['proveedor_id'] ?: null,
            ':precio_compra'=> (float)($b['precio_compra'] ?? 0),
            ':precio_venta' => (float)$b['precio_venta'],
            ':stock'        => (int)($b['stock'] ?? 0),
            ':stock_minimo' => (int)($b['stock_minimo'] ?? 5),
        ]);
        $res->getBody()->write(json_encode(['success' => true, 'id' => $db->lastInsertId()]));
        return $res->withStatus(201)->withHeader('Content-Type', 'application/json');
    } catch (\PDOException $e) {
        $msg = str_contains($e->getMessage(), 'Duplicate')
            ? 'Ya existe un repuesto con ese código' : 'Error al guardar el repuesto';
        $res->getBody()->write(json_encode(['error' => $msg]));
        return $res->withStatus(409)->withHeader('Content-Type', 'application/json');
    }
});

// PUT /api/repuestos/{id}
$group->put('/repuestos/{id}', function (Request $req, Response $res, array $args) {
    if (!ctype_digit((string)$args['id'])) {
        $res->getBody()->write(json_encode(['error' => 'ID inválido']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }
    $b = (array) $req->getParsedBody();
    if ($err = validarRepuesto($b)) {
        $res->getBody()->write(json_encode(['error' => $err]));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }
    try {
        $db = repuestosDB();
        $db->prepare("
            UPDATE repuestos SET nombre=:nombre, codigo=:codigo, descripcion=:descripcion,
            categoria_id=:categoria_id, proveedor_id=:proveedor_id,
            precio_compra=:precio_compra, precio_venta=:precio_venta,
            stock=:stock, stock_minimo=:stock_minimo WHERE id=:id AND activo=1
        ")->execute([
            ':nombre'       => trim($b['nombre']),
            ':codigo'       => trim($b['codigo'] ?? ''),
            ':descripcion'  => trim($b['descripcion'] ?? ''),
            ':categoria_id' => $b['categoria_id'] ?: null,
            ':proveedor_id' => $b['proveedor_id'] ?: null,
            ':precio_compra'=> (float)($b['precio_compra'] ?? 0),
            ':precio_venta' => (float)$b['precio_venta'],
            ':stock'        => (int)($b['stock'] ?? 0),
            ':stock_minimo' => (int)($b['stock_minimo'] ?? 5),
            ':id'           => (int)$args['id'],
        ]);
        $res->getBody()->write(json_encode(['success' => true]));
        return $res->withHeader('Content-Type', 'application/json');
    } catch (\Throwable $e) {
        error_log('[ElectriSys] Error actualizando repuesto: ' . $e->getMessage());
        $res->getBody()->write(json_encode(['error' => 'No se pudo actualizar el repuesto']));
        return $res->withStatus(500)->withHeader('Content-Type', 'application/json');
    }
});

// DELETE /api/repuestos/{id} — soft delete
$group->delete('/repuestos/{id}', function (Request $req, Response $res, array $args) {
    if (!ctype_digit((string)$args['id'])) {
        $res->getBody()->write(json_encode(['error' => 'ID inválido']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }
    $db = repuestosDB();
    $db->prepare("UPDATE repuestos SET activo=0, deleted_at=NOW() WHERE id=?")->execute([(int)$args['id']]);
    $res->getBody()->write(json_encode(['success' => true]));
    return $res->withHeader('Content-Type', 'application/json');
});

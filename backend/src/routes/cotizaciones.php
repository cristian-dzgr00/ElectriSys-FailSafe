<?php
use Psr\Http\Message\ResponseInterface as Response;
use Psr\Http\Message\ServerRequestInterface as Request;
use App\models\Database;

function cotDB() { return Database::getConnection(); }

// GET /api/cotizaciones
$group->get('/cotizaciones', function (Request $req, Response $res) {
    $p     = $req->getQueryParams();
    $page  = max(1, (int)($p['page']  ?? 1));
    $limit = min(100, max(1, (int)($p['limit'] ?? 15)));
    $off   = ($page - 1) * $limit;

    $db   = cotDB();
    $stmt = $db->prepare("
        SELECT q.*, c.nombre AS cliente_nombre, u.nombre AS vendedor_nombre, COUNT(*) OVER() AS total_filas
        FROM cotizaciones q
        LEFT JOIN clientes c ON q.cliente_id = c.id
        LEFT JOIN usuarios u ON q.usuario_id = u.id
        ORDER BY q.creado_en DESC OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
    ");
    $stmt->execute([$off, $limit]);
    $rows  = $stmt->fetchAll();
    $total = (int) ($rows[0]['total_filas'] ?? 0);
    foreach ($rows as &$fila) { unset($fila['total_filas']); }
    unset($fila);

    $res->getBody()->write(json_encode(['data' => $rows, 'total' => $total, 'page' => $page]));
    return $res->withHeader('Content-Type', 'application/json');
});

// GET /api/cotizaciones/{id}
$group->get('/cotizaciones/{id}', function (Request $req, Response $res, array $args) {
    if (!ctype_digit((string)$args['id'])) {
        $res->getBody()->write(json_encode(['error' => 'ID inválido']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }
    $db   = cotDB();
    $stmt = $db->prepare("
        SELECT q.*, c.nombre AS cliente_nombre, u.nombre AS vendedor_nombre
        FROM cotizaciones q
        LEFT JOIN clientes c ON q.cliente_id = c.id
        LEFT JOIN usuarios u ON q.usuario_id = u.id
        WHERE q.id = ?
    ");
    $stmt->execute([(int)$args['id']]);
    $cot = $stmt->fetch();
    if (!$cot) {
        $res->getBody()->write(json_encode(['error' => 'Cotización no encontrada']));
        return $res->withStatus(404)->withHeader('Content-Type', 'application/json');
    }
    $det = $db->prepare("
        SELECT dc.*, r.nombre AS producto_nombre, r.codigo
        FROM detalle_cotizaciones dc
        JOIN repuestos r ON dc.repuesto_id = r.id
        WHERE dc.cotizacion_id = ?
    ");
    $det->execute([(int)$args['id']]);
    $cot['detalle'] = $det->fetchAll();
    $res->getBody()->write(json_encode(['data' => $cot]));
    return $res->withHeader('Content-Type', 'application/json');
});

// POST /api/cotizaciones
$group->post('/cotizaciones', function (Request $req, Response $res) {
    $user = $req->getAttribute('user');
    $b    = (array) $req->getParsedBody();

    if (empty($b['items']) || !is_array($b['items'])) {
        $res->getBody()->write(json_encode(['error' => 'Debes agregar al menos un producto a la cotización']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }
    if (!isset($b['total']) || !is_numeric($b['total']) || $b['total'] <= 0) {
        $res->getBody()->write(json_encode(['error' => 'El total de la cotización debe ser mayor a $0']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }
    if (!empty($b['vence_en']) && strtotime($b['vence_en']) < strtotime('today')) {
        $res->getBody()->write(json_encode(['error' => 'La fecha de vencimiento no puede ser en el pasado']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }

    $db     = cotDB();
    $numero = 'COT-' . date('Ymd') . '-' . strtoupper(substr(uniqid(), -6));

    $db->beginTransaction();
    try {
        $stmt = $db->prepare("
            INSERT INTO cotizaciones (numero, cliente_id, usuario_id, subtotal, descuento, impuesto, total, estado, vence_en, notas)
            VALUES (?,?,?,?,?,?,?,'borrador',?,?)
            RETURNING id INTO :out_id
        ");
        $cotIdOut = 0;
        $stmt->bindOut(':out_id', $cotIdOut);
        $stmt->execute([
            $numero,
            $b['cliente_id'] ?? null,
            (int)$user['sub'],
            $b['subtotal'] ?? 0,
            $b['descuento'] ?? 0,
            $b['impuesto'] ?? 0,
            $b['total'],
            $b['vence_en'] ?: null,
            $b['notas'] ?? null,
        ]);
        $cotId = (int) $cotIdOut;

        foreach ($b['items'] as $item) {
            $sub = $item['cantidad'] * $item['precio_unit'];
            $db->prepare("
                INSERT INTO detalle_cotizaciones (cotizacion_id, repuesto_id, cantidad, precio_unit, descuento, subtotal)
                VALUES (?,?,?,?,?,?)
            ")->execute([
                $cotId, $item['repuesto_id'], $item['cantidad'],
                $item['precio_unit'], $item['descuento'] ?? 0, $sub,
            ]);
        }

        $db->commit();
        $res->getBody()->write(json_encode(['success' => true, 'data' => ['id' => $cotId, 'numero' => $numero]]));
        return $res->withStatus(201)->withHeader('Content-Type', 'application/json');
    } catch (\Throwable $e) {
        $db->rollBack();
        error_log('[ElectriSys] Error creando cotización: ' . $e->getMessage());
        $res->getBody()->write(json_encode(['error' => 'No se pudo crear la cotización']));
        return $res->withStatus(500)->withHeader('Content-Type', 'application/json');
    }
});

// PUT /api/cotizaciones/{id}/estado
$group->put('/cotizaciones/{id}/estado', function (Request $req, Response $res, array $args) {
    if (!ctype_digit((string)$args['id'])) {
        $res->getBody()->write(json_encode(['error' => 'ID inválido']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }
    $b = (array) $req->getParsedBody();
    $estadosValidos = ['borrador', 'enviada', 'aceptada', 'rechazada', 'vencida'];
    if (!in_array($b['estado'] ?? '', $estadosValidos, true)) {
        $res->getBody()->write(json_encode(['error' => 'Estado de cotización inválido']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }
    cotDB()->prepare("UPDATE cotizaciones SET estado=? WHERE id=?")->execute([$b['estado'], (int)$args['id']]);
    $res->getBody()->write(json_encode(['success' => true]));
    return $res->withHeader('Content-Type', 'application/json');
});

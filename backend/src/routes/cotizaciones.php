<?php
use Psr\Http\Message\ResponseInterface as Response;
use Psr\Http\Message\ServerRequestInterface as Request;
use App\models\Database;
use App\patterns\observer\GestorVentas;
use App\patterns\observer\AuditLogObserver;
use App\patterns\observer\WebSocketObserver;
use App\patterns\strategy\PrecioEstandarStrategy;

function cotDB() { return Database::getConnection(); }

/**
 * Gestor de ventas para convertir una cotización en venta.
 *
 * Se arma acá en vez de reutilizar makeGestorVentas() de ventas.php: esa es
 * una función global que solo existe si ese archivo ya se cargó, y el orden
 * de los require en index.php no es algo en lo que convenga apoyarse.
 * Registra los mismos Observers, así que una venta nacida de una cotización
 * audita y notifica igual que cualquier otra.
 */
function cotGestorVentas(): GestorVentas
{
    $gestor = new GestorVentas(new PrecioEstandarStrategy());
    $gestor->agregarObserver(new AuditLogObserver());
    $gestor->agregarObserver(new WebSocketObserver());
    return $gestor;
}

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
    $b      = (array) $req->getParsedBody();
    $estado = $b['estado'] ?? '';
    $id     = (int) $args['id'];

    // Ciclo de vida nuevo (ver oracle/11_cotizaciones_estados.sql):
    //   activa -> vencida | realizada
    if (!in_array($estado, ['activa', 'vencida', 'realizada'], true)) {
        $res->getBody()->write(json_encode(['error' => 'Estado de cotización inválido']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }

    // "realizada" no se marca a mano: significa que la cotización se
    // convirtió en una venta real, y eso exige descontar stock y registrar
    // la factura. Se hace por su propio endpoint para que no exista forma
    // de dejar una cotización marcada como vendida sin venta detrás.
    if ($estado === 'realizada') {
        $res->getBody()->write(json_encode([
            'error' => 'Para marcarla como realizada usá POST /api/cotizaciones/{id}/convertir-venta',
        ]));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }

    $db   = cotDB();
    $stmt = $db->prepare("SELECT estado FROM cotizaciones WHERE id = ?");
    $stmt->execute([$id]);
    $actual = $stmt->fetchColumn();

    if ($actual === false) {
        $res->getBody()->write(json_encode(['error' => 'Cotización no encontrada']));
        return $res->withStatus(404)->withHeader('Content-Type', 'application/json');
    }
    if ($actual === 'realizada') {
        $res->getBody()->write(json_encode(['error' => 'Esta cotización ya se vendió; su estado no puede cambiar.']));
        return $res->withStatus(409)->withHeader('Content-Type', 'application/json');
    }
    // Reactivar una vencida seria prometer de nuevo un precio que ya cambio.
    // Si el cliente todavia la quiere, se hace una cotizacion nueva con los
    // precios de hoy.
    if ($actual === 'vencida' && $estado === 'activa') {
        $res->getBody()->write(json_encode([
            'error' => 'Una cotización vencida no se puede reactivar: sus precios ya cambiaron. Creá una nueva.',
        ]));
        return $res->withStatus(409)->withHeader('Content-Type', 'application/json');
    }

    $db->prepare("UPDATE cotizaciones SET estado=? WHERE id=?")->execute([$estado, $id]);
    $res->getBody()->write(json_encode(['success' => true, 'estado' => $estado]));
    return $res->withHeader('Content-Type', 'application/json');
});

// POST /api/cotizaciones/{id}/convertir-venta
// Convierte la cotización en una venta real y la marca como realizada.
$group->post('/cotizaciones/{id}/convertir-venta', function (Request $req, Response $res, array $args) {
    if (!ctype_digit((string)$args['id'])) {
        $res->getBody()->write(json_encode(['error' => 'ID inválido']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }
    $id   = (int) $args['id'];
    $user = $req->getAttribute('user');
    $ip   = $req->getServerParams()['REMOTE_ADDR'] ?? '';
    $body = (array) $req->getParsedBody();
    $db   = cotDB();

    $cab = $db->prepare("SELECT * FROM cotizaciones WHERE id = ?");
    $cab->execute([$id]);
    $cot = $cab->fetch();
    if (!$cot) {
        $res->getBody()->write(json_encode(['error' => 'Cotización no encontrada']));
        return $res->withStatus(404)->withHeader('Content-Type', 'application/json');
    }
    if ($cot['estado'] === 'realizada') {
        $res->getBody()->write(json_encode(['error' => 'Esta cotización ya se convirtió en venta.']));
        return $res->withStatus(409)->withHeader('Content-Type', 'application/json');
    }
    if ($cot['estado'] === 'vencida') {
        $res->getBody()->write(json_encode([
            'error' => 'La cotización está vencida: el precio de alguno de sus repuestos cambió. Creá una nueva con los precios de hoy.',
        ]));
        return $res->withStatus(409)->withHeader('Content-Type', 'application/json');
    }

    $det = $db->prepare("SELECT repuesto_id, cantidad, precio_unit, descuento FROM detalle_cotizaciones WHERE cotizacion_id = ?");
    $det->execute([$id]);
    $items = $det->fetchAll();
    if (!$items) {
        $res->getBody()->write(json_encode(['error' => 'La cotización no tiene productos']));
        return $res->withStatus(422)->withHeader('Content-Type', 'application/json');
    }

    try {
        // Se venden los precios COTIZADOS, no los de hoy: es exactamente lo
        // que se le prometio al cliente. Si alguno hubiera cambiado, la
        // cotizacion ya estaria vencida y no habriamos llegado hasta aca
        // (lo garantiza trg_repuestos_vence_cotizaciones).
        $gestor = cotGestorVentas();
        $venta  = $gestor->crearVenta([
            'cliente_id'  => $cot['cliente_id'] ?? null,
            'subtotal'    => (float) $cot['subtotal'],
            'descuento'   => (float) $cot['descuento'],
            'impuesto'    => (float) $cot['impuesto'],
            'total'       => (float) $cot['total'],
            'metodo_pago' => $body['metodo_pago'] ?? 'efectivo',
            'notas'       => 'Generada desde la cotización ' . $cot['numero'],
            'items'       => array_map(fn($i) => [
                'repuesto_id' => (int) $i['repuesto_id'],
                'cantidad'    => (int) $i['cantidad'],
                'precio_unit' => (float) $i['precio_unit'],
                'descuento'   => (float) ($i['descuento'] ?? 0),
            ], $items),
        ], (int)($user['sub'] ?? $user['id'] ?? 0), $ip);

        // Solo despues de que la venta existe. Si esto fallara, quedaria una
        // venta real con la cotizacion aun activa: se prefiere eso a una
        // cotizacion marcada como vendida sin venta que la respalde.
        $db->prepare("UPDATE cotizaciones SET estado='realizada' WHERE id=?")->execute([$id]);

        $res->getBody()->write(json_encode([
            'success' => true,
            'venta'   => $venta,
            'mensaje' => "Venta {$venta['numero']} registrada desde la cotización {$cot['numero']}",
        ]));
        return $res->withStatus(201)->withHeader('Content-Type', 'application/json');
    } catch (\RuntimeException $e) {
        // Tipicamente stock insuficiente: el mensaje de VentaModel ya dice
        // que producto y cuanto falta.
        $res->getBody()->write(json_encode(['error' => $e->getMessage()]));
        return $res->withStatus(422)->withHeader('Content-Type', 'application/json');
    } catch (\Throwable $e) {
        error_log('[Cotizaciones] Error convirtiendo en venta: ' . $e->getMessage());
        $res->getBody()->write(json_encode(['error' => 'No se pudo registrar la venta']));
        return $res->withStatus(500)->withHeader('Content-Type', 'application/json');
    }
});

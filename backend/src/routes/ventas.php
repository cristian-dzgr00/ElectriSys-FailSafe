<?php
use Psr\Http\Message\ResponseInterface as Response;
use Psr\Http\Message\ServerRequestInterface as Request;
use App\models\VentaModel;
use App\models\Database;
use App\patterns\observer\GestorVentas;
use App\patterns\observer\AuditLogObserver;
use App\patterns\observer\WebSocketObserver;
use App\patterns\strategy\PrecioEstandarStrategy;

// ── Helper: obtener GestorVentas con todos los observers ──────
function makeGestorVentas(): GestorVentas
{
    $gestor = new GestorVentas(new PrecioEstandarStrategy());
    $gestor->agregarObserver(new AuditLogObserver());
    $gestor->agregarObserver(new WebSocketObserver());   // notif. tiempo real
    return $gestor;
}

// GET /api/ventas
$group->get('/ventas', function (Request $req, Response $res) {
    $params  = $req->getQueryParams();
    $page    = max(1, (int)($params['page']  ?? 1));
    $limit   = min(100, max(1, (int)($params['limit'] ?? 15)));
    $offset  = ($page - 1) * $limit;
    $q       = trim($params['q']      ?? '');
    $desde   = trim($params['desde']  ?? '');
    $hasta   = trim($params['hasta']  ?? '');
    $estado  = trim($params['estado'] ?? '');

    $filtros = ['q' => $q, 'limit' => $limit, 'offset' => $offset];
    if ($desde)  $filtros['desde']  = $desde;
    if ($hasta)  $filtros['hasta']  = $hasta;
    if ($estado) $filtros['estado'] = $estado;

    $model  = new VentaModel();
    $result = $model->listar($filtros);

    $res->getBody()->write(json_encode([
        'data'  => $result['rows'],
        'total' => $result['total'],
        'page'  => $page,
        'limit' => $limit,
    ]));
    return $res->withHeader('Content-Type', 'application/json');
});

// GET /api/ventas/resumen/semana
$group->get('/ventas/resumen/semana', function (Request $req, Response $res) {
    $conn = Database::getConnection();
    // Se agrupa por fecha local (fn_fecha_local) y no por TRUNC(creado_en):
    // los TIMESTAMP están en UTC, así que una venta nocturna caía en el día
    // siguiente y desaparecía del día que la UI muestra en la lista.
    $stmt = $conn->query("
        SELECT
            TRUNC(fn_fecha_local(creado_en)) AS fecha,
            NVL(SUM(total), 0)               AS ingresos,
            COUNT(*)                         AS ventas
        FROM ventas
        WHERE
            fn_fecha_local(creado_en) >= fn_hoy_local() - 6
            AND estado = 'completada'
        GROUP BY TRUNC(fn_fecha_local(creado_en))
        ORDER BY fecha ASC
    ");
    $res->getBody()->write(json_encode(['data' => $stmt->fetchAll()]));
    return $res->withHeader('Content-Type', 'application/json');
});

// GET /api/ventas/resumen/hoy
$group->get('/ventas/resumen/hoy', function (Request $req, Response $res) {
    $model   = new VentaModel();
    $resumen = $model->resumenHoy()
        ?: ['total_ventas' => 0, 'ingresos' => 0, 'ticket_promedio' => 0];
    $res->getBody()->write(json_encode(['data' => $resumen]));
    return $res->withHeader('Content-Type', 'application/json');
});

// GET /api/ventas/{id}
$group->get('/ventas/{id}', function (Request $req, Response $res, array $args) {
    if (!ctype_digit((string)$args['id'])) {
        $res->getBody()->write(json_encode(['error' => 'ID de venta inválido']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }
    $model = new VentaModel();
    $venta = $model->buscarPorId((int)$args['id']);
    if (!$venta) {
        $res->getBody()->write(json_encode(['error' => 'Venta no encontrada']));
        return $res->withStatus(404)->withHeader('Content-Type', 'application/json');
    }
    $res->getBody()->write(json_encode(['data' => $venta]));
    return $res->withHeader('Content-Type', 'application/json');
});

// POST /api/ventas — usa GestorVentas con Observer + Strategy
$group->post('/ventas', function (Request $req, Response $res) {
    $user = $req->getAttribute('user');
    $body = (array) $req->getParsedBody();
    $ip   = $req->getServerParams()['REMOTE_ADDR'] ?? '';

    if (empty($body['items']) || !is_array($body['items'])) {
        $res->getBody()->write(json_encode(['error' => 'Debes agregar al menos un producto a la venta']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }

    foreach ($body['items'] as $i => $item) {
        if (empty($item['repuesto_id']) || !is_numeric($item['repuesto_id'])) {
            $res->getBody()->write(json_encode(['error' => "Item #".($i+1).": repuesto_id inválido"]));
            return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
        }
        if (empty($item['cantidad']) || (int)$item['cantidad'] <= 0) {
            $res->getBody()->write(json_encode(['error' => "Item #".($i+1).": cantidad debe ser mayor a 0"]));
            return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
        }
        if (!isset($item['precio_unit']) || !is_numeric($item['precio_unit']) || $item['precio_unit'] <= 0) {
            $res->getBody()->write(json_encode(['error' => "Item #".($i+1).": precio_unit inválido"]));
            return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
        }
    }

    $metodosValidos = ['efectivo', 'tarjeta', 'transferencia', 'credito'];
    if (!empty($body['metodo_pago']) && !in_array($body['metodo_pago'], $metodosValidos)) {
        $res->getBody()->write(json_encode(['error' => 'Método de pago inválido']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }

    try {
        // GestorVentas aplica Strategy (descuento) + notifica Observers
        // (AuditLogObserver guarda en DB, WebSocketObserver notifica al frontend)
        $gestor = makeGestorVentas();
        $result = $gestor->crearVenta($body, (int)($user['sub'] ?? $user['id'] ?? 0), $ip);

        $res->getBody()->write(json_encode(['success' => true, ...$result]));
        return $res->withStatus(201)->withHeader('Content-Type', 'application/json');
    } catch (\RuntimeException $e) {
        $res->getBody()->write(json_encode(['error' => $e->getMessage()]));
        return $res->withStatus(422)->withHeader('Content-Type', 'application/json');
    } catch (\Throwable $e) {
        error_log('[Ventas] Error: ' . $e->getMessage());
        $res->getBody()->write(json_encode(['error' => 'Error interno al procesar la venta']));
        return $res->withStatus(500)->withHeader('Content-Type', 'application/json');
    }
});

// PUT /api/ventas/{id}/anular — usa GestorVentas con Observer
$group->put('/ventas/{id}/anular', function (Request $req, Response $res, array $args) {

    if (!ctype_digit((string)$args['id'])) {
        $res->getBody()->write(json_encode(['error' => 'ID inválido']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }

    $user   = $req->getAttribute('user');
    $ip     = $req->getServerParams()['REMOTE_ADDR'] ?? '';
    $gestor = makeGestorVentas();
    $result = $gestor->anularVenta(
        (int)$args['id'],
        (int)($user['sub'] ?? $user['id'] ?? 0),
        $ip
    );

    if (!$result) {
        $res->getBody()->write(json_encode(['error' => 'No se pudo anular (ya anulada o no existe)']));
        return $res->withStatus(409)->withHeader('Content-Type', 'application/json');
    }

    $res->getBody()->write(json_encode(['success' => true]));
    return $res->withHeader('Content-Type', 'application/json');
});

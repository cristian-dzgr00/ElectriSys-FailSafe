<?php
use Psr\Http\Message\ResponseInterface as Response;
use Psr\Http\Message\ServerRequestInterface as Request;
use App\models\PedidoModel;
use App\patterns\observer\GestorPedidos;
use App\patterns\observer\AuditLogObserver;
use App\patterns\observer\WebSocketObserver;
use App\middlewares\RoleMiddleware;

/**
 * Pedidos a proveedor (órdenes de reabastecimiento).
 *
 * Todas las rutas llevan RoleMiddleware(['admin','dueno']) — incluso las de
 * lectura: reabastecer no es parte de la operación del vendedor. El mismo
 * criterio se replica en los GRANT de oracle/10_pedidos.sql y en el menú del
 * frontend (Sidebar.jsx), para que la restricción no dependa solo de la UI.
 */

// ── Helper: GestorPedidos con los mismos Observers que las ventas ──
function makeGestorPedidos(): GestorPedidos
{
    $gestor = new GestorPedidos();
    $gestor->agregarObserver(new AuditLogObserver());   // audit_log
    $gestor->agregarObserver(new WebSocketObserver());  // notif. tiempo real
    return $gestor;
}

// GET /api/pedidos
$group->get('/pedidos', function (Request $req, Response $res) {
    $p     = $req->getQueryParams();
    $page  = max(1, (int)($p['page']  ?? 1));
    $limit = min(100, max(1, (int)($p['limit'] ?? 15)));

    $filtros = ['limit' => $limit, 'offset' => ($page - 1) * $limit];
    if (!empty($p['q']))            $filtros['q']            = trim($p['q']);
    if (!empty($p['estado']))       $filtros['estado']       = trim($p['estado']);
    if (!empty($p['proveedor_id'])) $filtros['proveedor_id'] = (int) $p['proveedor_id'];

    $result = (new PedidoModel())->listar($filtros);

    $res->getBody()->write(json_encode([
        'data'  => $result['rows'],
        'total' => $result['total'],
        'page'  => $page,
        'limit' => $limit,
    ]));
    return $res->withHeader('Content-Type', 'application/json');
})->add(new RoleMiddleware(['admin', 'dueno']));

// GET /api/pedidos/{id}
$group->get('/pedidos/{id}', function (Request $req, Response $res, array $args) {
    if (!ctype_digit((string)$args['id'])) {
        $res->getBody()->write(json_encode(['error' => 'ID de pedido inválido']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }
    $pedido = (new PedidoModel())->buscarPorId((int)$args['id']);
    if (!$pedido) {
        $res->getBody()->write(json_encode(['error' => 'Pedido no encontrado']));
        return $res->withStatus(404)->withHeader('Content-Type', 'application/json');
    }
    $res->getBody()->write(json_encode(['data' => $pedido]));
    return $res->withHeader('Content-Type', 'application/json');
})->add(new RoleMiddleware(['admin', 'dueno']));

// POST /api/pedidos — usa GestorPedidos (Observer: audit_log + WebSocket)
$group->post('/pedidos', function (Request $req, Response $res) {
    $user = $req->getAttribute('user');
    $body = (array) $req->getParsedBody();
    $ip   = $req->getServerParams()['REMOTE_ADDR'] ?? '';

    if (empty($body['proveedor_id']) || !is_numeric($body['proveedor_id'])) {
        $res->getBody()->write(json_encode(['error' => 'Debes seleccionar el proveedor al que se le hace el pedido']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }
    if (empty($body['items']) || !is_array($body['items'])) {
        $res->getBody()->write(json_encode(['error' => 'Debes agregar al menos un producto al pedido']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }

    foreach ($body['items'] as $i => $item) {
        $n = $i + 1;
        if (empty($item['repuesto_id']) || !is_numeric($item['repuesto_id'])) {
            $res->getBody()->write(json_encode(['error' => "Item #{$n}: repuesto_id inválido"]));
            return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
        }
        if (empty($item['cantidad']) || (int)$item['cantidad'] <= 0) {
            $res->getBody()->write(json_encode(['error' => "Item #{$n}: la cantidad debe ser mayor a 0"]));
            return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
        }
        // A diferencia de una venta, acá el precio puede ser 0: hay proveedores
        // que reponen una garantía sin cobrar. Solo se rechaza el negativo.
        if (!isset($item['precio_unit']) || !is_numeric($item['precio_unit']) || $item['precio_unit'] < 0) {
            $res->getBody()->write(json_encode(['error' => "Item #{$n}: precio_unit inválido"]));
            return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
        }
    }

    if (!empty($body['fecha_esperada']) && !preg_match('/^\d{4}-\d{2}-\d{2}$/', $body['fecha_esperada'])) {
        $res->getBody()->write(json_encode(['error' => 'La fecha esperada debe tener formato AAAA-MM-DD']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }

    try {
        $gestor = makeGestorPedidos();
        $result = $gestor->crearPedido($body, (int)($user['sub'] ?? $user['id'] ?? 0), $ip);

        $res->getBody()->write(json_encode(['success' => true, ...$result]));
        return $res->withStatus(201)->withHeader('Content-Type', 'application/json');
    } catch (\RuntimeException $e) {
        $res->getBody()->write(json_encode(['error' => $e->getMessage()]));
        return $res->withStatus(422)->withHeader('Content-Type', 'application/json');
    } catch (\Throwable $e) {
        error_log('[Pedidos] Error creando pedido: ' . $e->getMessage());
        $res->getBody()->write(json_encode(['error' => 'Error interno al registrar el pedido']));
        return $res->withStatus(500)->withHeader('Content-Type', 'application/json');
    }
})->add(new RoleMiddleware(['admin', 'dueno']));

// PATCH /api/pedidos/{id}/estado — avanzar el ciclo de vida del pedido
$group->patch('/pedidos/{id}/estado', function (Request $req, Response $res, array $args) {
    if (!ctype_digit((string)$args['id'])) {
        $res->getBody()->write(json_encode(['error' => 'ID de pedido inválido']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }

    $body   = (array) $req->getParsedBody();
    $estado = trim($body['estado'] ?? '');
    if (!array_key_exists($estado, \App\models\PedidoModel::TRANSICIONES)) {
        $res->getBody()->write(json_encode(['error' => 'Estado de pedido inválido']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }
    // Cancelar tiene su propio endpoint (DELETE) para que quede explícito en
    // el log de acceso qué request cancela un pedido y cuál solo lo avanza.
    if ($estado === 'cancelado') {
        $res->getBody()->write(json_encode(['error' => 'Para cancelar usa DELETE /api/pedidos/{id}']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }

    $user = $req->getAttribute('user');
    $ip   = $req->getServerParams()['REMOTE_ADDR'] ?? '';

    try {
        $ok = makeGestorPedidos()->cambiarEstado(
            (int)$args['id'], $estado, (int)($user['sub'] ?? $user['id'] ?? 0), $ip
        );
        if (!$ok) {
            $res->getBody()->write(json_encode(['error' => 'No se pudo actualizar el pedido']));
            return $res->withStatus(409)->withHeader('Content-Type', 'application/json');
        }
        $res->getBody()->write(json_encode(['success' => true, 'estado' => $estado]));
        return $res->withHeader('Content-Type', 'application/json');
    } catch (\RuntimeException $e) {
        // Transición inválida o pedido inexistente — el mensaje ya está
        // escrito para el usuario final (ver PedidoModel::cambiarEstado).
        $res->getBody()->write(json_encode(['error' => $e->getMessage()]));
        return $res->withStatus(409)->withHeader('Content-Type', 'application/json');
    } catch (\Throwable $e) {
        error_log('[Pedidos] Error cambiando estado: ' . $e->getMessage());
        $res->getBody()->write(json_encode(['error' => 'Error interno al actualizar el pedido']));
        return $res->withStatus(500)->withHeader('Content-Type', 'application/json');
    }
})->add(new RoleMiddleware(['admin', 'dueno']));

// DELETE /api/pedidos/{id} — cancela, no borra (igual que ventas anula)
$group->delete('/pedidos/{id}', function (Request $req, Response $res, array $args) {
    if (!ctype_digit((string)$args['id'])) {
        $res->getBody()->write(json_encode(['error' => 'ID de pedido inválido']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }

    $user = $req->getAttribute('user');
    $ip   = $req->getServerParams()['REMOTE_ADDR'] ?? '';

    try {
        $ok = makeGestorPedidos()->cancelarPedido(
            (int)$args['id'], (int)($user['sub'] ?? $user['id'] ?? 0), $ip
        );
        if (!$ok) {
            $res->getBody()->write(json_encode(['error' => 'No se pudo cancelar el pedido']));
            return $res->withStatus(409)->withHeader('Content-Type', 'application/json');
        }
        $res->getBody()->write(json_encode(['success' => true]));
        return $res->withHeader('Content-Type', 'application/json');
    } catch (\RuntimeException $e) {
        $res->getBody()->write(json_encode(['error' => $e->getMessage()]));
        return $res->withStatus(409)->withHeader('Content-Type', 'application/json');
    } catch (\Throwable $e) {
        error_log('[Pedidos] Error cancelando pedido: ' . $e->getMessage());
        $res->getBody()->write(json_encode(['error' => 'Error interno al cancelar el pedido']));
        return $res->withStatus(500)->withHeader('Content-Type', 'application/json');
    }
})->add(new RoleMiddleware(['admin', 'dueno']));

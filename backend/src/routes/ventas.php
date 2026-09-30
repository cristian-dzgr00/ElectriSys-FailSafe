<?php
use Psr\Http\Message\ResponseInterface as Response;
use Psr\Http\Message\ServerRequestInterface as Request;
use App\models\VentaModel;
use App\models\Database;
use App\services\NlpClient;
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

// GET /api/ventas/resumen/serie?dias=7|30|90
// Serie de ingresos para el gráfico del dashboard, con rango configurable.
// Reemplaza a /resumen/semana (que queda fija en 7 días y se conserva por
// compatibilidad): el selector del dashboard necesita 7 días, 1 mes y 3 meses.
$group->get('/ventas/resumen/serie', function (Request $req, Response $res) {
    $dias = (int)($req->getQueryParams()['dias'] ?? 7);
    // Lista blanca: el valor entra en un cálculo de fechas y, sobre todo,
    // evita que alguien pida 10 años y haga a Oracle recorrer la tabla entera.
    if (!in_array($dias, [7, 30, 90], true)) {
        $dias = 7;
    }

    // Más de un mes se agrupa por semana: 90 puntos en un gráfico de este
    // tamaño no se leen, y lo que interesa en ese rango es la tendencia.
    $porSemana = $dias > 31;
    $truncado  = $porSemana
        ? "TRUNC(fn_fecha_local(creado_en), 'IW')"   // lunes de la semana ISO
        : "TRUNC(fn_fecha_local(creado_en))";

    // fn_fecha_local y no TRUNC(creado_en) a secas: los TIMESTAMP están en
    // UTC, así que una venta nocturna caía en el día siguiente.
    $stmt = Database::getConnection()->prepare("
        SELECT
            TO_CHAR($truncado, 'YYYY-MM-DD') AS fecha,
            NVL(SUM(total), 0)               AS ingresos,
            COUNT(*)                         AS ventas
        FROM ventas
        WHERE fn_fecha_local(creado_en) >= fn_hoy_local() - ?
          AND estado = 'completada'
        GROUP BY $truncado
        ORDER BY 1 ASC
    ");
    $stmt->execute([$dias - 1]);

    $res->getBody()->write(json_encode([
        'data'       => $stmt->fetchAll(),
        'dias'       => $dias,
        'agrupacion' => $porSemana ? 'semana' : 'dia',
    ]));
    return $res->withHeader('Content-Type', 'application/json');
});

// GET /api/ventas/canastas?dias=180&limite=2000
// Ventas históricas como listas de repuesto_id. Materia prima de las reglas
// de asociación del microservicio (productos que se venden juntos).
// Solo ids: para contar co-ocurrencias no hacen falta nombres ni precios.
$group->get('/ventas/canastas', function (Request $req, Response $res) {
    $p      = $req->getQueryParams();
    $dias   = min(730,  max(7,  (int)($p['dias']   ?? 180)));
    $limite = min(5000, max(50, (int)($p['limite'] ?? 2000)));

    // Se agrupa en PHP y no con LISTAGG en Oracle porque LISTAGG trunca a
    // 4000 caracteres y una venta larga rompería la lista en silencio.
    $stmt = Database::getConnection()->prepare("
        SELECT venta_id, repuesto_id FROM (
            SELECT dv.venta_id, dv.repuesto_id,
                   DENSE_RANK() OVER (ORDER BY dv.venta_id DESC) AS rn
            FROM detalle_ventas dv
            JOIN ventas v ON v.id = dv.venta_id
            WHERE v.estado = 'completada'
              AND fn_fecha_local(v.creado_en) >= fn_hoy_local() - ?
        ) WHERE rn <= ?
        ORDER BY venta_id
    ");
    $stmt->execute([$dias, $limite]);

    $canastas = [];
    foreach ($stmt->fetchAll() as $fila) {
        $canastas[(int) $fila['venta_id']][] = (int) $fila['repuesto_id'];
    }

    $res->getBody()->write(json_encode([
        'canastas' => array_values($canastas),
        'dias'     => $dias,
    ]));
    return $res->withHeader('Content-Type', 'application/json');
});

// GET /api/ventas/complementos?ids=1,2,3
// Proxy: productos que suelen acompañar a los que ya están en la venta.
// Como el resto de las rutas de IA, responde 200 con disponible=false si el
// microservicio no contesta — la venta no puede depender de una sugerencia.
$group->get('/ventas/complementos', function (Request $req, Response $res) {
    $crudo = trim($req->getQueryParams()['ids'] ?? '');
    $ids   = [];
    foreach (explode(',', $crudo) as $v) {
        $v = trim($v);
        if (ctype_digit($v)) $ids[] = (int) $v;
    }
    $ids = array_slice(array_values(array_unique($ids)), 0, 50);

    if ($ids === []) {
        $res->getBody()->write(json_encode(['data' => [], 'disponible' => true]));
        return $res->withHeader('Content-Type', 'application/json');
    }

    $r = NlpClient::get('/complementos?ids=' . implode(',', $ids));
    $sugerencias = $r['data'] ?? [];

    // El microservicio solo devuelve ids y métricas: hay que darles nombre y
    // precio para poder mostrarlos, y de paso se descartan los que ya no
    // estén activos o se hayan quedado sin stock.
    $detalle = [];
    if ($sugerencias) {
        $marcas = implode(',', array_fill(0, count($sugerencias), '?'));
        $stmt = Database::getConnection()->prepare(
            "SELECT id, nombre, codigo, precio_venta, stock FROM repuestos
             WHERE activo = 1 AND stock > 0 AND id IN ($marcas)"
        );
        $stmt->execute(array_map(fn($s) => (int) $s['repuesto_id'], $sugerencias));
        $porId = [];
        foreach ($stmt->fetchAll() as $rep) { $porId[(int) $rep['id']] = $rep; }

        foreach ($sugerencias as $s) {
            $rep = $porId[(int) $s['repuesto_id']] ?? null;
            if (!$rep) continue;
            $detalle[] = [
                'id'           => (int) $rep['id'],
                'nombre'       => $rep['nombre'],
                'codigo'       => $rep['codigo'],
                'precio_venta' => (float) $rep['precio_venta'],
                'stock'        => (int) $rep['stock'],
                'veces_juntos' => $s['veces_juntos'] ?? 0,
                'confianza'    => $s['confianza'] ?? 0,
                'lift'         => $s['lift'] ?? 0,
            ];
        }
    }

    $res->getBody()->write(json_encode([
        'data'       => $detalle,
        'disponible' => $r !== null,
    ]));
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


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

    $db = repuestosDB();

    // Busca también por categoría (c.nombre LIKE) — lo usa el microservicio
    // NLP para el fallback de "sin compatibilidad exacta, buscar por categoría" —
    // y por proveedor, para el buscador de repuestos al armar una venta.
    $stmt = $db->prepare("
        SELECT r.*, c.nombre AS categoria, p.nombre AS proveedor, COUNT(*) OVER() AS total_filas
        FROM repuestos r
        LEFT JOIN categorias c ON r.categoria_id = c.id
        LEFT JOIN proveedores p ON r.proveedor_id = p.id
        WHERE r.activo = 1 AND (r.nombre LIKE ? OR r.codigo LIKE ? OR c.nombre LIKE ? OR p.nombre LIKE ?)
        ORDER BY r.nombre
        OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
    ");
    $stmt->execute([$q, $q, $q, $q, $off, $limit]);
    $rows  = $stmt->fetchAll();
    $total = (int) ($rows[0]['total_filas'] ?? 0);
    foreach ($rows as &$fila) { unset($fila['total_filas']); }
    unset($fila);

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

    // Oracle no tiene INSERT IGNORE: se intenta y se ignora el duplicado
    // (uq_repuesto_vehiculo -> ORA-00001), que es exactamente el caso que
    // MySQL silenciaba con IGNORE.
    try {
        $db->prepare("INSERT INTO repuesto_compatibilidad (repuesto_id, vehiculo_id) VALUES (?, ?)")
            ->execute([$repuestoId, $vehiculoId]);
    } catch (\Throwable $e) {
        if (!\App\models\OciConnection::esViolacionDeUnicidad($e)) { throw $e; }
    }

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
        $stmt = $db->prepare("
            INSERT INTO repuestos (nombre, codigo, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
            VALUES (:nombre, :codigo, :descripcion, :categoria_id, :proveedor_id, :precio_compra, :precio_venta, :stock, :stock_minimo)
            RETURNING id INTO :out_id
        ");
        $nuevoId = 0;
        $stmt->bindOut(':out_id', $nuevoId);
        $stmt->execute([
            ':nombre'       => trim($b['nombre']),
            ':codigo'       => trim($b['codigo'] ?? ''),
            ':descripcion'  => trim($b['descripcion'] ?? ''),
            ':categoria_id' => ($b['categoria_id'] ?? null) ?: null,
            ':proveedor_id' => ($b['proveedor_id'] ?? null) ?: null,
            ':precio_compra'=> (float)($b['precio_compra'] ?? 0),
            ':precio_venta' => (float)$b['precio_venta'],
            ':stock'        => (int)($b['stock'] ?? 0),
            ':stock_minimo' => (int)($b['stock_minimo'] ?? 5),
        ]);
        $res->getBody()->write(json_encode(['success' => true, 'id' => (int) $nuevoId]));
        return $res->withStatus(201)->withHeader('Content-Type', 'application/json');
    } catch (\PDOException $e) {
        $msg = \App\models\OciConnection::esViolacionDeUnicidad($e)
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
            ':categoria_id' => ($b['categoria_id'] ?? null) ?: null,
            ':proveedor_id' => ($b['proveedor_id'] ?? null) ?: null,
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
    $db->prepare("UPDATE repuestos SET activo=0, deleted_at=SYSTIMESTAMP WHERE id=?")->execute([(int)$args['id']]);
    $res->getBody()->write(json_encode(['success' => true]));
    return $res->withHeader('Content-Type', 'application/json');
});

// ─────────────────────────────────────────────────────────────────
// IA sobre el catálogo (Sprint 3) — todo lo calcula el microservicio
// propio en nlp-service/ (TF-IDF + coseno, promedio móvil). No hay
// ninguna llamada a un LLM externo en este flujo.
// ─────────────────────────────────────────────────────────────────

/**
 * GET a un path del microservicio de NLP.
 * Devuelve el array decodificado, o null si el servicio no responde /
 * responde con error — a propósito NO lanza: las funciones de IA son
 * un extra de la vista de repuestos, y si el microservicio está caído
 * la página tiene que seguir funcionando igual (criterio de aceptación
 * del sprint). Mismo patrón de llamada interna que GestorAsistente.
 */
function nlpGet(string $path): ?array
{
    $base = rtrim($_ENV['NLP_SERVICE_URL'] ?? '', '/');
    if ($base === '') {
        return null;
    }

    $ch = curl_init($base . $path);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_HTTPHEADER     => ['X-Internal-Key: ' . ($_ENV['NLP_INTERNAL_KEY'] ?? '')],
        // Timeouts cortos: esto corre mientras el usuario mira un modal ya
        // abierto. Es preferible perder las sugerencias a dejarlo esperando.
        CURLOPT_TIMEOUT        => 3,
        CURLOPT_CONNECTTIMEOUT => 2,
    ]);
    $body     = curl_exec($ch);
    $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $curlErr  = curl_errno($ch) ? curl_error($ch) : null;
    curl_close($ch);

    if ($curlErr !== null || $body === false || $httpCode >= 400) {
        error_log("[ElectriSys][NLP] {$path} no disponible (HTTP {$httpCode}) " . ($curlErr ?? ''));
        return null;
    }

    $decoded = json_decode((string) $body, true);
    return is_array($decoded) ? $decoded : null;
}

/**
 * GET /api/repuestos/{id}/demanda?dias=90
 * Serie diaria de unidades vendidas. La consume el microservicio de NLP
 * para estimar la demanda; la agregación la hace Oracle para no mover
 * las líneas de venta crudas por la red.
 */
$group->get('/repuestos/{id}/demanda', function (Request $req, Response $res, array $args) {
    if (!ctype_digit((string)$args['id'])) {
        $res->getBody()->write(json_encode(['error' => 'ID inválido']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }
    $id   = (int) $args['id'];
    $dias = min(365, max(7, (int)($req->getQueryParams()['dias'] ?? 90)));
    $db   = repuestosDB();

    $rep = $db->prepare("SELECT stock, stock_minimo FROM repuestos WHERE id = ?");
    $rep->execute([$id]);
    $repuesto = $rep->fetch();
    if (!$repuesto) {
        $res->getBody()->write(json_encode(['error' => 'Repuesto no encontrado']));
        return $res->withStatus(404)->withHeader('Content-Type', 'application/json');
    }

    // fn_fecha_local (no TRUNC crudo): los TIMESTAMP están en UTC y una venta
    // nocturna caería en el día siguiente — mismo criterio que el resumen
    // semanal de ventas.php. Las ventas anuladas no cuentan como demanda.
    $stmt = $db->prepare("
        SELECT TO_CHAR(TRUNC(fn_fecha_local(v.creado_en)), 'YYYY-MM-DD') AS fecha,
               SUM(dv.cantidad) AS unidades
        FROM detalle_ventas dv
        JOIN ventas v ON v.id = dv.venta_id
        WHERE dv.repuesto_id = ?
          AND v.estado = 'completada'
          AND fn_fecha_local(v.creado_en) >= fn_hoy_local() - ?
        GROUP BY TRUNC(fn_fecha_local(v.creado_en))
        ORDER BY 1
    ");
    $stmt->execute([$id, $dias]);

    $res->getBody()->write(json_encode([
        'repuesto_id'  => $id,
        'stock'        => (int) $repuesto['stock'],
        'stock_minimo' => (int) $repuesto['stock_minimo'],
        'dias'         => $dias,
        'serie'        => $stmt->fetchAll(),
    ]));
    return $res->withHeader('Content-Type', 'application/json');
});

/**
 * GET /api/repuestos/{id}/recomendaciones
 * Proxy hacia el microservicio: productos relacionados + señal de
 * reabastecimiento. Responde 200 aunque el microservicio esté caído, con
 * disponible=false, para que el frontend no tenga que distinguir "sin
 * sugerencias" de "servicio inaccesible" para poder seguir renderizando.
 */
$group->get('/repuestos/{id}/recomendaciones', function (Request $req, Response $res, array $args) {
    if (!ctype_digit((string)$args['id'])) {
        $res->getBody()->write(json_encode(['error' => 'ID inválido']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }
    $id = (int) $args['id'];

    // Dos llamadas secuenciales y no una: son dos modelos distintos del
    // microservicio, y si la predicción de demanda falla igual queremos
    // mostrar las sugerencias (y viceversa).
    $similares = nlpGet("/recomendaciones/{$id}");
    $demanda   = nlpGet("/prediccion-demanda/{$id}");

    $res->getBody()->write(json_encode([
        'data' => [
            'recomendaciones' => $similares['recomendaciones'] ?? [],
            'demanda'         => $demanda,
        ],
        'disponible' => $similares !== null || $demanda !== null,
    ]));
    return $res->withHeader('Content-Type', 'application/json');
});

/**
 * Helper: lee y valida el parámetro ?ids=1,2,3 de las rutas de demanda.
 * Devuelve enteros únicos, o [] si no hay ninguno válido.
 */
function idsDesdeQuery(array $params): array
{
    $crudo = trim($params['ids'] ?? '');
    if ($crudo === '') {
        return [];
    }
    $ids = [];
    foreach (explode(',', $crudo) as $valor) {
        $valor = trim($valor);
        if (ctype_digit($valor)) {
            $ids[] = (int) $valor;
        }
    }
    // Tope: la tabla pide 15 por página. Sin límite, un ids= gigante arma
    // un IN (...) enorme en Oracle desde una ruta que no tiene rate limit.
    return array_slice(array_values(array_unique($ids)), 0, 100);
}

/**
 * GET /api/repuestos/demanda/lote?ids=1,2,3&dias=90
 * Historial de ventas de VARIOS repuestos en una sola ida a la base.
 * La consume el microservicio de NLP para calcular las señales de toda una
 * página de la tabla; llamar N veces a /{id}/demanda multiplicaría por N
 * tanto los round-trips HTTP como las consultas a Oracle.
 *
 * Ruta de tres segmentos a propósito: "/repuestos/demanda" (dos segmentos)
 * chocaría con "/repuestos/{id}" y Slim la resolvería como id="demanda"
 * — el mismo motivo por el que buscar-compatibles se registra antes de {id}.
 */
$group->get('/repuestos/demanda/lote', function (Request $req, Response $res) {
    $params = $req->getQueryParams();
    $ids    = idsDesdeQuery($params);
    $dias   = min(365, max(7, (int)($params['dias'] ?? 90)));

    if ($ids === []) {
        $res->getBody()->write(json_encode(['dias' => $dias, 'repuestos' => []]));
        return $res->withHeader('Content-Type', 'application/json');
    }

    $db     = repuestosDB();
    $marcas = implode(',', array_fill(0, count($ids), '?'));

    // Los repuestos se leen aunque no tengan ventas: un producto sin
    // movimiento es justamente el caso "rotación baja", y si no viniera en
    // la respuesta el microservicio no tendría nada que reportar de él.
    $repStmt = $db->prepare("SELECT id, stock, stock_minimo FROM repuestos WHERE id IN ($marcas)");
    $repStmt->execute($ids);

    $porRepuesto = [];
    foreach ($repStmt->fetchAll() as $fila) {
        $porRepuesto[(int) $fila['id']] = [
            'repuesto_id'  => (int) $fila['id'],
            'stock'        => (int) $fila['stock'],
            'stock_minimo' => (int) $fila['stock_minimo'],
            'serie'        => [],
        ];
    }

    // Una sola agregación para todos: se agrupa además por repuesto_id.
    // fn_fecha_local por el mismo motivo que en /{id}/demanda (los
    // TIMESTAMP están en UTC y una venta nocturna caería en otro día).
    $stmt = $db->prepare("
        SELECT dv.repuesto_id AS repuesto_id,
               TO_CHAR(TRUNC(fn_fecha_local(v.creado_en)), 'YYYY-MM-DD') AS fecha,
               SUM(dv.cantidad) AS unidades
        FROM detalle_ventas dv
        JOIN ventas v ON v.id = dv.venta_id
        WHERE dv.repuesto_id IN ($marcas)
          AND v.estado = 'completada'
          AND fn_fecha_local(v.creado_en) >= fn_hoy_local() - ?
        GROUP BY dv.repuesto_id, TRUNC(fn_fecha_local(v.creado_en))
        ORDER BY 1, 2
    ");
    $stmt->execute([...$ids, $dias]);

    foreach ($stmt->fetchAll() as $fila) {
        $id = (int) $fila['repuesto_id'];
        if (!isset($porRepuesto[$id])) {
            continue;   // repuesto dado de baja: no se reporta
        }
        $porRepuesto[$id]['serie'][] = [
            'fecha'    => $fila['fecha'],
            'unidades' => (int) $fila['unidades'],
        ];
    }

    $res->getBody()->write(json_encode([
        'dias'      => $dias,
        'repuestos' => array_values($porRepuesto),
    ]));
    return $res->withHeader('Content-Type', 'application/json');
});

/**
 * GET /api/repuestos/demanda/senales?ids=1,2,3
 * Proxy hacia el microservicio: devuelve la señal de reabastecimiento de
 * cada repuesto para pintarla en la tabla. Como el resto de las rutas de
 * IA, responde 200 con disponible=false si el servicio no contesta: la
 * tabla tiene que renderizarse igual, solo que sin los badges.
 */
$group->get('/repuestos/demanda/senales', function (Request $req, Response $res) {
    $ids = idsDesdeQuery($req->getQueryParams());
    if ($ids === []) {
        $res->getBody()->write(json_encode(['data' => [], 'disponible' => true]));
        return $res->withHeader('Content-Type', 'application/json');
    }

    $resultado = nlpGet('/prediccion-demanda?ids=' . implode(',', $ids));

    $res->getBody()->write(json_encode([
        'data'       => $resultado['data'] ?? [],
        'disponible' => $resultado !== null,
    ]));
    return $res->withHeader('Content-Type', 'application/json');
});

<?php
use Psr\Http\Message\ResponseInterface as Response;
use Psr\Http\Message\ServerRequestInterface as Request;
use App\models\Database;

function clientesDB() { return Database::getConnection(); }

function validarCliente(array $b, bool $isNew = true): ?string {
    $nombre = trim($b['nombre'] ?? '');
    if (!$nombre)                              return 'El nombre del cliente es obligatorio';
    if (strlen($nombre) < 2)                   return 'El nombre debe tener al menos 2 caracteres';
    if (strlen($nombre) > 150)                 return 'El nombre no puede superar 150 caracteres';
    // Sin restricción de dígitos: tipo_doc admite NIT, y una razón social
    // como "Repuestos 4x4 S.A.S." o "Distribuidora 2000" es un nombre válido.
    if (isset($b['identificacion']) && $b['identificacion'] !== '' && !preg_match('/^\d{5,15}(-\d)?$/', $b['identificacion']))
                                               return 'La identificación debe tener entre 5 y 15 dígitos (NIT puede incluir dígito de verificación, ej: 900123456-7)';
    if (isset($b['telefono']) && $b['telefono'] !== '' && !preg_match('/^[0-9+\-\s()]{7,20}$/', $b['telefono']))
                                               return 'El formato del teléfono no es válido';
    if (!empty($b['email']) && !filter_var($b['email'], FILTER_VALIDATE_EMAIL))
                                               return 'El formato del email no es válido';
    $tiposValidos = ['CC','NIT','CE','Pasaporte'];
    if (!in_array($b['tipo_doc'] ?? 'CC', $tiposValidos, true))
                                               return 'Tipo de documento inválido';
    return null;
}

$group->get('/clientes', function (Request $req, Response $res) {
    $p     = $req->getQueryParams();
    $page  = max(1, (int)($p['page'] ?? 1));
    $limit = min(100, max(1, (int)($p['limit'] ?? 15)));
    $off   = ($page - 1) * $limit;
    $q     = '%' . trim($p['q'] ?? '') . '%';

    $db   = clientesDB();
    $stmt = $db->prepare("
        SELECT c.*, COUNT(*) OVER() AS total_filas FROM clientes c
        WHERE activo=1 AND (nombre LIKE ? OR identificacion LIKE ? OR email LIKE ?)
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

$group->get('/clientes/{id}', function (Request $req, Response $res, array $args) {
    if (!ctype_digit((string)$args['id'])) {
        $res->getBody()->write(json_encode(['error' => 'ID inválido']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }
    $stmt = clientesDB()->prepare("SELECT * FROM clientes WHERE id=? AND activo=1");
    $stmt->execute([(int)$args['id']]);
    $row = $stmt->fetch();
    if (!$row) {
        $res->getBody()->write(json_encode(['error' => 'Cliente no encontrado']));
        return $res->withStatus(404)->withHeader('Content-Type', 'application/json');
    }
    $res->getBody()->write(json_encode(['data' => $row]));
    return $res->withHeader('Content-Type', 'application/json');
});

$group->post('/clientes', function (Request $req, Response $res) {
    $b = (array) $req->getParsedBody();
    if ($err = validarCliente($b)) {
        $res->getBody()->write(json_encode(['error' => $err]));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }
    try {
        $db = clientesDB();
        $stmt = $db->prepare("
            INSERT INTO clientes (nombre, identificacion, tipo_doc, telefono, email, direccion)
            VALUES (:nombre,:identificacion,:tipo_doc,:telefono,:email,:direccion)
            RETURNING id INTO :out_id
        ");
        $nuevoId = 0;
        $stmt->bindOut(':out_id', $nuevoId);
        $stmt->execute([
            ':nombre'        => trim($b['nombre']),
            ':identificacion'=> trim($b['identificacion'] ?? ''),
            ':tipo_doc'      => $b['tipo_doc'] ?? 'CC',
            ':telefono'      => trim($b['telefono'] ?? ''),
            ':email'         => strtolower(trim($b['email'] ?? '')),
            ':direccion'     => trim($b['direccion'] ?? ''),
        ]);
        $res->getBody()->write(json_encode(['success' => true, 'id' => (int) $nuevoId]));
        return $res->withStatus(201)->withHeader('Content-Type', 'application/json');
    } catch (\PDOException $e) {
        $msg = \App\models\OciConnection::esViolacionDeUnicidad($e)
            ? 'Ya existe un cliente con esa identificación' : 'Error al guardar el cliente';
        $res->getBody()->write(json_encode(['error' => $msg]));
        return $res->withStatus(409)->withHeader('Content-Type', 'application/json');
    }
});

$group->put('/clientes/{id}', function (Request $req, Response $res, array $args) {
    if (!ctype_digit((string)$args['id'])) {
        $res->getBody()->write(json_encode(['error' => 'ID inválido']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }
    $b = (array) $req->getParsedBody();
    if ($err = validarCliente($b, false)) {
        $res->getBody()->write(json_encode(['error' => $err]));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }
    clientesDB()->prepare("
        UPDATE clientes SET nombre=:nombre, identificacion=:identificacion,
        tipo_doc=:tipo_doc, telefono=:telefono, email=:email, direccion=:direccion
        WHERE id=:id AND activo=1
    ")->execute([
        ':nombre'        => trim($b['nombre']),
        ':identificacion'=> trim($b['identificacion'] ?? ''),
        ':tipo_doc'      => $b['tipo_doc'] ?? 'CC',
        ':telefono'      => trim($b['telefono'] ?? ''),
        ':email'         => strtolower(trim($b['email'] ?? '')),
        ':direccion'     => trim($b['direccion'] ?? ''),
        ':id'            => (int)$args['id'],
    ]);
    $res->getBody()->write(json_encode(['success' => true]));
    return $res->withHeader('Content-Type', 'application/json');
});

$group->delete('/clientes/{id}', function (Request $req, Response $res, array $args) {
    if (!ctype_digit((string)$args['id'])) {
        $res->getBody()->write(json_encode(['error' => 'ID inválido']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }
    clientesDB()->prepare("UPDATE clientes SET activo=0, deleted_at=SYSTIMESTAMP WHERE id=?")->execute([(int)$args['id']]);
    $res->getBody()->write(json_encode(['success' => true]));
    return $res->withHeader('Content-Type', 'application/json');
});

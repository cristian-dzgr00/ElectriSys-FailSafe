<?php
use Psr\Http\Message\ResponseInterface as Response;
use Psr\Http\Message\ServerRequestInterface as Request;
use App\models\Database;
use App\middlewares\RoleMiddleware;

function usuariosDB() { return Database::getConnection(); }

function getRolId(AppmodelsOciConnection $db, string $rol): int
{
    $rolesValidos = ['admin', 'vendedor', 'dueno'];
    $rol = in_array($rol, $rolesValidos, true) ? $rol : 'vendedor';
    $stmt = $db->prepare("SELECT id FROM roles WHERE nombre = ?");
    $stmt->execute([$rol]);
    $row = $stmt->fetch();
    if (!$row) {
        $stmt = $db->prepare("INSERT INTO roles (nombre) VALUES (?) RETURNING id INTO :out_id");
        $nuevoId = 0;
        $stmt->bindOut(':out_id', $nuevoId);
        $stmt->execute([$rol]);
        return (int) $nuevoId;
    }
    return (int) $row['id'];
}

function validarUsuario(array $b, bool $isNew = true): ?string
{
    if (empty(trim($b['nombre'] ?? '')))          return 'El nombre del usuario es obligatorio';
    if (strlen(trim($b['nombre'])) < 2)            return 'El nombre debe tener al menos 2 caracteres';
    if (empty(trim($b['email'] ?? '')))            return 'El email es obligatorio';
    if (!filter_var($b['email'], FILTER_VALIDATE_EMAIL)) return 'El formato del email no es válido';
    if ($isNew && empty($b['password']))           return 'La contraseña es obligatoria para nuevos usuarios';
    if (!empty($b['password']) && strlen($b['password']) < 8)
                                                   return 'La contraseña debe tener al menos 8 caracteres';
    return null;
}

// GET /api/usuarios
$group->get('/usuarios', function (Request $req, Response $res) {
    $stmt = usuariosDB()->query("
        SELECT u.id, u.nombre, u.email, u.activo, u.creado_en, r.nombre AS rol
        FROM usuarios u
        JOIN roles r ON u.rol_id = r.id
        WHERE u.deleted_at IS NULL
        ORDER BY u.nombre
    ");
    $res->getBody()->write(json_encode(['data' => $stmt->fetchAll()]));
    return $res->withHeader('Content-Type', 'application/json');
})->add(new RoleMiddleware(['admin', 'dueno']));

// POST /api/usuarios
$group->post('/usuarios', function (Request $req, Response $res) {
    $b = (array) $req->getParsedBody();
    if ($err = validarUsuario($b, true)) {
        $res->getBody()->write(json_encode(['error' => $err]));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }

    try {
        $db    = usuariosDB();
        $hash  = password_hash($b['password'], PASSWORD_BCRYPT, ['cost' => 12]);
        $rolId = getRolId($db, $b['rol'] ?? 'vendedor');

        $stmt = $db->prepare("INSERT INTO usuarios (nombre, email, password, rol_id) VALUES (?,?,?,?) RETURNING id INTO :out_id");
        $nuevoId = 0;
        $stmt->bindOut(':out_id', $nuevoId);
        $stmt->execute([trim($b['nombre']), strtolower(trim($b['email'])), $hash, $rolId]);

        $res->getBody()->write(json_encode(['success' => true, 'id' => (int) $nuevoId]));
        return $res->withStatus(201)->withHeader('Content-Type', 'application/json');
    } catch (\PDOException $e) {
        $msg = \App\models\OciConnection::esViolacionDeUnicidad($e)
            ? 'El email ya está registrado por otro usuario'
            : 'Error al crear el usuario';
        $res->getBody()->write(json_encode(['error' => $msg]));
        return $res->withStatus(409)->withHeader('Content-Type', 'application/json');
    }
})->add(new RoleMiddleware(['admin', 'dueno']));

// PUT /api/usuarios/{id}
$group->put('/usuarios/{id}', function (Request $req, Response $res, array $args) {
    if (!ctype_digit((string)$args['id'])) {
        $res->getBody()->write(json_encode(['error' => 'ID inválido']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }
    $b = (array) $req->getParsedBody();
    if ($err = validarUsuario($b, false)) {
        $res->getBody()->write(json_encode(['error' => $err]));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }

    try {
        $db      = usuariosDB();
        $rolId   = getRolId($db, $b['rol'] ?? 'vendedor');
        $updates = ['nombre=?', 'email=?', 'rol_id=?', 'activo=?'];
        $params  = [trim($b['nombre']), strtolower(trim($b['email'])), $rolId, (int)($b['activo'] ?? 1)];

        if (!empty($b['password'])) {
            $updates[] = 'password=?';
            $params[]  = password_hash($b['password'], PASSWORD_BCRYPT, ['cost' => 12]);
        }

        $params[] = (int)$args['id'];
        $db->prepare("UPDATE usuarios SET " . implode(',', $updates) . " WHERE id=? AND deleted_at IS NULL")
           ->execute($params);

        $res->getBody()->write(json_encode(['success' => true]));
        return $res->withHeader('Content-Type', 'application/json');
    } catch (\PDOException $e) {
        $msg = \App\models\OciConnection::esViolacionDeUnicidad($e)
            ? 'El email ya está registrado por otro usuario'
            : 'Error al actualizar el usuario';
        $res->getBody()->write(json_encode(['error' => $msg]));
        return $res->withStatus(409)->withHeader('Content-Type', 'application/json');
    }
})->add(new RoleMiddleware(['admin', 'dueno']));

// DELETE /api/usuarios/{id} — soft deactivate
$group->delete('/usuarios/{id}', function (Request $req, Response $res, array $args) {
    if (!ctype_digit((string)$args['id'])) {
        $res->getBody()->write(json_encode(['error' => 'ID inválido']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }
    $user = $req->getAttribute('user');
    if ((int)$args['id'] === (int)$user['sub']) {
        $res->getBody()->write(json_encode(['error' => 'No puedes desactivarte a ti mismo']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }
    usuariosDB()->prepare("UPDATE usuarios SET activo=0 WHERE id=?")->execute([(int)$args['id']]);
    $res->getBody()->write(json_encode(['success' => true]));
    return $res->withHeader('Content-Type', 'application/json');
})->add(new RoleMiddleware(['admin', 'dueno']));

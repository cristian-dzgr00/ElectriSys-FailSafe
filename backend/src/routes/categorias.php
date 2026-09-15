<?php
use Psr\Http\Message\ResponseInterface as Response;
use Psr\Http\Message\ServerRequestInterface as Request;
use App\models\Database;

function catDB() { return Database::getConnection(); }

$group->get('/categorias', function (Request $req, Response $res) {
    $stmt = catDB()->query("SELECT * FROM categorias ORDER BY nombre");
    $res->getBody()->write(json_encode(['data' => $stmt->fetchAll()]));
    return $res->withHeader('Content-Type', 'application/json');
});

$group->post('/categorias', function (Request $req, Response $res) {
    $b = (array) $req->getParsedBody();
    $nombre = trim($b['nombre'] ?? '');
    if (!$nombre) {
        $res->getBody()->write(json_encode(['error' => 'El nombre de la categoría es obligatorio']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }
    if (strlen($nombre) > 100) {
        $res->getBody()->write(json_encode(['error' => 'El nombre no puede superar 100 caracteres']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }
    try {
        $db = catDB();
        $stmt = $db->prepare("INSERT INTO categorias (nombre) VALUES (?) RETURNING id INTO :out_id");
        $nuevoId = 0;
        $stmt->bindOut(':out_id', $nuevoId);
        $stmt->execute([$nombre]);
        $res->getBody()->write(json_encode(['success' => true, 'id' => (int) $nuevoId]));
        return $res->withStatus(201)->withHeader('Content-Type', 'application/json');
    } catch (\PDOException $e) {
        $msg = \App\models\OciConnection::esViolacionDeUnicidad($e)
            ? "Ya existe una categoría con el nombre \"$nombre\""
            : 'Error al crear la categoría';
        $res->getBody()->write(json_encode(['error' => $msg]));
        return $res->withStatus(409)->withHeader('Content-Type', 'application/json');
    }
});

$group->put('/categorias/{id}', function (Request $req, Response $res, array $args) {
    if (!ctype_digit((string)$args['id'])) {
        $res->getBody()->write(json_encode(['error' => 'ID inválido']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }
    $b = (array) $req->getParsedBody();
    $nombre = trim($b['nombre'] ?? '');
    if (!$nombre) {
        $res->getBody()->write(json_encode(['error' => 'El nombre de la categoría es obligatorio']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }
    try {
        catDB()->prepare("UPDATE categorias SET nombre=? WHERE id=?")->execute([$nombre, (int)$args['id']]);
        $res->getBody()->write(json_encode(['success' => true]));
        return $res->withHeader('Content-Type', 'application/json');
    } catch (\PDOException $e) {
        $msg = \App\models\OciConnection::esViolacionDeUnicidad($e)
            ? "Ya existe una categoría con el nombre \"$nombre\""
            : 'Error al actualizar la categoría';
        $res->getBody()->write(json_encode(['error' => $msg]));
        return $res->withStatus(409)->withHeader('Content-Type', 'application/json');
    }
});

$group->delete('/categorias/{id}', function (Request $req, Response $res, array $args) {
    if (!ctype_digit((string)$args['id'])) {
        $res->getBody()->write(json_encode(['error' => 'ID inválido']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }
    try {
        catDB()->prepare("DELETE FROM categorias WHERE id=?")->execute([(int)$args['id']]);
        $res->getBody()->write(json_encode(['success' => true]));
        return $res->withHeader('Content-Type', 'application/json');
    } catch (\PDOException $e) {
        $res->getBody()->write(json_encode(['error' => 'No se puede eliminar: la categoría tiene repuestos asociados']));
        return $res->withStatus(409)->withHeader('Content-Type', 'application/json');
    }
});

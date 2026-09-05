<?php
use Psr\Http\Message\ResponseInterface as Response;
use Psr\Http\Message\ServerRequestInterface as Request;
use App\models\VehiculoModel;

// GET /api/vehiculos — listado/búsqueda para selects del frontend
$group->get('/vehiculos', function (Request $req, Response $res) {
    $p = $req->getQueryParams();
    $filtros = [
        'marca'  => trim($p['marca']  ?? ''),
        'modelo' => trim($p['modelo'] ?? ''),
        'q'      => trim($p['q']      ?? ''),
    ];
    $data = (new VehiculoModel())->listar($filtros);
    $res->getBody()->write(json_encode(['data' => $data]));
    return $res->withHeader('Content-Type', 'application/json');
});

// GET /api/vehiculos/marcas — para el primer select encadenado
$group->get('/vehiculos/marcas', function (Request $req, Response $res) {
    $data = (new VehiculoModel())->marcas();
    $res->getBody()->write(json_encode(['data' => $data]));
    return $res->withHeader('Content-Type', 'application/json');
});

// GET /api/vehiculos/modelos?marca=X — segundo select encadenado
$group->get('/vehiculos/modelos', function (Request $req, Response $res) {
    $marca = trim($req->getQueryParams()['marca'] ?? '');
    if ($marca === '') {
        $res->getBody()->write(json_encode(['error' => 'El parámetro marca es obligatorio']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }
    $data = (new VehiculoModel())->modelos($marca);
    $res->getBody()->write(json_encode(['data' => $data]));
    return $res->withHeader('Content-Type', 'application/json');
});

// POST /api/vehiculos — alta (idempotente: si ya existe uno idéntico, lo reutiliza)
$group->post('/vehiculos', function (Request $req, Response $res) {
    $b = (array) $req->getParsedBody();
    if ($err = VehiculoModel::validar($b)) {
        $res->getBody()->write(json_encode(['error' => $err]));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }
    try {
        $modelo = new VehiculoModel();
        $id     = $modelo->buscarOcrear($b);
        $res->getBody()->write(json_encode(['success' => true, 'id' => $id, 'data' => $modelo->buscarPorId($id)]));
        return $res->withStatus(201)->withHeader('Content-Type', 'application/json');
    } catch (\Throwable $e) {
        error_log('[ElectriSys] Error creando vehículo: ' . $e->getMessage());
        $res->getBody()->write(json_encode(['error' => 'No se pudo guardar el vehículo']));
        return $res->withStatus(500)->withHeader('Content-Type', 'application/json');
    }
});

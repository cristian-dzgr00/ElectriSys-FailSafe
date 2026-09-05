<?php
use Psr\Http\Message\ResponseInterface as Response;
use Psr\Http\Message\ServerRequestInterface as Request;
use App\patterns\observer\GestorAsistente;
use App\patterns\observer\AsistenteLogObserver;

function makeGestorAsistente(): GestorAsistente
{
    $gestor = new GestorAsistente();
    $gestor->agregarObserver(new AsistenteLogObserver());
    return $gestor;
}

// POST /api/asistente/consultar
// Intermediario hacia el microservicio de NLP (nlp-service). Cada consulta
// se registra en consultas_asistente vía Observer (AsistenteLogObserver).
$group->post('/asistente/consultar', function (Request $req, Response $res) {
    $b     = (array) $req->getParsedBody();
    $texto = trim($b['texto'] ?? '');

    if ($texto === '') {
        $res->getBody()->write(json_encode(['error' => 'El texto de la consulta es obligatorio']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }
    if (strlen($texto) > 300) {
        $res->getBody()->write(json_encode(['error' => 'La consulta no puede superar 300 caracteres']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }

    $user      = $req->getAttribute('user');
    $usuarioId = (int) ($user['sub'] ?? 0);
    $ip        = $req->getServerParams()['REMOTE_ADDR'] ?? '';

    try {
        $gestor    = makeGestorAsistente();
        $respuesta = $gestor->consultar($texto, $usuarioId, $ip);

        $res->getBody()->write(json_encode($respuesta));
        return $res->withHeader('Content-Type', 'application/json');
    } catch (\Throwable $e) {
        error_log('[ElectriSys] Asistente no disponible: ' . $e->getMessage());
        $res->getBody()->write(json_encode([
            'error' => 'El asistente no está disponible en este momento. Intenta de nuevo en unos segundos.',
        ]));
        return $res->withStatus(503)->withHeader('Content-Type', 'application/json');
    }
});

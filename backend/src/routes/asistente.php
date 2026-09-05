<?php
use Psr\Http\Message\ResponseInterface as Response;
use Psr\Http\Message\ServerRequestInterface as Request;
use App\models\Database;
use App\patterns\observer\GestorAsistente;
use App\patterns\observer\AsistenteLogObserver;

const ASISTENTE_MAX_CONSULTAS_POR_MINUTO = 20;

function makeGestorAsistente(): GestorAsistente
{
    $gestor = new GestorAsistente();
    $gestor->agregarObserver(new AsistenteLogObserver());
    return $gestor;
}

/**
 * Rate limiting por usuario (no por IP, como en login): varios vendedores
 * suelen compartir la IP de la tienda, así que limitar por usuario_id evita
 * que uno solo pueda inundar al microservicio sin bloquear a sus compañeros.
 * Reutiliza consultas_asistente (ya registra cada consulta exitosa vía
 * AsistenteLogObserver) en vez de crear una tabla nueva solo para esto.
 */
function asistenteExcedioLimite(int $usuarioId): bool
{
    try {
        $stmt = Database::getConnection()->prepare("
            SELECT COUNT(*) FROM consultas_asistente
            WHERE usuario_id = ? AND creado_en > DATE_SUB(NOW(), INTERVAL 1 MINUTE)
        ");
        $stmt->execute([$usuarioId]);
        return (int) $stmt->fetchColumn() >= ASISTENTE_MAX_CONSULTAS_POR_MINUTO;
    } catch (\Throwable $e) {
        // Si falla la lectura del límite (ej. BD caída), no bloquear al
        // vendedor por un problema ajeno al rate limiting en sí.
        error_log('[ElectriSys] No se pudo verificar el límite de consultas: ' . $e->getMessage());
        return false;
    }
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

    if (asistenteExcedioLimite($usuarioId)) {
        $res->getBody()->write(json_encode([
            'error' => 'Demasiadas consultas al asistente. Espera un momento antes de continuar.',
            'code'  => 'RATE_LIMITED',
        ]));
        return $res->withStatus(429)
            ->withHeader('Content-Type', 'application/json')
            ->withHeader('Retry-After', '60');
    }

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

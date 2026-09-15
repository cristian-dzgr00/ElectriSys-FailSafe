<?php
use Psr\Http\Message\ResponseInterface as Response;
use Psr\Http\Message\ServerRequestInterface as Request;
use App\models\Database;

/**
 * GET /api/health
 * Retorna el estado del sistema: DB (Oracle, instancia única — ver
 * oracle/docs/migracion-oracle.md), versión. No requiere autenticación —
 * usado por K8s liveness/readiness probes.
 */
$group->get('/health', function (Request $req, Response $res) {
    $start = microtime(true);
    $status = [
        'status'    => 'ok',
        'timestamp' => date('c'),
        'version'   => '2.0.0',
        'checks'    => [],
    ];

    try {
        $db = Database::getConnection();
        $db->query("SELECT 1 FROM dual");
        $status['checks']['db'] = ['status' => 'ok', 'latency_ms' => round((microtime(true) - $start) * 1000, 1)];
    } catch (\Throwable $e) {
        $status['status'] = 'degraded';
        $status['checks']['db'] = ['status' => 'error', 'message' => 'No se pudo conectar a la base de datos'];
    }

    // Check espacio en disco (opcional)
    $freeBytes = disk_free_space('/') ?: 0;
    $totalBytes = disk_total_space('/') ?: 1;
    $freePercent = round($freeBytes / $totalBytes * 100, 1);
    $status['checks']['disk'] = [
        'status'      => $freePercent < 10 ? 'warning' : 'ok',
        'free_percent'=> $freePercent,
    ];

    $httpStatus = $status['status'] === 'ok' ? 200 : ($status['status'] === 'degraded' ? 207 : 503);
    $res->getBody()->write(json_encode($status, JSON_PRETTY_PRINT));
    return $res->withStatus($httpStatus)->withHeader('Content-Type', 'application/json');
});

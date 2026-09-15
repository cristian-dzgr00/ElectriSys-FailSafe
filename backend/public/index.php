<?php
declare(strict_types=1);

use Slim\Factory\AppFactory;
use Slim\Routing\RouteCollectorProxy;
use App\middlewares\JwtMiddleware;
use App\middlewares\VpnMiddleware;
use App\patterns\observer\AuditLogObserver;
use App\patterns\observer\WebSocketObserver;
use App\patterns\observer\GestorVentas;
use Dotenv\Dotenv;

require __DIR__ . '/../vendor/autoload.php';

$dotenv = Dotenv::createImmutable(__DIR__ . '/..');
$dotenv->load();

date_default_timezone_set('America/Bogota');

$app = AppFactory::create();

// ── CORS + Security Headers ──────────────────────────────────
$app->add(function ($request, $handler) {
    $response = $handler->handle($request);
    $isProd   = ($_ENV['APP_ENV'] ?? 'production') === 'production';

    return $response
        ->withHeader('Access-Control-Allow-Origin', $_ENV['FRONTEND_URL'] ?? '*')
        ->withHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        ->withHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, PATCH, DELETE, OPTIONS')
        ->withHeader('X-Content-Type-Options', 'nosniff')
        ->withHeader('X-Frame-Options', 'DENY')
        ->withHeader('X-XSS-Protection', '1; mode=block')
        ->withHeader('Referrer-Policy', 'strict-origin-when-cross-origin')
        ->withHeader('Permissions-Policy', 'geolocation=(), microphone=()')
        ->withHeader('Content-Security-Policy',
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; " .
            "img-src 'self' data:; connect-src 'self' ws: wss:")  // permite WS desde el frontend
        ->withHeader(
            'Strict-Transport-Security',
            $isProd ? 'max-age=63072000; includeSubDomains; preload' : 'max-age=0'
        );
});

$app->options('/{routes:.+}', function ($req, $res) { return $res; });
$app->addBodyParsingMiddleware();

$isProd = ($_ENV['APP_ENV'] ?? 'production') === 'production';
$errMiddleware = $app->addErrorMiddleware(!$isProd, true, true);
$errMiddleware->setDefaultErrorHandler(function ($req, \Throwable $e, bool $displayDetails) use ($app) {
    $payload = $displayDetails
        ? ['error' => $e->getMessage(), 'trace' => $e->getTraceAsString()]
        : ['error' => 'Error interno del servidor. Por favor intenta nuevamente.'];
    $res = $app->getResponseFactory()->createResponse(500);
    $res->getBody()->write(json_encode($payload));
    return $res->withHeader('Content-Type', 'application/json');
});

// ── GestorVentas con Observers registrados ───────────────────
// Se inyecta en el contenedor DI para que las rutas lo usen.
$gestorVentas = new GestorVentas();
$gestorVentas->agregarObserver(new AuditLogObserver());
$gestorVentas->agregarObserver(new WebSocketObserver());   // NUEVO: notif. tiempo real
$app->getContainer()?->set(GestorVentas::class, fn() => $gestorVentas);

// ── Rutas públicas ────────────────────────────────────────────
$app->group('/api', function (RouteCollectorProxy $group) {
    require __DIR__ . '/../src/routes/auth.php';
    require __DIR__ . '/../src/routes/health.php';
});

// ── Rutas admin: JWT + VPN requeridos ─────────────────────────
$app->group('/api', function (RouteCollectorProxy $group) {
    require __DIR__ . '/../src/routes/usuarios.php';
    require __DIR__ . '/../src/routes/auditlog.php';
})->add(new VpnMiddleware())->add(new JwtMiddleware());

// ── Rutas protegidas: JWT únicamente ──────────────────────────
$app->group('/api', function (RouteCollectorProxy $group) {
    require __DIR__ . '/../src/routes/auth_protected.php';
    require __DIR__ . '/../src/routes/ventas.php';
    require __DIR__ . '/../src/routes/vehiculos.php';
    require __DIR__ . '/../src/routes/repuestos.php';
    require __DIR__ . '/../src/routes/asistente.php';
    require __DIR__ . '/../src/routes/clientes.php';
    require __DIR__ . '/../src/routes/proveedores.php';
    require __DIR__ . '/../src/routes/cotizaciones.php';
    require __DIR__ . '/../src/routes/categorias.php';
})->add(new JwtMiddleware());

$app->run();

<?php
declare(strict_types=1);

namespace App\middlewares;

use Psr\Http\Message\ResponseInterface;
use Psr\Http\Message\ServerRequestInterface;
use Psr\Http\Server\MiddlewareInterface;
use Psr\Http\Server\RequestHandlerInterface;
use Slim\Psr7\Response;

/**
 * VpnMiddleware — restringe rutas de administración a IPs de la VPN.
 *
 * Solo las IPs de la subred WireGuard (10.100.0.0/24) pueden
 * acceder a /api/usuarios y /api/auditlog.
 *
 * Uso en index.php:
 *   $app->group('/api', function ($group) {
 *       require __DIR__ . '/../src/routes/usuarios.php';
 *       require __DIR__ . '/../src/routes/auditlog.php';
 *   })->add(new VpnMiddleware())->add(new JwtMiddleware());
 */
class VpnMiddleware implements MiddlewareInterface
{
    /** Subred de la VPN WireGuard */
    private const VPN_SUBNET = '10.100.0.0';
    private const VPN_CIDR   = 24;

    /** IPs siempre permitidas (útil en tests/dev) */
    private const ALWAYS_ALLOWED = ['127.0.0.1', '::1', '172.20.0.1', '172.29.0.1'];

    public function process(ServerRequestInterface $request, RequestHandlerInterface $handler): ResponseInterface
    {
        $ip = $this->getClientIp($request);

        if (in_array($ip, self::ALWAYS_ALLOWED, true)) {
            return $handler->handle($request);
        }

        if (!$this->isVpnIp($ip)) {
            error_log("[ElectriSys][VPN] Acceso denegado desde IP: $ip — ruta: " . $request->getUri()->getPath());
            return $this->forbidden($ip);
        }

        error_log("[ElectriSys][VPN] Acceso admin autorizado desde VPN IP: $ip");
        return $handler->handle($request);
    }

    /**
     * Verifica si una IP está dentro de la subred VPN.
     */
    private function isVpnIp(string $ip): bool
    {
        if (!filter_var($ip, FILTER_VALIDATE_IP, FILTER_FLAG_IPV4)) {
            return false;
        }

        $subnetLong = ip2long(self::VPN_SUBNET);
        $mask       = ~((1 << (32 - self::VPN_CIDR)) - 1);
        $ipLong     = ip2long($ip);

        return ($ipLong & $mask) === ($subnetLong & $mask);
    }

    /**
     * Obtiene la IP real del cliente considerando proxies de confianza.
     */
    private function getClientIp(ServerRequestInterface $request): string
    {
        // En producción detrás de Nginx, usar X-Real-IP
        $realIp = $request->getHeaderLine('X-Real-IP');
        if (!empty($realIp) && filter_var($realIp, FILTER_VALIDATE_IP)) {
            return $realIp;
        }

        // Fallback a REMOTE_ADDR
        $serverParams = $request->getServerParams();
        return $serverParams['REMOTE_ADDR'] ?? '0.0.0.0';
    }

    private function forbidden(string $ip): ResponseInterface
    {
        $response = new Response();
        $response->getBody()->write(json_encode([
            'error' => 'Acceso restringido. Esta ruta requiere conexión VPN.',
            'hint'  => 'Conéctate a la VPN WireGuard de ElectriSys.',
        ]));
        return $response->withStatus(403)->withHeader('Content-Type', 'application/json');
    }
}

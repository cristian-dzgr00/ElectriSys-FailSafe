<?php
declare(strict_types=1);

namespace App\middlewares;

use Psr\Http\Message\ResponseInterface;
use Psr\Http\Message\ServerRequestInterface;
use Psr\Http\Server\MiddlewareInterface;
use Psr\Http\Server\RequestHandlerInterface;
use Slim\Psr7\Response;

/**
 * VpnMiddleware — restringe las rutas de administración a IPs de la VPN.
 *
 * Solo las IPs de la subred WireGuard (10.100.0.0/24) pueden modificar
 * usuarios, respaldos o auditoría. Fuera de la VPN se permite únicamente la
 * LECTURA de tres listados (con JWT válido, aplicado por JwtMiddleware):
 *   - GET /api/usuarios y GET /api/usuarios/{id}
 *   - GET /api/admin/backups (solo el listado)
 *   - GET /api/audit-log
 * Todo lo demás (crear, editar, desactivar, respaldar, exportar CSV)
 * devuelve 403 con code VPN_REQUIRED.
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

    /** Rutas (solo GET) que pueden consultarse sin VPN. */
    private const LECTURA_SIN_VPN = [
        '#^/api/usuarios(/[^/]+)?$#',
        '#^/api/admin/backups$#',
        '#^/api/audit-log$#',
    ];

    public function process(ServerRequestInterface $request, RequestHandlerInterface $handler): ResponseInterface
    {
        $ip = self::getClientIp($request);

        if (self::ipPermitida($ip)) {
            error_log("[ElectriSys][VPN] Acceso admin autorizado desde VPN IP: $ip");
            return $handler->handle($request);
        }

        $ruta = $request->getUri()->getPath();
        if (self::esLecturaSinVpn($request->getMethod(), $ruta)) {
            return $handler->handle($request);
        }

        error_log("[ElectriSys][VPN] Acceso denegado desde IP: $ip — ruta: $ruta");
        return $this->forbidden();
    }

    /**
     * Indica si la petición llega desde la VPN (o desde una IP interna
     * siempre permitida). Es la misma decisión que usa el middleware y el
     * endpoint GET /api/vpn/estado, para que el frontend y el backend nunca
     * discrepen.
     */
    public static function estaEnVpn(ServerRequestInterface $request): bool
    {
        return self::ipPermitida(self::getClientIp($request));
    }

    private static function ipPermitida(string $ip): bool
    {
        return in_array($ip, self::ALWAYS_ALLOWED, true) || self::isVpnIp($ip);
    }

    /** Lectura (GET) de los listados que no exigen VPN. */
    private static function esLecturaSinVpn(string $metodo, string $ruta): bool
    {
        if (strtoupper($metodo) !== 'GET') {
            return false;
        }
        $ruta = rtrim($ruta, '/');
        foreach (self::LECTURA_SIN_VPN as $patron) {
            if (preg_match($patron, $ruta) === 1) {
                return true;
            }
        }
        return false;
    }

    /**
     * Verifica si una IP está dentro de la subred VPN.
     */
    private static function isVpnIp(string $ip): bool
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
     * Obtiene la IP real del cliente.
     *
     * IMPORTANTE: usar unicamente REMOTE_ADDR, nunca un header como
     * X-Real-IP o X-Forwarded-For. REMOTE_ADDR llega a PHP-FPM como
     * fastcgi_param seteado por Nginx desde el socket TCP real
     * (variable remote_addr de Nginx) - el cliente HTTP no puede falsificarlo. Un
     * header SI lo puede mandar cualquiera; confiar en el permitia que
     * un atacante externo enviara "X-Real-IP: 10.100.0.5" y pasara por
     * VPN sin estarlo (bypass confirmado: HTTP 200 en vez de 403).
     */
    private static function getClientIp(ServerRequestInterface $request): string
    {
        $serverParams = $request->getServerParams();
        return $serverParams['REMOTE_ADDR'] ?? '0.0.0.0';
    }

    private function forbidden(): ResponseInterface
    {
        $response = new Response();
        // code lo usa el frontend para mostrar el aviso de VPN en vez de un
        // error genérico.
        $response->getBody()->write(json_encode([
            'error' => 'Acceso restringido. Esta ruta requiere conexión VPN.',
            'hint'  => 'Conéctate a la VPN WireGuard de ElectriSys.',
            'code'  => 'VPN_REQUIRED',
        ]));
        return $response->withStatus(403)->withHeader('Content-Type', 'application/json');
    }
}

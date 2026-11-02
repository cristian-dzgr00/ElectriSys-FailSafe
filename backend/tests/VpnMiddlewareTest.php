<?php
declare(strict_types=1);

use App\middlewares\VpnMiddleware;
use PHPUnit\Framework\TestCase;
use Psr\Http\Message\ResponseInterface;
use Psr\Http\Message\ServerRequestInterface;
use Psr\Http\Server\RequestHandlerInterface;
use Slim\Psr7\Factory\ResponseFactory;
use Slim\Psr7\Factory\ServerRequestFactory;

/**
 * Pruebas de VpnMiddleware: lectura permitida fuera de la VPN solo en las
 * listas de usuarios, respaldos y auditoría; todo lo demás exige VPN.
 */
class VpnMiddlewareTest extends TestCase
{
    private const IP_PUBLICA = '203.0.113.9';
    private const IP_VPN     = '10.100.0.5';

    private function peticion(string $metodo, string $ruta, string $ip, array $headers = []): ServerRequestInterface
    {
        $req = (new ServerRequestFactory())->createServerRequest($metodo, $ruta, ['REMOTE_ADDR' => $ip]);
        foreach ($headers as $nombre => $valor) {
            $req = $req->withHeader($nombre, $valor);
        }
        return $req;
    }

    private function ejecutar(ServerRequestInterface $req): ResponseInterface
    {
        $handler = new class implements RequestHandlerInterface {
            public function handle(ServerRequestInterface $request): ResponseInterface
            {
                return (new ResponseFactory())->createResponse(200);
            }
        };
        return (new VpnMiddleware())->process($req, $handler);
    }

    public function testGetListaUsuariosPasaDesdeIpPublica(): void
    {
        $res = $this->ejecutar($this->peticion('GET', '/api/usuarios', self::IP_PUBLICA));
        $this->assertSame(200, $res->getStatusCode());
    }

    public function testGetUsuarioPorIdPasaDesdeIpPublica(): void
    {
        $res = $this->ejecutar($this->peticion('GET', '/api/usuarios/7', self::IP_PUBLICA));
        $this->assertSame(200, $res->getStatusCode());
    }

    public function testGetListaRespaldosPasaDesdeIpPublica(): void
    {
        $res = $this->ejecutar($this->peticion('GET', '/api/admin/backups', self::IP_PUBLICA));
        $this->assertSame(200, $res->getStatusCode());
    }

    public function testGetAuditLogPasaDesdeIpPublica(): void
    {
        $res = $this->ejecutar($this->peticion('GET', '/api/audit-log', self::IP_PUBLICA));
        $this->assertSame(200, $res->getStatusCode());
    }

    public function testPostUsuariosDesdeIpPublicaDevuelve403ConCodigo(): void
    {
        $res = $this->ejecutar($this->peticion('POST', '/api/usuarios', self::IP_PUBLICA));
        $this->assertSame(403, $res->getStatusCode());
        $cuerpo = json_decode((string) $res->getBody(), true);
        $this->assertSame('VPN_REQUIRED', $cuerpo['code']);
        $this->assertArrayHasKey('error', $cuerpo);
        $this->assertArrayHasKey('hint', $cuerpo);
    }

    public function testPutYDeleteUsuariosDesdeIpPublicaDevuelven403(): void
    {
        foreach (['PUT', 'DELETE', 'PATCH'] as $metodo) {
            $res = $this->ejecutar($this->peticion($metodo, '/api/usuarios/7', self::IP_PUBLICA));
            $this->assertSame(403, $res->getStatusCode(), $metodo);
        }
    }

    public function testExportarCsvDesdeIpPublicaDevuelve403(): void
    {
        $res = $this->ejecutar($this->peticion('GET', '/api/admin/backups/exportar-csv', self::IP_PUBLICA));
        $this->assertSame(403, $res->getStatusCode());
    }

    public function testPostRespaldoDesdeIpPublicaDevuelve403(): void
    {
        $res = $this->ejecutar($this->peticion('POST', '/api/admin/backups', self::IP_PUBLICA));
        $this->assertSame(403, $res->getStatusCode());
    }

    public function testCualquierMetodoDesdeVpnPasa(): void
    {
        foreach (['GET', 'POST', 'PUT', 'DELETE'] as $metodo) {
            $res = $this->ejecutar($this->peticion($metodo, '/api/admin/backups/exportar-csv', self::IP_VPN));
            $this->assertSame(200, $res->getStatusCode(), $metodo);
        }
    }

    public function testHeaderXRealIpNoSaltaLaVpn(): void
    {
        $req = $this->peticion('POST', '/api/usuarios', self::IP_PUBLICA, [
            'X-Real-IP'       => self::IP_VPN,
            'X-Forwarded-For' => self::IP_VPN,
        ]);
        $this->assertSame(403, $this->ejecutar($req)->getStatusCode());
    }

    public function testEstaEnVpnUsaSoloRemoteAddr(): void
    {
        $this->assertTrue(VpnMiddleware::estaEnVpn($this->peticion('GET', '/api/vpn/estado', self::IP_VPN)));
        $this->assertTrue(VpnMiddleware::estaEnVpn($this->peticion('GET', '/api/vpn/estado', '127.0.0.1')));
        $this->assertFalse(VpnMiddleware::estaEnVpn($this->peticion('GET', '/api/vpn/estado', self::IP_PUBLICA)));
        $this->assertFalse(VpnMiddleware::estaEnVpn(
            $this->peticion('GET', '/api/vpn/estado', self::IP_PUBLICA, ['X-Real-IP' => self::IP_VPN])
        ));
    }
}

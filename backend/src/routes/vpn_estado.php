<?php
use Psr\Http\Message\ResponseInterface as Response;
use Psr\Http\Message\ServerRequestInterface as Request;
use App\middlewares\VpnMiddleware;

// GET /api/vpn/estado — indica si la petición llega por la VPN.
// Va solo con JwtMiddleware (no tras VpnMiddleware): el frontend lo consulta
// justamente para saber si debe avisar que las acciones de administración
// requieren VPN. Usa la misma decisión que el middleware (solo REMOTE_ADDR).
$group->get('/vpn/estado', function (Request $req, Response $res) {
    $res->getBody()->write(json_encode(['vpn' => VpnMiddleware::estaEnVpn($req)]));
    return $res->withHeader('Content-Type', 'application/json');
});

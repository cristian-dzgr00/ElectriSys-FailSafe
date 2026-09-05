<?php
use Psr\Http\Message\ResponseInterface as Response;
use Psr\Http\Message\ServerRequestInterface as Request;

// GET /api/auth/me — verificar token (ruta protegida por JwtMiddleware)
$group->get('/auth/me', function (Request $req, Response $res) {
    $user = $req->getAttribute('user');
    $res->getBody()->write(json_encode(['user' => $user]));
    return $res->withHeader('Content-Type', 'application/json');
});

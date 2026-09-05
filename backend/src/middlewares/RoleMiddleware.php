<?php
namespace App\middlewares;

use Psr\Http\Message\ResponseInterface;
use Psr\Http\Message\ServerRequestInterface;
use Psr\Http\Server\MiddlewareInterface;
use Psr\Http\Server\RequestHandlerInterface;
use Slim\Psr7\Response;

class RoleMiddleware implements MiddlewareInterface
{
    private array $rolesPermitidos;

    public function __construct(array $rolesPermitidos)
    {
        $this->rolesPermitidos = $rolesPermitidos;
    }

    public function process(ServerRequestInterface $request, RequestHandlerInterface $handler): ResponseInterface
    {
        $user = $request->getAttribute('user');
        if (!$user || !in_array($user['rol'], $this->rolesPermitidos, true)) {
            $response = new Response();
            $response->getBody()->write(json_encode(['error' => 'Acceso denegado']));
            return $response->withStatus(403)->withHeader('Content-Type', 'application/json');
        }
        return $handler->handle($request);
    }
}

<?php
namespace App\middlewares;

use Firebase\JWT\JWT;
use Firebase\JWT\Key;
use Firebase\JWT\ExpiredException;
use Firebase\JWT\SignatureInvalidException;
use Psr\Http\Message\ResponseInterface;
use Psr\Http\Message\ServerRequestInterface;
use Psr\Http\Server\MiddlewareInterface;
use Psr\Http\Server\RequestHandlerInterface;
use Slim\Psr7\Response;

class JwtMiddleware implements MiddlewareInterface
{
    public function process(ServerRequestInterface $request, RequestHandlerInterface $handler): ResponseInterface
    {
        // Leer Authorization de múltiples fuentes
        $auth = $request->getHeaderLine('Authorization');
        if (empty($auth)) $auth = $_SERVER['HTTP_AUTHORIZATION'] ?? '';
        if (empty($auth)) $auth = $_SERVER['REDIRECT_HTTP_AUTHORIZATION'] ?? '';
        if (empty($auth) && function_exists('getallheaders')) {
            $h = getallheaders();
            $auth = $h['Authorization'] ?? $h['authorization'] ?? '';
        }

        if (empty($auth) || !str_starts_with($auth, 'Bearer ')) {
            return $this->unauthorized('Token no proporcionado');
        }

        $token = substr($auth, 7);

        // Solo capturar errores JWT — no errores de DB ni otros
        try {
            $decoded = JWT::decode($token, new Key($_ENV['JWT_SECRET'], 'HS256'));
        } catch (ExpiredException $e) {
            return $this->unauthorized('Token expirado');
        } catch (SignatureInvalidException $e) {
            return $this->unauthorized('Token inválido');
        } catch (\UnexpectedValueException $e) {
            return $this->unauthorized('Token inválido o expirado');
        } catch (\InvalidArgumentException $e) {
            return $this->unauthorized('Token mal formado');
        }
        // Cualquier otro error (DB, etc.) se propaga normalmente al error handler

        $request = $request->withAttribute('user', (array) $decoded);
        return $handler->handle($request);
    }

    private function unauthorized(string $msg): ResponseInterface
    {
        $response = new Response();
        $response->getBody()->write(json_encode(['error' => $msg]));
        return $response->withStatus(401)->withHeader('Content-Type', 'application/json');
    }
}

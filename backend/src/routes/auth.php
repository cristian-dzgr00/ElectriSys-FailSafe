<?php
use Psr\Http\Message\ResponseInterface as Response;
use Psr\Http\Message\ServerRequestInterface as Request;
use App\models\Database;
use Firebase\JWT\JWT;

/**
 * POST /api/auth/login
 * Rate limiting: máx 5 intentos fallidos por IP en 15 minutos.
 * Usa APCu si disponible, de lo contrario tabla DB como fallback.
 */
$group->post('/auth/login', function (Request $req, Response $res) {

    // ── IP del cliente ────────────────────────────────────────────
    // Solo REMOTE_ADDR: llega a PHP-FPM como fastcgi_param seteado por
    // Nginx desde el socket TCP real, no lo puede falsificar el cliente.
    // X-Forwarded-For SI se puede falsificar (nginx.conf no lo sobreescribe),
    // y usarlo aqui permitia evadir el limite de intentos rotando el header.
    $ip = $req->getServerParams()['REMOTE_ADDR'] ?? 'unknown';

    $MAX_ATTEMPTS = 5;
    $WINDOW_SEC   = 900; // 15 minutos
    $cacheKey     = 'login_fail:' . md5($ip);

    $attempts = 0;
    $db       = null;

    try {
        $db = Database::getConnection();
    } catch (\Throwable $e) {
        error_log('[ElectriSys] Login: no hay DB disponible - ' . $e->getMessage());
        $res->getBody()->write(json_encode(['error' => 'Servicio no disponible. Intenta más tarde.']));
        return $res->withStatus(503)->withHeader('Content-Type', 'application/json');
    }

    if (function_exists('apcu_fetch')) {
        $attempts = (int) apcu_fetch($cacheKey);
    } else {
        try {
            // Corte de fecha calculado en PHP y bindeado como parámetro
            // (en vez de DATE_SUB(NOW(), INTERVAL ? SECOND) de MySQL —
            // Oracle no acepta un placeholder dentro del literal INTERVAL).
            $desde = date('Y-m-d H:i:s', time() - $WINDOW_SEC);
            $stmt = $db->prepare("
                SELECT COUNT(*) FROM login_attempts
                WHERE ip = ? AND created_at > TO_TIMESTAMP(?, 'YYYY-MM-DD HH24:MI:SS')
            ");
            $stmt->execute([$ip, $desde]);
            $attempts = (int) $stmt->fetchColumn();
        } catch (\Throwable) {}
    }

    if ($attempts >= $MAX_ATTEMPTS) {
        $res->getBody()->write(json_encode([
            'error' => 'Demasiados intentos fallidos. Espera 15 minutos antes de intentar nuevamente.',
            'code'  => 'RATE_LIMITED',
        ]));
        return $res->withStatus(429)->withHeader('Content-Type', 'application/json')
                   ->withHeader('Retry-After', '900');
    }

    // ── Validación de input ───────────────────────────────────────
    $body  = (array) $req->getParsedBody();
    $email = trim($body['email'] ?? '');
    $pass  = $body['password'] ?? '';

    if (!$email || !$pass) {
        $res->getBody()->write(json_encode(['error' => 'Email y contraseña son requeridos']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }

    if (!filter_var($email, FILTER_VALIDATE_EMAIL)) {
        $res->getBody()->write(json_encode(['error' => 'El formato del email no es válido']));
        return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
    }

    try {
        $stmt = $db->prepare("
            SELECT u.*, r.nombre AS rol
            FROM usuarios u
            JOIN roles r ON u.rol_id = r.id
            WHERE u.email = ? AND u.activo = 1
        ");
        $stmt->execute([$email]);
        $user = $stmt->fetch();

        if (!$user || !password_verify($pass, $user['password'])) {
            if (function_exists('apcu_store')) {
                apcu_store($cacheKey, $attempts + 1, $WINDOW_SEC);
            } else {
                try {
                    $db->prepare("INSERT INTO login_attempts (ip) VALUES (?)")->execute([$ip]);
                } catch (\Throwable) {}
            }

            $remaining = $MAX_ATTEMPTS - $attempts - 1;
            $res->getBody()->write(json_encode([
                'error' => 'Credenciales incorrectas' . ($remaining > 0 ? " ($remaining intentos restantes)" : ''),
            ]));
            return $res->withStatus(401)->withHeader('Content-Type', 'application/json');
        }

        // Login exitoso — limpiar contador de intentos
        if (function_exists('apcu_delete')) {
            apcu_delete($cacheKey);
        }

        // Generar JWT
        $now     = time();
        $payload = [
            'iss'    => 'electrisys',
            'iat'    => $now,
            'exp'    => $now + (int)$_ENV['JWT_EXPIRATION'],
            'sub'    => $user['id'],
            'nombre' => $user['nombre'],
            'email'  => $user['email'],
            'rol'    => $user['rol'],
        ];

        $token = JWT::encode($payload, $_ENV['JWT_SECRET'], 'HS256');

        try {
            $db->prepare("
                INSERT INTO audit_log (usuario_id, accion, detalle, ip)
                VALUES (?, 'login', ?, ?)
            ")->execute([$user['id'], "Login exitoso desde $ip", $ip]);
        } catch (\Throwable) {}

        $res->getBody()->write(json_encode([
            'token' => $token,
            'user'  => [
                'id'     => $user['id'],
                'nombre' => $user['nombre'],
                'email'  => $user['email'],
                'rol'    => $user['rol'],
            ],
        ]));
        return $res->withHeader('Content-Type', 'application/json');

    } catch (\Throwable $e) {
        error_log('[ElectriSys] Login error: ' . $e->getMessage());
        $res->getBody()->write(json_encode(['error' => 'Error del servidor. Intenta nuevamente.']));
        return $res->withStatus(500)->withHeader('Content-Type', 'application/json');
    }
});

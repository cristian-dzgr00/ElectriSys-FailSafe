<?php
use Psr\Http\Message\ResponseInterface as Response;
use Psr\Http\Message\ServerRequestInterface as Request;
use App\models\Database;
use Firebase\JWT\JWT;

/**
 * POST /api/auth/login
 * Rate limiting: máx 5 intentos fallidos por IP en 15 minutos.
 * Usa APCu si disponible, de lo contrario tabla DB como fallback.
 * Funciona en modo réplica (solo lectura): omite escrituras de auditoría
 * sin bloquear el login.
 */
$group->post('/auth/login', function (Request $req, Response $res) {

    // ── IP del cliente ────────────────────────────────────────────
    $ip = $req->getServerParams()['HTTP_X_FORWARDED_FOR']
       ?? $req->getServerParams()['REMOTE_ADDR']
       ?? 'unknown';
    $ip = explode(',', $ip)[0];

    $MAX_ATTEMPTS = 5;
    $WINDOW_SEC   = 900; // 15 minutos
    $cacheKey     = 'login_fail:' . md5($ip);

    // ── Leer intentos fallidos ────────────────────────────────────
    // Primero intentamos la conexión para saber si estamos en réplica
    $attempts = 0;
    $db       = null;

    try {
        $db = Database::getConnection();
    } catch (\Throwable $e) {
        // Ambas bases de datos caídas
        error_log('[ElectriSys] Login: no hay DB disponible - ' . $e->getMessage());
        $res->getBody()->write(json_encode(['error' => 'Servicio no disponible. Intenta más tarde.']));
        return $res->withStatus(503)->withHeader('Content-Type', 'application/json');
    }

    if (function_exists('apcu_fetch')) {
        $attempts = (int) apcu_fetch($cacheKey);
    } elseif (!Database::$usingReplica) {
        // Solo consultamos login_attempts si hay escritura disponible
        // (en réplica esta tabla podría estar desactualizada, pero al menos no crashea)
        try {
            $stmt = $db->prepare("
                SELECT COUNT(*) FROM login_attempts
                WHERE ip = ? AND created_at > DATE_SUB(NOW(), INTERVAL ? SECOND)
            ");
            $stmt->execute([$ip, $WINDOW_SEC]);
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

    // ── Autenticación ─────────────────────────────────────────────
    // SELECT funciona tanto en primaria como en réplica
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
            // Registrar intento fallido SOLO si hay escritura disponible
            if (function_exists('apcu_store')) {
                apcu_store($cacheKey, $attempts + 1, $WINDOW_SEC);
            } elseif (!Database::$usingReplica) {
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

        // Log de acceso exitoso SOLO si hay escritura disponible
        // En modo réplica se omite silenciosamente para no bloquear el login
        if (!Database::$usingReplica) {
            try {
                $db->prepare("
                    INSERT INTO audit_log (usuario_id, accion, detalle, ip)
                    VALUES (?, 'login', ?, ?)
                ")->execute([$user['id'], "Login exitoso desde $ip", $ip]);
            } catch (\Throwable) {}
        } else {
            error_log("[ElectriSys] Login exitoso de {$user['email']} en modo réplica — audit_log omitido.");
        }

        $res->getBody()->write(json_encode([
            'token'      => $token,
            'en_replica' => Database::$usingReplica, // el frontend puede mostrar un aviso
            'user'       => [
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
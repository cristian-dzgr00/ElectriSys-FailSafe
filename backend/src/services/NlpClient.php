<?php
declare(strict_types=1);

namespace App\services;

/**
 * Cliente HTTP hacia el microservicio de NLP.
 *
 * Existe para que las rutas no dependan de funciones globales declaradas en
 * OTRO archivo de rutas. Antes nlpGet() vivía en repuestos.php y la usaban
 * también ventas.php y pedidos.php: funcionaba solo porque index.php hace
 * los require en cierto orden, que es una dependencia invisible y fácil de
 * romper al reordenar una línea.
 *
 * Contrato de toda la clase: NUNCA lanza. Devuelve null si el microservicio
 * no responde, responde con error o devuelve algo que no es JSON. Las
 * funciones de IA son un extra de la aplicación — si el servicio está caído,
 * la venta se registra igual, solo que sin sugerencias.
 */
class NlpClient
{
    /** Consultas de catálogo: corren mientras el usuario mira una pantalla. */
    private const TIMEOUT_CONSULTA = 3;

    /** Cálculos sobre todo el inventario: el usuario los pidió y espera. */
    private const TIMEOUT_CALCULO = 15;

    private const TIMEOUT_CONEXION = 3;

    public static function get(string $path, int $timeout = self::TIMEOUT_CONSULTA): ?array
    {
        return self::pedir($path, null, $timeout);
    }

    public static function post(string $path, array $payload, int $timeout = self::TIMEOUT_CALCULO): ?array
    {
        return self::pedir($path, $payload, $timeout);
    }

    private static function pedir(string $path, ?array $payload, int $timeout): ?array
    {
        $base = rtrim($_ENV['NLP_SERVICE_URL'] ?? '', '/');
        if ($base === '') {
            return null;
        }

        $opciones = [
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_TIMEOUT        => $timeout,
            CURLOPT_CONNECTTIMEOUT => self::TIMEOUT_CONEXION,
            CURLOPT_HTTPHEADER     => [
                'Content-Type: application/json',
                'X-Internal-Key: ' . ($_ENV['NLP_INTERNAL_KEY'] ?? ''),
            ],
        ];
        if ($payload !== null) {
            $opciones[CURLOPT_POST]       = true;
            $opciones[CURLOPT_POSTFIELDS] = json_encode($payload);
        }

        $ch = curl_init($base . $path);
        curl_setopt_array($ch, $opciones);
        $body     = curl_exec($ch);
        $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        $curlErr  = curl_errno($ch) ? curl_error($ch) : null;
        curl_close($ch);

        if ($curlErr !== null || $body === false || $httpCode >= 400) {
            error_log("[ElectriSys][NLP] {$path} no disponible (HTTP {$httpCode}) " . ($curlErr ?? ''));
            return null;
        }

        $decoded = json_decode((string) $body, true);
        return is_array($decoded) ? $decoded : null;
    }
}

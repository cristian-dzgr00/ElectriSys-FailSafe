<?php
declare(strict_types=1);

namespace App\config;

/**
 * TlsConfig — centraliza la configuración TLS/mTLS para PDO.
 *
 * Lee los certificados del volumen montado en /etc/tls/
 * y construye las opciones PDO necesarias para SSL mutuo.
 */
class TlsConfig
{
    private const TLS_DIR = '/etc/tls';

    /**
     * Retorna las opciones PDO para conexión con mTLS a MySQL.
     * Si los certificados no existen (entorno dev sin certs),
     * retorna un array vacío para no romper el desarrollo local.
     */
    public static function getMysqlPdoOptions(): array
    {
        $ca   = self::TLS_DIR . '/ca/ca.crt';
        $cert = self::TLS_DIR . '/php-fpm/php-fpm.crt';
        $key  = self::TLS_DIR . '/php-fpm/php-fpm.key';

        if (!file_exists($ca) || !file_exists($cert) || !file_exists($key)) {
            error_log('[ElectriSys][TLS] Certificados no encontrados — conexión sin TLS (solo en dev)');
            return [];
        }

        return [
            \PDO::MYSQL_ATTR_SSL_CA   => $ca,
            \PDO::MYSQL_ATTR_SSL_CERT => $cert,
            \PDO::MYSQL_ATTR_SSL_KEY  => $key,
            // Verificar CN del servidor MySQL (mTLS estricto)
            \PDO::MYSQL_ATTR_SSL_VERIFY_SERVER_CERT => true,
        ];
    }

    /**
     * Verifica que todos los archivos TLS necesarios estén presentes.
     */
    public static function isTlsAvailable(): bool
    {
        foreach (['ca/ca.crt', 'php-fpm/php-fpm.crt', 'php-fpm/php-fpm.key'] as $file) {
            if (!file_exists(self::TLS_DIR . '/' . $file)) {
                return false;
            }
        }
        return true;
    }
}

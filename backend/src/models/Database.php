<?php
namespace App\models;

use PDO;
use PDOException;
use App\config\TlsConfig;

class Database
{
    private static ?PDO $primaryConn   = null;
    private static ?PDO $replicaConn   = null;
    public  static bool $usingReplica  = false;
    private static bool $primaryFailed = false; // evita reintentos costosos en la misma petición

    public static function getConnection(): PDO
    {
        // Si ya tenemos conexión primaria activa, devolverla directamente
        if (self::$primaryConn !== null) {
            return self::$primaryConn;
        }

        // Solo intentar la primaria si no sabemos que ya falló en esta petición
        if (!self::$primaryFailed) {
            $intentos = 3;
            while ($intentos-- > 0) {
                try {
                    self::$primaryConn   = self::connect(
                        $_ENV['DB_PRIMARY_HOST'] ?? 'mysql-primary',
                        $_ENV['DB_PRIMARY_PORT'] ?? '3306',
                        $_ENV['DB_PRIMARY_NAME'] ?? 'electrisys',
                        $_ENV['DB_PRIMARY_USER'] ?? 'electrisys_user',
                        $_ENV['DB_PRIMARY_PASS'] ?? ''
                    );
                    self::$usingReplica  = false;
                    self::$primaryFailed = false;
                    return self::$primaryConn;
                } catch (PDOException $e) {
                    error_log('[ElectriSys] Primary no disponible, reintentando... ' . $e->getMessage());
                    usleep(300000);
                }
            }
            // Marcar que la primaria falló para no reintentar en esta misma petición
            self::$primaryFailed = true;
        }

        // Fallback: réplica (solo lectura)
        if (self::$replicaConn === null) {
            try {
                self::$replicaConn = self::connect(
                    $_ENV['DB_REPLICA_HOST'] ?? 'mysql-replica',
                    $_ENV['DB_REPLICA_PORT'] ?? '3306',
                    $_ENV['DB_REPLICA_NAME'] ?? 'electrisys',
                    $_ENV['DB_REPLICA_USER'] ?? 'electrisys_user',
                    $_ENV['DB_REPLICA_PASS'] ?? ''
                );
                error_log('[ElectriSys] Usando Réplica como fallback.');
            } catch (PDOException $e) {
                throw new PDOException('[ElectriSys] Ambas bases de datos no disponibles: ' . $e->getMessage());
            }
        }

        self::$usingReplica = true;
        return self::$replicaConn;
    }

    /**
     * Indica si hay conexión de escritura disponible (solo la primaria permite escritura).
     */
    public static function isWritable(): bool
    {
        return !self::$usingReplica;
    }

    private static function connect(string $host, string $port, string $dbname, string $user, string $pass): PDO
    {
        $dsn = "mysql:host={$host};port={$port};dbname={$dbname};charset=utf8mb4";

        $options = [
            PDO::ATTR_ERRMODE            => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
            PDO::ATTR_EMULATE_PREPARES   => false,
            PDO::ATTR_PERSISTENT         => false,
            PDO::MYSQL_ATTR_INIT_COMMAND => "SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci",
        ];

        // mTLS: agregar opciones SSL si los certificados existen
        $tlsOptions = TlsConfig::getMysqlPdoOptions();
        if (!empty($tlsOptions)) {
            $options = array_merge($options, $tlsOptions);
            error_log("[ElectriSys][mTLS] Conectando a {$host} con mTLS");
        }

        return new PDO($dsn, $user, $pass, $options);
    }
}
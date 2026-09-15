<?php
declare(strict_types=1);

namespace App\models;

use RuntimeException;

/**
 * Envoltorio delgado de una conexión oci8 con la misma superficie que ya
 * usaba el backend contra PDO (prepare/beginTransaction/commit/rollBack) —
 * así las rutas y modelos no cambian su forma de invocar la base de datos,
 * solo el texto SQL en sí (ver el detalle de cada cambio en las rutas).
 *
 * lastInsertId() NO existe acá a propósito: Oracle no tiene un "último id"
 * a nivel de sesión como MySQL. Cada INSERT que necesita el id nuevo usa
 * "RETURNING id INTO :id" + OciStatement::bindOut() directamente.
 */
class OciConnection
{
    /** @var resource|\OCI-Connection */
    private $conn;
    private bool $enTransaccion = false;

    public function __construct($conn)
    {
        $this->conn = $conn;
    }

    /** Equivalente a PDO::query() — prepara y ejecuta sin parámetros. */
    public function query(string $sql): OciStatement
    {
        $stmt = $this->prepare($sql);
        $stmt->execute();
        return $stmt;
    }

    public function prepare(string $sql): OciStatement
    {
        [$sqlConNombres, $placeholders] = self::posicionalANombrado($sql);
        $stid = @oci_parse($this->conn, $sqlConNombres);
        if ($stid === false) {
            $e = oci_error($this->conn);
            throw new RuntimeException('Error preparando SQL: ' . ($e['message'] ?? 'desconocido'));
        }
        $modo = $this->enTransaccion ? OCI_NO_AUTO_COMMIT : OCI_COMMIT_ON_SUCCESS;
        return new OciStatement($stid, $placeholders, $modo);
    }

    public function beginTransaction(): bool
    {
        $this->enTransaccion = true;
        return true;
    }

    public function commit(): bool
    {
        $ok = oci_commit($this->conn);
        $this->enTransaccion = false;
        return $ok;
    }

    public function rollBack(): bool
    {
        $ok = oci_rollback($this->conn);
        $this->enTransaccion = false;
        return $ok;
    }

    /** Equivalente a "str_contains($e->getMessage(), 'Duplicate')" de MySQL —
     *  Oracle reporta violación de UNIQUE/PK como ORA-00001. */
    public static function esViolacionDeUnicidad(\Throwable $e): bool
    {
        return str_contains($e->getMessage(), 'ORA-00001');
    }

    /** Conexión oci8 cruda — para llamadas a packages PL/SQL con REF CURSOR
     *  (oci_new_cursor necesita el resource de conexión, no un statement). */
    public function raw()
    {
        return $this->conn;
    }

    /** Convierte "?" posicionales (estilo PDO, el que ya usa todo el
     *  proyecto) a :p1,:p2,... — oci8 no soporta "?" en absoluto. */
    private static function posicionalANombrado(string $sql): array
    {
        $i = 0;
        $nombres = [];
        $convertido = preg_replace_callback('/\?/', function () use (&$i, &$nombres) {
            $i++;
            $n = ":p{$i}";
            $nombres[] = $n;
            return $n;
        }, $sql);
        return [$convertido, $nombres];
    }
}

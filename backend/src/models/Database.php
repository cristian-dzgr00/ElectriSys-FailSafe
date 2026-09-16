<?php
namespace App\models;

use RuntimeException;

/**
 * Conexión a Oracle Database 23ai Free (motor único del proyecto — ver
 * oracle/docs/migracion-oracle.md). Antes había primary+réplica MySQL con
 * failover automático; Oracle 23ai Free no soporta Data Guard/RAC (son
 * features Enterprise), así que esto quedó como una sola instancia. Se
 * retiró $usingReplica/isWritable() — ya no aplica sin réplica.
 */
class Database
{
    private static ?OciConnection $conn = null;

    public static function getConnection(): OciConnection
    {
        if (self::$conn !== null) {
            return self::$conn;
        }

        $host    = $_ENV['DB_HOST']         ?? 'oracle-db';
        $port    = $_ENV['DB_PORT']         ?? '1521';
        $service = $_ENV['DB_SERVICE_NAME'] ?? 'FREEPDB1';
        $user    = $_ENV['DB_USER']         ?? 'electrisys';
        $pass    = $_ENV['DB_PASS']         ?? '';

        $tns = "(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST={$host})(PORT={$port}))" .
               "(CONNECT_DATA=(SERVICE_NAME={$service})))";

        // TLS: diferido (ver oracle/docs/migracion-oracle.md) — Oracle usa
        // Wallets, un mecanismo distinto a los certificados PEM sueltos que
        // usaba MySQL; no se aborda en esta migración, igual que el mTLS de
        // MySQL tampoco llegó a validarse de punta a punta en producción
        // real (ver docs/asistente-nlp.md).
        $raw = @oci_connect($user, $pass, $tns, 'AL32UTF8');
        if ($raw === false) {
            $e = oci_error();
            throw new RuntimeException('[ElectriSys] No se pudo conectar a Oracle: ' . ($e['message'] ?? 'desconocido'));
        }

        // Sin esto Oracle devuelve las fechas en su formato NLS por defecto
        // ("16-SEP-26 04.38.34.781557 AM"), que new Date() del frontend no
        // puede parsear. Los TIMESTAMP se guardan con SYSTIMESTAMP y el
        // contenedor corre en UTC, así que la "Z" los marca como tales para
        // que el navegador los convierta a la zona horaria local.
        $alter = oci_parse($raw,
            "ALTER SESSION SET"
            . " NLS_DATE_FORMAT = 'YYYY-MM-DD'"
            . " NLS_TIMESTAMP_FORMAT = 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"'"
            . " NLS_TIMESTAMP_TZ_FORMAT = 'YYYY-MM-DD\"T\"HH24:MI:SSTZH:TZM'"
        );
        oci_execute($alter);

        self::$conn = new OciConnection($raw);
        return self::$conn;
    }
}

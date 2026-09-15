<?php
declare(strict_types=1);

namespace App\config;

/**
 * TlsConfig — diferido para Oracle (ver oracle/docs/migracion-oracle.md).
 *
 * Con MySQL esto armaba las opciones mTLS de PDO a partir de certificados
 * PEM sueltos (ca.crt/php-fpm.crt/php-fpm.key). Oracle usa un mecanismo
 * distinto (Wallets, vía sqlnet.ora/TNS_ADMIN), y esta migración no lo
 * aborda — mismo criterio que ya se documentó para el mTLS de MySQL, que
 * tampoco llegó a validarse de punta a punta en producción real (ver
 * docs/asistente-nlp.md). Queda como no-op explícito en vez de borrar el
 * archivo, para que quien retome TLS en Oracle sepa dónde engancharlo.
 */
class TlsConfig
{
    public static function isTlsAvailable(): bool
    {
        return false;
    }
}

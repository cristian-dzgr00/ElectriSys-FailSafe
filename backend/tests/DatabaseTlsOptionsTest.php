<?php
use PHPUnit\Framework\TestCase;

/**
 * Regresión de un bug real encontrado en la validación Docker/mTLS de la
 * Sprint 8 del asistente NLP: Database::connect() combinaba las opciones
 * base de PDO con las opciones TLS usando array_merge(). Como las claves
 * de ese array son las constantes PDO::* (enteros), array_merge() las
 * reindexa secuencialmente (0,1,2...) en vez de preservarlas — por pura
 * coincidencia posicional, el valor de SSL_VERIFY_SERVER_CERT (true)
 * terminaba en la posición que corresponde a PDO::ATTR_CASE, y PDO
 * interpretaba ese true como PDO::CASE_UPPER: TODAS las columnas de TODAS
 * las consultas volvían en mayúsculas con mTLS activo, rompiendo el login
 * y cualquier código que accediera a $row['columna'] en minúscula.
 *
 * Nunca se detectó en ningún sprint anterior porque ninguna prueba local
 * había usado certificados TLS reales — solo se manifestaba con mTLS
 * activo (el modo "producción" real de este proyecto).
 */
class DatabaseTlsOptionsTest extends TestCase
{
    public function testCombinarOpcionesConArrayMergeCorrompeLasClaves(): void
    {
        // Documenta el bug en sí: array_merge() SÍ reindexa claves enteras.
        // Esta prueba no valida el código de Database.php — prueba que
        // nuestra suposición sobre el comportamiento de PHP es correcta,
        // para que quede claro por qué el fix (usar +) es necesario.
        $base = [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION];
        $tls  = [PDO::MYSQL_ATTR_SSL_VERIFY_SERVER_CERT => true];

        $corrompido = array_merge($base, $tls);

        $this->assertArrayNotHasKey(
            PDO::MYSQL_ATTR_SSL_VERIFY_SERVER_CERT,
            $corrompido,
            'array_merge() debería haber perdido la clave entera original (es el bug documentado)'
        );
    }

    public function testCombinarOpcionesConUnionPreservaLasClaves(): void
    {
        $base = [
            PDO::ATTR_ERRMODE            => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
        ];
        $tls = [
            PDO::MYSQL_ATTR_SSL_VERIFY_SERVER_CERT => true,
            PDO::ATTR_CASE => PDO::CASE_NATURAL, // por si acaso, nunca debe quedar en CASE_UPPER
        ];

        $combinado = $base + $tls;

        $this->assertSame(PDO::ERRMODE_EXCEPTION, $combinado[PDO::ATTR_ERRMODE]);
        $this->assertSame(PDO::FETCH_ASSOC, $combinado[PDO::ATTR_DEFAULT_FETCH_MODE]);
        $this->assertTrue($combinado[PDO::MYSQL_ATTR_SSL_VERIFY_SERVER_CERT]);
        $this->assertNotSame(
            PDO::CASE_UPPER,
            $combinado[PDO::ATTR_CASE] ?? PDO::CASE_NATURAL,
            'PDO::ATTR_CASE nunca debe terminar en CASE_UPPER por un mal combinado de opciones'
        );
    }

    /** Guarda que Database.php no vuelva a usar array_merge() para esto */
    public function testDatabasePhpNoUsaArrayMergeParaOpcionesTls(): void
    {
        $codigo = file_get_contents(__DIR__ . '/../src/models/Database.php');
        $this->assertStringNotContainsString(
            'array_merge($options, $tlsOptions)',
            $codigo,
            'Database::connect() no debe combinar opciones de PDO con array_merge() — ' .
            'reindexa las claves enteras (constantes PDO::*) y corrompe el array. Usar + o array_replace().'
        );
        $this->assertStringContainsString('$options + $tlsOptions', $codigo);
    }
}

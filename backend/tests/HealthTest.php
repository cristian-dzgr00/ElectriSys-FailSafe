<?php
use PHPUnit\Framework\TestCase;

/**
 * Tests básicos de ElectriSys POS
 * Expandir con tests de rutas usando Slim TestApp o HTTP Kernel testing.
 */
class HealthTest extends TestCase
{
    /** Valida que el schema SQL tiene las tablas críticas */
    public function testSchemaContiensTablasEsenciales(): void
    {
        $schema = file_get_contents(__DIR__ . '/../../database/schema.sql');
        $this->assertStringContainsString('CREATE TABLE ventas',       $schema);
        $this->assertStringContainsString('CREATE TABLE repuestos',    $schema);
        $this->assertStringContainsString('CREATE TABLE clientes',     $schema);
        $this->assertStringContainsString('CREATE TABLE audit_log',    $schema);
        $this->assertStringContainsString('CREATE TABLE login_attempts',$schema);
    }

    /** Valida que el schema incluye índice compuesto crítico */
    public function testSchemaContieneIndiceCompuesto(): void
    {
        $schema = file_get_contents(__DIR__ . '/../../database/schema.sql');
        $this->assertStringContainsString('idx_detalle_ventas_venta_repuesto', $schema);
    }

    /** Valida que el seed no contiene contraseñas en texto plano */
    public function testSeedNoContienePasswordTextoPlano(): void
    {
        $seed = file_get_contents(__DIR__ . '/../../database/seed.sql');
        // Debe contener hash de bcrypt (empieza con $2y$)
        $this->assertStringContainsString('$2y$', $seed);
        // No debe tener "admin123" en texto plano
        $this->assertStringNotContainsString("'admin123'", $seed);
    }

    /** Valida que el health endpoint está definido */
    public function testHealthRouteExiste(): void
    {
        $health = file_get_contents(__DIR__ . '/../src/routes/health.php');
        $this->assertStringContainsString('/health', $health);
        $this->assertStringContainsString('db_primary', $health);
    }

    /** Valida que el rate limiting está implementado en login */
    public function testRateLimitingEnLogin(): void
    {
        $auth = file_get_contents(__DIR__ . '/../src/routes/auth.php');
        $this->assertStringContainsString('RATE_LIMITED', $auth);
        $this->assertStringContainsString('MAX_ATTEMPTS', $auth);
    }

    /** Valida que los mensajes de error no exponen stack traces */
    public function testIndexPHPManejaErroresProduccion(): void
    {
        $index = file_get_contents(__DIR__ . '/../public/index.php');
        $this->assertStringContainsString('setDefaultErrorHandler', $index);
        $this->assertStringContainsString('Error interno del servidor', $index);
    }

    /** Valida que la migración v3 (asistente NLP) crea las tablas necesarias */
    public function testMigracionV3ContieneTablasNlp(): void
    {
        $migracion = file_get_contents(__DIR__ . '/../../database/schema_v3_migration_nlp.sql');
        $this->assertStringContainsString('CREATE TABLE IF NOT EXISTS vehiculos', $migracion);
        $this->assertStringContainsString('CREATE TABLE IF NOT EXISTS repuesto_compatibilidad', $migracion);
        $this->assertStringContainsString('CREATE TABLE IF NOT EXISTS consultas_asistente', $migracion);
        $this->assertStringContainsString('FOREIGN KEY (repuesto_id) REFERENCES repuestos(id)', $migracion);
    }

    /** Valida que la ruta del asistente maneja el timeout y la caída del microservicio */
    public function testRutaAsistenteManejaFalloDelMicroservicio(): void
    {
        $ruta = file_get_contents(__DIR__ . '/../src/routes/asistente.php');
        $this->assertStringContainsString('/asistente/consultar', $ruta);
        $this->assertStringContainsString('withStatus(503)', $ruta);
        $this->assertStringContainsString('AsistenteLogObserver', $ruta);
    }

    /** Valida que el .env define las variables del microservicio NLP */
    public function testEnvDefineVariablesNlp(): void
    {
        $env = file_get_contents(__DIR__ . '/../.env');
        $this->assertStringContainsString('NLP_SERVICE_URL', $env);
        $this->assertStringContainsString('NLP_INTERNAL_KEY', $env);
    }
}

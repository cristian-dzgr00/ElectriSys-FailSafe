<?php
use PHPUnit\Framework\TestCase;
use App\services\ListaIds;
use App\services\SugerenciaBusqueda;

/**
 * Casos límite de las piezas que alimentan las sugerencias de IA: lectura
 * de ?ids=, "¿Quisiste decir…?" y el comportamiento cuando el microservicio
 * de NLP no responde.
 */
class SugerenciasIaTest extends TestCase
{
    private ?string $urlOriginal;

    protected function setUp(): void
    {
        $this->urlOriginal = $_ENV['NLP_SERVICE_URL'] ?? null;
    }

    protected function tearDown(): void
    {
        if ($this->urlOriginal === null) {
            unset($_ENV['NLP_SERVICE_URL']);
        } else {
            $_ENV['NLP_SERVICE_URL'] = $this->urlOriginal;
        }
    }

    // ── ListaIds ─────────────────────────────────────────────────────

    public function testListaIdsVaciaONula(): void
    {
        $this->assertSame([], ListaIds::desdeTexto(null));
        $this->assertSame([], ListaIds::desdeTexto(''));
        $this->assertSame([], ListaIds::desdeTexto('  , ,'));
    }

    public function testListaIdsDescartaBasuraDuplicadosYNoPositivos(): void
    {
        $this->assertSame([1, 3, 7], ListaIds::desdeTexto('1, abc,3,,1,-5,0,7,2.5,1e3'));
    }

    public function testListaIdsTopeaLaCantidad(): void
    {
        $crudo = implode(',', range(1, 500));
        $this->assertCount(100, ListaIds::desdeTexto($crudo, 100));
        $this->assertSame([1, 2, 3], ListaIds::desdeTexto($crudo, 3));
        $this->assertSame([], ListaIds::desdeTexto('1,2', 0));
    }

    public function testListaIdsIgnoraNumerosDemasiadoGrandesParaUnId(): void
    {
        $this->assertSame([5], ListaIds::desdeTexto('99999999999999999999999,5'));
    }

    // ── SugerenciaBusqueda ───────────────────────────────────────────

    public function testBusquedaMuyCortaOMuyLargaNoConsultaAlMicroservicio(): void
    {
        // Si consultara, fallaría la conexión y el resultado sería igual (null);
        // por eso se usa una URL imposible Y se mide que sea inmediato.
        $_ENV['NLP_SERVICE_URL'] = 'http://127.0.0.1:1';
        $inicio = microtime(true);

        $this->assertNull(SugerenciaBusqueda::corregir(''));
        $this->assertNull(SugerenciaBusqueda::corregir('  ab '));
        $this->assertNull(SugerenciaBusqueda::corregir(str_repeat('filtro ', 50)));

        $this->assertLessThan(0.5, microtime(true) - $inicio);
    }

    public function testMicroservicioCaidoDevuelveNullSinLanzar(): void
    {
        $_ENV['NLP_SERVICE_URL'] = 'http://127.0.0.1:1';   // puerto que no acepta conexiones
        $this->assertNull(SugerenciaBusqueda::corregir('pastila de freno'));
    }

    public function testSinUrlConfiguradaDevuelveNull(): void
    {
        unset($_ENV['NLP_SERVICE_URL']);
        $this->assertNull(SugerenciaBusqueda::corregir('pastila de freno'));
    }

    // ── Rutas: orden de registro y rate limit del asistente ─────────

    public function testLasRutasDeSugerenciaSeRegistranAntesDeLasRutasConId(): void
    {
        $pedidos = file_get_contents(__DIR__ . '/../src/routes/pedidos.php');
        $this->assertLessThan(
            strpos($pedidos, "'/pedidos/{id}'"),
            strpos($pedidos, "'/pedidos/sugerencia/items'"),
            '/pedidos/sugerencia/items debe registrarse antes de /pedidos/{id}'
        );
        $this->assertStringContainsString("RoleMiddleware(['admin', 'dueno'])", $pedidos);

        $ventas = file_get_contents(__DIR__ . '/../src/routes/ventas.php');
        $this->assertLessThan(
            strpos($ventas, "'/ventas/{id}'"),
            strpos($ventas, "'/ventas/complementos'"),
            '/ventas/complementos debe registrarse antes de /ventas/{id}'
        );
    }

    public function testElRateLimitDelAsistenteSigueAntesDeLlamarAlMicroservicio(): void
    {
        $asistente = file_get_contents(__DIR__ . '/../src/routes/asistente.php');

        $this->assertStringContainsString('const ASISTENTE_MAX_CONSULTAS_POR_MINUTO = 20;', $asistente);
        $posLimite   = strpos($asistente, 'asistenteExcedioLimite($usuarioId)');
        $posConsulta = strpos($asistente, '$gestor->consultar(');
        $this->assertNotFalse($posLimite);
        $this->assertNotFalse($posConsulta);
        $this->assertLessThan($posConsulta, $posLimite, 'el límite debe evaluarse antes de consultar');
        $this->assertStringContainsString("'code'  => 'RATE_LIMITED'", $asistente);
        $this->assertStringContainsString('withStatus(429)', $asistente);
        $this->assertStringContainsString("'Retry-After', '60'", $asistente);
    }

    public function testElAsistenteSigueValidandoTextoVacioYLargo(): void
    {
        $asistente = file_get_contents(__DIR__ . '/../src/routes/asistente.php');
        $this->assertStringContainsString("if (\$texto === '')", $asistente);
        $this->assertStringContainsString('strlen($texto) > 300', $asistente);
    }
}

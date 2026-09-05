<?php
use PHPUnit\Framework\TestCase;
use App\patterns\observer\GestorAsistente;
use App\patterns\observer\VentaObserver;

/**
 * Pruebas del Subject del patrón Observer para el asistente NLP.
 * No dependen de un microservicio real: usan una URL que falla rápido
 * para probar el manejo de errores, y un Observer falso para probar
 * la mecánica de notificación sin tocar la base de datos.
 */
class GestorAsistenteTest extends TestCase
{
    private ?string $nlpServiceUrlOriginal;

    protected function setUp(): void
    {
        $this->nlpServiceUrlOriginal = $_ENV['NLP_SERVICE_URL'] ?? null;
    }

    protected function tearDown(): void
    {
        if ($this->nlpServiceUrlOriginal === null) {
            unset($_ENV['NLP_SERVICE_URL']);
        } else {
            $_ENV['NLP_SERVICE_URL'] = $this->nlpServiceUrlOriginal;
        }
    }

    public function testConsultarLanzaExcepcionSiElMicroservicioNoResponde(): void
    {
        $_ENV['NLP_SERVICE_URL'] = 'http://127.0.0.1:1'; // puerto que no acepta conexiones

        $observerFalso = new class implements VentaObserver {
            public bool $fueNotificado = false;
            public function actualizar(string $accion, array $contexto): void
            {
                $this->fueNotificado = true;
            }
        };

        $gestor = new GestorAsistente();
        $gestor->agregarObserver($observerFalso);

        $this->expectException(\RuntimeException::class);
        try {
            $gestor->consultar('no hay filtro de aceite', 1, '127.0.0.1');
        } finally {
            // Si el microservicio falla, NO debe notificarse a los Observers
            // (no hay nada útil que registrar todavía).
            $this->assertFalse($observerFalso->fueNotificado);
        }
    }

    public function testAgregarYRemoverObserverFunciona(): void
    {
        $observer = new class implements VentaObserver {
            public int $veces = 0;
            public function actualizar(string $accion, array $contexto): void
            {
                $this->veces++;
            }
        };

        $gestor = new GestorAsistente();
        $gestor->agregarObserver($observer);
        $gestor->notificarObservers('prueba', []);
        $this->assertSame(1, $observer->veces);

        $gestor->removerObserver($observer);
        $gestor->notificarObservers('prueba', []);
        $this->assertSame(1, $observer->veces, 'No debería notificarse tras remover el observer');
    }

    public function testUnObserverQueFallaNoBloqueaALosDemas(): void
    {
        $observerQueFalla = new class implements VentaObserver {
            public function actualizar(string $accion, array $contexto): void
            {
                throw new \RuntimeException('Observer roto a propósito');
            }
        };
        $observerBueno = new class implements VentaObserver {
            public bool $fueNotificado = false;
            public function actualizar(string $accion, array $contexto): void
            {
                $this->fueNotificado = true;
            }
        };

        $gestor = new GestorAsistente();
        $gestor->agregarObserver($observerQueFalla);
        $gestor->agregarObserver($observerBueno);

        $gestor->notificarObservers('prueba', []);

        $this->assertTrue($observerBueno->fueNotificado);
    }
}

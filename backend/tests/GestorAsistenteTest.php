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

    /** Gestor cuyo "microservicio" devuelve una respuesta fija y recuerda qué texto recibió. */
    private function gestorConMicroservicioFalso(array $respuesta, ?string &$textoRecibido): GestorAsistente
    {
        return new class($respuesta, $textoRecibido) extends GestorAsistente {
            public function __construct(private array $respuesta, private ?string &$recibido) {}
            protected function llamarMicroservicio(string $texto, ?array $contextoPrevio = null): array
            {
                $this->recibido = $texto;
                return $this->respuesta;
            }
        };
    }

    public function testElRegistroGuardaElTextoEnmascaradoPeroElMicroservicioRecibeElOriginal(): void
    {
        $textoRecibido = null;
        $gestor = $this->gestorConMicroservicioFalso(
            ['intencion' => 'consultar_stock', 'entidades' => ['codigo' => '7701234567890'], 'respuesta_texto' => 'ok'],
            $textoRecibido
        );
        $observer = new class implements VentaObserver {
            public array $contexto = [];
            public function actualizar(string $accion, array $contexto): void { $this->contexto = $contexto; }
        };
        $gestor->agregarObserver($observer);

        $original = 'stock del 7701234567890, avisar a cliente@correo.com o al 3001234567';
        $devuelta = $gestor->consultar($original, 5, '10.0.0.1');

        // El microservicio recibe el texto tal cual: un código numérico largo debe poder buscarse.
        $this->assertSame($original, $textoRecibido);
        // El historial no guarda ningún dato personal.
        $this->assertSame('stock del ***, avisar a *** o al ***', $observer->contexto['texto_consulta']);
        $this->assertSame('***', $observer->contexto['respuesta']['entidades']['codigo']);
        // Y quien consulta recibe la respuesta sin alterar.
        $this->assertSame('7701234567890', $devuelta['entidades']['codigo']);
    }

    public function testUnaConsultaSinDatosPersonalesSeRegistraIntacta(): void
    {
        $textoRecibido = null;
        $gestor = $this->gestorConMicroservicioFalso(['intencion' => 'buscar_repuesto'], $textoRecibido);
        $observer = new class implements VentaObserver {
            public array $contexto = [];
            public function actualizar(string $accion, array $contexto): void { $this->contexto = $contexto; }
        };
        $gestor->agregarObserver($observer);

        $texto = 'filtro de aceite para Toyota Hilux 2.7 gasolina 2024';
        $gestor->consultar($texto, 5);

        $this->assertSame($texto, $observer->contexto['texto_consulta']);
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

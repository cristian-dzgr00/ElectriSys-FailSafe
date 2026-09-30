<?php
use PHPUnit\Framework\TestCase;
use App\patterns\observer\ErroresNlpObserver;

/**
 * El aviso al microservicio NLP nunca debe hacer fallar el alta de un
 * vehículo: si el servicio no responde, se registra en el log y listo.
 */
class ErroresNlpObserverTest extends TestCase
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

    public function testNoLanzaSiElMicroservicioNoResponde(): void
    {
        $_ENV['NLP_SERVICE_URL'] = 'http://127.0.0.1:1'; // puerto que no acepta conexiones

        (new ErroresNlpObserver())->actualizar('vehiculo_creado', ['marca' => 'Geely', 'modelo' => 'Coolray']);

        $this->addToAssertionCount(1); // llegar aquí sin excepción es la prueba
    }

    public function testIgnoraOtrosEventosYDatosVacios(): void
    {
        $_ENV['NLP_SERVICE_URL'] = 'http://127.0.0.1:1';
        $observer = new ErroresNlpObserver();

        $observer->actualizar('crear_venta', ['marca' => 'Geely']);
        $observer->actualizar('vehiculo_creado', []);

        $this->addToAssertionCount(1);
    }
}

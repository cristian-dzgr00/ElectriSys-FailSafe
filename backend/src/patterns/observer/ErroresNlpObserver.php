<?php
declare(strict_types=1);

namespace App\patterns\observer;

use App\services\NlpClient;

/**
 * ErroresNlpObserver — Observer concreto que avisa al microservicio NLP
 * cuando entra un vehículo nuevo al catálogo.
 *
 * El microservicio genera en ese momento todos los posibles errores de
 * escritura de la marca y el modelo ("geely" -> "yili", "jili"...) y los
 * deja buscables en el asistente sin reiniciarse (POST /nlp/errores/registrar).
 *
 * Se registra en VehiculoModel. Nunca hace fallar el guardado del
 * vehículo: NlpClient no lanza, y si el microservicio no responde solo
 * queda el aviso en el log — la sincronización automática del
 * microservicio (al arrancar y al refrescar su catálogo) lo corrige después.
 */
class ErroresNlpObserver implements VentaObserver
{
    /** Registrar un nombre tarda poco; no hacer esperar al alta del vehículo. */
    private const TIMEOUT_SEGUNDOS = 3;

    public function actualizar(string $accion, array $contexto): void
    {
        if ($accion !== 'vehiculo_creado') {
            return;
        }

        $marca  = trim((string) ($contexto['marca']  ?? ''));
        $modelo = trim((string) ($contexto['modelo'] ?? ''));

        if ($marca !== '') {
            $this->registrar(['tipo' => 'marca', 'nombre' => $marca]);
        }
        if ($modelo !== '') {
            $this->registrar(['tipo' => 'modelo', 'nombre' => $modelo, 'marca' => $marca ?: null]);
        }
    }

    private function registrar(array $cuerpo): void
    {
        if (NlpClient::post('/nlp/errores/registrar', $cuerpo, self::TIMEOUT_SEGUNDOS) === null) {
            error_log(
                "[ElectriSys][ErroresNlpObserver] No se pudo avisar al NLP del {$cuerpo['tipo']} " .
                "'{$cuerpo['nombre']}'; lo registrará la sincronización automática del microservicio."
            );
        }
    }
}

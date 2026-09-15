<?php
declare(strict_types=1);

namespace App\patterns\observer;

/**
 * GestorAsistente — Subject Concreto
 *
 * Mismo patrón que GestorVentas: hace la operación principal (llamar al
 * microservicio de NLP) y notifica a los Observers registrados al
 * terminar. Reutiliza VentaSubject/VentaObserver — su forma ya es
 * genérica, no específica de ventas.
 *
 * @package App\patterns\observer
 */
class GestorAsistente implements VentaSubject
{
    /** @var VentaObserver[] */
    private array $observers = [];

    public function agregarObserver(VentaObserver $observer): void
    {
        $this->observers[] = $observer;
    }

    public function removerObserver(VentaObserver $observer): void
    {
        $this->observers = array_filter($this->observers, fn($o) => $o !== $observer);
    }

    public function notificarObservers(string $accion, array $contexto): void
    {
        foreach ($this->observers as $observer) {
            try {
                $observer->actualizar($accion, $contexto);
            } catch (\Throwable $e) {
                error_log(
                    "[ElectriSys][GestorAsistente] Observer " . get_class($observer) .
                    " falló silenciosamente: " . $e->getMessage()
                );
            }
        }
    }

    /**
     * Llama al microservicio de NLP y notifica a los Observers con el
     * resultado. Lanza RuntimeException si el microservicio no responde
     * o responde con error — la ruta HTTP decide qué código devolver.
     *
     * @param string     $texto          Consulta del vendedor
     * @param int        $usuarioId      ID del usuario autenticado (del JWT)
     * @param string     $ip             IP del cliente, para el log
     * @param array|null $contextoPrevio Entidades del turno anterior (diálogo
     *                                   multi-turno); se reenvía sin interpretar.
     * @return array                     Respuesta decodificada del microservicio
     */
    public function consultar(string $texto, int $usuarioId, string $ip = '', ?array $contextoPrevio = null): array
    {
        $respuesta = $this->llamarMicroservicio($texto, $contextoPrevio);

        $this->notificarObservers('consulta_asistente', [
            'usuario_id'     => $usuarioId,
            'texto_consulta' => $texto,
            'respuesta'      => $respuesta,
            'ip'             => $ip,
        ]);

        // AsistenteLogObserver es el único Observer que persiste la
        // consulta; se le pregunta directamente el id insertado en vez de
        // que notificarObservers() devuelva algo, para no romper el
        // contrato genérico VentaObserver::actualizar(): void (compartido
        // con GestorVentas).
        foreach ($this->observers as $observer) {
            if ($observer instanceof AsistenteLogObserver) {
                $respuesta['consulta_id'] = $observer->ultimoIdInsertado();
                break;
            }
        }

        return $respuesta;
    }

    private function llamarMicroservicio(string $texto, ?array $contextoPrevio = null): array
    {
        $url = rtrim($_ENV['NLP_SERVICE_URL'] ?? '', '/') . '/nlp/consultar';

        $body = ['texto' => $texto];
        if ($contextoPrevio !== null) {
            $body['contexto_previo'] = $contextoPrevio;
        }

        $ch = curl_init($url);
        curl_setopt_array($ch, [
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_POST           => true,
            CURLOPT_POSTFIELDS     => json_encode($body),
            CURLOPT_HTTPHEADER     => [
                'Content-Type: application/json',
                'X-Internal-Key: ' . ($_ENV['NLP_INTERNAL_KEY'] ?? ''),
            ],
            CURLOPT_TIMEOUT        => 5,
            CURLOPT_CONNECTTIMEOUT => 3,
        ]);
        $body     = curl_exec($ch);
        $curlErr  = curl_errno($ch) ? curl_error($ch) : null;
        $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);

        if ($curlErr !== null || $body === false) {
            throw new \RuntimeException("No se pudo conectar con el microservicio de NLP: {$curlErr}");
        }
        if ($httpCode >= 400) {
            throw new \RuntimeException("El microservicio de NLP respondió con error HTTP {$httpCode}");
        }

        $decoded = json_decode($body, true);
        if (!is_array($decoded)) {
            throw new \RuntimeException('Respuesta inválida del microservicio de NLP');
        }
        return $decoded;
    }
}

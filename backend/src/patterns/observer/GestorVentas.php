<?php
declare(strict_types=1);

namespace App\patterns\observer;

use App\models\VentaModel;
use App\patterns\strategy\DiscountStrategy;

/**
 * GestorVentas — Subject Concreto
 *
 * Implementa VentaSubject y actúa como el Subject del patrón Observer.
 * Mantiene la lista de Observers registrados y los notifica
 * después de ejecutar operaciones críticas de ventas.
 *
 * Además integra el patrón Strategy para el cálculo de descuentos:
 * recibe una DiscountStrategy inyectada y la aplica antes de
 * crear la venta, sin conocer los detalles del cálculo.
 *
 * Flujo principal:
 *   1. (Strategy) Calcular precio final con el descuento inyectado
 *   2. Ejecutar la operación de venta en VentaModel
 *   3. (Observer) Notificar a todos los Observers registrados
 *
 * @package App\patterns\observer
 */
class GestorVentas implements VentaSubject
{
    /** @var VentaObserver[] Lista de Observers suscritos */
    private array $observers = [];

    private VentaModel $model;

    /**
     * @param DiscountStrategy|null $strategy  Estrategia de descuento (inyección de Strategy)
     */
    public function __construct(
        private ?DiscountStrategy $strategy = null
    ) {
        $this->model = new VentaModel();
    }

    // ── Gestión de Observers ──────────────────────────────────────

    /**
     * {@inheritDoc}
     */
    public function agregarObserver(VentaObserver $observer): void
    {
        $this->observers[] = $observer;
    }

    /**
     * {@inheritDoc}
     */
    public function removerObserver(VentaObserver $observer): void
    {
        $this->observers = array_filter(
            $this->observers,
            fn($o) => $o !== $observer
        );
    }

    /**
     * {@inheritDoc}
     * Notifica a cada Observer de forma independiente.
     * Si un Observer falla, el resto sigue siendo notificado.
     */
    public function notificarObservers(string $accion, array $contexto): void
    {
        foreach ($this->observers as $observer) {
            try {
                $observer->actualizar($accion, $contexto);
            } catch (\Throwable $e) {
                error_log(
                    "[ElectriSys][GestorVentas] Observer " . get_class($observer) .
                    " falló silenciosamente: " . $e->getMessage()
                );
            }
        }
    }

    // ── Operaciones de Ventas ────────────────────────────────────

    /**
     * Crea una venta aplicando la Strategy de descuento activa
     * y notifica a los Observers registrados al completar.
     *
     * @param array $data      Payload de la venta (items, subtotal, metodo_pago…)
     * @param int   $usuarioId ID del usuario autenticado (del JWT)
     * @param string $ip       IP del cliente para auditoría
     * @return array           Resultado de la creación {id, numero, en_replica}
     */
    public function crearVenta(array $data, int $usuarioId, string $ip = ''): array
    {
        // ── Aplicar Strategy de descuento si está configurada ────
        // desglosar() le pide a la Strategy misma el detalle (descuento,
        // impuesto, total) en vez de que GestorVentas adivine la tasa de
        // IVA a partir del total — eso asumía 19% fijo y calculaba un
        // impuesto/descuento incorrecto (pero no nulo) para estrategias
        // como ExentoIvaStrategy, que no cobran IVA.
        if ($this->strategy !== null && isset($data['subtotal'])) {
            $subtotal  = (float) $data['subtotal'];
            $desglose  = $this->strategy->desglosar($subtotal);

            $data['descuento'] = $desglose['descuento'];
            $data['impuesto']  = $desglose['impuesto'];
            $data['total']     = $desglose['total'];

            error_log(
                "[ElectriSys][Strategy] " . get_class($this->strategy) .
                " aplicada — subtotal: {$subtotal} → total: {$data['total']}"
            );
        }

        // ── Ejecutar la operación principal ──────────────────────
        $resultado = $this->model->crear($data, $usuarioId);

        // ── Notificar Observers (Observer desacoplado) ───────────
        $this->notificarObservers('crear_venta', [
            'usuario_id' => $usuarioId,
            'detalle'    => 'Venta ' . ($resultado['numero'] ?? 'N/A') .
                            ' por $' . ($data['total'] ?? 0),
            'ip'         => $ip,
        ]);

        return $resultado;
    }

    /**
     * Anula una venta y notifica a los Observers registrados.
     *
     * @param int    $ventaId  ID de la venta a anular
     * @param int    $usuarioId ID del usuario que anula
     * @param string $ip       IP del cliente para auditoría
     * @return bool            true si se anuló, false si no existía o ya estaba anulada
     */
    public function anularVenta(int $ventaId, int $usuarioId, string $ip = ''): bool
    {
        // ── Ejecutar la operación principal ──────────────────────
        $resultado = $this->model->anular($ventaId);

        if ($resultado) {
            // ── Notificar Observers solo si la anulación fue exitosa ──
            $this->notificarObservers('anular_venta', [
                'usuario_id' => $usuarioId,
                'detalle'    => "Venta ID {$ventaId} anulada",
                'ip'         => $ip,
            ]);
        }

        return $resultado;
    }
}
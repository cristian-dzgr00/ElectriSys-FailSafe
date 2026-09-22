<?php
declare(strict_types=1);

namespace App\patterns\observer;

use App\models\PedidoModel;
use RuntimeException;

/**
 * GestorPedidos — Subject Concreto del módulo de pedidos a proveedor.
 *
 * Implementa la MISMA interfaz VentaSubject que GestorVentas y notifica a los
 * MISMOS Observers concretos (AuditLogObserver, WebSocketObserver) en vez de
 * declarar un par PedidoSubject/PedidoObserver paralelo. La razón: el contrato
 * del Observer acá es (string $accion, array $contexto) — no menciona ventas en
 * ninguna parte. Duplicar las interfaces obligaría a duplicar también los dos
 * Observers concretos (un AuditLogPedidoObserver que hace el mismo INSERT en
 * audit_log, un WebSocketPedidoObserver que hace el mismo POST a /notify), que
 * es justamente lo que el patrón busca evitar.
 *
 * Flujo, igual que en GestorVentas:
 *   1. Ejecutar la operación en PedidoModel
 *   2. (Observer) Notificar la acción de negocio — queda auditada y va al WS
 *   3. (Observer) Si el inventario se movió, notificar 'stock_actualizado'
 *      para que las vistas de inventario abiertas se actualicen solas
 *
 * @package App\patterns\observer
 */
class GestorPedidos implements VentaSubject
{
    /** @var VentaObserver[] Lista de Observers suscritos */
    private array $observers = [];

    private PedidoModel $model;

    public function __construct(?PedidoModel $model = null)
    {
        $this->model = $model ?? new PedidoModel();
    }

    // ── Gestión de Observers ──────────────────────────────────────

    public function agregarObserver(VentaObserver $observer): void
    {
        $this->observers[] = $observer;
    }

    public function removerObserver(VentaObserver $observer): void
    {
        $this->observers = array_filter(
            $this->observers,
            fn($o) => $o !== $observer
        );
    }

    /**
     * Notifica a cada Observer de forma independiente.
     * Si un Observer falla, el resto sigue siendo notificado y la operación
     * de negocio ya confirmada no se revierte.
     */
    public function notificarObservers(string $accion, array $contexto): void
    {
        foreach ($this->observers as $observer) {
            try {
                $observer->actualizar($accion, $contexto);
            } catch (\Throwable $e) {
                error_log(
                    "[ElectriSys][GestorPedidos] Observer " . get_class($observer) .
                    " falló silenciosamente: " . $e->getMessage()
                );
            }
        }
    }

    // ── Operaciones de negocio ────────────────────────────────────

    /**
     * Crea el pedido y notifica. NO emite 'stock_actualizado': un pedido
     * recién solicitado todavía no movió el inventario (ver PedidoModel).
     *
     * @return array{id:int, numero:string}
     */
    public function crearPedido(array $data, int $usuarioId, string $ip = ''): array
    {
        $resultado = $this->model->crear($data, $usuarioId);

        $this->notificarObservers('crear_pedido', [
            'usuario_id' => $usuarioId,
            'detalle'    => "Pedido {$resultado['numero']} creado ("
                            . count($data['items']) . ' línea(s))',
            'ip'         => $ip,
            'payload'    => ['pedido_id' => $resultado['id'], 'estado' => 'solicitado'],
        ]);

        return $resultado;
    }

    /**
     * Cambia el estado del pedido y notifica.
     *
     * Cuando el pedido pasa a 'recibido', trg_pedidos_recibido_suma_stock ya
     * sumó la mercancía al inventario: se lee el stock resultante y se difunde
     * como 'stock_actualizado', el mismo evento que emite GestorVentas al
     * vender o anular. Así Repuestos.jsx se actualiza en vivo sin saber si el
     * movimiento vino de una venta o de una entrada de mercancía.
     *
     * @throws RuntimeException si la transición no es válida
     */
    public function cambiarEstado(int $pedidoId, string $nuevoEstado, int $usuarioId, string $ip = ''): bool
    {
        // Los repuestos se leen ANTES de tocar el pedido: si la transición
        // falla, no se hizo ninguna consulta de más; si tiene éxito, ya se
        // sabe qué filas de inventario hay que releer.
        $repuestoIds = $nuevoEstado === 'recibido' ? $this->model->itemsDePedido($pedidoId) : [];

        $resultado = $this->model->cambiarEstado($pedidoId, $nuevoEstado);
        if (!$resultado) {
            return false;
        }

        $accion = $nuevoEstado === 'cancelado' ? 'cancelar_pedido' : 'estado_pedido';
        $this->notificarObservers($accion, [
            'usuario_id' => $usuarioId,
            'detalle'    => "Pedido ID {$pedidoId} → estado \"{$nuevoEstado}\"",
            'ip'         => $ip,
            'payload'    => ['pedido_id' => $pedidoId, 'estado' => $nuevoEstado],
        ]);

        if ($repuestoIds !== []) {
            $this->notificarObservers('stock_actualizado', [
                'usuario_id' => $usuarioId,
                'items'      => $this->model->stockDe($repuestoIds),
                'ip'         => $ip,
            ]);
        }

        return $resultado;
    }

    /**
     * Cancelar es un cambio de estado más — no repone stock porque el pedido
     * nunca lo reservó (ver PedidoModel::cancelar).
     */
    public function cancelarPedido(int $pedidoId, int $usuarioId, string $ip = ''): bool
    {
        return $this->cambiarEstado($pedidoId, 'cancelado', $usuarioId, $ip);
    }
}

<?php
declare(strict_types=1);

namespace App\patterns\observer;

/**
 * WebSocketObserver — Observer concreto que notifica al servidor WS.
 *
 * Se registra en GestorVentas igual que AuditLogObserver.
 * Cuando ocurre una venta, hace un POST interno al servidor
 * Node.js que retransmite el evento a los clientes conectados.
 *
 * El servidor WS corre en el mismo cluster — la comunicación
 * es interna, nunca expuesta al exterior.
 */
class WebSocketObserver implements VentaObserver
{
    private const WS_NOTIFY_URL = 'http://websocket-server:8080/notify';
    private string $notifyKey;

    public function __construct()
    {
        $this->notifyKey = $_ENV['WS_NOTIFY_KEY'] ?? 'ws_internal_notify_key';
    }

    /**
     * Recibe el evento del GestorVentas y lo reenvía al servidor WS.
     */
    public function actualizar(string $accion, array $contexto): void
    {
        // stock_actualizado es distinto al resto: a diferencia de
        // crear_venta/anular_venta, también debe llegar a 'vendedor'
        // (necesita ver el stock real al vender), y no lleva "detail"
        // legible sino el mapa {repuesto_id: stock}. El cast a (object)
        // evita que json_encode lo serialice como array JSON si las keys
        // resultan ser una secuencia 0,1,2,... por casualidad.
        if ($accion === 'stock_actualizado') {
            $this->postToWsServer([
                'type'        => 'stock_actualizado',
                'timestamp'   => date('c'),
                'userId'      => $contexto['usuario_id'] ?? null,
                'items'       => (object) ($contexto['items'] ?? []),
                'targetRoles' => ['admin', 'vendedor', 'dueno'],
            ]);
            return;
        }

        $event = [
            'type'        => $accion,           // 'crear_venta' | 'anular_venta' | 'crear_pedido' | 'estado_pedido' | ...
            'timestamp'   => date('c'),
            'userId'      => $contexto['usuario_id'] ?? null,
            'detail'      => $contexto['detalle']    ?? '',
            // Por defecto solo admin/dueno — roles reales del sistema (ver
            // roles: admin/vendedor/dueno). El Subject puede ampliarlo con
            // 'target_roles' si el evento le sirve también al vendedor.
            'targetRoles' => $contexto['target_roles'] ?? ['admin', 'dueno'],
        ];

        // Datos estructurados opcionales para que la vista sepa QUÉ cambió y
        // no solo lea un texto (ej. {pedido_id, estado} desde GestorPedidos).
        // Va como campo genérico a propósito: así este Observer no necesita
        // conocer cada módulo que lo use.
        if (isset($contexto['payload'])) {
            $event['payload'] = $contexto['payload'];
        }

        $this->postToWsServer($event);
    }

    private function postToWsServer(array $event): void
    {
        $payload = json_encode($event);

        $ch = curl_init(self::WS_NOTIFY_URL);
        curl_setopt_array($ch, [
            CURLOPT_POST           => true,
            CURLOPT_POSTFIELDS     => $payload,
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_TIMEOUT        => 2,       // no bloquear el request principal
            CURLOPT_HTTPHEADER     => [
                'Content-Type: application/json',
                'X-Notify-Key: ' . $this->notifyKey,
            ],
        ]);

        $response = curl_exec($ch);
        $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);

        if ($httpCode !== 200) {
            error_log("[ElectriSys][WS] Notificación falló — HTTP $httpCode: $response");
        }
    }
}

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
        $event = [
            'type'        => $accion,           // 'crear_venta' | 'anular_venta'
            'timestamp'   => date('c'),
            'userId'      => $contexto['usuario_id'] ?? null,
            'detail'      => $contexto['detalle']    ?? '',
            'targetRoles' => ['admin', 'dueno'], // quién recibe la notif. — roles reales del sistema (ver roles: admin/vendedor/dueno)
        ];

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

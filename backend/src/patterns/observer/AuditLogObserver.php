<?php
declare(strict_types=1);

namespace App\patterns\observer;

use App\models\Database;
use App\models\OciConnection;

/**
 * AuditLogObserver — Observer Concreto
 *
 * Implementación concreta del patrón Observer que persiste
 * los eventos de ventas en la tabla `audit_log` de la base de datos.
 *
 * Es notificado por el Subject (GestorVentas) cada vez que
 * ocurre una operación crítica (crear_venta, anular_venta).
 *
 * El registro de auditoría se realiza de forma desacoplada:
 * si falla la escritura en el log, el flujo principal de la venta
 * NO se ve afectado (el error queda en el log del servidor).
 *
 * @package App\patterns\observer
 */
class AuditLogObserver implements VentaObserver
{
    private OciConnection $db;

    public function __construct()
    {
        $this->db = Database::getConnection();
    }

    /**
     * Recibe la notificación del Subject y persiste el evento
     * en la tabla audit_log.
     *
     * @param string $accion   Evento ocurrido ('crear_venta', 'anular_venta')
     * @param array  $contexto Datos de contexto: usuario_id, detalle, ip
     */
    public function actualizar(string $accion, array $contexto): void
    {
        try {
            $stmt = $this->db->prepare(
                "INSERT INTO audit_log (usuario_id, accion, detalle, ip)
                 VALUES (:usuario_id, :accion, :detalle, :ip)"
            );
            $stmt->execute([
                ':usuario_id' => $contexto['usuario_id'] ?? null,
                ':accion'     => $accion,
                ':detalle'    => $contexto['detalle']    ?? null,
                ':ip'         => $contexto['ip']         ?? null,
            ]);

            error_log(
                "[ElectriSys][AuditLog] Evento registrado: {$accion} — " .
                "usuario_id={$contexto['usuario_id']} | {$contexto['detalle']}"
            );
        } catch (\Throwable $e) {
            // La falla del log NO interrumpe el flujo de la venta.
            // Principio fundamental del Observer desacoplado.
            error_log(
                "[ElectriSys][AuditLog] ERROR al registrar evento '{$accion}': " .
                $e->getMessage()
            );
        }
    }
}
<?php
declare(strict_types=1);

namespace App\patterns\observer;

/**
 * VentaObserver — Interfaz del Observer
 *
 * Patrón Observer aplicado al sistema de auditoría de ventas.
 * Todo Observer concreto que desee recibir notificaciones
 * de operaciones sobre ventas debe implementar este contrato.
 *
 * @package App\patterns\observer
 */
interface VentaObserver
{
    /**
     * Recibe la notificación de un evento de venta.
     *
     * El Subject (VentaSubject) llama a este método de forma
     * desacoplada: el resultado de la notificación no afecta
     * el flujo principal de la operación de venta.
     *
     * @param string $accion   Nombre del evento ('crear_venta', 'anular_venta')
     * @param array  $contexto Datos de contexto: usuario_id, detalle, ip, etc.
     */
    public function actualizar(string $accion, array $contexto): void;
}
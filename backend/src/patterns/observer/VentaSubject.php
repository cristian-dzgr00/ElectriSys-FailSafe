<?php
declare(strict_types=1);

namespace App\patterns\observer;

/**
 * VentaSubject — Interfaz del Subject
 *
 * Define el contrato que debe cumplir cualquier clase que actúe
 * como sujeto observable dentro del sistema de ventas.
 * Permite registrar, eliminar y notificar Observers.
 *
 * @package App\patterns\observer
 */
interface VentaSubject
{
    /**
     * Registra un Observer para recibir notificaciones de eventos.
     *
     * @param VentaObserver $observer Observer a agregar
     */
    public function agregarObserver(VentaObserver $observer): void;

    /**
     * Elimina un Observer previamente registrado.
     *
     * @param VentaObserver $observer Observer a remover
     */
    public function removerObserver(VentaObserver $observer): void;

    /**
     * Notifica a todos los Observers registrados sobre un evento.
     *
     * @param string $accion   Nombre del evento ocurrido
     * @param array  $contexto Datos de contexto del evento
     */
    public function notificarObservers(string $accion, array $contexto): void;
}
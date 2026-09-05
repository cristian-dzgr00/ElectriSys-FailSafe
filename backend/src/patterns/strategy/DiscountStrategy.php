<?php
declare(strict_types=1);

namespace App\patterns\strategy;

/**
 * DiscountStrategy — Interfaz del Strategy
 *
 * Patrón Strategy aplicado al cálculo del precio final de una venta.
 * Encapsula la lógica de descuento e impuesto en clases intercambiables,
 * permitiendo modificar el algoritmo de cálculo sin alterar el código
 * que lo consume (GestorVentas).
 *
 * Cada implementación concreta aplica su propia fórmula para
 * calcular el monto final a cobrar a partir del subtotal bruto.
 *
 * @package App\patterns\strategy
 */
interface DiscountStrategy
{
    /**
     * Calcula el precio final (con descuento e impuesto incluidos)
     * a partir del subtotal bruto de la venta.
     *
     * @param  float $subtotal Monto bruto antes de descuentos e impuestos
     * @return float           Monto final que el cliente debe pagar
     */
    public function calcular(float $subtotal): float;

    /**
     * Retorna el nombre descriptivo de la estrategia.
     * Útil para logs y auditoría.
     *
     * @return string
     */
    public function getNombre(): string;
}
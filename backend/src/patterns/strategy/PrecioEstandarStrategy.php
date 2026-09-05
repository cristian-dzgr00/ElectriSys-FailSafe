<?php
declare(strict_types=1);

namespace App\patterns\strategy;

/**
 * PrecioEstandarStrategy — Strategy Concreta
 *
 * Estrategia de precio estándar para ventas normales.
 * No aplica ningún descuento comercial; solo calcula el total
 * añadiendo el IVA colombiano vigente del 19%.
 *
 * Fórmula:
 *   total = subtotal × 1.19
 *
 * Aplicación: cliente general sin convenio ni promoción activa.
 *
 * @package App\patterns\strategy
 */
class PrecioEstandarStrategy implements DiscountStrategy
{
    /** IVA colombiano vigente */
    private const IVA = 0.19;

    /**
     * {@inheritDoc}
     *
     * @param  float $subtotal Monto bruto antes de impuestos
     * @return float           Subtotal + IVA 19%
     */
    public function calcular(float $subtotal): float
    {
        return round($subtotal * (1 + self::IVA), 2);
    }

    /**
     * {@inheritDoc}
     */
    public function getNombre(): string
    {
        return 'Precio estándar con IVA 19%';
    }
}
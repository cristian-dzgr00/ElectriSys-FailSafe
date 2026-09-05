<?php
declare(strict_types=1);

namespace App\patterns\strategy;

/**
 * ExentoIvaStrategy — Strategy Concreta
 *
 * Estrategia para clientes del régimen tributario especial
 * o entidades del Estado, exentos del pago de IVA.
 * El precio final es igual al subtotal sin ningún recargo.
 *
 * Fórmula:
 *   total = subtotal (sin IVA, sin descuento)
 *
 * Aplicación: entidades gubernamentales, ONGs certificadas,
 *             o clientes con resolución de exención vigente.
 *
 * @package App\patterns\strategy
 */
class ExentoIvaStrategy implements DiscountStrategy
{
    /**
     * {@inheritDoc}
     *
     * @param  float $subtotal Monto bruto
     * @return float           Mismo monto sin modificaciones
     */
    public function calcular(float $subtotal): float
    {
        return round($subtotal, 2);
    }

    /**
     * {@inheritDoc}
     */
    public function getNombre(): string
    {
        return 'Exento de IVA (régimen especial)';
    }
}
<?php
declare(strict_types=1);

namespace App\patterns\strategy;

/**
 * DescuentoVolumenStrategy — Strategy Concreta
 *
 * Estrategia de descuento por volumen para clientes mayoristas.
 * Aplica un 10% de descuento sobre el subtotal y luego
 * agrega el IVA colombiano del 19% sobre el monto descontado.
 *
 * Fórmula:
 *   subtotalDescontado = subtotal × (1 − 0.10)
 *   total              = subtotalDescontado × 1.19
 *
 * Aplicación: pedidos de 10 o más unidades, clientes con convenio.
 *
 * @package App\patterns\strategy
 */
class DescuentoVolumenStrategy implements DiscountStrategy
{
    private const DESCUENTO = 0.10;
    private const IVA       = 0.19;

    /**
     * @param float $porcentajeDescuento Porcentaje de descuento a aplicar (0.0 – 1.0).
     *                                   Por defecto 10% (0.10).
     */
    public function __construct(
        private float $porcentajeDescuento = self::DESCUENTO
    ) {}

    /**
     * {@inheritDoc}
     *
     * @param  float $subtotal Monto bruto antes de descuento e impuestos
     * @return float           Subtotal con descuento + IVA 19%
     */
    public function calcular(float $subtotal): float
    {
        $subtotalDescontado = $subtotal * (1 - $this->porcentajeDescuento);
        return round($subtotalDescontado * (1 + self::IVA), 2);
    }

    /**
     * {@inheritDoc}
     */
    public function desglosar(float $subtotal): array
    {
        $descuento          = round($subtotal * $this->porcentajeDescuento, 2);
        $subtotalDescontado = $subtotal - $descuento;
        $impuesto           = round($subtotalDescontado * self::IVA, 2);
        return [
            'subtotal'  => round($subtotal, 2),
            'descuento' => $descuento,
            'impuesto'  => $impuesto,
            'total'     => round($subtotalDescontado + $impuesto, 2),
        ];
    }

    /**
     * {@inheritDoc}
     */
    public function getNombre(): string
    {
        $pct = (int) ($this->porcentajeDescuento * 100);
        return "Descuento por volumen {$pct}% + IVA 19%";
    }
}
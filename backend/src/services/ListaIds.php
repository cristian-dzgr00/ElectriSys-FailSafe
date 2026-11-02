<?php
declare(strict_types=1);

namespace App\services;

/**
 * Interpreta el parámetro `?ids=1,2,3` de las rutas de sugerencias.
 *
 * Antes cada archivo de rutas traía su propia copia (idsDesdeQuery en
 * repuestos.php, un bucle suelto en ventas.php): quien reordenara los require
 * rompía una sin enterarse. Acá vive una sola, probada.
 */
final class ListaIds
{
    /**
     * Enteros positivos únicos, en el orden en que llegaron. Descarta lo que
     * no sea un entero (un id mal formado no debe tumbar la pantalla entera)
     * y recorta a `$maximo`: una ruta que termina en un IN (...) de Oracle no
     * puede aceptar listas de tamaño arbitrario.
     *
     * @return int[]
     */
    public static function desdeTexto(?string $crudo, int $maximo = 100): array
    {
        $crudo = trim((string) $crudo);
        if ($crudo === '' || $maximo < 1) {
            return [];
        }

        $ids = [];
        foreach (explode(',', $crudo) as $valor) {
            $valor = trim($valor);
            // ctype_digit + longitud: evita desbordes de int con "99999999999999999999".
            if ($valor !== '' && ctype_digit($valor) && strlen($valor) <= 15 && (int) $valor > 0) {
                $ids[(int) $valor] = true;
                if (count($ids) >= $maximo) {
                    break;
                }
            }
        }
        return array_keys($ids);
    }
}

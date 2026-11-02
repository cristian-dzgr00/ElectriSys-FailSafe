<?php
declare(strict_types=1);

namespace App\services;

/**
 * Búsqueda de texto que no distingue mayúsculas ni tildes.
 *
 * Oracle compara con LIKE respetando mayúsculas y tildes (MySQL no lo hacía),
 * así que "carlos" no encontraba a "Carlos" ni "munoz" a "Muñoz". Las dos mitades
 * de la comparación tienen que normalizarse igual: la columna en SQL
 * (`columna()`) y el texto buscado en PHP (`patron()`). Mantenerlas juntas acá
 * evita que una se actualice sin la otra.
 */
final class BusquedaTexto
{
    private const CON_TILDE = 'áéíóúüñÁÉÍÓÚÜÑ';
    private const SIN_TILDE = 'aeiouunAEIOUUN';

    /** Mayúsculas y sin tildes ni diéresis; la ñ pasa a N. */
    public static function normalizar(string $texto): string
    {
        return strtoupper(strtr(trim($texto), [
            'á' => 'a', 'é' => 'e', 'í' => 'i', 'ó' => 'o', 'ú' => 'u', 'ü' => 'u', 'ñ' => 'n',
            'Á' => 'A', 'É' => 'E', 'Í' => 'I', 'Ó' => 'O', 'Ú' => 'U', 'Ü' => 'U', 'Ñ' => 'N',
        ]));
    }

    /**
     * Valor para el parámetro del LIKE: `%texto%` normalizado. Los `%` y `_`
     * que escribió el usuario se escapan para que sean texto y no comodines
     * (se usa junto con `como()`, que declara el carácter de escape).
     */
    public static function patron(string $texto): string
    {
        $escapado = strtr(self::normalizar($texto), ['\\' => '\\\\', '%' => '\\%', '_' => '\\_']);
        return '%' . $escapado . '%';
    }

    /** Expresión SQL de la columna con la misma normalización que `normalizar()`. */
    public static function columna(string $columna): string
    {
        return "UPPER(TRANSLATE({$columna}, '" . self::CON_TILDE . "', '" . self::SIN_TILDE . "'))";
    }

    /** Condición completa `columna LIKE ?` lista para usar con `patron()`. */
    public static function como(string $columna): string
    {
        return self::columna($columna) . " LIKE ? ESCAPE '\\'";
    }
}

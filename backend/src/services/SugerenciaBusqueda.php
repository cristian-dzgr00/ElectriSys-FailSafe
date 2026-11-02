<?php
declare(strict_types=1);

namespace App\services;

/**
 * "¿Quisiste decir…?" para la búsqueda de repuestos.
 *
 * Envuelve al corrector del microservicio de NLP. Como NlpClient, nunca
 * lanza: si el servicio está caído o no encuentra nada parecido devuelve
 * null y la búsqueda sigue mostrando su "sin resultados" de siempre.
 */
final class SugerenciaBusqueda
{
    public const LARGO_MINIMO = 3;

    /** Un término más largo no es una búsqueda de producto: no vale la pena corregirlo. */
    public const LARGO_MAXIMO = 80;

    public static function corregir(string $termino): ?string
    {
        $termino = trim($termino);
        $largo   = mb_strlen($termino);
        if ($largo < self::LARGO_MINIMO || $largo > self::LARGO_MAXIMO) {
            return null;
        }

        $respuesta = NlpClient::get('/corregir-busqueda?q=' . urlencode($termino));
        $corregida = $respuesta['corregida'] ?? null;

        if (!is_string($corregida) || trim($corregida) === '') {
            return null;
        }
        // Una "corrección" idéntica a lo escrito no es una sugerencia.
        if (mb_strtolower(trim($corregida)) === mb_strtolower($termino)) {
            return null;
        }
        return trim($corregida);
    }
}

<?php
declare(strict_types=1);

namespace App\services;

/**
 * Enmascara datos personales evidentes (correo, teléfono, cédula) en textos
 * libres antes de guardarlos.
 *
 * Existe porque el asistente recibe texto escrito a mano por el vendedor y lo
 * guarda en `consultas_asistente`: aunque la interfaz le pide no escribir
 * datos de clientes, nada impide que alguien pegue un teléfono. Mejor no
 * almacenarlo que confiar en la disciplina de quien teclea.
 *
 * Es deliberadamente simple (expresiones regulares, sin NER): detecta lo
 * obvio y falla hacia enmascarar de más. Un código de producto de 7+ dígitos
 * seguidos también quedará como `***` en el REGISTRO — el microservicio sí
 * recibe el texto original, así que la búsqueda por código no se ve afectada.
 *
 * Las mismas reglas están replicadas en el frontend (datosPersonales.js)
 * para avisar antes de enviar; si se cambian acá, cambiarlas allá.
 */
final class EnmascaradorDatosPersonales
{
    public const MARCA = '***';

    /** Cantidad de dígitos a partir de la cual una secuencia parece teléfono o cédula. */
    private const MIN_DIGITOS = 7;

    private const PATRON_CORREO = '/[\p{L}\p{N}._%+\-]+@[\p{L}\p{N}\-]+(?:\.[\p{L}\p{N}\-]+)*\.\p{L}{2,}/u';

    /**
     * Dígitos que pueden venir separados por espacios, puntos o guiones
     * ("300 123 4567", "1.234.567.890", "+57 300-123-4567"). No arranca ni
     * termina pegado a letras o guiones bajos, para no tocar códigos como
     * "M1-102" o "90915-YZZD4".
     */
    private const PATRON_NUMERO = '/(?<![\p{L}\p{N}_\-])\+?\d(?:[\d .\-]{5,}\d|\d{5,})(?![\p{L}\p{N}_])/u';

    public static function enmascarar(string $texto): string
    {
        if ($texto === '') {
            return '';
        }
        // Una secuencia UTF-8 inválida haría que preg_* devuelva null y se
        // perdería el texto entero: se sanea primero.
        $limpio = mb_convert_encoding($texto, 'UTF-8', 'UTF-8');

        $limpio = preg_replace(self::PATRON_CORREO, self::MARCA, $limpio) ?? $limpio;

        return preg_replace_callback(
            self::PATRON_NUMERO,
            static fn(array $m): string => self::pareceDatoPersonal($m[0]) ? self::MARCA : $m[0],
            $limpio
        ) ?? $limpio;
    }

    public static function contiene(string $texto): bool
    {
        return self::enmascarar($texto) !== mb_convert_encoding($texto, 'UTF-8', 'UTF-8');
    }

    /**
     * Enmascara todos los valores de texto de una estructura (la respuesta
     * del microservicio se guarda entera como JSON y puede repetir el texto
     * del usuario en entidades o en la frase de respuesta). Los números y
     * booleanos no se tocan.
     *
     * @param mixed $valor
     * @return mixed
     */
    public static function enmascararEstructura(mixed $valor): mixed
    {
        if (is_string($valor)) {
            return self::enmascarar($valor);
        }
        if (is_array($valor)) {
            return array_map([self::class, 'enmascararEstructura'], $valor);
        }
        return $valor;
    }

    private static function pareceDatoPersonal(string $candidato): bool
    {
        $grupos = preg_split('/\D+/', $candidato, -1, PREG_SPLIT_NO_EMPTY) ?: [];

        // "1.8 2015 2019": un rango de años de un vehículo junto a otro dato
        // técnico no es una cédula. Con dos o más grupos que parecen año se
        // descartan esos grupos y se evalúa solo lo que sobra.
        $anios = array_filter($grupos, static fn(string $g): bool => (bool) preg_match('/^(19[5-9]\d|20\d{2}|21\d{2})$/', $g));
        if (count($anios) >= 2) {
            $grupos = array_diff_key($grupos, $anios);
        }

        return strlen(implode('', $grupos)) >= self::MIN_DIGITOS;
    }
}

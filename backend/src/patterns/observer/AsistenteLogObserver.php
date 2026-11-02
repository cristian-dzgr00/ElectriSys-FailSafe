<?php
declare(strict_types=1);

namespace App\patterns\observer;

use App\models\Database;
use App\models\OciConnection;

/**
 * AsistenteLogObserver — Observer Concreto
 *
 * Reutiliza la interfaz VentaObserver (su forma ya es genérica:
 * actualizar(string $accion, array $contexto)) para persistir cada
 * consulta al asistente NLP.
 *
 * Esquema normalizado (3FN, fase 2 — oracle/16_normalizacion_3fn_fase2.sql):
 *   - consultas_asistente: usuario, texto (ya enmascarado), intencion_id
 *     (FK a nlp_intenciones, resuelta por nombre) y confianza.
 *   - consulta_entidades: una fila por entidad extraída (marca, modelo, anio,
 *     categoria y el código como tipo 'repuesto').
 *   - consulta_recomendaciones: una fila por repuesto sugerido, con su
 *     posición, si fue sustituto y el puntaje (similitud * 100).
 * Ya no se guarda el JSON de la respuesta: las tres columnas JSON se eliminaron.
 *
 * Todo se escribe en UNA transacción: o queda la consulta con sus hijos o no
 * queda nada. Igual que AuditLogObserver: si falla el registro, el flujo
 * principal (responderle al vendedor) NO se ve afectado.
 *
 * @package App\patterns\observer
 */
class AsistenteLogObserver implements VentaObserver
{
    /** Entidad del NLP -> valor de consulta_entidades.tipo (CHECK ck_consent_tipo).
     *  motor y combustible no tienen tipo permitido, igual que en la migración. */
    private const TIPOS_ENTIDAD = [
        'marca'     => 'marca',
        'modelo'    => 'modelo',
        'anio'      => 'anio',
        'categoria' => 'categoria',
        'codigo'    => 'repuesto',
    ];

    private const LONGITUD_MAX_VALOR = 200;

    private OciConnection $db;
    private ?int $ultimoIdInsertado = null;

    /** @param OciConnection|null $db Inyectable para las pruebas; por defecto la conexión del proyecto. */
    public function __construct(?OciConnection $db = null)
    {
        $this->db = $db ?? Database::getConnection();
    }

    /**
     * @param string $accion   'consulta_asistente'
     * @param array  $contexto usuario_id, texto_consulta, respuesta (array decodificado del microservicio)
     */
    public function actualizar(string $accion, array $contexto): void
    {
        $this->ultimoIdInsertado = null;
        $enTransaccion = false;
        try {
            $respuesta = is_array($contexto['respuesta'] ?? null) ? $contexto['respuesta'] : [];
            $intencion = $respuesta['intencion'] ?? null;

            $this->db->beginTransaction();
            $enTransaccion = true;

            $nuevoId = $this->insertarConsulta($contexto, $respuesta);
            $this->insertarEntidades($nuevoId, $respuesta['entidades'] ?? null);
            $this->insertarRecomendaciones(
                $nuevoId,
                $respuesta['sugerencias'] ?? null,
                $intencion === 'recomendar_sustituto'
            );

            $this->db->commit();
            $enTransaccion = false;
            $this->ultimoIdInsertado = $nuevoId;
        } catch (\Throwable $e) {
            $this->ultimoIdInsertado = null;
            if ($enTransaccion) {
                try {
                    $this->db->rollBack();
                } catch (\Throwable $e2) {
                    error_log("[ElectriSys][AsistenteLog] ERROR en rollback: " . $e2->getMessage());
                }
            }
            error_log(
                "[ElectriSys][AsistenteLog] ERROR al registrar consulta '{$accion}': " .
                $e->getMessage()
            );
        }
    }

    /** ID de la última fila insertada, o null si el último intento falló. */
    public function ultimoIdInsertado(): ?int
    {
        return $this->ultimoIdInsertado;
    }

    private function insertarConsulta(array $contexto, array $respuesta): int
    {
        $intencion = $respuesta['intencion'] ?? null;
        $stmt = $this->db->prepare("
            INSERT INTO consultas_asistente (usuario_id, texto_consulta, intencion_id, confianza)
            VALUES (:usuario_id, :texto_consulta,
                    (SELECT i.id FROM nlp_intenciones i WHERE i.nombre = :intencion),
                    :confianza)
            RETURNING id INTO :out_id
        ");
        $nuevoId = 0;
        $stmt->bindOut(':out_id', $nuevoId);
        $stmt->execute([
            ':usuario_id'     => $contexto['usuario_id'] ?? null,
            ':texto_consulta' => $contexto['texto_consulta'] ?? '',
            ':intencion'      => is_string($intencion) && $intencion !== '' ? $intencion : null,
            ':confianza'      => self::confianzaValida($respuesta['confianza'] ?? null),
        ]);
        return (int) $nuevoId;
    }

    /** La columna es NUMBER(5,4) con CHECK 0..1: lo ilegible o fuera de rango queda NULL. */
    private static function confianzaValida(mixed $valor): ?float
    {
        if (!is_int($valor) && !is_float($valor) && !(is_string($valor) && is_numeric($valor))) {
            return null;
        }
        $n = (float) $valor;
        return ($n >= 0.0 && $n <= 1.0) ? round($n, 4) : null;
    }

    private function insertarEntidades(int $consultaId, mixed $entidades): void
    {
        if (!is_array($entidades)) {
            return;
        }
        $stmt = null;
        foreach (self::TIPOS_ENTIDAD as $clave => $tipo) {
            $valor = $entidades[$clave] ?? null;
            if (!is_scalar($valor) || is_bool($valor)) {
                continue;
            }
            $valor = mb_substr(trim((string) $valor), 0, self::LONGITUD_MAX_VALOR);
            if ($valor === '') {
                continue; // en Oracle '' es NULL y la columna es NOT NULL
            }
            $stmt ??= $this->db->prepare(
                "INSERT INTO consulta_entidades (consulta_id, tipo, valor) VALUES (:consulta_id, :tipo, :valor)"
            );
            $stmt->execute([
                ':consulta_id' => $consultaId,
                ':tipo'        => $tipo,
                ':valor'       => $valor,
            ]);
        }
    }

    private function insertarRecomendaciones(int $consultaId, mixed $sugerencias, bool $esSustituto): void
    {
        if (!is_array($sugerencias)) {
            return;
        }
        // INSERT ... SELECT sobre repuestos: una sugerencia cuyo repuesto ya no
        // existe se omite en vez de romper la FK y perder toda la consulta.
        $stmt = null;
        $vistos = [];
        $posicion = 0;
        foreach (array_values($sugerencias) as $sug) {
            $posicion++;
            $rid = is_array($sug) ? ($sug['id'] ?? null) : null;
            if (!(is_int($rid) || (is_string($rid) && ctype_digit($rid))) || $posicion > 999) {
                continue;
            }
            $rid = (int) $rid;
            if (isset($vistos[$rid])) {
                continue; // PK (consulta_id, repuesto_id): un repuesto repetido cuenta una vez
            }
            $vistos[$rid] = true;

            $sim = $sug['similitud'] ?? null;
            $puntaje = (is_int($sim) || is_float($sim) || (is_string($sim) && is_numeric($sim)))
                && (float) $sim >= 0.0 && (float) $sim <= 9.9999
                ? round((float) $sim * 100, 2)
                : null;

            $stmt ??= $this->db->prepare("
                INSERT INTO consulta_recomendaciones (consulta_id, repuesto_id, posicion, es_sustituto, puntaje)
                SELECT :consulta_id, r.id, :posicion, :es_sustituto, :puntaje
                FROM repuestos r WHERE r.id = :repuesto_id
            ");
            $stmt->execute([
                ':consulta_id'  => $consultaId,
                ':posicion'     => $posicion,
                ':es_sustituto' => $esSustituto ? 1 : 0,
                ':puntaje'      => $puntaje,
                ':repuesto_id'  => $rid,
            ]);
        }
    }
}

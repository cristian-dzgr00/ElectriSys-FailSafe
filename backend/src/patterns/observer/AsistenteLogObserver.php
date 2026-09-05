<?php
declare(strict_types=1);

namespace App\patterns\observer;

use App\models\Database;
use PDO;

/**
 * AsistenteLogObserver — Observer Concreto
 *
 * Reutiliza la interfaz VentaObserver (su forma ya es genérica:
 * actualizar(string $accion, array $contexto)) para persistir cada
 * consulta al asistente NLP en la tabla `consultas_asistente`.
 *
 * Igual que AuditLogObserver: si falla el registro, el flujo principal
 * (responderle al vendedor) NO se ve afectado.
 *
 * @package App\patterns\observer
 */
class AsistenteLogObserver implements VentaObserver
{
    private PDO $db;

    public function __construct()
    {
        $this->db = Database::getConnection();
    }

    /**
     * @param string $accion   'consulta_asistente'
     * @param array  $contexto usuario_id, texto_consulta, respuesta (array decodificado del microservicio)
     */
    public function actualizar(string $accion, array $contexto): void
    {
        try {
            $respuesta = $contexto['respuesta'] ?? [];
            $stmt = $this->db->prepare("
                INSERT INTO consultas_asistente
                    (usuario_id, texto_consulta, intencion_detectada, entidades_json, respuesta_json)
                VALUES (:usuario_id, :texto_consulta, :intencion, :entidades, :respuesta)
            ");
            $stmt->execute([
                ':usuario_id'     => $contexto['usuario_id'] ?? null,
                ':texto_consulta' => $contexto['texto_consulta'] ?? '',
                ':intencion'      => $respuesta['intencion'] ?? null,
                ':entidades'      => json_encode($respuesta['entidades'] ?? null),
                ':respuesta'      => json_encode($respuesta),
            ]);
        } catch (\Throwable $e) {
            error_log(
                "[ElectriSys][AsistenteLog] ERROR al registrar consulta '{$accion}': " .
                $e->getMessage()
            );
        }
    }
}

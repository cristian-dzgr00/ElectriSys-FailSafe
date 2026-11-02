<?php
declare(strict_types=1);

namespace App\services;

use App\models\OciConnection;

class ConsultasAsistenteListado
{
    /**
     * Reconstruye, para el listado de curación, la forma que tenían las filas
     * cuando consultas_asistente guardaba JSON (intencion_detectada, entidades_json,
     * respuesta_json), a partir de las tablas normalizadas consulta_entidades y
     * consulta_recomendaciones. Así los consumidores (nlp-service/eval/
     * exportar_feedback.py) no cambian de contrato. Además expone `confianza`,
     * `entidades` y `sugerencias` ya decodificadas.
     *
     * Límite conocido: el JSON viejo traía la respuesta completa del microservicio;
     * ahora solo se conserva lo que persiste el esquema (entidades marca, modelo,
     * anio, categoria y código; por sugerencia: id, posición, similitud y si fue sustituto).
     *
     * @param array<int,array<string,mixed>> $filas Filas de consultas_asistente ya leídas
     * @return array<int,array<string,mixed>>
     */
    public static function armar(OciConnection $db, array $filas): array
    {
        if ($filas === []) {
            return [];
        }
        $ids = array_map(static fn(array $f): int => (int) $f['id'], $filas);
        $ph  = implode(',', array_fill(0, count($ids), '?'));

        // Clave del campo de la entidad en el JSON viejo (el código se guarda como tipo 'repuesto').
        $claveEntidad = ['repuesto' => 'codigo'];

        $entidades = [];
        $st = $db->prepare("SELECT consulta_id, tipo, valor FROM consulta_entidades WHERE consulta_id IN ($ph) ORDER BY id");
        $st->execute($ids);
        foreach ($st->fetchAll() as $e) {
            $entidades[(int) $e['consulta_id']][$claveEntidad[$e['tipo']] ?? $e['tipo']] = $e['valor'];
        }

        $sugerencias = [];
        $st = $db->prepare("
            SELECT consulta_id, repuesto_id, posicion, es_sustituto, puntaje
            FROM consulta_recomendaciones WHERE consulta_id IN ($ph)
            ORDER BY consulta_id, posicion
        ");
        $st->execute($ids);
        foreach ($st->fetchAll() as $r) {
            $sugerencias[(int) $r['consulta_id']][] = [
                'id'           => (int) $r['repuesto_id'],
                'posicion'     => (int) $r['posicion'],
                'similitud'    => $r['puntaje'] === null ? null : round((float) $r['puntaje'] / 100, 4),
                'es_sustituto' => (int) $r['es_sustituto'] === 1,
            ];
        }

        $out = [];
        foreach ($filas as $f) {
            $id        = (int) $f['id'];
            $ents      = $entidades[$id] ?? [];
            $sugs      = $sugerencias[$id] ?? [];
            $confianza = $f['confianza'] === null ? null : (float) $f['confianza'];
            $out[] = [
                'id'                  => $id,
                'texto_consulta'      => $f['texto_consulta'],
                'intencion_detectada' => $f['intencion_detectada'],
                'confianza'           => $confianza,
                'entidades'           => (object) $ents,
                'sugerencias'         => $sugs,
                // Compatibilidad con el contrato anterior (columnas JSON eliminadas).
                'entidades_json'      => json_encode((object) $ents),
                'respuesta_json'      => json_encode([
                    'intencion'   => $f['intencion_detectada'],
                    'confianza'   => $confianza,
                    'entidades'   => (object) $ents,
                    'sugerencias' => $sugs,
                ]),
                'util'                => $f['util'],
                'creado_en'           => $f['creado_en'],
            ];
        }
        return $out;
    }
}

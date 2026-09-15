<?php
declare(strict_types=1);

namespace App\models;

use RuntimeException;

/**
 * Envoltorio de un statement oci8 con la misma superficie que ya usaba el
 * backend contra PDOStatement (execute/fetch/fetchAll/fetchColumn/rowCount).
 * Traduce placeholders posicionales "?" (los que ya usa todo el SQL del
 * proyecto) a los nombrados que exige oci8 — ver Database::posicionalANombrado().
 */
class OciStatement
{
    /** @var resource|\OCIStatement */
    private $stid;
    private array $placeholders;
    private int $modoCommit;
    private array $bindStorage = [];
    private ?array $tiposColumna = null;

    public function __construct($stid, array $placeholders, int $modoCommit)
    {
        $this->stid         = $stid;
        $this->placeholders = $placeholders;
        $this->modoCommit   = $modoCommit;
    }

    public function execute(array $params = []): bool
    {
        // Soporta las dos convenciones que ya usa el proyecto (igual que
        // PDO real): posicional ("?" -> [$v1, $v2,...]) y nombrada
        // (":clave" en el SQL -> [':clave' => $v, ...]).
        $esNombrado = $params !== [] && array_keys($params) !== range(0, count($params) - 1);

        if ($esNombrado) {
            foreach ($params as $nombre => $valor) {
                $n = str_starts_with($nombre, ':') ? $nombre : ':' . $nombre;
                $this->bindStorage[$n] = $valor;
                oci_bind_by_name($this->stid, $n, $this->bindStorage[$n], -1);
            }
        } else {
            foreach (array_values($params) as $i => $valor) {
                $nombre = $this->placeholders[$i] ?? null;
                if ($nombre === null) {
                    continue;
                }
                $this->bindStorage[$i] = $valor;
                oci_bind_by_name($this->stid, $nombre, $this->bindStorage[$i], -1);
            }
        }

        $ok = @oci_execute($this->stid, $this->modoCommit);
        if (!$ok) {
            $e = oci_error($this->stid);
            throw new RuntimeException($e['message'] ?? 'Error ejecutando SQL', (int) ($e['code'] ?? 0));
        }
        return true;
    }

    /** @return array<string,mixed>|false */
    public function fetch()
    {
        $fila = oci_fetch_assoc($this->stid);
        return $fila === false ? false : $this->normalizar($fila);
    }

    public function fetchAll(): array
    {
        $filas = [];
        while (($f = oci_fetch_assoc($this->stid)) !== false) {
            $filas[] = $this->normalizar($f);
        }
        return $filas;
    }

    /** @return mixed|false */
    public function fetchColumn()
    {
        $fila = oci_fetch_row($this->stid);
        if ($fila === false) {
            return false;
        }
        $valor = $fila[0];
        return (is_object($valor) && method_exists($valor, 'load')) ? $valor->load() : $valor;
    }

    /** Equivalente a fetchAll(PDO::FETCH_COLUMN): todos los valores de la primera columna. */
    public function fetchColumnAll(): array
    {
        $valores = [];
        while (($fila = oci_fetch_row($this->stid)) !== false) {
            $v = $fila[0];
            $valores[] = (is_object($v) && method_exists($v, 'load')) ? $v->load() : $v;
        }
        return $valores;
    }

    public function rowCount(): int
    {
        return oci_num_rows($this->stid);
    }

    /**
     * Bindea un parámetro de SALIDA (para RETURNING ... INTO :nombre) —
     * llamar ANTES de execute(). Reemplaza a PDO::lastInsertId(), que no
     * tiene equivalente en Oracle (no hay "último id" a nivel de sesión).
     */
    public function bindOut(string $nombre, &$variable, int $maxLength = 40): void
    {
        oci_bind_by_name($this->stid, $nombre, $variable, $maxLength);
    }

    /**
     * oci8 devuelve TODAS las columnas como string (incluidas NUMBER) y las
     * claves en MAYÚSCULAS, y los CLOB/JSON como objetos OCI-Lob. Con MySQL
     * (driver nativo, sin prepares emulados) los NUMBER/DECIMAL sí volvían
     * tipados como int/float en el JSON de cada endpoint — el frontend y el
     * microservicio NLP (Python) dependen de eso (ej. "stock" > 0 explota
     * si "stock" es string). Se resuelve casteando por metadata real de la
     * columna (oci_field_type), no por heurística sobre el valor.
     */
    private function normalizar(array $fila): array
    {
        if ($this->tiposColumna === null) {
            $this->tiposColumna = [];
            $n = oci_num_fields($this->stid);
            for ($i = 1; $i <= $n; $i++) {
                $nombre = strtolower(oci_field_name($this->stid, $i));
                $this->tiposColumna[$nombre] = oci_field_type($this->stid, $i);
            }
        }

        $out = [];
        foreach ($fila as $col => $val) {
            if (is_object($val) && method_exists($val, 'load')) {
                $val = $val->load();
            }
            $colLower = strtolower($col);
            if ($val !== null && ($this->tiposColumna[$colLower] ?? null) === 'NUMBER') {
                $val = (strpos((string) $val, '.') !== false) ? (float) $val : (int) $val;
            }
            $out[$colLower] = $val;
        }
        return $out;
    }
}

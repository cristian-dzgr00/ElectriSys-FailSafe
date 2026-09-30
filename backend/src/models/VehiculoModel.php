<?php
namespace App\models;

use App\patterns\observer\ErroresNlpObserver;
use App\patterns\observer\VentaObserver;
use App\patterns\observer\VentaSubject;

/**
 * También es Subject (patrón Observer): al insertar un vehículo nuevo
 * notifica 'vehiculo_creado'. Es el único punto por donde entran marcas y
 * modelos nuevos (POST /api/vehiculos y la alta de compatibilidad de
 * repuestos.php pasan por buscarOcrear()).
 */
class VehiculoModel implements VentaSubject
{
    private const COMBUSTIBLES_VALIDOS = ['gasolina', 'diesel', 'hibrido', 'electrico', 'gas'];

    private OciConnection $db;

    /** @var VentaObserver[] */
    private array $observers = [];

    public function __construct()
    {
        $this->db = Database::getConnection();
        // El asistente NLP genera los posibles errores de escritura de cada
        // marca/modelo nuevo ("geely" -> "yili") para reconocerlos al instante.
        $this->agregarObserver(new ErroresNlpObserver());
    }

    public function agregarObserver(VentaObserver $observer): void
    {
        $this->observers[] = $observer;
    }

    public function removerObserver(VentaObserver $observer): void
    {
        $this->observers = array_filter($this->observers, fn($o) => $o !== $observer);
    }

    public function notificarObservers(string $accion, array $contexto): void
    {
        foreach ($this->observers as $observer) {
            try {
                $observer->actualizar($accion, $contexto);
            } catch (\Throwable $e) {
                // El vehículo ya se guardó: un Observer que falla no lo deshace.
                error_log(
                    "[ElectriSys][VehiculoModel] Observer " . get_class($observer) .
                    " falló silenciosamente: " . $e->getMessage()
                );
            }
        }
    }

    public function listar(array $filtros = []): array
    {
        $where  = ['1=1'];
        $params = [];

        if (!empty($filtros['marca'])) {
            $where[]  = 'marca = ?';
            $params[] = $filtros['marca'];
        }
        if (!empty($filtros['modelo'])) {
            $where[]  = 'modelo = ?';
            $params[] = $filtros['modelo'];
        }
        if (!empty($filtros['q'])) {
            $where[]  = '(marca LIKE ? OR modelo LIKE ?)';
            $q = '%' . $filtros['q'] . '%';
            $params[] = $q;
            $params[] = $q;
        }

        $stmt = $this->db->prepare("
            SELECT * FROM vehiculos
            WHERE " . implode(' AND ', $where) . "
            ORDER BY marca, modelo, anio_desde
        ");
        $stmt->execute($params);
        return $stmt->fetchAll();
    }

    public function marcas(): array
    {
        return $this->db->query("SELECT DISTINCT marca FROM vehiculos ORDER BY marca")
            ->fetchColumnAll();
    }

    public function modelos(string $marca): array
    {
        $stmt = $this->db->prepare("SELECT DISTINCT modelo FROM vehiculos WHERE marca = ? ORDER BY modelo");
        $stmt->execute([$marca]);
        return $stmt->fetchColumnAll();
    }

    public function buscarPorId(int $id): ?array
    {
        $stmt = $this->db->prepare("SELECT * FROM vehiculos WHERE id = ?");
        $stmt->execute([$id]);
        return $stmt->fetch() ?: null;
    }

    /**
     * Devuelve el id del vehículo con estos datos exactos, creándolo si no existe.
     * Se apoya en la UNIQUE KEY uq_vehiculo para no depender de una transacción explícita:
     * si dos peticiones concurrentes intentan crear el mismo vehículo, la segunda
     * captura el error de duplicado y reutiliza el registro ya insertado.
     */
    public function buscarOcrear(array $d): int
    {
        $marca       = trim($d['marca']);
        $modelo      = trim($d['modelo']);
        $anioDesde   = (int) $d['anio_desde'];
        $anioHasta   = (int) $d['anio_hasta'];
        $motor       = trim((string)($d['motor'] ?? '')) !== '' ? trim($d['motor']) : null;
        $combustible = $d['combustible'] ?? 'gasolina';

        $existente = $this->buscarExacto($marca, $modelo, $anioDesde, $anioHasta, $motor, $combustible);
        if ($existente !== null) {
            return $existente;
        }

        try {
            $stmt = $this->db->prepare("
                INSERT INTO vehiculos (marca, modelo, anio_desde, anio_hasta, motor, combustible)
                VALUES (?, ?, ?, ?, ?, ?)
                RETURNING id INTO :out_id
            ");
            $nuevoId = 0;
            $stmt->bindOut(':out_id', $nuevoId);
            $stmt->execute([$marca, $modelo, $anioDesde, $anioHasta, $motor, $combustible]);
            $this->notificarObservers('vehiculo_creado', ['marca' => $marca, 'modelo' => $modelo]);
            return (int) $nuevoId;
        } catch (\Throwable $e) {
            if (OciConnection::esViolacionDeUnicidad($e)) {
                $existente = $this->buscarExacto($marca, $modelo, $anioDesde, $anioHasta, $motor, $combustible);
                if ($existente !== null) {
                    return $existente;
                }
            }
            throw $e;
        }
    }

    private function buscarExacto(
        string $marca,
        string $modelo,
        int $anioDesde,
        int $anioHasta,
        ?string $motor,
        string $combustible
    ): ?int {
        // Oracle no tiene "<=>" (null-safe equal de MySQL): se resuelve
        // igualando o, si ambos lados son NULL, tratándolo como coincidencia.
        $stmt = $this->db->prepare("
            SELECT id FROM vehiculos
            WHERE marca = ? AND modelo = ? AND anio_desde = ? AND anio_hasta = ?
              AND (motor = ? OR (motor IS NULL AND ? IS NULL))
              AND combustible = ?
        ");
        $stmt->execute([$marca, $modelo, $anioDesde, $anioHasta, $motor, $motor, $combustible]);
        $id = $stmt->fetchColumn();
        return $id !== false ? (int) $id : null;
    }

    public static function validar(array $b): ?string
    {
        $marca  = trim((string)($b['marca']  ?? ''));
        $modelo = trim((string)($b['modelo'] ?? ''));

        if ($marca === '')  return 'La marca del vehículo es obligatoria';
        if ($modelo === '') return 'El modelo del vehículo es obligatorio';
        if (strlen($marca) > 80 || strlen($modelo) > 80) return 'Marca/modelo no pueden superar 80 caracteres';

        $anioDesde = $b['anio_desde'] ?? null;
        $anioHasta = $b['anio_hasta'] ?? null;
        if (!ctype_digit((string)$anioDesde) || !ctype_digit((string)$anioHasta)) {
            return 'anio_desde y anio_hasta deben ser numéricos';
        }
        $anioActualMax = (int) date('Y') + 2;
        if ((int)$anioDesde < 1950 || (int)$anioDesde > $anioActualMax) {
            return "anio_desde debe estar entre 1950 y $anioActualMax";
        }
        if ((int)$anioHasta < (int)$anioDesde) {
            return 'anio_hasta no puede ser menor que anio_desde';
        }

        $combustible = $b['combustible'] ?? 'gasolina';
        if (!in_array($combustible, self::COMBUSTIBLES_VALIDOS, true)) {
            return 'Combustible inválido. Valores permitidos: ' . implode(', ', self::COMBUSTIBLES_VALIDOS);
        }

        if (isset($b['motor']) && strlen((string)$b['motor']) > 50) {
            return 'El motor no puede superar 50 caracteres';
        }

        return null;
    }
}

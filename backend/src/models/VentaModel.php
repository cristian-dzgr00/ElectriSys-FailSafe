<?php
namespace App\models;

use PDO;

class VentaModel
{
    private PDO $db;
    private bool $enReplica;

    public function __construct()
    {
        $this->db = Database::getConnection();
        $this->enReplica = Database::$usingReplica;
    }

    /**
     * Listar ventas con paginación real y búsqueda.
     * Retorna ['rows' => [...], 'total' => int]
     */
    public function listar(array $filtros = []): array
    {
        $params  = [];
        $where   = ['1=1'];

        if (!empty($filtros['estado'])) {
            $where[]  = 'v.estado = ?';
            $params[] = $filtros['estado'];
        }
        if (!empty($filtros['desde'])) {
            $where[]  = 'DATE(v.creado_en) >= ?';
            $params[] = $filtros['desde'];
        }
        if (!empty($filtros['hasta'])) {
            $where[]  = 'DATE(v.creado_en) <= ?';
            $params[] = $filtros['hasta'];
        }
        if (!empty($filtros['q'])) {
            $where[]  = '(v.numero LIKE ? OR c.nombre LIKE ?)';
            $q = '%' . $filtros['q'] . '%';
            $params[] = $q;
            $params[] = $q;
        }

        $whereStr = implode(' AND ', $where);
        $limit    = min(100, max(1, (int)($filtros['limit']  ?? 15)));
        $offset   = max(0, (int)($filtros['offset'] ?? 0));

        // Total sin paginación
        $countStmt = $this->db->prepare("
            SELECT COUNT(*) FROM ventas v
            LEFT JOIN clientes c ON v.cliente_id = c.id
            WHERE $whereStr
        ");
        $countStmt->execute($params);
        $total = (int) $countStmt->fetchColumn();

        // Filas paginadas
        $dataStmt = $this->db->prepare("
            SELECT v.*, c.nombre AS cliente_nombre, u.nombre AS vendedor_nombre
            FROM ventas v
            LEFT JOIN clientes c ON v.cliente_id = c.id
            LEFT JOIN usuarios u ON v.usuario_id = u.id
            WHERE $whereStr
            ORDER BY v.creado_en DESC
            LIMIT ? OFFSET ?
        ");
        $dataStmt->execute([...$params, $limit, $offset]);

        return ['rows' => $dataStmt->fetchAll(), 'total' => $total];
    }

    public function buscarPorId(int $id): ?array
    {
        $stmt = $this->db->prepare("
            SELECT v.*, c.nombre AS cliente_nombre, u.nombre AS vendedor_nombre
            FROM ventas v
            LEFT JOIN clientes c ON v.cliente_id = c.id
            LEFT JOIN usuarios u ON v.usuario_id = u.id
            WHERE v.id = ?
        ");
        $stmt->execute([$id]);
        $venta = $stmt->fetch() ?: null;

        if ($venta) {
            $det = $this->db->prepare("
                SELECT dv.*, r.nombre AS producto_nombre, r.codigo
                FROM detalle_ventas dv
                JOIN repuestos r ON dv.repuesto_id = r.id
                WHERE dv.venta_id = ?
            ");
            $det->execute([$id]);
            $venta['detalle'] = $det->fetchAll();
        }
        return $venta;
    }

    public function crear(array $data, int $usuarioId): array
    {
        $numero   = 'VTA-' . date('Ymd') . '-' . strtoupper(substr(uniqid(), -6));
        $pendiente = $this->enReplica ? 1 : 0;

        $this->db->beginTransaction();
        try {
            // Verificar stock antes de insertar
            foreach ($data['items'] as $item) {
                $stockStmt = $this->db->prepare("SELECT stock, nombre FROM repuestos WHERE id = ? AND activo = 1");
                $stockStmt->execute([$item['repuesto_id']]);
                $rep = $stockStmt->fetch();
                if (!$rep) {
                    throw new \RuntimeException("Repuesto ID {$item['repuesto_id']} no encontrado");
                }
                if ($rep['stock'] < $item['cantidad']) {
                    throw new \RuntimeException("Stock insuficiente para \"{$rep['nombre']}\": disponible {$rep['stock']}, solicitado {$item['cantidad']}");
                }
            }

            $stmt = $this->db->prepare("
                INSERT INTO ventas (numero, cliente_id, usuario_id, subtotal, descuento, impuesto,
                    total, metodo_pago, estado, notas, pendiente_sync)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'completada', ?, ?)
            ");
            $stmt->execute([
                $numero,
                $data['cliente_id'] ?? null,
                $usuarioId,
                $data['subtotal'],
                $data['descuento'] ?? 0,
                $data['impuesto']  ?? 0,
                $data['total'],
                $data['metodo_pago'] ?? 'efectivo',
                $data['notas']    ?? null,
                $pendiente,
            ]);
            $ventaId = (int) $this->db->lastInsertId();

            foreach ($data['items'] as $item) {
                $subtotalItem = $item['cantidad'] * $item['precio_unit'] - ($item['descuento'] ?? 0);
                $this->db->prepare("
                    INSERT INTO detalle_ventas (venta_id, repuesto_id, cantidad, precio_unit, descuento, subtotal)
                    VALUES (?, ?, ?, ?, ?, ?)
                ")->execute([
                    $ventaId,
                    $item['repuesto_id'],
                    $item['cantidad'],
                    $item['precio_unit'],
                    $item['descuento'] ?? 0,
                    $subtotalItem,
                ]);

                // Descontar stock (atómico)
                $this->db->prepare("
                    UPDATE repuestos SET stock = stock - ? WHERE id = ? AND stock >= ?
                ")->execute([$item['cantidad'], $item['repuesto_id'], $item['cantidad']]);
            }

            $this->db->commit();
            return ['id' => $ventaId, 'numero' => $numero, 'en_replica' => (bool)$pendiente];
        } catch (\Throwable $e) {
            $this->db->rollBack();
            throw $e;
        }
    }

    public function anular(int $id): bool
    {
        $stmt = $this->db->prepare("UPDATE ventas SET estado = 'anulada' WHERE id = ? AND estado = 'completada'");
        $stmt->execute([$id]);
        return $stmt->rowCount() > 0;
    }

    public function resumenHoy(): array
    {
        $stmt = $this->db->query("
            SELECT
                COUNT(*) AS total_ventas,
                COALESCE(SUM(total), 0) AS ingresos,
                COALESCE(AVG(total), 0) AS ticket_promedio
            FROM ventas
            WHERE DATE(creado_en) = CURDATE() AND estado = 'completada'
        ");
        return $stmt->fetch() ?: ['total_ventas' => 0, 'ingresos' => 0, 'ticket_promedio' => 0];
    }
}

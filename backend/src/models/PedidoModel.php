<?php
namespace App\models;

use RuntimeException;

/**
 * Pedidos a proveedor (órdenes de reabastecimiento) — ver oracle/10_pedidos.sql.
 *
 * Al igual que VentaModel, este modelo NUNCA toca repuestos.stock: la entrada
 * de mercancía la hace el trigger trg_pedidos_recibido_suma_stock al detectar
 * el paso a 'recibido'. Si se sumara también acá, cada pedido recibido entraría
 * dos veces al inventario.
 *
 * A diferencia de una venta, un pedido NO reserva stock al crearse: el
 * inventario solo cambia cuando la mercancía llega físicamente. Por eso acá
 * no hay SELECT ... FOR UPDATE — no hay stock que proteger de una condición
 * de carrera mientras el pedido está en tránsito.
 *
 * Usa SQL directo vía OciConnection (no un package PL/SQL como VentaModel):
 * el módulo no tiene lógica compartida con otros consumidores que justifique
 * un pkg_pedidos; las reglas que sí deben vivir en la base son los triggers.
 */
class PedidoModel
{
    /** Estados a los que se puede pasar desde cada estado. */
    public const TRANSICIONES = [
        'solicitado'  => ['en_transito', 'recibido', 'cancelado'],
        'en_transito' => ['recibido', 'cancelado'],
        'recibido'    => [],   // estado final — lo refuerza trg_pedidos_before_update
        'cancelado'   => [],   // estado final
    ];

    private OciConnection $db;

    public function __construct()
    {
        $this->db = Database::getConnection();
    }

    /**
     * Listar pedidos con paginación real, búsqueda por número/proveedor y
     * filtros por estado y proveedor.
     * Retorna ['rows' => [...], 'total' => int]
     */
    public function listar(array $filtros = []): array
    {
        $limit  = min(100, max(1, (int)($filtros['limit']  ?? 15)));
        $offset = max(0, (int)($filtros['offset'] ?? 0));

        $where  = ['1 = 1'];
        $params = [];

        if (!empty($filtros['estado'])) {
            $where[]  = 'p.estado = ?';
            $params[] = $filtros['estado'];
        }
        if (!empty($filtros['proveedor_id'])) {
            $where[]  = 'p.proveedor_id = ?';
            $params[] = (int) $filtros['proveedor_id'];
        }
        if (!empty($filtros['q'])) {
            $where[]  = '(p.numero LIKE ? OR pr.nombre LIKE ?)';
            $q        = '%' . $filtros['q'] . '%';
            $params[] = $q;
            $params[] = $q;
        }

        $stmt = $this->db->prepare("
            SELECT p.id, p.numero, p.estado, p.subtotal, p.total, p.fecha_esperada,
                   p.notas, p.creado_en, p.recibido_en, p.proveedor_id,
                   pr.nombre AS proveedor_nombre,
                   u.nombre  AS usuario_nombre,
                   (SELECT COUNT(*) FROM pedido_detalle d WHERE d.pedido_id = p.id) AS lineas,
                   COUNT(*) OVER() AS total_filas
            FROM pedidos p
            JOIN proveedores pr ON pr.id = p.proveedor_id
            JOIN usuarios    u  ON u.id  = p.usuario_id
            WHERE " . implode(' AND ', $where) . "
            ORDER BY p.creado_en DESC
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
        ");
        $stmt->execute([...$params, $offset, $limit]);

        $rows  = $stmt->fetchAll();
        $total = (int) ($rows[0]['total_filas'] ?? 0);
        foreach ($rows as &$fila) { unset($fila['total_filas']); }
        unset($fila);

        return ['rows' => $rows, 'total' => $total];
    }

    public function buscarPorId(int $id): ?array
    {
        $stmt = $this->db->prepare("
            SELECT p.*, pr.nombre AS proveedor_nombre, u.nombre AS usuario_nombre
            FROM pedidos p
            JOIN proveedores pr ON pr.id = p.proveedor_id
            JOIN usuarios    u  ON u.id  = p.usuario_id
            WHERE p.id = ?
        ");
        $stmt->execute([$id]);
        $pedido = $stmt->fetch();
        if (!$pedido) {
            return null;
        }

        $det = $this->db->prepare("
            SELECT d.id, d.repuesto_id, d.cantidad, d.precio_unit, d.subtotal,
                   r.nombre AS producto_nombre, r.codigo, r.stock
            FROM pedido_detalle d
            JOIN repuestos r ON r.id = d.repuesto_id
            WHERE d.pedido_id = ?
            ORDER BY d.id
        ");
        $det->execute([$id]);
        $pedido['detalle'] = $det->fetchAll();

        return $pedido;
    }

    /**
     * Crea el pedido con su detalle en una sola transacción.
     * El número lo asigna trg_pedidos_numero (secuencia atómica en Oracle),
     * no PHP: dos pedidos creados en el mismo milisegundo no pueden chocar.
     *
     * subtotal/total se recalculan acá a partir de los items y NO se toman
     * del body: el cliente no decide cuánto se le debe al proveedor.
     * total == subtotal a propósito — una orden de compra no lleva el IVA
     * de venta que sí aplica GestorVentas a través de su Strategy.
     *
     * @return array{id:int, numero:string}
     */
    public function crear(array $data, int $usuarioId): array
    {
        $subtotal = 0.0;
        foreach ($data['items'] as $item) {
            $subtotal += (int) $item['cantidad'] * (float) $item['precio_unit'];
        }

        $this->db->beginTransaction();
        try {
            $stmt = $this->db->prepare("
                INSERT INTO pedidos (proveedor_id, usuario_id, subtotal, total, fecha_esperada, notas)
                VALUES (?, ?, ?, ?, TO_DATE(?, 'YYYY-MM-DD'), ?)
                RETURNING id INTO :out_id
            ");
            $nuevoId = 0;
            $stmt->bindOut(':out_id', $nuevoId);
            $stmt->execute([
                (int) $data['proveedor_id'],
                $usuarioId,
                $subtotal,
                $subtotal,
                !empty($data['fecha_esperada']) ? $data['fecha_esperada'] : null,
                $data['notas'] ?? null,
            ]);
            $pedidoId = (int) $nuevoId;

            foreach ($data['items'] as $item) {
                $cantidad   = (int) $item['cantidad'];
                $precioUnit = (float) $item['precio_unit'];
                $this->db->prepare("
                    INSERT INTO pedido_detalle (pedido_id, repuesto_id, cantidad, precio_unit, subtotal)
                    VALUES (?, ?, ?, ?, ?)
                ")->execute([
                    $pedidoId,
                    (int) $item['repuesto_id'],
                    $cantidad,
                    $precioUnit,
                    $cantidad * $precioUnit,
                ]);
            }

            $this->db->commit();

            $numStmt = $this->db->prepare("SELECT numero FROM pedidos WHERE id = ?");
            $numStmt->execute([$pedidoId]);

            return ['id' => $pedidoId, 'numero' => (string) $numStmt->fetchColumn()];
        } catch (\Throwable $e) {
            $this->db->rollBack();
            throw $e;
        }
    }

    /**
     * Avanza el estado del pedido. Al pasar a 'recibido', el trigger
     * trg_pedidos_recibido_suma_stock suma el stock — este método no lo toca.
     *
     * @throws RuntimeException si la transición no es válida (mensaje legible
     *         para el usuario; la ruta lo traduce a 409).
     */
    public function cambiarEstado(int $id, string $nuevoEstado): bool
    {
        $stmt = $this->db->prepare("SELECT estado FROM pedidos WHERE id = ?");
        $stmt->execute([$id]);
        $actual = $stmt->fetchColumn();

        if ($actual === false) {
            throw new RuntimeException('Pedido no encontrado');
        }
        if ($actual === $nuevoEstado) {
            throw new RuntimeException("El pedido ya esta en estado \"{$nuevoEstado}\"");
        }
        if (!in_array($nuevoEstado, self::TRANSICIONES[$actual] ?? [], true)) {
            throw new RuntimeException("No se puede pasar de \"{$actual}\" a \"{$nuevoEstado}\"");
        }

        try {
            $upd = $this->db->prepare("UPDATE pedidos SET estado = ? WHERE id = ?");
            $upd->execute([$nuevoEstado, $id]);
            return $upd->rowCount() > 0;
        } catch (RuntimeException $e) {
            // trg_pedidos_before_update vuelve a validar los estados finales
            // (ORA-20010/20011) por si alguien actualiza por fuera del modelo.
            // Se reexpone el texto del trigger, que ya está escrito para el
            // usuario final, en vez del volcado completo de oci_error().
            if (preg_match('/ORA-200(10|11):\s*(.+)/', $e->getMessage(), $m)) {
                throw new RuntimeException(trim(explode("\n", $m[2])[0]));
            }
            throw $e;
        }
    }

    /**
     * Cancela el pedido. No repone ni libera stock porque nunca lo reservó
     * (el inventario solo se mueve al recibir). Cancelar un pedido ya
     * recibido se rechaza — lo valida cambiarEstado() y lo refuerza el
     * trigger trg_pedidos_before_update.
     */
    public function cancelar(int $id): bool
    {
        return $this->cambiarEstado($id, 'cancelado');
    }

    /** repuesto_id únicos de un pedido — para notificar el stock afectado. */
    public function itemsDePedido(int $pedidoId): array
    {
        $stmt = $this->db->prepare("SELECT DISTINCT repuesto_id FROM pedido_detalle WHERE pedido_id = ?");
        $stmt->execute([$pedidoId]);
        return array_map('intval', $stmt->fetchColumnAll());
    }

    /**
     * Stock actual de un conjunto de repuestos, como mapa [id => stock].
     * Es la misma consulta que VentaModel::stockDe(); se repite acá en vez
     * de acoplar PedidoModel a VentaModel — son tres líneas de SQL de
     * lectura, no una regla de negocio que pueda quedar desincronizada.
     */
    public function stockDe(array $repuestoIds): array
    {
        if ($repuestoIds === []) {
            return [];
        }
        $placeholders = implode(',', array_fill(0, count($repuestoIds), '?'));
        $stmt = $this->db->prepare("SELECT id, stock FROM repuestos WHERE activo = 1 AND id IN ($placeholders)");
        $stmt->execute(array_values($repuestoIds));

        $stock = [];
        foreach ($stmt->fetchAll() as $fila) {
            $stock[(int) $fila['id']] = (int) $fila['stock'];
        }
        return $stock;
    }
}

<?php
namespace App\models;

/**
 * Delega en pkg_ventas/pkg_reportes (oracle/06_packages_plsql.sql) en vez
 * de armar el SQL acá. El descuento/restauración de stock lo hacen los
 * triggers de Oracle (trg_detven_descuenta_stock,
 * trg_ventas_anulada_restaura_stock) — este modelo NUNCA toca
 * repuestos.stock directamente, para no descontarlo/restaurarlo dos veces.
 *
 * subtotal/descuento/impuesto/total llegan ya calculados por GestorVentas
 * (aplica la Strategy de descuento antes de llamar acá) — Oracle solo los
 * persiste, no reimplementa esa regla de negocio.
 *
 * Usa la conexión oci8 cruda (Database::getConnection()->raw()) para las
 * llamadas a pkg_ventas/pkg_reportes: necesitan REF CURSOR y parámetros de
 * salida, que el wrapper OciConnection/OciStatement (pensado para SQL
 * directo estilo PDO) no cubre.
 */
class VentaModel
{
    private OciConnection $db;

    public function __construct()
    {
        $this->db = Database::getConnection();
    }

    /**
     * Listar ventas con paginación real y búsqueda.
     * Retorna ['rows' => [...], 'total' => int]
     */
    public function listar(array $filtros = []): array
    {
        $conn = $this->db->raw();
        $limit  = min(100, max(1, (int)($filtros['limit']  ?? 15)));
        $offset = max(0, (int)($filtros['offset'] ?? 0));
        $estado = $filtros['estado'] ?? null;
        $desde  = $filtros['desde']  ?? null;
        $hasta  = $filtros['hasta']  ?? null;
        $q      = !empty($filtros['q']) ? $filtros['q'] : null;

        $stmt = oci_parse($conn, "
            BEGIN
                :c := pkg_ventas.listar_ventas(
                    p_estado => :estado, p_desde => :desde, p_hasta => :hasta,
                    p_q => :q, p_limit => :limit, p_offset => :offset
                );
            END;
        ");
        $cursor = oci_new_cursor($conn);
        oci_bind_by_name($stmt, ':c', $cursor, -1, OCI_B_CURSOR);
        oci_bind_by_name($stmt, ':estado', $estado, 20);
        oci_bind_by_name($stmt, ':desde', $desde, 10);
        oci_bind_by_name($stmt, ':hasta', $hasta, 10);
        oci_bind_by_name($stmt, ':q', $q, 100);
        oci_bind_by_name($stmt, ':limit', $limit);
        oci_bind_by_name($stmt, ':offset', $offset);
        oci_execute($stmt);
        oci_execute($cursor);

        $rows  = [];
        $total = 0;
        while (($f = oci_fetch_assoc($cursor)) !== false) {
            $f = array_change_key_case($f, CASE_LOWER);
            $total = (int) ($f['total_filas'] ?? 0);
            unset($f['total_filas']);
            $rows[] = $f;
        }
        return ['rows' => $rows, 'total' => $total];
    }

    public function buscarPorId(int $id): ?array
    {
        $conn = $this->db->raw();
        $stmt = oci_parse($conn, "BEGIN pkg_ventas.buscar_venta_por_id(:id, :cab, :det); END;");
        $cab  = oci_new_cursor($conn);
        $det  = oci_new_cursor($conn);
        oci_bind_by_name($stmt, ':id', $id);
        oci_bind_by_name($stmt, ':cab', $cab, -1, OCI_B_CURSOR);
        oci_bind_by_name($stmt, ':det', $det, -1, OCI_B_CURSOR);
        oci_execute($stmt);
        oci_execute($cab);
        oci_execute($det);

        $venta = oci_fetch_assoc($cab);
        if ($venta === false) {
            return null;
        }
        $venta = array_change_key_case($venta, CASE_LOWER);

        $detalle = [];
        while (($f = oci_fetch_assoc($det)) !== false) {
            $detalle[] = array_change_key_case($f, CASE_LOWER);
        }
        $venta['detalle'] = $detalle;
        return $venta;
    }

    public function crear(array $data, int $usuarioId): array
    {
        $conn = $this->db->raw();
        $this->db->beginTransaction();

        try {
            // Verificar stock antes de insertar. FOR UPDATE bloquea la fila
            // dentro de esta transacción para que dos ventas simultáneas del
            // mismo repuesto no pasen ambas esta validación con el mismo stock.
            // El trigger trg_detven_descuenta_stock vuelve a validar al
            // insertar cada línea (ck_repuestos_stock) — esto es una
            // verificación temprana con mensaje claro, no la única barrera.
            foreach ($data['items'] as $item) {
                $stockStmt = $this->db->prepare("SELECT stock, nombre FROM repuestos WHERE id = ? AND activo = 1 FOR UPDATE");
                $stockStmt->execute([$item['repuesto_id']]);
                $rep = $stockStmt->fetch();
                if (!$rep) {
                    throw new \RuntimeException("Repuesto ID {$item['repuesto_id']} no encontrado");
                }
                if ($rep['stock'] < $item['cantidad']) {
                    throw new \RuntimeException("Stock insuficiente para \"{$rep['nombre']}\": disponible {$rep['stock']}, solicitado {$item['cantidad']}");
                }
            }

            $ventaId = 0;
            $clienteId  = $data['cliente_id'] ?? null;
            $subtotal   = (float) $data['subtotal'];
            $descuento  = (float) ($data['descuento'] ?? 0);
            $impuesto   = (float) ($data['impuesto']  ?? 0);
            $total      = (float) $data['total'];
            $metodoPago = $data['metodo_pago'] ?? 'efectivo';
            $notas      = $data['notas'] ?? null;

            $stmt = oci_parse($conn, "
                BEGIN
                    :id := pkg_ventas.registrar_venta(
                        p_cliente_id => :cliente_id, p_usuario_id => :usuario_id,
                        p_subtotal => :subtotal, p_descuento => :descuento,
                        p_impuesto => :impuesto, p_total => :total,
                        p_metodo_pago => :metodo_pago, p_notas => :notas
                    );
                END;
            ");
            oci_bind_by_name($stmt, ':id', $ventaId, 20);
            oci_bind_by_name($stmt, ':cliente_id', $clienteId);
            oci_bind_by_name($stmt, ':usuario_id', $usuarioId);
            oci_bind_by_name($stmt, ':subtotal', $subtotal);
            oci_bind_by_name($stmt, ':descuento', $descuento);
            oci_bind_by_name($stmt, ':impuesto', $impuesto);
            oci_bind_by_name($stmt, ':total', $total);
            oci_bind_by_name($stmt, ':metodo_pago', $metodoPago, 20);
            oci_bind_by_name($stmt, ':notas', $notas, 4000);
            if (!oci_execute($stmt, OCI_NO_AUTO_COMMIT)) {
                throw $this->errorDesdeOci($stmt);
            }
            $ventaId = (int) $ventaId;

            foreach ($data['items'] as $item) {
                $repuestoId = (int) $item['repuesto_id'];
                $cantidad   = (int) $item['cantidad'];
                $precioUnit = (float) $item['precio_unit'];
                $descItem   = (float) ($item['descuento'] ?? 0);

                $stmtItem = oci_parse($conn, "
                    BEGIN
                        pkg_ventas.agregar_item_venta(:venta_id, :repuesto_id, :cantidad, :precio_unit, :descuento);
                    END;
                ");
                oci_bind_by_name($stmtItem, ':venta_id', $ventaId);
                oci_bind_by_name($stmtItem, ':repuesto_id', $repuestoId);
                oci_bind_by_name($stmtItem, ':cantidad', $cantidad);
                oci_bind_by_name($stmtItem, ':precio_unit', $precioUnit);
                oci_bind_by_name($stmtItem, ':descuento', $descItem);
                // Si el stock no alcanza, ck_repuestos_stock revierte esta
                // sentencia (ORA-02290) — se relanza como excepción PHP y
                // el catch de abajo hace rollback de toda la venta.
                if (!oci_execute($stmtItem, OCI_NO_AUTO_COMMIT)) {
                    throw $this->errorDesdeOci($stmtItem);
                }
            }

            $this->db->commit();

            $numStmt = $this->db->prepare("SELECT numero FROM ventas WHERE id = ?");
            $numStmt->execute([$ventaId]);
            $numero = $numStmt->fetchColumn();

            return ['id' => $ventaId, 'numero' => $numero];
        } catch (\Throwable $e) {
            $this->db->rollBack();
            throw $e;
        }
    }

    /**
     * Anula una venta. trg_ventas_anulada_restaura_stock repone el stock
     * automáticamente al detectar el cambio de estado.
     */
    public function anular(int $id): bool
    {
        $conn = $this->db->raw();
        $stmt = oci_parse($conn, "BEGIN pkg_ventas.anular_venta(:id); END;");
        oci_bind_by_name($stmt, ':id', $id);
        // anular_venta lanza ORA-20002 (ya anulada) / ORA-20003 (no existe)
        // vía RAISE_APPLICATION_ERROR — ambos casos se traducen a "false",
        // igual que el contrato anterior (la ruta ya da un mensaje genérico).
        if (!@oci_execute($stmt, OCI_COMMIT_ON_SUCCESS)) {
            $e = oci_error($stmt);
            error_log('[ElectriSys] anular_venta: ' . ($e['message'] ?? 'error desconocido'));
            return false;
        }
        return true;
    }

    /**
     * Stock actual de un conjunto de repuestos, como mapa [id => stock].
     * Usado tras crear/anular una venta para difundir el stock real por
     * WebSocket (ver GestorVentas::crearVenta/anularVenta).
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

    /**
     * repuesto_id únicos vendidos en una venta. Hay que leerlos ANTES de
     * anular: trg_ventas_anulada_restaura_stock repone el stock recién al
     * anular, pero las líneas de detalle_ventas no dicen qué se vendió
     * después de ese momento.
     */
    public function itemsDeVenta(int $ventaId): array
    {
        $stmt = $this->db->prepare("SELECT DISTINCT repuesto_id FROM detalle_ventas WHERE venta_id = ?");
        $stmt->execute([$ventaId]);
        return array_map('intval', $stmt->fetchColumnAll());
    }

    public function resumenHoy(): array
    {
        $conn = $this->db->raw();
        $stmt = oci_parse($conn, "BEGIN pkg_reportes.resumen_hoy(:c); END;");
        $cursor = oci_new_cursor($conn);
        oci_bind_by_name($stmt, ':c', $cursor, -1, OCI_B_CURSOR);
        oci_execute($stmt);
        oci_execute($cursor);
        $fila = oci_fetch_assoc($cursor);
        if ($fila === false) {
            return ['total_ventas' => 0, 'ingresos' => 0, 'ticket_promedio' => 0];
        }
        return array_change_key_case($fila, CASE_LOWER);
    }

    private function errorDesdeOci($stmt): \RuntimeException
    {
        $e = oci_error($stmt);
        return new \RuntimeException($e['message'] ?? 'Error de base de datos desconocido');
    }
}

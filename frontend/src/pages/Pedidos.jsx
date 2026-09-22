// frontend/src/pages/Pedidos.jsx
// Pedidos a proveedor (órdenes de reabastecimiento).
//
// Un pedido acá NO es un encargo de un cliente: es una orden de compra hacia
// un proveedor. Por eso el stock no se reserva al crearlo — sube cuando el
// pedido se marca "recibido" (lo hace el trigger trg_pedidos_recibido_suma_stock
// en Oracle, ver oracle/10_pedidos.sql).
//
// La vista completa está restringida a admin/dueño, tanto en el menú
// (Sidebar.jsx) como en la ruta (App.jsx) y en el backend (RoleMiddleware).

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Plus, Search, X, Trash2, Eye, Truck, PackageCheck, Wifi, WifiOff,
} from 'lucide-react';
import Table from '../components/Table';
import Pagination from '../components/Pagination';
import { StatusBadge } from '../components/Tooltip';
import BuscadorRepuesto from '../components/BuscadorRepuesto';
import { useToastContext } from '../context/ToastContext';
import { pedidosService } from '../services/pedidosService';
import { proveedoresService } from '../services/ventasService';
import { useWebSocket } from '../hooks/useWebSocket';

const fmt = n => new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 }).format(n ?? 0);
const fmtFecha = v => (v ? new Date(v).toLocaleDateString('es-CO', { dateStyle: 'short' }) : '—');

const PAGE_SIZE = 15;

const ESTADOS = ['solicitado', 'en_transito', 'recibido', 'cancelado'];
const ESTADO_LABEL = {
  solicitado:  'Solicitado',
  en_transito: 'En tránsito',
  recibido:    'Recibido',
  cancelado:   'Cancelado',
};
const estadoBadge = e => ({
  solicitado:  'badge-warning',
  en_transito: 'badge-accent',
  recibido:    'badge-success',
  cancelado:   'badge-danger',
}[e] || 'badge-neutral');

export default function Pedidos() {
  const toast = useToastContext();

  const [data,        setData]        = useState([]);
  const [total,       setTotal]       = useState(0);
  const [page,        setPage]        = useState(1);
  const [loading,     setLoading]     = useState(true);
  const [q,           setQ]           = useState('');
  const [filtroEstado, setFiltroEstado] = useState('');
  const [filtroProv,   setFiltroProv]   = useState('');

  const [proveedores, setProveedores] = useState([]);
  const [modal,       setModal]       = useState(false);   // false | 'new' | 'detail'
  const [detalle,     setDetalle]     = useState(null);
  const [confirmCancel, setConfirmCancel] = useState(null);
  const [accionando,  setAccionando]  = useState(false);

  // ── Formulario de nuevo pedido ──
  const [provId,   setProvId]   = useState('');
  const [fechaEsp, setFechaEsp] = useState('');
  const [notas,    setNotas]    = useState('');
  const [items,    setItems]    = useState([]);
  const [saving,   setSaving]   = useState(false);
  const [error,    setError]    = useState('');

  // Refs para leer los filtros vigentes desde callbacks que no deben
  // recrearse (el del WebSocket) — mismo motivo que en Ventas.jsx.
  const filtrosRef = useRef({ page, q, estado: filtroEstado, prov: filtroProv });
  useEffect(() => {
    filtrosRef.current = { page, q, estado: filtroEstado, prov: filtroProv };
  }, [page, q, filtroEstado, filtroProv]);

  const load = useCallback(async (p, search, estado, prov) => {
    setLoading(true);
    try {
      const params = { page: p, limit: PAGE_SIZE };
      if (search) params.q = search;
      if (estado) params.estado = estado;
      if (prov)   params.proveedor_id = prov;
      const r = await pedidosService.listar(params);
      setData(r.data.data ?? []);
      setTotal(r.data.total ?? 0);
    } catch {
      toast('Error cargando pedidos', { type: 'error' });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  // Carga inicial + catálogo de proveedores para el filtro y el modal
  useEffect(() => {
    proveedoresService.listar({ limit: 100 })
      .then(r => setProveedores(r.data.data ?? []))
      .catch(() => {});
  }, []);

  // Cualquier cambio de filtro vuelve a página 1; el cambio de página no
  // resetea nada. Se separan para no disparar dos cargas por interacción.
  const primeraCarga = useRef(true);
  useEffect(() => {
    if (primeraCarga.current) { primeraCarga.current = false; load(1, '', '', ''); return; }
    setPage(1);
    load(1, q, filtroEstado, filtroProv);
  }, [q, filtroEstado, filtroProv]);   // eslint-disable-line react-hooks/exhaustive-deps

  const prevPage = useRef(1);
  useEffect(() => {
    if (page === prevPage.current) return;
    prevPage.current = page;
    const f = filtrosRef.current;
    load(page, f.q, f.estado, f.prov);
  }, [page]);                          // eslint-disable-line react-hooks/exhaustive-deps

  // ── Tiempo real ────────────────────────────────────────────────
  // Si otra sesión crea un pedido o le cambia el estado, esta vista se
  // entera por el mismo WebSocket que usa el inventario. Para un cambio de
  // estado basta con parchear la fila en sitio (el payload trae pedido_id y
  // estado); para un pedido nuevo hace falta recargar, porque no sabemos si
  // entra en la página y los filtros que el usuario tiene puestos.
  const handleWsMessage = useCallback((event) => {
    if (event.type === 'estado_pedido' || event.type === 'cancelar_pedido') {
      const { pedido_id: id, estado } = event.payload || {};
      if (!id || !estado) return;
      setData(prev => prev.map(p => (p.id === id ? { ...p, estado } : p)));
      return;
    }
    if (event.type === 'crear_pedido') {
      const f = filtrosRef.current;
      load(f.page, f.q, f.estado, f.prov);
    }
  }, [load]);

  const { connected: wsConnected } = useWebSocket(handleWsMessage);

  // ── Acciones ───────────────────────────────────────────────────
  const openNew = () => {
    setProvId(''); setFechaEsp(''); setNotas(''); setItems([]); setError('');
    setModal('new');
  };

  const openDetalle = async (id) => {
    try {
      const r = await pedidosService.buscar(id);
      setDetalle(r.data.data);
      setModal('detail');
    } catch {
      toast('No se pudo abrir el pedido', { type: 'error' });
    }
  };

  const addItem = (rep) => {
    setItems(prev => {
      const idx = prev.findIndex(i => i.repuesto_id === rep.id);
      if (idx >= 0) {
        const copy = [...prev];
        copy[idx] = { ...copy[idx], cantidad: copy[idx].cantidad + 1 };
        return copy;
      }
      // precio_compra y no precio_venta: es lo que se le paga al proveedor.
      return [...prev, {
        repuesto_id: rep.id,
        nombre: rep.nombre,
        cantidad: 1,
        precio_unit: Number(rep.precio_compra) || 0,
      }];
    });
  };

  const removeItem = idx => setItems(p => p.filter((_, i) => i !== idx));

  const totalPedido = items.reduce((s, i) => s + i.cantidad * i.precio_unit, 0);

  const guardarPedido = async () => {
    if (!provId)          { setError('Selecciona el proveedor'); return; }
    if (items.length === 0) { setError('Agrega al menos un producto'); return; }
    setSaving(true);
    try {
      const r = await pedidosService.crear({
        proveedor_id: provId,
        fecha_esperada: fechaEsp || null,
        notas,
        items,
      });
      setModal(false);
      prevPage.current = 1;
      setPage(1);
      await load(1, q, filtroEstado, filtroProv);
      toast(`Pedido ${r.data.numero} registrado`, { type: 'success' });
    } catch (e) {
      setError(e.response?.data?.error || 'Error al registrar el pedido');
    } finally {
      setSaving(false);
    }
  };

  const avanzarEstado = async (pedido, estado) => {
    if (accionando) return;
    setAccionando(true);
    try {
      await pedidosService.cambiarEstado(pedido.id, estado);
      // Se parchea en sitio en vez de recargar: el WebSocket avisa a las
      // demás sesiones, pero el evento no vuelve al emisor de forma
      // garantizada (el servidor filtra por rol, no reenvía al autor).
      setData(prev => prev.map(p => (p.id === pedido.id ? { ...p, estado } : p)));
      toast(
        estado === 'recibido'
          ? `Pedido ${pedido.numero} recibido — stock actualizado`
          : `Pedido ${pedido.numero} marcado como ${ESTADO_LABEL[estado].toLowerCase()}`,
        { type: 'success' },
      );
    } catch (e) {
      toast(e.response?.data?.error || 'No se pudo actualizar el pedido', { type: 'error' });
    } finally {
      setAccionando(false);
    }
  };

  const confirmarCancelacion = async () => {
    if (!confirmCancel || accionando) return;
    const { id, numero } = confirmCancel;
    setAccionando(true);
    setConfirmCancel(null);
    try {
      await pedidosService.cancelar(id);
      setData(prev => prev.map(p => (p.id === id ? { ...p, estado: 'cancelado' } : p)));
      toast(`Pedido ${numero} cancelado`, { type: 'warning' });
    } catch (e) {
      toast(e.response?.data?.error || 'No se pudo cancelar el pedido', { type: 'error' });
    } finally {
      setAccionando(false);
    }
  };

  // ── Tabla ──────────────────────────────────────────────────────
  const columns = [
    { key: 'numero',           label: 'N° Pedido' },
    { key: 'proveedor_nombre', label: 'Proveedor' },
    { key: 'usuario_nombre',   label: 'Solicitado por' },
    { key: 'lineas',           label: 'Ítems', render: v => <span className="badge badge-neutral">{v}</span> },
    { key: 'total',            label: 'Total', render: v => fmt(v) },
    { key: 'fecha_esperada',   label: 'Llegada estimada', render: v => fmtFecha(v) },
    { key: 'estado',           label: 'Estado', render: v => (
      <StatusBadge status={ESTADO_LABEL[v] ?? v} className={`badge ${estadoBadge(v)}`} />
    )},
    { key: 'id', label: '', render: (_, r) => (
      <div style={{ display: 'flex', gap: 6 }}>
        <button className="btn-icon" onClick={() => openDetalle(r.id)} title="Ver detalle"><Eye size={13} /></button>

        {r.estado === 'solicitado' && (
          <button className="btn-icon" title="Marcar en tránsito" disabled={accionando}
            onClick={() => avanzarEstado(r, 'en_transito')}>
            <Truck size={13} />
          </button>
        )}

        {(r.estado === 'solicitado' || r.estado === 'en_transito') && (
          <button className="btn-icon" style={{ color: 'var(--success)' }} disabled={accionando}
            title="Marcar recibido — suma la mercancía al inventario"
            onClick={() => avanzarEstado(r, 'recibido')}>
            <PackageCheck size={13} />
          </button>
        )}

        {(r.estado === 'solicitado' || r.estado === 'en_transito') && (
          <button className="btn-icon" style={{ color: 'var(--danger)' }} disabled={accionando}
            title="Cancelar pedido"
            onClick={() => setConfirmCancel({ id: r.id, numero: r.numero })}>
            <X size={13} />
          </button>
        )}
      </div>
    )},
  ];

  return (
    <>
      <div className="page-header">
        <div>
          <div className="page-title">Pedidos a proveedor</div>
          <div className="page-subtitle" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {total} órdenes de reabastecimiento
            <span
              title={wsConnected
                ? 'Tiempo real activo'
                : 'Sin conexión en tiempo real — los cambios de otras sesiones no se ven solos, recarga la página'}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 11,
                color: wsConnected ? 'var(--success)' : 'var(--text-muted)',
              }}
            >
              {wsConnected ? <Wifi size={12} /> : <WifiOff size={12} />} {wsConnected ? 'En vivo' : 'Offline'}
            </span>
          </div>
        </div>
        <button className="btn btn-primary" onClick={openNew}><Plus size={15} /> Nuevo pedido</button>
      </div>

      <div className="toolbar" style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <div className="search-bar" style={{ flex: 1, minWidth: 220 }}>
          <Search size={14} className="search-icon" />
          <input className="form-control" placeholder="Buscar por número o proveedor…"
            value={q} onChange={e => setQ(e.target.value)} />
        </div>
        <select className="form-control" style={{ maxWidth: 180 }}
          value={filtroEstado} onChange={e => setFiltroEstado(e.target.value)}>
          <option value="">Todos los estados</option>
          {ESTADOS.map(e => <option key={e} value={e}>{ESTADO_LABEL[e]}</option>)}
        </select>
        <select className="form-control" style={{ maxWidth: 220 }}
          value={filtroProv} onChange={e => setFiltroProv(e.target.value)}>
          <option value="">Todos los proveedores</option>
          {proveedores.map(p => <option key={p.id} value={p.id}>{p.nombre}</option>)}
        </select>
      </div>

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <Table columns={columns} data={data} loading={loading} />
        <Pagination page={page} pageSize={PAGE_SIZE} total={total}
          onPrev={() => setPage(p => p - 1)} onNext={() => setPage(p => p + 1)} />
      </div>

      {/* Modal nuevo pedido */}
      {modal === 'new' && (
        <div className="modal-overlay">
          <div className="modal modal-lg">
            <div className="modal-header">
              <div className="modal-title">Nuevo pedido a proveedor</div>
              <button className="modal-close" onClick={() => setModal(false)}><X size={18} /></button>
            </div>
            <div className="modal-body">
              {error && <div className="alert alert-error">{error}</div>}

              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Proveedor *</label>
                  <select className="form-control" value={provId} onChange={e => setProvId(e.target.value)}>
                    <option value="">Selecciona un proveedor…</option>
                    {proveedores.map(p => <option key={p.id} value={p.id}>{p.nombre}</option>)}
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">Llegada estimada</label>
                  <input type="date" className="form-control" value={fechaEsp}
                    onChange={e => setFechaEsp(e.target.value)} />
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">Agregar producto</label>
                {/* precio de compra: es una orden hacia el proveedor, no una venta */}
                <BuscadorRepuesto onSeleccionar={addItem} campoPrecio="precio_compra" />
              </div>

              {items.length > 0 && (
                <div className="card" style={{ padding: 0, overflow: 'hidden', marginBottom: 16 }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                      <tr style={{ background: 'var(--bg-hover)' }}>
                        {['Producto', 'Cant.', 'Costo unit.', 'Subtotal', ''].map(h => (
                          <th key={h} style={{
                            padding: '8px 12px',
                            textAlign: h === 'Cant.' ? 'center' : (h === 'Costo unit.' || h === 'Subtotal') ? 'right' : 'left',
                            fontSize: 11, color: 'var(--text-secondary)',
                          }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {items.map((it, i) => (
                        <tr key={it.repuesto_id} style={{ borderTop: '1px solid var(--border)' }}>
                          <td style={{ padding: '8px 12px' }}>{it.nombre}</td>
                          <td style={{ padding: '8px 12px', textAlign: 'center' }}>
                            <input type="number" min={1}
                              style={{ width: 60, background: 'var(--bg-input)', border: '1px solid var(--border)', borderRadius: 6, color: 'var(--text-primary)', textAlign: 'center', padding: '4px 6px' }}
                              value={it.cantidad}
                              onChange={e => {
                                const c = [...items];
                                c[i] = { ...c[i], cantidad: Math.max(1, +e.target.value) };
                                setItems(c);
                              }} />
                          </td>
                          <td style={{ padding: '8px 12px', textAlign: 'right' }}>
                            {/* Editable: el proveedor puede cotizar distinto al
                                precio_compra que hoy tiene el repuesto. */}
                            <input type="number" min={0} step="1"
                              style={{ width: 110, background: 'var(--bg-input)', border: '1px solid var(--border)', borderRadius: 6, color: 'var(--text-primary)', textAlign: 'right', padding: '4px 6px' }}
                              value={it.precio_unit}
                              onChange={e => {
                                const c = [...items];
                                c[i] = { ...c[i], precio_unit: Math.max(0, +e.target.value) };
                                setItems(c);
                              }} />
                          </td>
                          <td style={{ padding: '8px 12px', textAlign: 'right', fontWeight: 600 }}>
                            {fmt(it.cantidad * it.precio_unit)}
                          </td>
                          <td style={{ padding: '8px 12px' }}>
                            <button className="btn-icon" style={{ color: 'var(--danger)' }}
                              onClick={() => removeItem(i)}><Trash2 size={13} /></button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              <div style={{ textAlign: 'right', marginBottom: 12 }}>
                <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--accent)' }}>
                  Total a pagar: {fmt(totalPedido)}
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
                  El stock no cambia hasta marcar el pedido como recibido.
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">Notas</label>
                <input className="form-control" value={notas} onChange={e => setNotas(e.target.value)}
                  placeholder="Condiciones de pago, transportadora, observaciones…" />
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn btn-ghost" onClick={() => setModal(false)}>Cancelar</button>
              <button className="btn btn-primary" onClick={guardarPedido} disabled={saving}>
                {saving ? 'Registrando…' : 'Registrar pedido'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal detalle */}
      {modal === 'detail' && detalle && (
        <div className="modal-overlay" onClick={e => e.target === e.currentTarget && setModal(false)}>
          <div className="modal modal-lg">
            <div className="modal-header">
              <div className="modal-title">Pedido {detalle.numero}</div>
              <button className="modal-close" onClick={() => setModal(false)}><X size={18} /></button>
            </div>
            <div className="modal-body">
              <div className="form-row" style={{ marginBottom: 12 }}>
                <div><span style={{ color: 'var(--text-muted)', fontSize: 12 }}>Proveedor</span><br /><strong>{detalle.proveedor_nombre}</strong></div>
                <div><span style={{ color: 'var(--text-muted)', fontSize: 12 }}>Solicitado por</span><br /><strong>{detalle.usuario_nombre}</strong></div>
                <div><span style={{ color: 'var(--text-muted)', fontSize: 12 }}>Estado</span><br />
                  <StatusBadge status={ESTADO_LABEL[detalle.estado] ?? detalle.estado} className={`badge ${estadoBadge(detalle.estado)}`} />
                </div>
                <div><span style={{ color: 'var(--text-muted)', fontSize: 12 }}>Llegada estimada</span><br /><strong>{fmtFecha(detalle.fecha_esperada)}</strong></div>
              </div>

              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ background: 'var(--bg-hover)' }}>
                    {['Producto', 'Stock actual', 'Cant.', 'Costo unit.', 'Subtotal'].map(h => (
                      <th key={h} style={{
                        padding: '8px 12px',
                        textAlign: h === 'Producto' ? 'left' : h === 'Cant.' || h === 'Stock actual' ? 'center' : 'right',
                        fontSize: 11, color: 'var(--text-secondary)',
                      }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {detalle.detalle?.map(d => (
                    <tr key={d.id} style={{ borderTop: '1px solid var(--border)' }}>
                      <td style={{ padding: '8px 12px' }}>{d.producto_nombre}</td>
                      <td style={{ padding: '8px 12px', textAlign: 'center', color: 'var(--text-muted)' }}>{d.stock}</td>
                      <td style={{ padding: '8px 12px', textAlign: 'center' }}>{d.cantidad}</td>
                      <td style={{ padding: '8px 12px', textAlign: 'right' }}>{fmt(d.precio_unit)}</td>
                      <td style={{ padding: '8px 12px', textAlign: 'right', fontWeight: 600 }}>{fmt(d.subtotal)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <div style={{ textAlign: 'right', marginTop: 12 }}>
                <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--accent)' }}>Total: {fmt(detalle.total)}</div>
                {detalle.recibido_en && (
                  <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                    Recibido el {new Date(detalle.recibido_en).toLocaleString('es-CO', { dateStyle: 'short', timeStyle: 'short' })}
                  </div>
                )}
              </div>

              {detalle.notas && (
                <div className="form-group" style={{ marginTop: 12 }}>
                  <label className="form-label">Notas</label>
                  <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{detalle.notas}</div>
                </div>
              )}
            </div>
            <div className="modal-footer">
              <button className="btn btn-ghost" onClick={() => setModal(false)}>Cerrar</button>
            </div>
          </div>
        </div>
      )}

      {/* Confirmación de cancelación */}
      {confirmCancel && (
        <div className="modal-overlay" style={{ zIndex: 1000 }}>
          <div className="modal" style={{ maxWidth: 420, textAlign: 'center', padding: 0, overflow: 'hidden' }}>
            <div style={{ background: 'var(--danger-dim)', borderBottom: '1px solid var(--danger)', padding: '24px 28px 20px' }}>
              <div style={{
                width: 52, height: 52, borderRadius: '50%', background: 'var(--danger)',
                margin: '0 auto 12px', display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <X size={22} color="#fff" />
              </div>
              <div style={{ fontSize: 17, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 6 }}>
                Cancelar pedido
              </div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                Estás a punto de cancelar el pedido<br />
                <span style={{ color: 'var(--accent)', fontWeight: 700, fontSize: 15 }}>{confirmCancel.numero}</span>
              </div>
            </div>
            <div style={{ padding: '16px 28px' }}>
              <div style={{
                background: 'var(--bg-hover)', borderRadius: 8, padding: '10px 14px',
                fontSize: 12, color: 'var(--text-muted)', marginBottom: 20,
                display: 'flex', alignItems: 'center', gap: 8,
              }}>
                <X size={14} color="var(--danger)" style={{ flexShrink: 0 }} />
                El pedido no se borra: queda en estado "cancelado". El inventario no cambia,
                porque la mercancía nunca llegó a entrar.
              </div>
              <div style={{ display: 'flex', gap: 10 }}>
                <button className="btn btn-ghost" style={{ flex: 1 }} onClick={() => setConfirmCancel(null)}>
                  Volver
                </button>
                <button className="btn btn-danger" style={{ flex: 1 }} onClick={confirmarCancelacion} disabled={accionando}>
                  <X size={14} /> {accionando ? 'Cancelando…' : 'Sí, cancelar'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

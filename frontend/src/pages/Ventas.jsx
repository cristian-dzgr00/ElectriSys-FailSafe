import { useEffect, useState, useRef } from 'react';
import { Plus, Search, X, Trash2, Eye } from 'lucide-react';
import Table from '../components/Table';
import Pagination from '../components/Pagination';
import { StatusBadge } from '../components/Tooltip';
import AsistenteFlotante from '../components/AsistenteFlotante';
import { useToastContext } from '../context/ToastContext';
import { ventasService, repuestosService, clientesService } from '../services/ventasService';

const fmt = n => new Intl.NumberFormat('es-CO',{style:'currency',currency:'COP',maximumFractionDigits:0}).format(n);
const estadoBadge = e => ({ completada:'badge-success', anulada:'badge-danger', pendiente:'badge-warning' }[e]||'badge-neutral');
const PAGE_SIZE = 15;

export default function Ventas() {
  const toast = useToastContext();

  const [ventas,    setVentas]    = useState([]);
  const [total,     setTotal]     = useState(0);
  const [page,      setPage]      = useState(1);
  const [loading,   setLoading]   = useState(true);
  const [q,         setQ]         = useState('');

  const [confirmAnular, setConfirmAnular] = useState(null);
  const [anulando,      setAnulando]      = useState(false);

  const [modal,     setModal]     = useState(false);
  const [detalle,   setDetalle]   = useState(null);
  const [repuestos, setRepuestos] = useState([]);
  const [clientes,  setClientes]  = useState([]);
  const [items,     setItems]     = useState([]);
  const [clienteId, setClienteId] = useState('');
  const [metodo,    setMetodo]    = useState('efectivo');
  const [notas,     setNotas]     = useState('');
  const [saving,    setSaving]    = useState(false);
  const [error,     setError]     = useState('');

  // Ref para acceder a page y q actuales sin stale closures
  const pageRef = useRef(page);
  const qRef    = useRef(q);
  useEffect(() => { pageRef.current = page; }, [page]);
  useEffect(() => { qRef.current = q; }, [q]);

  // Función de carga — siempre recibe p y search como argumentos explícitos
  const load = async (p, search) => {
    setLoading(true);
    try {
      const r = await ventasService.listar({ page: p, limit: PAGE_SIZE, q: search });
      console.log('[Ventas] API response:', r.data);
      const rows = r.data.data ?? r.data.rows ?? [];
      const totalCount = r.data.total ?? 0;
      setVentas(rows);
      setTotal(totalCount);
    } catch {
      toast('Error cargando ventas', { type: 'error' });
    } finally {
      setLoading(false);
    }
  };

  // Carga inicial
  useEffect(() => { load(1, ''); }, []);

  // Cuando cambia q: ir a página 1
  const prevQ = useRef('');
  useEffect(() => {
    if (q === prevQ.current) return;
    prevQ.current = q;
    setPage(1);
    load(1, q);
  }, [q]);

  // Cuando cambia page (por paginación)
  const prevPage = useRef(1);
  useEffect(() => {
    if (page === prevPage.current) return;
    prevPage.current = page;
    load(page, qRef.current);
  }, [page]);

  const openNew = async () => {
    setItems([]); setClienteId(''); setMetodo('efectivo'); setNotas(''); setError('');
    const [r, c] = await Promise.all([repuestosService.listar(), clientesService.listar()]);
    setRepuestos(r.data.data ?? []);
    setClientes(c.data.data ?? []);
    setModal('new');
  };

  const openDetalle = async (id) => {
    const r = await ventasService.buscar(id);
    setDetalle(r.data.data);
    setModal('detail');
  };

  const addItem = (repuesto_id) => {
    const rep = repuestos.find(r => r.id == repuesto_id);
    if (!rep) return;
    setItems(prev => {
      const idx = prev.findIndex(i => i.repuesto_id == repuesto_id);
      if (idx >= 0) {
        const copy = [...prev];
        copy[idx] = { ...copy[idx], cantidad: copy[idx].cantidad + 1 };
        return copy;
      }
      return [...prev, { repuesto_id: rep.id, nombre: rep.nombre, cantidad: 1, precio_unit: rep.precio_venta, descuento: 0 }];
    });
  };

  const removeItem = idx => setItems(p => p.filter((_, i) => i !== idx));

  const calcTotales = () => {
    const subtotal = items.reduce((s, i) => s + i.cantidad * i.precio_unit - (i.descuento||0), 0);
    const impuesto = subtotal * 0.19;
    return { subtotal, impuesto, total: subtotal + impuesto };
  };

  const guardarVenta = async () => {
    if (items.length === 0) { setError('Agrega al menos un producto'); return; }
    setSaving(true);
    const { subtotal, impuesto, total: totalVenta } = calcTotales();
    try {
      const r = await ventasService.crear({
        cliente_id: clienteId || null,
        metodo_pago: metodo,
        notas,
        items,
        subtotal,
        impuesto,
        total: totalVenta,
      });
      const num = r.data.numero || '';
      const enReplica = r.data.en_replica;
      setModal(false);
      // Si se guardó en réplica, esperar a que replique al primario
      if (enReplica) await new Promise(res => setTimeout(res, 1200));
      prevPage.current = 1;
      setPage(1);
      await load(1, qRef.current);
      toast(`Venta ${num} registrada exitosamente`, { type: 'success' });
    } catch(e) {
      setError(e.response?.data?.error || 'Error al registrar la venta');
    } finally {
      setSaving(false);
    }
  };

  const confirmarAnulacion = async () => {
    if (!confirmAnular || anulando) return;
    const { id, numero } = confirmAnular;
    setAnulando(true);
    setConfirmAnular(null);
    try {
      await ventasService.anular(id);
      await load(pageRef.current, qRef.current);
      toast(`Venta ${numero} anulada`, { type: 'warning' });
    } catch (e) {
      const msg = e.response?.data?.error || 'Error al anular la venta';
      toast(msg, { type: 'error' });
    } finally {
      setAnulando(false);
    }
  };

  const { subtotal, impuesto, total: totalModal } = calcTotales();

  const columns = [
    { key:'numero',          label:'N° Venta' },
    { key:'cliente_nombre',  label:'Cliente',  render: v => v || <span style={{color:'var(--text-muted)'}}>General</span> },
    { key:'vendedor_nombre', label:'Vendedor' },
    { key:'total',           label:'Total',    render: v => fmt(v) },
    { key:'metodo_pago',     label:'Pago',     render: v => <span className="badge badge-neutral" style={{textTransform:'capitalize'}}>{v}</span> },
    { key:'estado',          label:'Estado',   render: v => <StatusBadge status={v} className={`badge ${estadoBadge(v)}`} /> },
    { key:'creado_en',       label:'Fecha',    render: v => new Date(v).toLocaleString('es-CO',{dateStyle:'short',timeStyle:'short'}) },
    { key:'id', label:'', render:(_,r) => (
      <div style={{display:'flex',gap:6}}>
        <button className="btn-icon" onClick={()=>openDetalle(r.id)} title="Ver detalle"><Eye size={13}/></button>
        {r.estado==='completada' && (
          <button className="btn-icon" style={{color:'var(--danger)'}} title="Anular venta"
            onClick={()=>setConfirmAnular({ id: r.id, numero: r.numero })}>
            <X size={13}/>
          </button>
        )}
      </div>
    )},
  ];

  return (
    <>
      <div className="page-header">
        <div>
          <div className="page-title">Ventas</div>
          <div className="page-subtitle">{total} registros</div>
        </div>
        <button className="btn btn-primary" onClick={openNew}><Plus size={15}/> Nueva venta</button>
      </div>

      <div className="toolbar">
        <div className="search-bar">
          <Search size={14} className="search-icon"/>
          <input className="form-control" placeholder="Buscar por número de venta…" value={q} onChange={e=>setQ(e.target.value)}/>
        </div>
      </div>

      <div className="card" style={{padding:0,overflow:'hidden'}}>
        <Table columns={columns} data={ventas} loading={loading}/>
        <Pagination page={page} pageSize={PAGE_SIZE} total={total}
          onPrev={()=>setPage(p=>p-1)} onNext={()=>setPage(p=>p+1)} />
      </div>

      {/* Modal nueva venta */}
      {modal==='new' && (
        <div className="modal-overlay">
          <div className="modal modal-lg">
            <div className="modal-header">
              <div className="modal-title">Nueva venta</div>
              <button className="modal-close" onClick={()=>setModal(false)}><X size={18}/></button>
            </div>
            <div className="modal-body">
              {error && <div className="alert alert-error">{error}</div>}
              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Cliente</label>
                  <select className="form-control" value={clienteId} onChange={e=>setClienteId(e.target.value)}>
                    <option value="">Cliente general</option>
                    {clientes.map(c=><option key={c.id} value={c.id}>{c.nombre}</option>)}
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">Método de pago</label>
                  <select className="form-control" value={metodo} onChange={e=>setMetodo(e.target.value)}>
                    {['efectivo','tarjeta','transferencia','credito'].map(m=><option key={m} value={m} style={{textTransform:'capitalize'}}>{m}</option>)}
                  </select>
                </div>
              </div>
              <div className="form-group">
                <label className="form-label">Agregar producto</label>
                <select className="form-control" value="" onChange={e=>addItem(e.target.value)}>
                  <option value="">-- Selecciona un repuesto --</option>
                  {repuestos.map(r=><option key={r.id} value={r.id}>{r.nombre} — {fmt(r.precio_venta)} (stock: {r.stock})</option>)}
                </select>
              </div>
              {items.length > 0 && (
                <div className="card" style={{padding:0,overflow:'hidden',marginBottom:16}}>
                  <table style={{width:'100%',borderCollapse:'collapse'}}>
                    <thead>
                      <tr style={{background:'var(--bg-hover)'}}>
                        {['Producto','Cant.','Precio unit.','Subtotal',''].map(h=>(
                          <th key={h} style={{padding:'8px 12px',textAlign:h==='Cant.'?'center':h==='Precio unit.'||h==='Subtotal'?'right':'left',fontSize:11,color:'var(--text-secondary)'}}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {items.map((it,i)=>(
                        <tr key={i} style={{borderTop:'1px solid var(--border)'}}>
                          <td style={{padding:'8px 12px'}}>{it.nombre}</td>
                          <td style={{padding:'8px 12px',textAlign:'center'}}>
                            <input type="number" min={1}
                              style={{width:60,background:'var(--bg-input)',border:'1px solid var(--border)',borderRadius:6,color:'var(--text-primary)',textAlign:'center',padding:'4px 6px'}}
                              value={it.cantidad}
                              onChange={e=>{const c=[...items];c[i]={...c[i],cantidad:Math.max(1,+e.target.value)};setItems(c);}}
                            />
                          </td>
                          <td style={{padding:'8px 12px',textAlign:'right'}}>{fmt(it.precio_unit)}</td>
                          <td style={{padding:'8px 12px',textAlign:'right',fontWeight:600}}>{fmt(it.cantidad*it.precio_unit)}</td>
                          <td style={{padding:'8px 12px'}}>
                            <button className="btn-icon" style={{color:'var(--danger)'}} onClick={()=>removeItem(i)}><Trash2 size={13}/></button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <div style={{textAlign:'right',marginBottom:12}}>
                <div style={{color:'var(--text-secondary)',fontSize:13}}>Subtotal: <strong>{fmt(subtotal)}</strong></div>
                <div style={{color:'var(--text-secondary)',fontSize:13}}>IVA (19%): <strong>{fmt(impuesto)}</strong></div>
                <div style={{fontSize:18,fontWeight:700,color:'var(--accent)',marginTop:4}}>Total: {fmt(totalModal)}</div>
              </div>
              <div className="form-group">
                <label className="form-label">Notas</label>
                <input className="form-control" value={notas} onChange={e=>setNotas(e.target.value)} placeholder="Observaciones opcionales…"/>
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn btn-ghost" onClick={()=>setModal(false)}>Cancelar</button>
              <button className="btn btn-primary" onClick={guardarVenta} disabled={saving}>{saving?'Registrando…':'Registrar venta'}</button>
            </div>
          </div>
        </div>
      )}

      {/* Modal detalle */}
      {modal==='detail' && detalle && (
        <div className="modal-overlay" onClick={e=>e.target===e.currentTarget&&setModal(false)}>
          <div className="modal modal-lg">
            <div className="modal-header">
              <div className="modal-title">Venta {detalle.numero}</div>
              <button className="modal-close" onClick={()=>setModal(false)}><X size={18}/></button>
            </div>
            <div className="modal-body">
              <div className="form-row" style={{marginBottom:12}}>
                <div><span style={{color:'var(--text-muted)',fontSize:12}}>Cliente</span><br/><strong>{detalle.cliente_nombre||'General'}</strong></div>
                <div><span style={{color:'var(--text-muted)',fontSize:12}}>Vendedor</span><br/><strong>{detalle.vendedor_nombre}</strong></div>
                <div><span style={{color:'var(--text-muted)',fontSize:12}}>Estado</span><br/><StatusBadge status={detalle.estado} className={`badge ${estadoBadge(detalle.estado)}`}/></div>
                <div><span style={{color:'var(--text-muted)',fontSize:12}}>Pago</span><br/><strong style={{textTransform:'capitalize'}}>{detalle.metodo_pago}</strong></div>
              </div>
              <table style={{width:'100%',borderCollapse:'collapse'}}>
                <thead><tr style={{background:'var(--bg-hover)'}}>
                  {['Producto','Cant.','Precio unit.','Subtotal'].map(h=>(
                    <th key={h} style={{padding:'8px 12px',textAlign:h==='Cant.'?'center':h!=='Producto'?'right':'left',fontSize:11,color:'var(--text-secondary)'}}>{h}</th>
                  ))}
                </tr></thead>
                <tbody>
                  {detalle.detalle?.map((d,i)=>(
                    <tr key={i} style={{borderTop:'1px solid var(--border)'}}>
                      <td style={{padding:'8px 12px'}}>{d.producto_nombre}</td>
                      <td style={{padding:'8px 12px',textAlign:'center'}}>{d.cantidad}</td>
                      <td style={{padding:'8px 12px',textAlign:'right'}}>{fmt(d.precio_unit)}</td>
                      <td style={{padding:'8px 12px',textAlign:'right',fontWeight:600}}>{fmt(d.subtotal)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div style={{textAlign:'right',marginTop:12}}>
                <div style={{color:'var(--text-secondary)',fontSize:13}}>Subtotal: {fmt(detalle.subtotal)}</div>
                <div style={{color:'var(--text-secondary)',fontSize:13}}>IVA: {fmt(detalle.impuesto)}</div>
                <div style={{fontSize:18,fontWeight:700,color:'var(--accent)'}}>Total: {fmt(detalle.total)}</div>
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn btn-ghost" onClick={()=>setModal(false)}>Cerrar</button>
            </div>
          </div>
        </div>
      )}

      {/* Modal confirmación anulación */}
      {confirmAnular && (
        <div className="modal-overlay" style={{ zIndex: 1000 }}>
          <div className="modal" style={{ maxWidth: 420, textAlign: 'center', padding: 0, overflow: 'hidden' }}>
            <div style={{
              background: 'var(--danger-dim)',
              borderBottom: '1px solid var(--danger)',
              padding: '24px 28px 20px',
            }}>
              <div style={{
                width: 52, height: 52, borderRadius: '50%',
                background: 'var(--danger)', margin: '0 auto 12px',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <Trash2 size={22} color="#fff" />
              </div>
              <div style={{ fontSize: 17, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 6 }}>
                Anular venta
              </div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                Estás a punto de anular la venta<br/>
                <span style={{ color: 'var(--accent)', fontWeight: 700, fontSize: 15 }}>
                  {confirmAnular.numero}
                </span>
              </div>
            </div>
            <div style={{ padding: '16px 28px' }}>
              <div style={{
                background: 'var(--bg-hover)', borderRadius: 8, padding: '10px 14px',
                fontSize: 12, color: 'var(--text-muted)', marginBottom: 20,
                display: 'flex', alignItems: 'center', gap: 8,
              }}>
                <X size={14} color="var(--danger)" style={{ flexShrink: 0 }} />
                Esta acción no se puede deshacer y restaurará el stock de los productos.
              </div>
              <div style={{ display: 'flex', gap: 10 }}>
                <button className="btn btn-ghost" style={{ flex: 1 }} onClick={() => setConfirmAnular(null)}>
                  Cancelar
                </button>
                <button className="btn btn-danger" style={{ flex: 1 }} onClick={confirmarAnulacion} disabled={anulando}>
                  <Trash2 size={14} /> {anulando ? 'Anulando…' : 'Sí, anular'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      <AsistenteFlotante />
    </>
  );
}

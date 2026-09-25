import { useEffect, useState, useCallback } from 'react';
import { Plus, X, Trash2, Eye, ShoppingCart } from 'lucide-react';
import Table from '../components/Table';
import Pagination from '../components/Pagination';
import { StatusBadge } from '../components/Tooltip';
import AsistenteFlotante from '../components/AsistenteFlotante';
import BuscadorRepuesto from '../components/BuscadorRepuesto';
import { useToastContext } from '../context/ToastContext';
import api from '../services/api';
import { clientesService } from '../services/ventasService';

const fmt = n => new Intl.NumberFormat('es-CO',{style:'currency',currency:'COP',maximumFractionDigits:0}).format(n);
const estadoBadge = e => ({ activa:'badge-success', vencida:'badge-danger', realizada:'badge-accent' }[e]||'badge-neutral');
const PAGE_SIZE = 15;

export default function Cotizaciones() {
  const toast = useToastContext();

  const [data,      setData]      = useState([]);
  const [totalRegistros, setTotal] = useState(0);
  const [page,      setPage]      = useState(1);
  const [loading,   setLoading]   = useState(true);
  const [modal,     setModal]     = useState(false);
  const [detalle,   setDetalle]   = useState(null);
  // Cotización pendiente de confirmar como venta (null = sin confirmación abierta)
  const [confirmVenta, setConfirmVenta] = useState(null);
  const [vendiendo,    setVendiendo]    = useState(false);
  const [clientes,  setClientes]  = useState([]);
  const [items,     setItems]     = useState([]);
  const [clienteId, setClienteId] = useState('');
  const [vence,     setVence]     = useState('');
  const [notas,     setNotas]     = useState('');
  const [saving,    setSaving]    = useState(false);
  const [error,     setError]     = useState('');

  const load = useCallback(async (p = page) => {
    setLoading(true);
    try {
      const r = await api.get('/cotizaciones', { params: { page: p, limit: PAGE_SIZE } });
      setData(r.data.data ?? []);
      setTotal(r.data.total ?? 0);
    } catch { toast('Error cargando cotizaciones', { type:'error' }); }
    finally  { setLoading(false); }
  }, [page]);

  useEffect(() => { load(page); }, [page]);

  const openNew = async () => {
    setItems([]); setClienteId(''); setVence(''); setNotas(''); setError('');
    const c = await clientesService.listar();
    setClientes(c.data.data ?? []);
    setModal('new');
  };

  // Abre "Nueva cotización" ya con un producto cargado — lo usa el botón
  // "Agregar producto" de las sugerencias del asistente de repuestos.
  const abrirNuevaCotizacionConProducto = async (producto) => {
    await openNew();
    addItem(producto);
  };

  const openDetalle = async (id) => {
    try {
      const r = await api.get(`/cotizaciones/${id}`);
      setDetalle(r.data.data);
      setModal('detail');
    } catch { toast('Error al cargar el detalle de la cotización', { type:'error' }); }
  };

  const addItem = (rep) => {
    setItems(prev => {
      const idx = prev.findIndex(i => i.repuesto_id === rep.id);
      if (idx >= 0) {
        const c = [...prev]; c[idx] = {...c[idx], cantidad: c[idx].cantidad + 1}; return c;
      }
      return [...prev, {repuesto_id: rep.id, nombre: rep.nombre, cantidad: 1, precio_unit: rep.precio_venta}];
    });
  };

  const removeItem = i => setItems(p => p.filter((_,x) => x !== i));

  const calcTotales = () => {
    const subtotal = items.reduce((s,i) => s + i.cantidad * i.precio_unit, 0);
    const impuesto = subtotal * 0.19;
    return { subtotal, impuesto, total: subtotal + impuesto };
  };

  const guardar = async () => {
    if (items.length === 0) { setError('Agrega al menos un producto a la cotización'); return; }
    if (vence && new Date(vence) < new Date()) { setError('La fecha de vencimiento no puede ser en el pasado'); return; }
    setSaving(true);
    const { subtotal, impuesto, total } = calcTotales();
    try {
      const r = await api.post('/cotizaciones', {
        cliente_id: clienteId || null, vence_en: vence || null,
        notas, items, subtotal, impuesto, total
      });
      const num = r.data.data?.numero || '';
      setModal(false);
      load(page);
      toast(`Cotización ${num} creada exitosamente`, { type:'success' });
    } catch(e) { setError(e.response?.data?.error || 'Error al crear la cotización'); }
    finally { setSaving(false); }
  };

  const cambiarEstado = async (id, estado) => {
    // "Realizada" no es un cambio de estado cualquiera: implica vender, con
    // su descuento de stock y su factura. Se pide confirmación antes, y el
    // trabajo real lo hace confirmarVenta().
    if (estado === 'realizada') { setConfirmVenta(detalle); return; }
    try {
      await api.put(`/cotizaciones/${id}/estado`, { estado });
      load(page);
      if (detalle) setDetalle(prev => ({...prev, estado}));
      toast(`Estado cambiado a "${ESTADO_LABEL[estado] ?? estado}"`, { type:'success' });
    } catch (e) {
      toast(e.response?.data?.error || 'No se pudo cambiar el estado', { type:'error' });
    }
  };

  // Convierte la cotización en venta. El backend valida el stock y registra
  // la factura con los precios COTIZADOS, no con los de hoy.
  const confirmarVenta = async () => {
    if (!confirmVenta || vendiendo) return;
    setVendiendo(true);
    try {
      const r = await api.post(`/cotizaciones/${confirmVenta.id}/convertir-venta`);
      setConfirmVenta(null);
      setDetalle(prev => prev ? {...prev, estado:'realizada'} : prev);
      load(page);
      toast(r.data.mensaje || 'Venta registrada', { type:'success' });
    } catch (e) {
      // Cancelar el modal dejaría al usuario sin saber por qué falló (stock
      // insuficiente, cotización vencida): se cierra y se explica en el toast.
      setConfirmVenta(null);
      toast(e.response?.data?.error || 'No se pudo registrar la venta', { type:'error' });
    } finally {
      setVendiendo(false);
    }
  };

  const { subtotal, impuesto, total } = calcTotales();

  const ESTADOS = ['activa','vencida','realizada'];
  const ESTADO_LABEL = {
    activa:    'Cotización activa',
    vencida:   'Cotización vencida',
    realizada: 'Cotización realizada',
  };
  const ESTADO_DESC = {
    activa:    'Los precios cotizados siguen vigentes',
    vencida:   'Cambió el precio de algún repuesto: ya no se puede sostener este total',
    realizada: 'Se convirtió en venta y quedó en el historial',
  };

  const columns = [
    { key:'numero',         label:'Nº Cotización' },
    { key:'cliente_nombre', label:'Cliente', render: v => v || <span style={{color:'var(--text-muted)'}}>General</span> },
    { key:'total',          label:'Total',   render: v => fmt(v) },
    { key:'estado',         label:'Estado',  render: v => <StatusBadge status={v} className={`badge ${estadoBadge(v)}`}/> },
    { key:'vence_en',       label:'Vence',   render: v => {
      if (!v) return '—';
      const d = new Date(v);
      const vencida = d < new Date();
      return <span style={{color: vencida ? 'var(--danger)' : 'inherit'}}>{d.toLocaleDateString('es-CO')}</span>;
    }},
    { key:'creado_en',      label:'Creada',  render: v => new Date(v).toLocaleDateString('es-CO') },
    { key:'id', label:'', render: (_,r) => (
      <button className="btn-icon" title="Ver detalle" onClick={() => openDetalle(r.id)}><Eye size={13}/></button>
    )},
  ];

  return (
    <>
      <div className="page-header">
        <div>
          <div className="page-title">Cotizaciones</div>
          <div className="page-subtitle">{totalRegistros} cotizaciones</div>
        </div>
        <button className="btn btn-primary" onClick={openNew}><Plus size={15}/> Nueva cotización</button>
      </div>

      <div className="card" style={{padding:0,overflow:'hidden'}}>
        <Table columns={columns} data={data} loading={loading}/>
        <Pagination page={page} pageSize={PAGE_SIZE} total={totalRegistros} onPrev={()=>setPage(p=>p-1)} onNext={()=>setPage(p=>p+1)}/>
      </div>

      {/* Modal nueva cotización */}
      {modal === 'new' && (
        <div className="modal-overlay">
          <div className="modal modal-lg">
            <div className="modal-header">
              <div className="modal-title">Nueva cotización</div>
              <button className="modal-close" onClick={() => setModal(false)}><X size={18}/></button>
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
                  <label className="form-label">Fecha de vencimiento <span style={{color:'var(--text-muted)',fontSize:11}}>(opcional)</span></label>
                  <input type="date" className="form-control" value={vence}
                    min={new Date().toISOString().split('T')[0]}
                    onChange={e=>setVence(e.target.value)}/>
                </div>
              </div>
              <div className="form-group">
                <label className="form-label">Agregar producto</label>
                <BuscadorRepuesto onSeleccionar={addItem} />
              </div>
              {items.length > 0 && (
                <div className="card" style={{padding:0,overflow:'hidden',marginBottom:16}}>
                  <table style={{width:'100%',borderCollapse:'collapse'}}>
                    <thead><tr style={{background:'var(--bg-hover)'}}>
                      {['Producto','Cant.','Precio','Subtotal',''].map(h=>(
                        <th key={h} style={{padding:'8px 12px',textAlign:h==='Cant.'?'center':h==='Precio'||h==='Subtotal'?'right':'left',fontSize:11,color:'var(--text-secondary)'}}>{h}</th>
                      ))}
                    </tr></thead>
                    <tbody>
                      {items.map((it,i)=>(
                        <tr key={i} style={{borderTop:'1px solid var(--border)'}}>
                          <td style={{padding:'8px 12px'}}>{it.nombre}</td>
                          <td style={{padding:'8px 12px',textAlign:'center'}}>
                            <input type="number" min={1} value={it.cantidad}
                              style={{width:60,background:'var(--bg-input)',border:'1px solid var(--border)',borderRadius:6,color:'var(--text-primary)',textAlign:'center',padding:'4px 6px'}}
                              onChange={e=>{const c=[...items];c[i]={...c[i],cantidad:Math.max(1,+e.target.value)};setItems(c);}}/>
                          </td>
                          <td style={{padding:'8px 12px',textAlign:'right'}}>{fmt(it.precio_unit)}</td>
                          <td style={{padding:'8px 12px',textAlign:'right',fontWeight:600}}>{fmt(it.cantidad*it.precio_unit)}</td>
                          <td style={{padding:'8px 12px'}}><button className="btn-icon" style={{color:'var(--danger)'}} onClick={()=>removeItem(i)}><Trash2 size={13}/></button></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <div style={{textAlign:'right',marginBottom:12}}>
                <div style={{color:'var(--text-secondary)',fontSize:13}}>Subtotal: <strong>{fmt(subtotal)}</strong></div>
                <div style={{color:'var(--text-secondary)',fontSize:13}}>IVA (19%): <strong>{fmt(impuesto)}</strong></div>
                <div style={{fontSize:18,fontWeight:700,color:'var(--accent)'}}>Total: {fmt(total)}</div>
              </div>
              <div className="form-group">
                <label className="form-label">Notas / Términos</label>
                <input className="form-control" value={notas} onChange={e=>setNotas(e.target.value)} placeholder="Términos, condiciones, observaciones…"/>
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn btn-ghost" onClick={()=>setModal(false)}>Cancelar</button>
              <button className="btn btn-primary" onClick={guardar} disabled={saving}>{saving?'Creando…':'Crear cotización'}</button>
            </div>
          </div>
        </div>
      )}

      {/* Modal detalle */}
      {modal === 'detail' && detalle && (
        <div className="modal-overlay" onClick={e=>e.target===e.currentTarget&&setModal(false)}>
          <div className="modal modal-lg">
            <div className="modal-header">
              <div className="modal-title">Cotización {detalle.numero}</div>
              <button className="modal-close" onClick={()=>setModal(false)}><X size={18}/></button>
            </div>
            <div className="modal-body">
              <div className="form-row" style={{marginBottom:16}}>
                <div><span style={{color:'var(--text-muted)',fontSize:12}}>Cliente</span><br/><strong>{detalle.cliente_nombre||'General'}</strong></div>
                <div><span style={{color:'var(--text-muted)',fontSize:12}}>Vendedor</span><br/><strong>{detalle.vendedor_nombre}</strong></div>
                <div><span style={{color:'var(--text-muted)',fontSize:12}}>Estado</span><br/><StatusBadge status={detalle.estado} className={`badge ${estadoBadge(detalle.estado)}`}/></div>
                <div><span style={{color:'var(--text-muted)',fontSize:12}}>Vence</span><br/><strong>{detalle.vence_en?new Date(detalle.vence_en).toLocaleDateString('es-CO'):'—'}</strong></div>
              </div>
              <div className="form-group">
                <label className="form-label">Cambiar estado</label>
                <div style={{display:'flex',gap:8,flexWrap:'wrap'}}>
                  {ESTADOS.map(e=>(
                    <button key={e} title={ESTADO_DESC[e]}
                      className={`btn btn-sm ${detalle.estado===e?'btn-primary':'btn-ghost'}`}
                      // Una cotización vencida o ya vendida no vuelve atrás:
                      // sus botones quedan inertes en vez de fallar con un 409.
                      disabled={detalle.estado==='realizada' || (detalle.estado==='vencida' && e!=='vencida')}
                      onClick={()=>cambiarEstado(detalle.id,e)}>
                      {ESTADO_LABEL[e]}
                    </button>
                  ))}
                </div>
                <div style={{fontSize:11,color:'var(--text-muted)',marginTop:6}}>
                  {ESTADO_DESC[detalle.estado]}
                </div>
              </div>
              <table style={{width:'100%',borderCollapse:'collapse',marginTop:8}}>
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
                <div style={{color:'var(--text-secondary)',fontSize:13}}>IVA (19%): {fmt(detalle.impuesto)}</div>
                <div style={{fontSize:18,fontWeight:700,color:'var(--accent)'}}>Total: {fmt(detalle.total)}</div>
              </div>
              {detalle.notas && (
                <div style={{marginTop:12,padding:'10px 14px',background:'var(--bg-hover)',borderRadius:8,fontSize:13,color:'var(--text-secondary)'}}>
                  <strong>Notas:</strong> {detalle.notas}
                </div>
              )}
            </div>
            <div className="modal-footer">
              <button className="btn btn-ghost" onClick={()=>setModal(false)}>Cerrar</button>
            </div>
          </div>
        </div>
      )}

      {/* Confirmación antes de convertir la cotización en venta.
          Va por encima del modal de detalle (zIndex mayor): si el usuario
          cancela, vuelve a ver la cotización tal como estaba. */}
      {confirmVenta && (
        <div className="modal-overlay" style={{zIndex:1000}}>
          <div className="modal" style={{maxWidth:440,padding:0,overflow:'hidden'}}>
            <div style={{background:'var(--accent-dim)',borderBottom:'1px solid var(--accent)',padding:'24px 28px 20px',textAlign:'center'}}>
              <div style={{width:52,height:52,borderRadius:'50%',background:'var(--accent)',margin:'0 auto 12px',display:'flex',alignItems:'center',justifyContent:'center'}}>
                <ShoppingCart size={22} color="#121212"/>
              </div>
              <div style={{fontSize:17,fontWeight:700,color:'var(--text-primary)',marginBottom:6}}>
                ¿Vas a realizar la venta de esta cotización?
              </div>
              <div style={{fontSize:13,color:'var(--text-secondary)',lineHeight:1.5}}>
                Cotización <span style={{color:'var(--accent)',fontWeight:700}}>{confirmVenta.numero}</span>
                {confirmVenta.cliente_nombre ? <> para <strong>{confirmVenta.cliente_nombre}</strong></> : null}
                <br/>
                <span style={{fontSize:15,fontWeight:700,color:'var(--text-primary)'}}>{fmt(confirmVenta.total)}</span>
              </div>
            </div>
            <div style={{padding:'16px 28px'}}>
              <div style={{background:'var(--bg-hover)',borderRadius:8,padding:'10px 14px',fontSize:12,color:'var(--text-muted)',marginBottom:20,lineHeight:1.6}}>
                Al confirmar se registra la venta en el historial, se descuenta el stock
                de los productos y la cotización queda marcada como realizada.
                Se cobran los precios cotizados, no los actuales.
              </div>
              <div style={{display:'flex',gap:10}}>
                <button className="btn btn-ghost" style={{flex:1}} onClick={()=>setConfirmVenta(null)} disabled={vendiendo}>
                  Cancelar
                </button>
                <button className="btn btn-primary" style={{flex:1}} onClick={confirmarVenta} disabled={vendiendo}>
                  <ShoppingCart size={14}/> {vendiendo ? 'Registrando…' : 'Confirmar venta'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      <AsistenteFlotante onAgregarProducto={abrirNuevaCotizacionConProducto} />
    </>
  );
}
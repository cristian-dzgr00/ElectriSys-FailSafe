import { useEffect, useState, useCallback, useRef } from 'react';
import { Plus, Search, Edit2, Trash2, X, Tag, AlertTriangle, Car, Wifi, WifiOff, Sparkles, ArrowRight } from 'lucide-react';
import Table from '../components/Table';
import Pagination from '../components/Pagination';
import { useToastContext } from '../context/ToastContext';
import { repuestosService } from '../services/ventasService';
import { vehiculosService } from '../services/vehiculosService';
import api from '../services/api';
import { useWebSocket } from '../hooks/useWebSocket';

const HIGHLIGHT_MS = 2500;

// Señal de reabastecimiento que devuelve el microservicio (promedio móvil
// sobre ventas reales, ver nlp-service/app/demanda/forecast.py). Los
// umbrales viven allá; acá solo se traduce a color y texto.
// Señales que SÍ se pintan en la tabla. 'normal' y 'sin_datos' quedan
// fuera a propósito: un badge en cada fila deja de ser una señal y pasa a
// ser ruido; solo se marca lo que pide una decisión de compra.
const SENAL_TABLA = {
  reabastecer:   { clase: 'badge-danger',  texto: 'Reabastecer pronto',
                   tip: 'Al ritmo de venta de las últimas semanas, el stock se agota pronto.' },
  rotacion_baja: { clase: 'badge-warning', texto: 'Rotación baja',
                   tip: 'Hay inventario para mucho tiempo: capital parado.' },
};

const SENAL_DEMANDA = {
  reabastecer:   { clase: 'badge-danger',  texto: 'Reabastecer pronto' },
  rotacion_baja: { clase: 'badge-warning', texto: 'Rotación baja' },
  normal:        { clase: 'badge-success', texto: 'Rotación normal' },
  sin_datos:     { clase: 'badge-neutral', texto: 'Sin historial de ventas' },
};

const fmt = n => new Intl.NumberFormat('es-CO',{style:'currency',currency:'COP',maximumFractionDigits:0}).format(n);
const EMPTY = { nombre:'', codigo:'', descripcion:'', categoria_id:'', proveedor_id:'', precio_compra:0, precio_venta:0, stock:0, stock_minimo:5 };
const EMPTY_CAT = { nombre:'' };
const EMPTY_VEH = { marca:'', modelo:'', anio_desde:'', anio_hasta:'', motor:'', combustible:'gasolina' };
const COMBUSTIBLES = ['gasolina','diesel','hibrido','electrico','gas'];
const PAGE_SIZE = 15;
const soloPositivo = v => { const l=String(v).replace(/[^\d]/g,''); return l===''?'':String(parseInt(l,10)); };

export default function Repuestos() {
  const toast = useToastContext();

  const [data,        setData]        = useState([]);
  const [total,       setTotal]       = useState(0);
  const [page,        setPage]        = useState(1);
  const [categorias,  setCategorias]  = useState([]);
  const [proveedores, setProveedores] = useState([]);
  const [loading,     setLoading]     = useState(true);
  const [q,           setQ]           = useState('');
  const [modal,       setModal]       = useState(false);
  const [modalCat,    setModalCat]    = useState(false);
  const [form,        setForm]        = useState(EMPTY);
  const [formCat,     setFormCat]     = useState(EMPTY_CAT);
  const [editing,     setEditing]     = useState(null);
  const [editingCat,  setEditingCat]  = useState(null);
  const [saving,      setSaving]      = useState(false);
  const [savingCat,   setSavingCat]   = useState(false);
  const [error,       setError]       = useState('');
  const [errorCat,    setErrorCat]    = useState('');
  const [confirmDlg,  setConfirmDlg]  = useState(null);

  // ── Stock en tiempo real (WebSocket) ──
  const [highlights, setHighlights] = useState({}); // { [repuesto_id]: 'up' | 'down' }
  const dataRef = useRef(data);
  const highlightTimers = useRef({});

  // ── Sugerencias de IA (microservicio propio: TF-IDF + coseno) ──
  const [senales,         setSenales]         = useState({});   // { [id]: 'reabastecer' | ... }
  const [sugerencias,     setSugerencias]     = useState([]);
  const [demanda,         setDemanda]         = useState(null);
  const [cargandoSug,     setCargandoSug]     = useState(false);
  const [sugDisponibles,  setSugDisponibles]  = useState(true);

  // ── Compatibilidad de vehículos (asistente NLP) ──
  const [compatibilidades, setCompatibilidades] = useState([]);
  const [marcas,           setMarcas]           = useState([]);
  const [modelos,          setModelos]          = useState([]);
  const [nuevoVeh,         setNuevoVeh]         = useState(EMPTY_VEH);
  const [savingCompat,     setSavingCompat]     = useState(false);
  const [errorCompat,      setErrorCompat]      = useState('');

  const loadCats = async () => {
    const r = await api.get('/categorias');
    setCategorias(r.data.data || []);
  };

  const load = useCallback(async (p = page, search = q) => {
    setLoading(true);
    try {
      const r = await repuestosService.listar(search ? { q: search, page: p, limit: PAGE_SIZE } : { page: p, limit: PAGE_SIZE });
      const filas = r.data.data ?? [];
      setData(filas);
      setTotal(r.data.total ?? 0);
      // Sin await: la tabla se pinta ya, y los badges aparecen cuando el
      // microservicio conteste. Si nunca contesta, la tabla queda igual.
      cargarSenales(filas.map(f => f.id));
    } catch { toast('Error cargando repuestos', { type: 'error' }); }
    finally { setLoading(false); }
  }, [page, q]);

  // Una sola llamada para toda la página, no una por fila: el backend
  // agrupa las N series en una consulta y el microservicio hace la
  // aritmética en memoria. Cualquier fallo se traga en silencio — esto
  // decora la tabla, no la sostiene.
  const cargarSenales = async (ids) => {
    if (!ids.length) { setSenales({}); return; }
    try {
      const r = await repuestosService.senalesDemanda(ids);
      const mapa = {};
      (r.data.data ?? []).forEach(s => { mapa[s.repuesto_id] = s.senal; });
      setSenales(mapa);
    } catch {
      setSenales({});
    }
  };

  useEffect(() => {
    load(); loadCats();
    api.get('/proveedores').then(r=>setProveedores(r.data.data||[])).catch(()=>{});
    vehiculosService.marcas().then(r=>setMarcas(r.data.data||[])).catch(()=>{});
  }, []);
  useEffect(() => { load(1, q); setPage(1); }, [q]);
  useEffect(() => { load(page, q); }, [page]);

  useEffect(() => { dataRef.current = data; }, [data]);
  useEffect(() => () => {
    Object.values(highlightTimers.current).forEach(clearTimeout);
  }, []);

  // dataRef (no `data`) evita que el callback cambie de referencia en cada
  // venta y reconecte el WebSocket: useWebSocket vuelve a abrir la conexión
  // cuando cambia el callback que recibe.
  const handleWsMessage = useCallback((event) => {
    if (event.type !== 'stock_actualizado') return;
    const items = event.items || {};

    const cambios = {};
    dataRef.current.forEach(r => {
      const key = String(r.id);
      if (!(key in items)) return;
      const nuevoStock = Number(items[key]);
      if (nuevoStock !== r.stock) cambios[r.id] = nuevoStock > r.stock ? 'up' : 'down';
    });
    if (Object.keys(cambios).length === 0) return;

    setData(prev => prev.map(r => {
      const key = String(r.id);
      return key in items ? { ...r, stock: Number(items[key]) } : r;
    }));

    setHighlights(h => ({ ...h, ...cambios }));
    Object.keys(cambios).forEach(id => {
      clearTimeout(highlightTimers.current[id]);
      highlightTimers.current[id] = setTimeout(() => {
        setHighlights(h => {
          const next = { ...h };
          delete next[id];
          return next;
        });
      }, HIGHLIGHT_MS);
    });
  }, []);

  const { connected: wsConnected } = useWebSocket(handleWsMessage);

  const loadCompatibilidad = async (repuestoId) => {
    try {
      const r = await repuestosService.listarCompatibilidad(repuestoId);
      setCompatibilidades(r.data.data ?? []);
    } catch { setCompatibilidades([]); }
  };

  const cargarModelos = async (marca) => {
    if (!marca.trim()) { setModelos([]); return; }
    try {
      const r = await vehiculosService.modelos(marca.trim());
      setModelos(r.data.data ?? []);
    } catch { setModelos([]); }
  };

  // El microservicio de NLP es opcional por diseño: si no responde, el
  // backend contesta 200 con disponible:false y acá solo se oculta la
  // sección. Nunca se propaga el error al resto del modal.
  const cargarSugerencias = async (repuestoId) => {
    setCargandoSug(true);
    setSugerencias([]); setDemanda(null); setSugDisponibles(true);
    try {
      const r = await repuestosService.recomendaciones(repuestoId);
      setSugerencias(r.data.data?.recomendaciones ?? []);
      setDemanda(r.data.data?.demanda ?? null);
      setSugDisponibles(r.data.disponible !== false);
    } catch {
      setSugDisponibles(false);
    } finally {
      setCargandoSug(false);
    }
  };

  // Abre otro repuesto desde la lista de sugerencias sin cerrar el flujo:
  // se recarga la fila completa porque la sugerencia solo trae lo que hace
  // falta para mostrarla (id, nombre, stock, precio), no el registro entero.
  const abrirSugerido = async (repuestoId) => {
    try {
      const r = await repuestosService.buscar(repuestoId);
      openEdit(r.data.data);
    } catch {
      toast('No se pudo abrir el producto sugerido', { type: 'error' });
    }
  };

  const openNew  = () => {
    setForm(EMPTY); setEditing(null); setError(''); setModal(true);
    setCompatibilidades([]); setNuevoVeh(EMPTY_VEH); setErrorCompat('');
    setSugerencias([]); setDemanda(null); setSugDisponibles(true);
  };
  const openEdit = row => {
    setForm({...row}); setEditing(row.id); setError(''); setModal(true);
    setNuevoVeh(EMPTY_VEH); setErrorCompat('');
    loadCompatibilidad(row.id);
    cargarSugerencias(row.id);
  };
  const closeModal = () => { setModal(false); setError(''); };

  const agregarCompat = async () => {
    const v = nuevoVeh;
    if (!v.marca.trim() || !v.modelo.trim()) { setErrorCompat('Marca y modelo son obligatorios'); return; }
    if (!v.anio_desde || !v.anio_hasta) { setErrorCompat('Año desde y año hasta son obligatorios'); return; }
    if (Number(v.anio_hasta) < Number(v.anio_desde)) { setErrorCompat('El año hasta no puede ser menor al año desde'); return; }
    setSavingCompat(true); setErrorCompat('');
    try {
      await repuestosService.agregarCompatibilidad(editing, {
        marca: v.marca.trim(),
        modelo: v.modelo.trim(),
        anio_desde: Number(v.anio_desde),
        anio_hasta: Number(v.anio_hasta),
        motor: v.motor.trim() || undefined,
        combustible: v.combustible,
      });
      toast('Compatibilidad agregada', { type: 'success' });
      setNuevoVeh(EMPTY_VEH);
      loadCompatibilidad(editing);
      vehiculosService.marcas().then(r=>setMarcas(r.data.data||[])).catch(()=>{}); // por si se creó marca nueva
    } catch(e) {
      setErrorCompat(e.response?.data?.error || 'Error al agregar la compatibilidad');
    } finally {
      setSavingCompat(false);
    }
  };

  const quitarCompat = async (vehiculoId) => {
    try {
      await repuestosService.quitarCompatibilidad(editing, vehiculoId);
      setCompatibilidades(prev => prev.filter(v => v.id !== vehiculoId));
      toast('Compatibilidad quitada', { type: 'warning' });
    } catch {
      toast('No se pudo quitar la compatibilidad', { type: 'error' });
    }
  };

  const handleSave = async () => {
    if (!form.nombre) { setError('El nombre es obligatorio'); return; }
    if (!form.precio_venta || Number(form.precio_venta) <= 0) { setError('El precio de venta debe ser mayor a $0'); return; }
    if (Number(form.precio_compra) < 0) { setError('El precio de compra no puede ser negativo'); return; }
    if (Number(form.stock) < 0) { setError('El stock no puede ser negativo'); return; }
    setSaving(true);
    try {
      if (editing) {
        await repuestosService.actualizar(editing, form);
        toast(`Repuesto "${form.nombre}" actualizado`, { type: 'success' });
      } else {
        await repuestosService.crear(form);
        toast(`Repuesto "${form.nombre}" creado exitosamente`, { type: 'success' });
      }
      closeModal(); load(page, q);
    } catch(e) { setError(e.response?.data?.error || 'Error al guardar el repuesto'); }
    finally { setSaving(false); }
  };

  // Reemplaza window.confirm() con modal propio
  const askConfirm = (message) => new Promise(resolve =>
    setConfirmDlg({
      message,
      onConfirm: () => { setConfirmDlg(null); resolve(true); },
      onCancel:  () => { setConfirmDlg(null); resolve(false); },
    })
  );

  const handleDelete = async (id, nombre) => {
    const ok = await askConfirm(`¿Eliminar el repuesto "${nombre}"? Esta acción no se puede deshacer.`);
    if (!ok) return;
    try {
      await repuestosService.eliminar(id);
      load(page, q);
      toast(`Repuesto "${nombre}" eliminado`, { type: 'warning' });
    } catch { toast('No se pudo eliminar el repuesto', { type: 'error' }); }
  };

  const openCats    = () => { setFormCat(EMPTY_CAT); setEditingCat(null); setErrorCat(''); setModalCat(true); };
  const openEditCat = cat => { setFormCat({nombre:cat.nombre}); setEditingCat(cat.id); setErrorCat(''); };
  const closeCats   = () => { setModalCat(false); setErrorCat(''); setEditingCat(null); setFormCat(EMPTY_CAT); };

  const saveCat = async () => {
    if (!formCat.nombre) { setErrorCat('El nombre es obligatorio'); return; }
    setSavingCat(true);
    try {
      if (editingCat) { await api.put(`/categorias/${editingCat}`, formCat); toast('Categoría actualizada', { type:'success' }); }
      else            { await api.post('/categorias', formCat); toast(`Categoría "${formCat.nombre}" creada`, { type:'success' }); }
      setFormCat(EMPTY_CAT); setEditingCat(null); setErrorCat(''); loadCats();
    } catch(e) { setErrorCat(e.response?.data?.error || 'Error'); }
    finally { setSavingCat(false); }
  };

  const deleteCat = async (id, nombre) => {
    const ok = await askConfirm(`¿Eliminar la categoría "${nombre}"?`);
    if (!ok) return;
    try { await api.delete(`/categorias/${id}`); loadCats(); toast(`Categoría "${nombre}" eliminada`, { type:'warning' }); }
    catch { toast('No se pudo eliminar (puede tener repuestos asociados)', { type:'error' }); }
  };

  const f = (k, v) => setForm(p => ({...p, [k]: v}));
  const numInput = (key) => ({
    type:'text', inputMode:'numeric', className:'form-control',
    value: form[key],
    onChange: e => f(key, soloPositivo(e.target.value)),
    onKeyDown: e => { if(['-','e','+'].includes(e.key)) e.preventDefault(); },
    onPaste: e => { e.preventDefault(); f(key, soloPositivo(e.clipboardData.getData('text'))); },
  });

  const columns = [
    { key:'codigo',        label:'Código' },
    { key:'nombre',        label:'Producto/Repuesto', render:(v, r) => {
      const meta = SENAL_TABLA[senales[r.id]];
      if (!meta) return v;
      return (
        <span style={{display:'inline-flex',alignItems:'center',gap:6,flexWrap:'wrap'}}>
          {v}
          <span className={`badge ${meta.clase}`} style={{fontSize:10}} title={meta.tip}>
            {meta.texto}
          </span>
        </span>
      );
    }},
    { key:'categoria',     label:'Categoría' },
    { key:'stock',         label:'Stock', render:(v,r) => {
      const hl = highlights[r.id];
      return (
        <span
          className={`badge ${v <= r.stock_minimo ? 'badge-danger' : 'badge-success'}`}
          title={v <= r.stock_minimo ? 'Stock bajo — reponer pronto' : 'Stock normal'}
          style={hl ? {
            outline: `2px solid ${hl === 'up' ? 'var(--success)' : 'var(--danger)'}`,
            outlineOffset: 2,
            transition: `outline-color ${HIGHLIGHT_MS}ms ease`,
          } : undefined}
        >
          {v}
        </span>
      );
    }},
    { key:'precio_venta',  label:'Precio venta',  render: v => fmt(v) },
    { key:'precio_compra', label:'Precio compra', render: v => fmt(v) },
    { key:'id', label:'Acciones', render:(_,r) => (
      <div style={{display:'flex',gap:6}}>
        <button className="btn-icon" onClick={()=>openEdit(r)} title="Editar repuesto"><Edit2 size={13}/></button>
        <button className="btn-icon" style={{color:'var(--danger)'}} title="Eliminar repuesto" onClick={()=>handleDelete(r.id,r.nombre)}><Trash2 size={13}/></button>
      </div>
    )},
  ];

  return (
    <>
      <div className="page-header">
        <div>
          <div className="page-title">Repuestos</div>
          <div className="page-subtitle" style={{display:'flex',alignItems:'center',gap:8}}>
            {total} productos en inventario
            <span
              title={wsConnected ? 'Tiempo real activo' : 'Sin conexión en tiempo real — el stock no se actualiza solo, recargá la página'}
              style={{display:'inline-flex',alignItems:'center',gap:4,fontSize:11,color: wsConnected ? 'var(--success)' : 'var(--text-muted)'}}
            >
              {wsConnected ? <Wifi size={12}/> : <WifiOff size={12}/>} {wsConnected ? 'En vivo' : 'Offline'}
            </span>
          </div>
        </div>
        <div style={{display:'flex',gap:10}}>
          <button className="btn btn-ghost" onClick={openCats}><Tag size={15}/> Categorías</button>
          <button className="btn btn-primary" onClick={openNew}><Plus size={15}/> Nuevo repuesto</button>
        </div>
      </div>

      <div className="toolbar">
        <div className="search-bar">
          <Search size={14} className="search-icon"/>
          <input className="form-control" placeholder="Buscar por nombre o código…" value={q} onChange={e=>setQ(e.target.value)}/>
        </div>
      </div>

      <div className="card" style={{padding:0,overflow:'hidden'}}>
        <Table columns={columns} data={data} loading={loading} emptyText="No se encontraron repuestos"/>
        <Pagination page={page} pageSize={PAGE_SIZE} total={total} onPrev={()=>setPage(p=>p-1)} onNext={()=>setPage(p=>p+1)}/>
      </div>

      {/* Modal repuesto */}
      {modal && (
        <div className="modal-overlay" onClick={e=>e.target===e.currentTarget&&closeModal()}>
          <div className="modal">
            <div className="modal-header">
              <div className="modal-title">{editing?'Editar repuesto':'Nuevo repuesto'}</div>
              <button className="modal-close" onClick={closeModal}><X size={18}/></button>
            </div>
            <div className="modal-body">
              {error && <div className="alert alert-error">{error}</div>}
              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Nombre *</label>
                  <input className="form-control" value={form.nombre} onChange={e=>f('nombre',e.target.value)}/>
                </div>
                <div className="form-group">
                  <label className="form-label">Código</label>
                  <input className="form-control" value={form.codigo} onChange={e=>f('codigo',e.target.value)}/>
                </div>
              </div>
              <div className="form-group">
                <label className="form-label">Descripción</label>
                <input className="form-control" value={form.descripcion} onChange={e=>f('descripcion',e.target.value)}/>
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Categoría</label>
                  <select className="form-control" value={form.categoria_id} onChange={e=>f('categoria_id',e.target.value)}>
                    <option value="">-- Seleccionar --</option>
                    {categorias.map(c=><option key={c.id} value={c.id}>{c.nombre}</option>)}
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">Proveedor</label>
                  <select className="form-control" value={form.proveedor_id} onChange={e=>f('proveedor_id',e.target.value)}>
                    <option value="">-- Seleccionar --</option>
                    {proveedores.map(p=><option key={p.id} value={p.id}>{p.nombre}</option>)}
                  </select>
                </div>
              </div>
              <div className="form-row-3">
                <div className="form-group"><label className="form-label">Precio compra</label><input {...numInput('precio_compra')} placeholder="0"/></div>
                <div className="form-group"><label className="form-label">Precio venta *</label><input {...numInput('precio_venta')} placeholder="0"/></div>
                <div className="form-group"><label className="form-label">Stock actual</label><input {...numInput('stock')} placeholder="0"/></div>
              </div>
              <div className="form-group">
                <label className="form-label">Stock mínimo <span style={{color:'var(--text-muted)',fontSize:11}}>(alerta de reposición)</span></label>
                <input {...numInput('stock_minimo')} placeholder="5" style={{maxWidth:140}}/>
              </div>

              <div className="form-group">
                <label className="form-label">
                  <Car size={13} style={{verticalAlign:-2,marginRight:4}}/>
                  Compatibilidad de vehículos
                  <span style={{color:'var(--text-muted)',fontSize:11,fontWeight:400}}> (para el asistente de recomendación)</span>
                </label>

                {!editing ? (
                  <div style={{fontSize:12,color:'var(--text-muted)',fontStyle:'italic',padding:'8px 0'}}>
                    Guarda el repuesto primero para poder agregar los vehículos a los que le sirve.
                  </div>
                ) : (
                  <>
                    {compatibilidades.length > 0 && (
                      <div style={{display:'flex',flexDirection:'column',gap:6,marginBottom:10}}>
                        {compatibilidades.map(v => (
                          <div key={v.id} style={{
                            display:'flex',alignItems:'center',justifyContent:'space-between',
                            padding:'8px 12px',background:'var(--bg-hover)',borderRadius:'var(--radius)',
                          }}>
                            <span style={{fontSize:13}}>
                              {v.marca} {v.modelo} · {v.anio_desde}-{v.anio_hasta}
                              {v.motor ? ` · ${v.motor}` : ''}
                              {v.combustible ? ` · ${v.combustible}` : ''}
                            </span>
                            <button className="btn-icon" style={{color:'var(--danger)'}} title="Quitar compatibilidad"
                              onClick={()=>quitarCompat(v.id)}>
                              <Trash2 size={13}/>
                            </button>
                          </div>
                        ))}
                      </div>
                    )}

                    <div style={{display:'flex',flexDirection:'column',gap:8,padding:12,background:'var(--bg-hover)',borderRadius:'var(--radius)'}}>
                      {errorCompat && <div className="alert alert-error" style={{fontSize:12,padding:'6px 10px',margin:0}}>{errorCompat}</div>}
                      <div className="form-row">
                        <div className="form-group">
                          <label className="form-label">Marca</label>
                          <input className="form-control" list="rep-marcas-list" placeholder="Ej: Toyota"
                            value={nuevoVeh.marca}
                            onChange={e=>{
                              const marca = e.target.value;
                              setNuevoVeh(v=>({...v, marca, modelo:''}));
                              cargarModelos(marca);
                            }}
                          />
                          <datalist id="rep-marcas-list">{marcas.map(m=><option key={m} value={m}/>)}</datalist>
                        </div>
                        <div className="form-group">
                          <label className="form-label">Modelo</label>
                          <input className="form-control" list="rep-modelos-list" placeholder="Ej: Hilux"
                            value={nuevoVeh.modelo}
                            onChange={e=>setNuevoVeh(v=>({...v, modelo:e.target.value}))}
                          />
                          <datalist id="rep-modelos-list">{modelos.map(m=><option key={m} value={m}/>)}</datalist>
                        </div>
                      </div>
                      <div className="form-row-3">
                        <div className="form-group">
                          <label className="form-label">Año desde</label>
                          <input className="form-control" type="number" placeholder="2020"
                            value={nuevoVeh.anio_desde} onChange={e=>setNuevoVeh(v=>({...v, anio_desde:e.target.value}))}/>
                        </div>
                        <div className="form-group">
                          <label className="form-label">Año hasta</label>
                          <input className="form-control" type="number" placeholder="2025"
                            value={nuevoVeh.anio_hasta} onChange={e=>setNuevoVeh(v=>({...v, anio_hasta:e.target.value}))}/>
                        </div>
                        <div className="form-group">
                          <label className="form-label">Combustible</label>
                          <select className="form-control" value={nuevoVeh.combustible}
                            onChange={e=>setNuevoVeh(v=>({...v, combustible:e.target.value}))}>
                            {COMBUSTIBLES.map(c=><option key={c} value={c} style={{textTransform:'capitalize'}}>{c}</option>)}
                          </select>
                        </div>
                      </div>
                      <div className="form-group" style={{marginBottom:0}}>
                        <label className="form-label">Motor <span style={{color:'var(--text-muted)',fontSize:11}}>(opcional, ej. 2.7)</span></label>
                        <input className="form-control" placeholder="2.7" style={{maxWidth:140}}
                          value={nuevoVeh.motor} onChange={e=>setNuevoVeh(v=>({...v, motor:e.target.value}))}/>
                      </div>
                      <button className="btn btn-ghost" onClick={agregarCompat} disabled={savingCompat} style={{alignSelf:'flex-start'}}>
                        <Plus size={14}/> {savingCompat ? 'Agregando…' : 'Agregar compatibilidad'}
                      </button>
                    </div>
                  </>
                )}
              </div>

              {/* ── Sugerencias del modelo propio (Sprint 3) ──────────────
                  Solo con el repuesto ya guardado: el modelo necesita un id
                  contra el cual comparar el catálogo. Toda la sección es
                  opcional — si el microservicio no responde, desaparece y el
                  resto del modal sigue funcionando igual. */}
              {editing && (
                <div className="form-group">
                  <label className="form-label">
                    <Sparkles size={13} style={{verticalAlign:-2,marginRight:4}}/>
                    Sugerencias
                    <span style={{color:'var(--text-muted)',fontSize:11,fontWeight:400}}>
                      {' '}(modelo propio: TF-IDF + similitud coseno, sin IA externa)
                    </span>
                  </label>

                  {cargandoSug && (
                    <div style={{fontSize:12,color:'var(--text-muted)',padding:'8px 0'}}>
                      Analizando el catálogo…
                    </div>
                  )}

                  {!cargandoSug && !sugDisponibles && (
                    <div style={{fontSize:12,color:'var(--text-muted)',fontStyle:'italic',padding:'8px 0'}}>
                      El servicio de sugerencias no está disponible en este momento.
                    </div>
                  )}

                  {!cargandoSug && sugDisponibles && demanda && (
                    <div style={{display:'flex',alignItems:'center',gap:8,marginBottom:10,flexWrap:'wrap'}}>
                      <span className={`badge ${(SENAL_DEMANDA[demanda.senal] ?? SENAL_DEMANDA.sin_datos).clase}`}>
                        {(SENAL_DEMANDA[demanda.senal] ?? SENAL_DEMANDA.sin_datos).texto}
                      </span>
                      <span style={{fontSize:11,color:'var(--text-muted)'}}>
                        {demanda.demanda_semanal_estimada > 0
                          ? `≈ ${demanda.demanda_semanal_estimada} u./semana`
                          : 'Sin ventas en el período'}
                        {demanda.dias_cobertura != null && ` · stock para ~${demanda.dias_cobertura} días`}
                        {` · ${demanda.unidades_periodo} u. vendidas en ${demanda.dias_historial} días`}
                      </span>
                    </div>
                  )}

                  {!cargandoSug && sugDisponibles && sugerencias.length === 0 && (
                    <div style={{fontSize:12,color:'var(--text-muted)',fontStyle:'italic',padding:'4px 0'}}>
                      No se encontraron productos parecidos en el catálogo.
                    </div>
                  )}

                  {!cargandoSug && sugerencias.length > 0 && (
                    <div style={{border:'1px solid var(--border)',borderRadius:'var(--radius)',overflow:'hidden'}}>
                      {sugerencias.map(sg => (
                        <div key={sg.id} style={{
                          display:'flex',alignItems:'center',gap:10,padding:'8px 12px',
                          borderBottom:'1px solid var(--border)',
                        }}>
                          <div style={{flex:1,minWidth:0}}>
                            <div style={{fontSize:13,fontWeight:600,whiteSpace:'nowrap',overflow:'hidden',textOverflow:'ellipsis'}}>
                              {sg.nombre}
                            </div>
                            <div style={{fontSize:11,color:'var(--text-muted)'}}>
                              {sg.codigo}{sg.categoria ? ` · ${sg.categoria}` : ''} · Stock: {sg.stock}
                              {' · '}
                              <span title="Qué tan parecido es al producto abierto, según el modelo">
                                {Math.round(sg.similitud * 100)}% similar
                              </span>
                            </div>
                          </div>
                          <div style={{fontSize:12,color:'var(--accent)',fontWeight:600,whiteSpace:'nowrap'}}>
                            {fmt(sg.precio_venta)}
                          </div>
                          <button className="btn-icon" title="Abrir este producto"
                            onClick={() => abrirSugerido(sg.id)}>
                            <ArrowRight size={14}/>
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
            <div className="modal-footer">
              <button className="btn btn-ghost" onClick={closeModal}>Cancelar</button>
              <button className="btn btn-primary" onClick={handleSave} disabled={saving}>{saving?'Guardando…':'Guardar'}</button>
            </div>
          </div>
        </div>
      )}

      {/* Modal categorías */}
      {modalCat && (
        <div className="modal-overlay" onClick={e=>e.target===e.currentTarget&&closeCats()}>
          <div className="modal">
            <div className="modal-header">
              <div className="modal-title">Gestionar categorías</div>
              <button className="modal-close" onClick={closeCats}><X size={18}/></button>
            </div>
            <div className="modal-body">
              {errorCat && <div className="alert alert-error">{errorCat}</div>}
              <div style={{display:'flex',gap:8,marginBottom:16}}>
                <input className="form-control" placeholder={editingCat?'Editar nombre…':'Nueva categoría…'} value={formCat.nombre}
                  onChange={e=>setFormCat({nombre:e.target.value})} onKeyDown={e=>e.key==='Enter'&&saveCat()} style={{flex:1}}/>
                <button className="btn btn-primary" onClick={saveCat} disabled={savingCat}>
                  {savingCat?'…':editingCat?'Actualizar':<><Plus size={14}/> Agregar</>}
                </button>
                {editingCat && <button className="btn btn-ghost" onClick={()=>{setEditingCat(null);setFormCat(EMPTY_CAT);}}><X size={14}/></button>}
              </div>
              <div style={{display:'flex',flexDirection:'column',gap:6}}>
                {categorias.length===0 ? <div className="empty-state"><p>Sin categorías</p></div>
                : categorias.map(cat=>(
                  <div key={cat.id} style={{
                    display:'flex',alignItems:'center',justifyContent:'space-between',
                    padding:'10px 14px',borderRadius:'var(--radius)',
                    background:editingCat===cat.id?'var(--accent-dim)':'var(--bg-hover)',
                    border:editingCat===cat.id?'1px solid var(--accent)':'1px solid transparent',
                    transition:'all var(--transition)',
                  }}>
                    <div style={{display:'flex',alignItems:'center',gap:10}}>
                      <Tag size={14} color="var(--accent)"/>
                      <span style={{fontSize:14,fontWeight:editingCat===cat.id?600:400}}>{cat.nombre}</span>
                    </div>
                    <div style={{display:'flex',gap:6}}>
                      <button className="btn-icon" onClick={()=>openEditCat(cat)} title="Editar"><Edit2 size={13}/></button>
                      <button className="btn-icon" style={{color:'var(--danger)'}} title="Eliminar" onClick={()=>deleteCat(cat.id,cat.nombre)}><Trash2 size={13}/></button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div className="modal-footer"><button className="btn btn-ghost" onClick={closeCats}>Cerrar</button></div>
          </div>
        </div>
      )}

      {/* ── Modal confirmación (reemplaza window.confirm) ── */}
      {confirmDlg && (
        <div className="modal-overlay" style={{zIndex:9999,animation:'cdFadeIn 0.15s ease'}}>
          <div className="modal" style={{maxWidth:420,animation:'cdSlideUp 0.22s cubic-bezier(0.34,1.56,0.64,1)',border:'1px solid var(--danger)'}}>
            <div className="modal-header" style={{borderBottom:'1px solid var(--border)',paddingBottom:16}}>
              <div style={{display:'flex',alignItems:'center',gap:10}}>
                <span style={{
                  display:'flex',alignItems:'center',justifyContent:'center',
                  width:36,height:36,borderRadius:'50%',flexShrink:0,
                  background:'rgba(239,68,68,0.15)',
                }}>
                  <AlertTriangle size={18} color="var(--danger)"/>
                </span>
                <div className="modal-title" style={{color:'var(--danger)'}}>Confirmar eliminación</div>
              </div>
            </div>
            <div className="modal-body" style={{padding:'18px 24px'}}>
              <p style={{margin:0,fontSize:14,lineHeight:1.6,color:'var(--text-secondary)'}}>
                {confirmDlg.message}
              </p>
            </div>
            <div className="modal-footer" style={{gap:8}}>
              <button className="btn btn-ghost" onClick={confirmDlg.onCancel}>
                Cancelar
              </button>
              <button
                className="btn"
                style={{background:'var(--danger)',color:'#fff',border:'none',display:'flex',alignItems:'center',gap:6}}
                onClick={confirmDlg.onConfirm}
              >
                <Trash2 size={14}/> Eliminar
              </button>
            </div>
          </div>
        </div>
      )}

      <style>{`
        @keyframes cdFadeIn  { from{opacity:0} to{opacity:1} }
        @keyframes cdSlideUp { from{transform:translateY(16px) scale(0.97);opacity:0} to{transform:none;opacity:1} }
      `}</style>
    </>
  );
}
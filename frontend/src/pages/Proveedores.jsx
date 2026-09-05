import { useEffect, useState, useCallback } from 'react';
import { Plus, Search, Edit2, Trash2, X, AlertTriangle } from 'lucide-react';
import Table from '../components/Table';
import Pagination from '../components/Pagination';
import { useToastContext } from '../context/ToastContext';
import api from '../services/api';

const EMPTY = { nombre:'', contacto:'', telefono:'', email:'', direccion:'' };
const PAGE_SIZE = 15;
const soloLetras  = v => v.replace(/[^a-zA-ZáéíóúÁÉÍÓÚñÑüÜ\s]/g,'');
const soloNumeros = v => v.replace(/\D/g,'');

function ConfirmModal({ mensaje, onConfirm, onCancel }) {
  return (
    <div className="modal-overlay" style={{zIndex:2000}}>
      <div className="modal" style={{maxWidth:380}}>
        <div className="modal-body" style={{textAlign:'center',padding:'32px 24px'}}>
          <div style={{width:56,height:56,borderRadius:'50%',background:'var(--danger-dim)',border:'2px solid var(--danger)',display:'flex',alignItems:'center',justifyContent:'center',margin:'0 auto 16px'}}>
            <AlertTriangle size={26} color="var(--danger)"/>
          </div>
          <div style={{fontSize:16,fontWeight:700,marginBottom:8}}>¿Confirmar eliminación?</div>
          <div style={{fontSize:13,color:'var(--text-secondary)',marginBottom:24}}>{mensaje}</div>
          <div style={{display:'flex',gap:10,justifyContent:'center'}}>
            <button className="btn btn-ghost" onClick={onCancel} style={{minWidth:100}}>Cancelar</button>
            <button className="btn btn-danger" onClick={onConfirm} style={{minWidth:100}}>Sí, eliminar</button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Proveedores() {
  const toast = useToastContext();

  const [data,    setData]    = useState([]);
  const [total,   setTotal]   = useState(0);
  const [page,    setPage]    = useState(1);
  const [loading, setLoading] = useState(true);
  const [q,       setQ]       = useState('');
  const [modal,   setModal]   = useState(false);
  const [form,    setForm]    = useState(EMPTY);
  const [editing, setEditing] = useState(null);
  const [saving,  setSaving]  = useState(false);
  const [error,   setError]   = useState('');
  const [confirm, setConfirm] = useState(null);

  const load = useCallback(async (p = page, search = q) => {
    setLoading(true);
    try {
      const r = await api.get('/proveedores', { params: { q: search, page: p, limit: PAGE_SIZE } });
      setData(r.data.data ?? []);
      setTotal(r.data.total ?? 0);
    } catch { toast('Error cargando proveedores', { type:'error' }); }
    finally  { setLoading(false); }
  }, [page, q]);

  useEffect(() => { load(); }, []);
  useEffect(() => { load(1,q); setPage(1); }, [q]);
  useEffect(() => { load(page,q); }, [page]);

  const openNew  = () => { setForm(EMPTY); setEditing(null); setError(''); setModal(true); };
  const openEdit = r  => { setForm({...r}); setEditing(r.id); setError(''); setModal(true); };
  const close    = () => { setModal(false); setError(''); };

  const save = async () => {
    if (!form.nombre.trim()) { setError('El nombre del proveedor es obligatorio'); return; }
    if (form.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) { setError('El formato del email no es válido'); return; }
    setSaving(true);
    try {
      if (editing) { await api.put(`/proveedores/${editing}`, form); toast(`Proveedor "${form.nombre}" actualizado`, { type:'success' }); }
      else         { await api.post('/proveedores', form); toast(`Proveedor "${form.nombre}" registrado`, { type:'success' }); }
      close(); load(page,q);
    } catch(e) { setError(e.response?.data?.error || 'Error al guardar el proveedor'); }
    finally { setSaving(false); }
  };

  const confirmarEliminar = async () => {
    try {
      await api.delete(`/proveedores/${confirm.id}`);
      setConfirm(null); load(page,q);
      toast(`Proveedor "${confirm.nombre}" eliminado`, { type:'warning' });
    } catch { toast('No se pudo eliminar (puede tener repuestos asociados)', { type:'error' }); setConfirm(null); }
  };

  const f = (k,v) => setForm(p => ({...p, [k]:v}));

  const columns = [
    { key:'nombre',   label:'Empresa / Proveedor' },
    { key:'contacto', label:'Contacto' },
    { key:'telefono', label:'Teléfono' },
    { key:'email',    label:'Email' },
    { key:'id', label:'Acciones', render:(_,r) => (
      <div style={{display:'flex',gap:6}}>
        <button className="btn-icon" onClick={()=>openEdit(r)} title="Editar proveedor"><Edit2 size={13}/></button>
        <button className="btn-icon" style={{color:'var(--danger)'}} title="Eliminar proveedor" onClick={()=>setConfirm({id:r.id,nombre:r.nombre})}><Trash2 size={13}/></button>
      </div>
    )},
  ];

  return (
    <>
      {confirm && <ConfirmModal mensaje={`Estás a punto de eliminar a "${confirm.nombre}". Esta acción no se puede deshacer.`} onConfirm={confirmarEliminar} onCancel={()=>setConfirm(null)}/>}

      <div className="page-header">
        <div>
          <div className="page-title">Proveedores</div>
          <div className="page-subtitle">{total} proveedores registrados</div>
        </div>
        <button className="btn btn-primary" onClick={openNew}><Plus size={15}/> Nuevo proveedor</button>
      </div>

      <div className="toolbar">
        <div className="search-bar">
          <Search size={14} className="search-icon"/>
          <input className="form-control" placeholder="Buscar proveedor…" value={q} onChange={e=>setQ(e.target.value)}/>
        </div>
      </div>

      <div className="card" style={{padding:0,overflow:'hidden'}}>
        <Table columns={columns} data={data} loading={loading} emptyText="No se encontraron proveedores"/>
        <Pagination page={page} pageSize={PAGE_SIZE} total={total} onPrev={()=>setPage(p=>p-1)} onNext={()=>setPage(p=>p+1)}/>
      </div>

      {modal && (
        <div className="modal-overlay" onClick={e=>e.target===e.currentTarget&&close()}>
          <div className="modal">
            <div className="modal-header">
              <div className="modal-title">{editing?'Editar proveedor':'Nuevo proveedor'}</div>
              <button className="modal-close" onClick={close}><X size={18}/></button>
            </div>
            <div className="modal-body">
              {error && <div className="alert alert-error">{error}</div>}
              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Nombre / Empresa *</label>
                  <input className="form-control" value={form.nombre} onChange={e=>f('nombre',e.target.value)}/>
                </div>
                <div className="form-group">
                  <label className="form-label">Persona de contacto</label>
                  <input className="form-control" value={form.contacto} placeholder="Solo letras"
                    onChange={e=>f('contacto',soloLetras(e.target.value))}/>
                </div>
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Teléfono <span style={{color:'var(--text-muted)',fontSize:11}}>(solo números)</span></label>
                  <input className="form-control" value={form.telefono} placeholder="Ej: 3001234567" inputMode="numeric"
                    onChange={e=>f('telefono',soloNumeros(e.target.value))}/>
                </div>
                <div className="form-group">
                  <label className="form-label">Email</label>
                  <input type="email" className="form-control" value={form.email} placeholder="correo@proveedor.com" onChange={e=>f('email',e.target.value)}/>
                </div>
              </div>
              <div className="form-group">
                <label className="form-label">Dirección</label>
                <input className="form-control" value={form.direccion} onChange={e=>f('direccion',e.target.value)}/>
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn btn-ghost" onClick={close}>Cancelar</button>
              <button className="btn btn-primary" onClick={save} disabled={saving}>{saving?'Guardando…':'Guardar'}</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

import { useEffect, useState } from 'react';
import { Plus, Edit2, Trash2, X, ShieldAlert, AlertTriangle } from 'lucide-react';
import Table from '../components/Table';
import { StatusBadge } from '../components/Tooltip';
import { useToastContext } from '../context/ToastContext';
import { usuariosService } from '../services/ventasService';
import { useAuth } from '../context/AuthContext';

const EMPTY = { nombre:'', email:'', password:'', rol:'vendedor', activo:1 };
const rolBadge = r => ({ admin:'badge-accent', dueno:'badge-warning', vendedor:'badge-neutral' }[r]||'badge-neutral');
const rolLabel = r => ({ admin:'Administrador', dueno:'Dueño', vendedor:'Vendedor' }[r]||r);

export default function Usuarios() {
  const toast = useToastContext();
  const { user: me } = useAuth();

  const [data,       setData]       = useState([]);
  const [loading,    setLoading]    = useState(true);
  const [modal,      setModal]      = useState(false);
  const [form,       setForm]       = useState(EMPTY);
  const [editing,    setEditing]    = useState(null);
  const [saving,     setSaving]     = useState(false);
  const [error,      setError]      = useState('');
  const [confirmDlg, setConfirmDlg] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const r = await usuariosService.listar();
      setData(r.data.data ?? []);
    } catch { toast('Error cargando usuarios', { type:'error' }); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const openNew  = () => { setForm(EMPTY); setEditing(null); setError(''); setModal(true); };
  const openEdit = r => { setForm({...r, password:''}); setEditing(r.id); setError(''); setModal(true); };
  const close    = () => { setModal(false); setError(''); };

  const save = async () => {
    if (!form.nombre.trim()) { setError('El nombre es obligatorio'); return; }
    if (!form.email.trim())  { setError('El email es obligatorio'); return; }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) { setError('El formato del email no es válido'); return; }
    if (!editing && !form.password) { setError('La contraseña es obligatoria para usuarios nuevos'); return; }
    if (form.password && form.password.length < 8) { setError('La contraseña debe tener al menos 8 caracteres'); return; }
    setSaving(true);
    try {
      if (editing) {
        await usuariosService.actualizar(editing, form);
        toast(`Usuario "${form.nombre}" actualizado`, { type:'success' });
      } else {
        await usuariosService.crear(form);
        toast(`Usuario "${form.nombre}" creado como ${rolLabel(form.rol)}`, { type:'success' });
      }
      close(); load();
    } catch(e) {
      setError(e.response?.data?.error || 'Error al guardar el usuario');
    } finally { setSaving(false); }
  };

  const askConfirm = (message) => new Promise(resolve =>
    setConfirmDlg({
      message,
      onConfirm: () => { setConfirmDlg(null); resolve(true); },
      onCancel:  () => { setConfirmDlg(null); resolve(false); },
    })
  );

  const del = async (id, nombre) => {
    if (id === me?.id) { toast('No puedes desactivarte a ti mismo', { type:'warning' }); return; }
    const ok = await askConfirm(`¿Desactivar al usuario "${nombre}"? No podrá ingresar al sistema.`);
    if (!ok) return;
    try {
      await usuariosService.eliminar(id);
      load();
      toast(`Usuario "${nombre}" desactivado`, { type:'warning' });
    } catch { toast('No se pudo desactivar el usuario', { type:'error' }); }
  };

  const f = (k,v) => setForm(p => ({...p, [k]:v}));

  const columns = [
    { key:'nombre',    label:'Nombre' },
    { key:'email',     label:'Email' },
    { key:'rol',       label:'Rol',    render: v => <span className={`badge ${rolBadge(v)}`}>{rolLabel(v)}</span> },
    { key:'activo',    label:'Estado', render: v => <StatusBadge status={v?'activo':'inactivo'} className={`badge ${v?'badge-success':'badge-danger'}`}/> },
    { key:'creado_en', label:'Creado', render: v => new Date(v).toLocaleDateString('es-CO') },
    { key:'id', label:'', render:(_,r) => (
      <div style={{display:'flex',gap:6}}>
        <button className="btn-icon" onClick={()=>openEdit(r)} title="Editar usuario"><Edit2 size={13}/></button>
        <button className="btn-icon" style={{color:'var(--danger)'}} title="Desactivar usuario" onClick={()=>del(r.id,r.nombre)}><Trash2 size={13}/></button>
      </div>
    )},
  ];

  return (
    <>
      <div className="page-header">
        <div>
          <div className="page-title">Usuarios</div>
          <div className="page-subtitle">{data.length} usuarios registrados</div>
        </div>
        <button className="btn btn-primary" onClick={openNew}><Plus size={15}/> Nuevo usuario</button>
      </div>

      <div className="card" style={{padding:0,overflow:'hidden'}}>
        <Table columns={columns} data={data} loading={loading}/>
      </div>

      {modal && (
        <div className="modal-overlay" onClick={e=>e.target===e.currentTarget&&close()}>
          <div className="modal">
            <div className="modal-header">
              <div className="modal-title">{editing?'Editar usuario':'Nuevo usuario'}</div>
              <button className="modal-close" onClick={close}><X size={18}/></button>
            </div>
            <div className="modal-body">
              {error && <div className="alert alert-error"><ShieldAlert size={14}/> {error}</div>}
              <div className="form-group">
                <label className="form-label">Nombre completo *</label>
                <input className="form-control" value={form.nombre} onChange={e=>f('nombre',e.target.value)}/>
              </div>
              <div className="form-group">
                <label className="form-label">Email * <span style={{color:'var(--text-muted)',fontSize:11}}>(se usa para iniciar sesión)</span></label>
                <input type="email" className="form-control" value={form.email} placeholder="correo@empresa.com" onChange={e=>f('email',e.target.value)}/>
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">
                    Contraseña {editing?<span style={{color:'var(--text-muted)',fontSize:11}}>(vacío = no cambiar)</span>:'*'}
                  </label>
                  <input type="password" className="form-control" value={form.password}
                    placeholder={editing?'Dejar vacío para mantener':'Mínimo 8 caracteres'}
                    onChange={e=>f('password',e.target.value)}/>
                </div>
                <div className="form-group">
                  <label className="form-label">Rol</label>
                  <select className="form-control" value={form.rol} onChange={e=>f('rol',e.target.value)}>
                    <option value="dueno">Dueño</option>
                    <option value="admin">Administrador</option>
                    <option value="vendedor">Vendedor</option>
                  </select>
                </div>
              </div>
              {editing && (
                <div className="form-group">
                  <label className="form-label">Estado de acceso</label>
                  <select className="form-control" value={form.activo} onChange={e=>f('activo',+e.target.value)}>
                    <option value={1}>Activo — puede iniciar sesión</option>
                    <option value={0}>Inactivo — sin acceso al sistema</option>
                  </select>
                </div>
              )}
            </div>
            <div className="modal-footer">
              <button className="btn btn-ghost" onClick={close}>Cancelar</button>
              <button className="btn btn-primary" onClick={save} disabled={saving}>{saving?'Guardando…':'Guardar'}</button>
            </div>
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
                <div className="modal-title" style={{color:'var(--danger)'}}>Confirmar acción</div>
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
                <Trash2 size={14}/> Desactivar
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
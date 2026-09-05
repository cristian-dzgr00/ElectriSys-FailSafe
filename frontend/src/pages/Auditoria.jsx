import { useEffect, useState, useCallback } from 'react';
import {
  ShieldCheck, Filter, X, ChevronUp, ChevronDown,
  RefreshCw, User, Calendar, Activity, Clock, Search
} from 'lucide-react';
import api from '../services/api';

// ── Helpers ────────────────────────────────────────────────────────
const ACCION_META = {
  crear_venta:  { label: 'Crear Venta',  color: 'var(--success)',  bg: 'var(--success-dim)' },
  anular_venta: { label: 'Anular Venta', color: 'var(--danger)',   bg: 'var(--danger-dim)'  },
};

function accionMeta(accion) {
  return ACCION_META[accion] ?? { label: accion, color: 'var(--text-secondary)', bg: 'var(--bg-hover)' };
}

function formatFecha(ts) {
  if (!ts) return '—';
  const d = new Date(ts);
  return d.toLocaleString('es-CO', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
}

function rolLabel(rol) {
  return { admin: 'Admin', dueno: 'Dueño', vendedor: 'Vendedor' }[rol] ?? rol;
}

// ── Componente principal ───────────────────────────────────────────
export default function Auditoria() {
  const [rows,      setRows]      = useState([]);
  const [total,     setTotal]     = useState(0);
  const [loading,   setLoading]   = useState(true);
  const [page,      setPage]      = useState(1);
  const LIMIT = 20;

  // Filtros
  const [showPanel, setShowPanel] = useState(false);
  const [orden,     setOrden]     = useState('DESC');
  const [accion,    setAccion]    = useState('');
  const [usuarioId, setUsuarioId] = useState('');
  const [desde,     setDesde]     = useState('');
  const [hasta,     setHasta]     = useState('');

  // Opciones de los selectores
  const [opAcciones,  setOpAcciones]  = useState([]);
  const [opUsuarios,  setOpUsuarios]  = useState([]);

  // Filtros aplicados (los que están activos realmente)
  const [applied, setApplied] = useState({
    orden: 'DESC', accion: '', usuarioId: '', desde: '', hasta: '',
  });

  const totalPages = Math.max(1, Math.ceil(total / LIMIT));
  const activeFilters = Object.values(applied).filter(Boolean).length -
    (applied.orden === 'DESC' ? 0 : -1); // orden siempre tiene valor

  const load = useCallback(async (p = 1, filtros = applied) => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        page:  p,
        limit: LIMIT,
        orden: filtros.orden,
        ...(filtros.accion     && { accion:     filtros.accion }),
        ...(filtros.usuarioId  && { usuario_id: filtros.usuarioId }),
        ...(filtros.desde      && { desde:      filtros.desde }),
        ...(filtros.hasta      && { hasta:      filtros.hasta }),
      });
      const { data } = await api.get(`/audit-log?${params}`);
      setRows(data.data     ?? []);
      setTotal(data.total   ?? 0);
      setOpAcciones(data.acciones ?? []);
      setOpUsuarios(data.usuarios ?? []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [applied]);

  useEffect(() => { load(1, applied); setPage(1); }, []);

  const aplicarFiltros = () => {
    const f = { orden, accion, usuarioId, desde, hasta };
    setApplied(f);
    setPage(1);
    load(1, f);
    setShowPanel(false);
  };

  const limpiarFiltros = () => {
    const f = { orden: 'DESC', accion: '', usuarioId: '', desde: '', hasta: '' };
    setOrden('DESC'); setAccion(''); setUsuarioId(''); setDesde(''); setHasta('');
    setApplied(f);
    setPage(1);
    load(1, f);
    setShowPanel(false);
  };

  const goPage = (p) => {
    setPage(p);
    load(p, applied);
  };

  // ── Render ────────────────────────────────────────────────────────
  return (
    <div style={{ padding: '24px 28px', maxWidth: 1100, margin: '0 auto' }}>

      {/* Encabezado */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{
            width: 42, height: 42, borderRadius: 10,
            background: 'var(--accent-dim)', display: 'flex',
            alignItems: 'center', justifyContent: 'center',
          }}>
            <ShieldCheck size={20} color="var(--accent)" />
          </div>
          <div>
            <h1 style={{ fontSize: 20, fontWeight: 700, color: 'var(--text-primary)', margin: 0 }}>
              Log de Auditoría
            </h1>
            <p style={{ fontSize: 12, color: 'var(--text-muted)', margin: 0 }}>
              Registro de operaciones críticas del sistema · Patrón Observer
            </p>
          </div>
        </div>

        <div style={{ display: 'flex', gap: 8 }}>
          {/* Botón refrescar */}
          <button className="btn btn-ghost btn-sm"
            onClick={() => load(page, applied)}
            title="Refrescar"
          >
            <RefreshCw size={14} style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }} />
            Refrescar
          </button>

          {/* Botón Filtrar */}
          <button
            className="btn btn-sm"
            onClick={() => setShowPanel(v => !v)}
            style={{
              background: showPanel ? 'var(--accent)' : 'var(--bg-hover)',
              color:      showPanel ? '#111' : 'var(--text-primary)',
              border: '1px solid var(--border)',
              position: 'relative',
            }}
          >
            <Filter size={14} />
            Filtrar
            {/* Badge de filtros activos */}
            {(applied.accion || applied.usuarioId || applied.desde || applied.hasta || applied.orden !== 'DESC') && (
              <span style={{
                position: 'absolute', top: -6, right: -6,
                background: 'var(--accent)', color: '#111',
                borderRadius: '50%', width: 16, height: 16,
                fontSize: 10, fontWeight: 700,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>!</span>
            )}
          </button>
        </div>
      </div>

      {/* Panel de filtros */}
      {showPanel && (
        <div style={{
          background: 'var(--bg-card)',
          border: '1px solid var(--border-accent)',
          borderRadius: 12,
          padding: 20,
          marginBottom: 20,
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          gap: 14,
          boxShadow: '0 4px 24px rgba(245,166,35,0.08)',
        }}>
          {/* Ordenar */}
          <div>
            <label style={labelSt}>Ordenar por fecha</label>
            <select style={inputSt} value={orden} onChange={e => setOrden(e.target.value)}>
              <option value="DESC">Más reciente primero</option>
              <option value="ASC">Más antiguo primero</option>
            </select>
          </div>

          {/* Tipo de acción */}
          <div>
            <label style={labelSt}>Tipo de acción</label>
            <select style={inputSt} value={accion} onChange={e => setAccion(e.target.value)}>
              <option value="">Todas las acciones</option>
              {opAcciones.map(a => (
                <option key={a} value={a}>{accionMeta(a).label}</option>
              ))}
            </select>
          </div>

          {/* Usuario */}
          <div>
            <label style={labelSt}>Usuario</label>
            <select style={inputSt} value={usuarioId} onChange={e => setUsuarioId(e.target.value)}>
              <option value="">Todos los usuarios</option>
              {opUsuarios.map(u => (
                <option key={u.id} value={u.id}>{u.nombre}</option>
              ))}
            </select>
          </div>

          {/* Desde */}
          <div>
            <label style={labelSt}>Desde</label>
            <input type="date" style={inputSt} value={desde} onChange={e => setDesde(e.target.value)} />
          </div>

          {/* Hasta */}
          <div>
            <label style={labelSt}>Hasta</label>
            <input type="date" style={inputSt} value={hasta} onChange={e => setHasta(e.target.value)} />
          </div>

          {/* Acciones del panel */}
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8 }}>
            <button className="btn btn-primary btn-sm" style={{ flex: 1 }} onClick={aplicarFiltros}>
              <Search size={13} /> Aplicar
            </button>
            <button className="btn btn-ghost btn-sm" onClick={limpiarFiltros}>
              <X size={13} /> Limpiar
            </button>
          </div>
        </div>
      )}

      {/* Stats rápidas */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
        <StatChip icon={<Activity size={13} />} label="Total registros" value={total} />
        <StatChip icon={<Clock size={13} />}    label="Orden" value={applied.orden === 'DESC' ? 'Reciente → Antiguo' : 'Antiguo → Reciente'} />
        {applied.accion    && <StatChip icon={<Filter size={13} />} label="Acción"  value={accionMeta(applied.accion).label} onRemove={() => { setAccion('');    aplicarFiltros(); }} />}
        {applied.usuarioId && <StatChip icon={<User size={13} />}   label="Usuario" value={opUsuarios.find(u => String(u.id) === applied.usuarioId)?.nombre ?? applied.usuarioId} onRemove={() => { setUsuarioId(''); aplicarFiltros(); }} />}
        {applied.desde     && <StatChip icon={<Calendar size={13} />} label="Desde" value={applied.desde} onRemove={() => { setDesde(''); aplicarFiltros(); }} />}
        {applied.hasta     && <StatChip icon={<Calendar size={13} />} label="Hasta" value={applied.hasta} onRemove={() => { setHasta(''); aplicarFiltros(); }} />}
      </div>

      {/* Tabla */}
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        {loading ? (
          <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>
            <RefreshCw size={22} style={{ animation: 'spin 1s linear infinite', marginBottom: 8 }} />
            <p style={{ margin: 0 }}>Cargando registros...</p>
          </div>
        ) : rows.length === 0 ? (
          <div style={{ padding: 60, textAlign: 'center' }}>
            <ShieldCheck size={40} color="var(--text-muted)" style={{ marginBottom: 12 }} />
            <p style={{ color: 'var(--text-muted)', margin: 0, fontSize: 14 }}>
              No hay registros de auditoría con los filtros seleccionados
            </p>
          </div>
        ) : (
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th style={thSt}>#</th>
                  <th style={thSt}>Fecha y hora</th>
                  <th style={thSt}>Acción</th>
                  <th style={thSt}>Usuario</th>
                  <th style={thSt}>Rol</th>
                  <th style={thSt}>Detalle</th>
                  <th style={thSt}>IP</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => {
                  const meta = accionMeta(r.accion);
                  return (
                    <tr key={r.id} style={{
                      borderBottom: '1px solid var(--border)',
                      background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)',
                      transition: 'background 0.15s',
                    }}
                      onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-hover)'}
                      onMouseLeave={e => e.currentTarget.style.background = i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)'}
                    >
                      <td style={tdSt}>
                        <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>
                          {(page - 1) * LIMIT + i + 1}
                        </span>
                      </td>
                      <td style={tdSt}>
                        <span style={{ fontSize: 12, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
                          {formatFecha(r.created_at)}
                        </span>
                      </td>
                      <td style={tdSt}>
                        <span style={{
                          display: 'inline-flex', alignItems: 'center', gap: 5,
                          padding: '3px 10px', borderRadius: 20, fontSize: 11, fontWeight: 600,
                          background: meta.bg, color: meta.color,
                          border: `1px solid ${meta.color}33`,
                        }}>
                          {meta.label}
                        </span>
                      </td>
                      <td style={tdSt}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                          <div style={{
                            width: 26, height: 26, borderRadius: '50%',
                            background: 'var(--accent-dim)',
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            flexShrink: 0,
                          }}>
                            <User size={12} color="var(--accent)" />
                          </div>
                          <div>
                            <div style={{ fontSize: 13, color: 'var(--text-primary)', fontWeight: 500 }}>
                              {r.usuario_nombre ?? '—'}
                            </div>
                            <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                              {r.usuario_email ?? ''}
                            </div>
                          </div>
                        </div>
                      </td>
                      <td style={tdSt}>
                        <span style={{
                          fontSize: 11, padding: '2px 8px', borderRadius: 4,
                          background: 'var(--bg-hover)', color: 'var(--text-secondary)',
                        }}>
                          {rolLabel(r.usuario_rol)}
                        </span>
                      </td>
                      <td style={{ ...tdSt, maxWidth: 280 }}>
                        <span style={{ fontSize: 12, color: 'var(--text-primary)' }}>
                          {r.detalle ?? '—'}
                        </span>
                      </td>
                      <td style={tdSt}>
                        <span style={{ fontSize: 11, fontFamily: 'monospace', color: 'var(--text-muted)' }}>
                          {r.ip ?? '—'}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Paginación */}
        {!loading && total > LIMIT && (
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '12px 16px', borderTop: '1px solid var(--border)',
          }}>
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              Mostrando {(page - 1) * LIMIT + 1}–{Math.min(page * LIMIT, total)} de {total} registros
            </span>
            <div style={{ display: 'flex', gap: 6 }}>
              <button className="btn btn-ghost btn-sm" disabled={page === 1} onClick={() => goPage(page - 1)}>
                <ChevronUp size={13} style={{ transform: 'rotate(-90deg)' }} /> Anterior
              </button>
              <span style={{
                padding: '5px 12px', fontSize: 12,
                background: 'var(--accent-dim)', color: 'var(--accent)',
                borderRadius: 6, fontWeight: 600,
              }}>
                {page} / {totalPages}
              </span>
              <button className="btn btn-ghost btn-sm" disabled={page === totalPages} onClick={() => goPage(page + 1)}>
                Siguiente <ChevronDown size={13} style={{ transform: 'rotate(-90deg)' }} />
              </button>
            </div>
          </div>
        )}
      </div>

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
}

// ── Sub-componentes ───────────────────────────────────────────────
function StatChip({ icon, label, value, onRemove }) {
  return (
    <div style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      padding: '5px 10px', borderRadius: 20,
      background: 'var(--bg-card)', border: '1px solid var(--border)',
      fontSize: 12, color: 'var(--text-secondary)',
    }}>
      <span style={{ color: 'var(--accent)' }}>{icon}</span>
      <span style={{ color: 'var(--text-muted)' }}>{label}:</span>
      <span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{value}</span>
      {onRemove && (
        <button onClick={onRemove} style={{
          background: 'none', border: 'none', cursor: 'pointer',
          padding: 0, color: 'var(--text-muted)', display: 'flex',
          alignItems: 'center', marginLeft: 2,
        }}>
          <X size={11} />
        </button>
      )}
    </div>
  );
}

// ── Estilos inline reutilizables ──────────────────────────────────
const labelSt = {
  display: 'block', fontSize: 11, color: 'var(--text-muted)',
  marginBottom: 5, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '.04em',
};

const inputSt = {
  width: '100%', padding: '7px 10px', borderRadius: 6,
  background: 'var(--bg-input)', border: '1px solid var(--border)',
  color: 'var(--text-primary)', fontSize: 13, outline: 'none',
  boxSizing: 'border-box',
};

const thSt = {
  padding: '11px 14px', textAlign: 'left',
  fontSize: 11, fontWeight: 600, color: 'var(--text-muted)',
  textTransform: 'uppercase', letterSpacing: '.05em', whiteSpace: 'nowrap',
};

const tdSt = {
  padding: '12px 14px', fontSize: 13, verticalAlign: 'middle',
};
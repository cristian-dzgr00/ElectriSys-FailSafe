import { useAuth } from '../context/AuthContext';
import { LogOut, User, PanelLeft } from 'lucide-react';
import NotificationBell from './NotificationBell';

export default function Navbar({ onToggleSidebar }) {
  const { user, logout } = useAuth();

  return (
    <header style={{
      height: 'var(--header-height)',
      background: 'var(--bg-secondary)',
      borderBottom: '1px solid var(--border)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '0 24px',
      gap: 12,
      flexShrink: 0,
    }}>
      {/* Solo visible en el drawer móvil (ver .sidebar-toggle en
          index.css) — en escritorio el sidebar ya está siempre visible. */}
      <button className="sidebar-toggle btn-icon" onClick={onToggleSidebar} title="Menú">
        <PanelLeft size={18} />
      </button>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
      {/* Campana: vive acá y no en una página para escuchar el WebSocket
          desde cualquier vista del POS. */}
      <NotificationBell />

      <div style={{ width: 1, height: 24, background: 'var(--border)' }} />

      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <div style={{
          width: 30, height: 30,
          borderRadius: '50%',
          background: 'var(--accent-dim)',
          border: '1px solid var(--accent)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: 'var(--accent)',
        }}>
          <User size={14} />
        </div>
        <div>
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
            {user?.nombre}
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'capitalize' }}>
            {user?.rol}
          </div>
        </div>
      </div>

      <div style={{ width: 1, height: 24, background: 'var(--border)' }} />

      <button className="btn-icon" onClick={logout} title="Cerrar sesión">
        <LogOut size={15} />
      </button>
      </div>
    </header>
  );
}

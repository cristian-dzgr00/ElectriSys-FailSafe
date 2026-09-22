import { useAuth } from '../context/AuthContext';
import { LogOut, User } from 'lucide-react';
import NotificationBell from './NotificationBell';

export default function Navbar() {
  const { user, logout } = useAuth();

  return (
    <header style={{
      height: 'var(--header-height)',
      background: 'var(--bg-secondary)',
      borderBottom: '1px solid var(--border)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'flex-end',
      padding: '0 24px',
      gap: 12,
      flexShrink: 0,
    }}>
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
    </header>
  );
}

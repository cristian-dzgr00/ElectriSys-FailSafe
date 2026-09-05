// frontend/src/components/NotificationBell.jsx
// Campana de notificaciones en tiempo real vía WebSocket.
// Añadir a <Navbar> para mostrar alertas de ventas y auditoría.

import { useState, useCallback } from 'react';
import { Bell, ShoppingCart, AlertTriangle, Wifi, WifiOff } from 'lucide-react';
import { useWebSocket } from '../hooks/useWebSocket';

const MAX_NOTIFICATIONS = 50;

const EVENT_CONFIG = {
  crear_venta: {
    icon: <ShoppingCart size={14} />,
    color: '#0F6E56',
    label: 'Nueva venta',
  },
  anular_venta: {
    icon: <AlertTriangle size={14} />,
    color: '#854F0B',
    label: 'Venta anulada',
  },
};

export default function NotificationBell() {
  const [notifications, setNotifications] = useState([]);
  const [open, setOpen]                   = useState(false);
  const [unread, setUnread]               = useState(0);

  const handleMessage = useCallback((event) => {
    if (event.type === 'connected') return;

    setNotifications(prev => {
      const next = [
        { ...event, id: Date.now(), read: false, receivedAt: new Date() },
        ...prev,
      ].slice(0, MAX_NOTIFICATIONS);
      return next;
    });

    setUnread(n => n + 1);
  }, []);

  const { connected } = useWebSocket(handleMessage);

  const markAllRead = () => {
    setUnread(0);
    setNotifications(prev => prev.map(n => ({ ...n, read: true })));
  };

  const togglePanel = () => {
    setOpen(prev => {
      if (!prev) markAllRead();
      return !prev;
    });
  };

  return (
    <div style={{ position: 'relative', display: 'inline-block' }}>
      {/* Botón campana */}
      <button
        onClick={togglePanel}
        aria-label={`Notificaciones${unread > 0 ? ` — ${unread} sin leer` : ''}`}
        style={{
          position: 'relative',
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          padding: '6px',
          color: 'var(--color-text-secondary)',
          display: 'flex',
          alignItems: 'center',
        }}
      >
        <Bell size={20} />
        {/* Badge de no leídos */}
        {unread > 0 && (
          <span style={{
            position: 'absolute',
            top: '2px',
            right: '2px',
            background: '#E24B4A',
            color: '#fff',
            borderRadius: '50%',
            width: '16px',
            height: '16px',
            fontSize: '10px',
            fontWeight: 500,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}>
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>

      {/* Indicador de conexión */}
      <span
        title={connected ? 'Tiempo real activo' : 'Sin conexión tiempo real'}
        style={{
          position: 'absolute',
          bottom: '4px',
          right: '4px',
          color: connected ? '#1D9E75' : '#888780',
        }}
      >
        {connected
          ? <Wifi size={10} />
          : <WifiOff size={10} />
        }
      </span>

      {/* Panel de notificaciones */}
      {open && (
        <div style={{
          position: 'absolute',
          right: 0,
          top: '110%',
          width: '320px',
          background: 'var(--color-background-primary)',
          border: '0.5px solid var(--color-border-tertiary)',
          borderRadius: 'var(--border-radius-lg)',
          boxShadow: 'none',
          zIndex: 1000,
          overflow: 'hidden',
        }}>
          {/* Header */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '12px 16px',
            borderBottom: '0.5px solid var(--color-border-tertiary)',
          }}>
            <span style={{ fontSize: '14px', fontWeight: 500, color: 'var(--color-text-primary)' }}>
              Notificaciones
            </span>
            <span style={{ fontSize: '12px', color: connected ? '#1D9E75' : '#888780' }}>
              {connected ? 'En vivo' : 'Offline'}
            </span>
          </div>

          {/* Lista */}
          <div style={{ maxHeight: '360px', overflowY: 'auto' }}>
            {notifications.length === 0 ? (
              <p style={{
                textAlign: 'center',
                padding: '2rem',
                fontSize: '13px',
                color: 'var(--color-text-tertiary)',
                margin: 0,
              }}>
                Sin notificaciones aún
              </p>
            ) : (
              notifications.map(notif => {
                const cfg = EVENT_CONFIG[notif.type] ?? {
                  icon: <Bell size={14} />,
                  color: '#888780',
                  label: notif.type,
                };
                return (
                  <div
                    key={notif.id}
                    style={{
                      display: 'flex',
                      alignItems: 'flex-start',
                      gap: '10px',
                      padding: '10px 16px',
                      borderBottom: '0.5px solid var(--color-border-tertiary)',
                      background: notif.read
                        ? 'transparent'
                        : 'var(--color-background-secondary)',
                    }}
                  >
                    <span style={{ color: cfg.color, marginTop: '2px', flexShrink: 0 }}>
                      {cfg.icon}
                    </span>
                    <div style={{ flex: 1 }}>
                      <p style={{ margin: 0, fontSize: '13px', fontWeight: 500, color: 'var(--color-text-primary)' }}>
                        {cfg.label}
                      </p>
                      <p style={{ margin: '2px 0 0', fontSize: '12px', color: 'var(--color-text-secondary)' }}>
                        {notif.detail}
                      </p>
                      <p style={{ margin: '2px 0 0', fontSize: '11px', color: 'var(--color-text-tertiary)' }}>
                        {notif.receivedAt?.toLocaleTimeString('es-CO')}
                      </p>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}

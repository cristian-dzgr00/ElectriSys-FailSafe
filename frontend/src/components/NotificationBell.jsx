// frontend/src/components/NotificationBell.jsx
// Campana de notificaciones en tiempo real.
//
// Vive en el Navbar, así que escucha el WebSocket desde cualquier página.
// El servidor ya filtra por rol (targetRoles), de modo que acá solo llega
// lo que a este usuario le corresponde ver: un vendedor no recibe los
// eventos de ventas/pedidos que el backend marca para admin y dueño.
//
// Las notificaciones viven en memoria a propósito: son avisos de "esto
// acaba de pasar", no un historial. El historial real es Auditoría, que
// sale de audit_log y sobrevive a un F5.

import { useCallback, useEffect, useRef, useState } from 'react';
import { Bell, Wifi, WifiOff, X } from 'lucide-react';
import { useWebSocket } from '../hooks/useWebSocket';

const MAX_NOTIFICACIONES = 20;

// Cómo se muestra cada tipo de evento. Lo que no esté acá no se muestra:
// es una lista blanca, no una lista negra, para que un evento nuevo del
// backend no aparezca como una notificación vacía sin que nadie lo decida.
const EVENTOS = {
  crear_venta:     { titulo: 'Venta registrada',  color: 'var(--success)' },
  anular_venta:    { titulo: 'Venta anulada',     color: 'var(--danger)' },
  crear_pedido:    { titulo: 'Pedido creado',     color: 'var(--accent)' },
  estado_pedido:   { titulo: 'Pedido actualizado', color: 'var(--accent)' },
  cancelar_pedido: { titulo: 'Pedido cancelado',  color: 'var(--danger)' },
};

const fmtHora = iso => {
  try {
    return new Date(iso).toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit' });
  } catch {
    return '';
  }
};

export default function NotificationBell() {
  const [notificaciones, setNotificaciones] = useState([]);
  const [noLeidas, setNoLeidas] = useState(0);
  const [abierto, setAbierto] = useState(false);
  const contenedorRef = useRef(null);

  const handleMessage = useCallback((event) => {
    // stock_actualizado NO entra en la campana. Es un evento derivado del
    // mismo hecho de negocio que crear_venta/anular_venta (que sí se
    // muestran): no trae un `detail` legible sino el mapa {id: stock}, y
    // se dispara en CADA venta, así que duplicaría la notificación. Su
    // lugar es la tabla de Repuestos, que lo usa para actualizar el stock
    // en vivo — ver Repuestos.jsx.
    if (event.type === 'stock_actualizado') return;

    // Handshake del servidor al abrir la conexión, no es una notificación.
    if (event.type === 'connected') return;

    const meta = EVENTOS[event.type];
    if (!meta) return;

    setNotificaciones(prev => [
      {
        id: `${event.type}-${event.timestamp}-${Math.random()}`,
        titulo: meta.titulo,
        color: meta.color,
        detalle: event.detail || '',
        hora: fmtHora(event.timestamp),
      },
      ...prev,
    ].slice(0, MAX_NOTIFICACIONES));

    setNoLeidas(n => n + 1);
  }, []);

  const { connected } = useWebSocket(handleMessage);

  // Cerrar al hacer clic fuera del panel.
  useEffect(() => {
    if (!abierto) return;
    const alClicar = (e) => {
      if (contenedorRef.current && !contenedorRef.current.contains(e.target)) {
        setAbierto(false);
      }
    };
    document.addEventListener('mousedown', alClicar);
    return () => document.removeEventListener('mousedown', alClicar);
  }, [abierto]);

  const alternar = () => {
    setAbierto(a => !a);
    if (!abierto) setNoLeidas(0);   // abrirla es darlas por leídas
  };

  return (
    <div ref={contenedorRef} style={{ position: 'relative', display: 'flex', alignItems: 'center', gap: 8 }}>
      {/* Estado de la conexión: los mismos iconos que usa Repuestos.jsx */}
      <span
        title={connected
          ? 'Conectado: las notificaciones llegan en tiempo real'
          : 'Sin conexión en tiempo real — no llegarán avisos hasta reconectar'}
        style={{ display: 'inline-flex', color: connected ? 'var(--success)' : 'var(--text-muted)' }}
      >
        {connected ? <Wifi size={13} /> : <WifiOff size={13} />}
      </span>

      <button className="btn-icon" onClick={alternar} title="Notificaciones"
        style={{ position: 'relative' }}>
        <Bell size={15} />
        {noLeidas > 0 && (
          <span style={{
            position: 'absolute', top: -4, right: -4,
            minWidth: 16, height: 16, padding: '0 4px',
            borderRadius: 8, background: 'var(--danger)', color: '#fff',
            fontSize: 10, fontWeight: 700,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            {noLeidas > 9 ? '9+' : noLeidas}
          </span>
        )}
      </button>

      {abierto && (
        <div style={{
          position: 'absolute', top: '100%', right: 0, marginTop: 8,
          width: 320, maxHeight: 400, overflowY: 'auto',
          background: 'var(--bg-secondary)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius)', boxShadow: '0 8px 24px rgba(0,0,0,.4)',
          zIndex: 200,
        }}>
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '10px 14px', borderBottom: '1px solid var(--border)',
          }}>
            <span style={{ fontSize: 13, fontWeight: 600 }}>Notificaciones</span>
            <button className="btn-icon" onClick={() => setAbierto(false)} title="Cerrar">
              <X size={13} />
            </button>
          </div>

          {notificaciones.length === 0 ? (
            <div style={{ padding: '18px 14px', fontSize: 12, color: 'var(--text-muted)', textAlign: 'center' }}>
              {connected
                ? 'Sin novedades por ahora.'
                : 'Sin conexión en tiempo real.'}
            </div>
          ) : (
            notificaciones.map(n => (
              <div key={n.id} style={{
                padding: '10px 14px', borderBottom: '1px solid var(--border)',
                display: 'flex', gap: 10,
              }}>
                <span style={{
                  width: 6, height: 6, borderRadius: '50%', background: n.color,
                  marginTop: 6, flexShrink: 0,
                }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 12, fontWeight: 600 }}>{n.titulo}</div>
                  {n.detalle && (
                    <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 2 }}>
                      {n.detalle}
                    </div>
                  )}
                </div>
                <span style={{ fontSize: 10, color: 'var(--text-muted)', flexShrink: 0 }}>{n.hora}</span>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

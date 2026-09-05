import { useState } from 'react';

const ESTADO_TOOLTIP = {
  completada:  'La venta fue procesada exitosamente.',
  anulada:     'Esta venta fue cancelada y no afecta el inventario.',
  pendiente:   'En espera de confirmación o pago.',
  borrador:    'Cotización sin enviar al cliente.',
  enviada:     'Cotización enviada, esperando respuesta.',
  aceptada:    'El cliente aceptó la cotización.',
  rechazada:   'El cliente rechazó la cotización.',
  vencida:     'La cotización superó su fecha límite.',
  activo:      'Usuario con acceso al sistema.',
  inactivo:    'Usuario desactivado sin acceso.',
};

export function StatusBadge({ status, className }) {
  const [show, setShow] = useState(false);
  const tip = ESTADO_TOOLTIP[status?.toLowerCase()];

  return (
    <span
      style={{ position: 'relative', display: 'inline-flex' }}
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
    >
      <span className={className} style={{ textTransform: 'capitalize', cursor: tip ? 'help' : 'default' }}>
        {status}
      </span>
      {tip && show && (
        <span style={{
          position: 'absolute', bottom: '110%', left: '50%',
          transform: 'translateX(-50%)',
          background: '#111', border: '1px solid var(--border)',
          borderRadius: 6, padding: '6px 10px',
          fontSize: 11, color: 'var(--text-secondary)',
          whiteSpace: 'nowrap', zIndex: 100,
          boxShadow: '0 4px 16px rgba(0,0,0,.5)',
          pointerEvents: 'none',
        }}>
          {tip}
          <span style={{
            position: 'absolute', top: '100%', left: '50%',
            transform: 'translateX(-50%)',
            border: '5px solid transparent',
            borderTopColor: 'var(--border)',
          }} />
        </span>
      )}
    </span>
  );
}

export function Tooltip({ children, text }) {
  const [show, setShow] = useState(false);
  return (
    <span
      style={{ position: 'relative', display: 'inline-flex' }}
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
    >
      {children}
      {show && text && (
        <span style={{
          position: 'absolute', bottom: '110%', left: '50%',
          transform: 'translateX(-50%)',
          background: '#111', border: '1px solid var(--border)',
          borderRadius: 6, padding: '6px 10px',
          fontSize: 11, color: 'var(--text-secondary)',
          whiteSpace: 'nowrap', zIndex: 100,
          boxShadow: '0 4px 16px rgba(0,0,0,.5)',
          pointerEvents: 'none',
        }}>
          {text}
        </span>
      )}
    </span>
  );
}

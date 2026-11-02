// frontend/src/components/VpnRequiredModal.jsx
// Aviso que se muestra ANTES de abrir cualquier formulario de administración
// cuando el usuario no está dentro de la VPN. Ver context/VpnContext.jsx.

import { useEffect } from 'react';
import { ShieldAlert, X } from 'lucide-react';

export default function VpnRequiredModal({ onClose }) {
  // Se cierra con Escape además del botón y el clic fuera del cuadro.
  useEffect(() => {
    const onKey = e => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div
      className="modal-overlay"
      style={{ zIndex: 9999 }}
      onClick={e => e.target === e.currentTarget && onClose()}
    >
      <div
        className="modal"
        style={{ maxWidth: 420 }}
        role="dialog"
        aria-modal="true"
        aria-labelledby="vpn-modal-titulo"
      >
        <div className="modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              width: 36, height: 36, borderRadius: '50%', flexShrink: 0,
              background: 'var(--accent-dim)',
            }}>
              <ShieldAlert size={18} color="var(--accent)" />
            </span>
            <div className="modal-title" id="vpn-modal-titulo">Acceso por VPN requerido</div>
          </div>
          <button className="modal-close" onClick={onClose} aria-label="Cerrar"><X size={18} /></button>
        </div>
        <div className="modal-body">
          <p style={{ margin: 0, fontSize: 14, lineHeight: 1.6, color: 'var(--text-secondary)' }}>
            Para poder realizar esta acción debes ingresar por un túnel VPN.
          </p>
        </div>
        <div className="modal-footer">
          <button className="btn btn-primary" onClick={onClose} autoFocus>Entendido</button>
        </div>
      </div>
    </div>
  );
}

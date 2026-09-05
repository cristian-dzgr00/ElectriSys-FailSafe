import { createPortal } from 'react-dom';
import { CheckCircle, AlertCircle, Info, X, RotateCcw } from 'lucide-react';

const ICONS = {
  success: CheckCircle,
  error:   AlertCircle,
  warning: Info,
  info:    Info,
};

const COLORS = {
  success: { bg: 'var(--success)',      text: '#fff' },
  error:   { bg: 'var(--danger)',       text: '#fff' },
  warning: { bg: 'var(--warning)',      text: '#111' },
  info:    { bg: 'var(--accent)',       text: '#111' },
};

function Toast({ toast, onRemove, onUndo }) {
  const { id, msg, type, undoFn } = toast;
  const Icon = ICONS[type] || CheckCircle;
  const colors = COLORS[type] || COLORS.success;

  return (
    <div
      role="alert"
      aria-live="polite"
      style={{
        display: 'flex', alignItems: 'center', gap: 10,
        background: colors.bg, color: colors.text,
        padding: '12px 16px', borderRadius: 10,
        fontSize: 13, fontWeight: 500,
        boxShadow: '0 8px 32px rgba(0,0,0,.45)',
        animation: 'slideInRight .25s ease',
        minWidth: 280, maxWidth: 400,
        pointerEvents: 'all',
      }}
    >
      <Icon size={16} style={{ flexShrink: 0 }} />
      <span style={{ flex: 1 }}>{msg}</span>
      {undoFn && (
        <button
          onClick={() => onUndo(id)}
          title="Deshacer"
          style={{
            display: 'flex', alignItems: 'center', gap: 4,
            background: 'rgba(255,255,255,.2)', border: 'none',
            color: 'inherit', borderRadius: 6, padding: '4px 8px',
            cursor: 'pointer', fontSize: 12, fontWeight: 600,
          }}
        >
          <RotateCcw size={12} /> Deshacer
        </button>
      )}
      <button
        onClick={() => onRemove(id)}
        style={{
          background: 'none', border: 'none', color: 'inherit',
          cursor: 'pointer', padding: 2, borderRadius: 4, lineHeight: 1,
        }}
      >
        <X size={14} />
      </button>
    </div>
  );
}

export default function ToastContainer({ toasts, onRemove, onUndo }) {
  return createPortal(
    <div style={{
      position: 'fixed', bottom: 24, right: 24,
      zIndex: 9999, display: 'flex', flexDirection: 'column',
      gap: 10, pointerEvents: 'none',
    }}>
      {toasts.map(t => (
        <Toast key={t.id} toast={t} onRemove={onRemove} onUndo={onUndo} />
      ))}
    </div>,
    document.body
  );
}

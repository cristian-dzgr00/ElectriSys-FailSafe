import { useState, useEffect } from 'react';
import { X, ArrowRight, ArrowLeft, Zap } from 'lucide-react';

const STEPS = [
  {
    title: '¡Bienvenido a ElectriSys POS! ⚡',
    desc: 'Sistema de punto de venta para repuestos eléctricos. Te guiamos en los primeros pasos.',
    target: null,
  },
  {
    title: 'Dashboard',
    desc: 'Aquí verás el resumen del día: ventas, ingresos y métricas clave de un vistazo.',
    target: 'nav-dashboard',
  },
  {
    title: 'Registrar una venta',
    desc: 'Ve a "Ventas" y presiona "Nueva venta" para iniciar una transacción. Puedes agregar múltiples productos.',
    target: 'nav-ventas',
  },
  {
    title: 'Inventario de repuestos',
    desc: 'En "Repuestos" administras el inventario. Las alertas de stock bajo se muestran en rojo.',
    target: 'nav-repuestos',
  },
  {
    title: 'Reportes',
    desc: 'Analiza ventas por período, métodos de pago y productos con mayor movimiento.',
    target: 'nav-reportes',
  },
];

const TOUR_KEY = 'es_tour_done';

export default function OnboardingTour() {
  const [step,    setStep]    = useState(0);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const done = localStorage.getItem(TOUR_KEY);
    if (!done) setVisible(true);
  }, []);

  const finish = () => {
    localStorage.setItem(TOUR_KEY, '1');
    setVisible(false);
  };

  if (!visible) return null;

  const current = STEPS[step];
  const isLast  = step === STEPS.length - 1;

  return (
    <div style={{
      position: 'fixed', inset: 0,
      background: 'rgba(0,0,0,.65)', backdropFilter: 'blur(3px)',
      zIndex: 9000, display: 'flex', alignItems: 'center', justifyContent: 'center',
      animation: 'fadeIn .2s ease',
    }}>
      <div style={{
        background: 'var(--bg-card)', border: '1px solid var(--accent)',
        borderRadius: 'var(--radius-lg)', padding: '32px 36px',
        width: '100%', maxWidth: 480,
        boxShadow: '0 24px 64px rgba(0,0,0,.6), 0 0 0 1px rgba(245,166,35,.2)',
        animation: 'slideUp .25s ease',
      }}>
        {/* Logo */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 24 }}>
          <div style={{
            width: 36, height: 36, background: 'var(--accent)',
            borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Zap size={18} color="#111" strokeWidth={2.5} />
          </div>
          <span style={{ fontWeight: 700, fontSize: 15 }}>ElectriSys POS</span>
          <span style={{
            marginLeft: 'auto', fontSize: 11, color: 'var(--text-muted)',
            background: 'var(--bg-hover)', padding: '3px 8px', borderRadius: 20,
          }}>
            {step + 1} / {STEPS.length}
          </span>
        </div>

        {/* Progreso */}
        <div style={{ display: 'flex', gap: 4, marginBottom: 24 }}>
          {STEPS.map((_, i) => (
            <div key={i} style={{
              height: 3, flex: 1, borderRadius: 2,
              background: i <= step ? 'var(--accent)' : 'var(--border)',
              transition: 'background .3s ease',
            }} />
          ))}
        </div>

        <div style={{ fontSize: 17, fontWeight: 700, marginBottom: 10 }}>{current.title}</div>
        <div style={{ fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: 28 }}>
          {current.desc}
        </div>

        <div style={{ display: 'flex', gap: 10, justifyContent: 'space-between', alignItems: 'center' }}>
          <button className="btn btn-ghost btn-sm" onClick={finish} style={{ color: 'var(--text-muted)' }}>
            <X size={13} /> Saltar tour
          </button>
          <div style={{ display: 'flex', gap: 8 }}>
            {step > 0 && (
              <button className="btn btn-ghost btn-sm" onClick={() => setStep(s => s - 1)}>
                <ArrowLeft size={13} /> Anterior
              </button>
            )}
            <button
              className="btn btn-primary btn-sm"
              onClick={isLast ? finish : () => setStep(s => s + 1)}
              style={{ gap: 6 }}
            >
              {isLast ? '¡Empezar!' : (<>Siguiente <ArrowRight size={13} /></>)}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

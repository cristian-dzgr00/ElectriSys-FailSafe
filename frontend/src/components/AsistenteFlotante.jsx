// frontend/src/components/AsistenteFlotante.jsx
// Botón flotante + panel de chat del asistente de NLP para recomendación
// de repuestos. Se usa en la vista de Ventas: cuando un producto está
// agotado, el vendedor pregunta y el asistente sugiere sustitutos reales
// del inventario (ver nlp-service/, backend /api/asistente/consultar).

import { useEffect, useRef, useState } from 'react';
import { Loader2, MessageCircle, Send, X } from 'lucide-react';
import { useToastContext } from '../context/ToastContext';
import { asistenteService } from '../services/asistenteService';

const MAX_CHARS = 300;

const INTENCION_LABEL = {
  recomendar_sustituto:     'Sustituto',
  buscar_repuesto:          'Búsqueda',
  consultar_stock:          'Stock',
  consultar_precio:         'Precio',
  consultar_compatibilidad: 'Compatibilidad',
  saludo_despedida:         'Saludo',
  fuera_de_dominio:         'Fuera de tema',
};

const fmt = n => n == null ? null : new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 }).format(n);

export default function AsistenteFlotante() {
  const toast = useToastContext();
  const [open, setOpen]         = useState(false);
  const [mensajes, setMensajes] = useState([]);
  const [texto, setTexto]       = useState('');
  const [enviando, setEnviando] = useState(false);
  const scrollRef = useRef(null);
  const inputRef  = useRef(null);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [mensajes, enviando]);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  const enviar = async () => {
    const consulta = texto.trim();
    if (!consulta || enviando) return;
    if (consulta.length > MAX_CHARS) {
      toast(`La consulta no puede superar ${MAX_CHARS} caracteres`, { type: 'error' });
      return;
    }

    setMensajes(prev => [...prev, { rol: 'usuario', texto: consulta }]);
    setTexto('');
    setEnviando(true);
    try {
      const { data } = await asistenteService.consultar(consulta);
      setMensajes(prev => [...prev, {
        rol: 'asistente',
        texto: data.respuesta_texto,
        intencion: data.intencion,
        sugerencias: data.sugerencias || [],
      }]);
    } catch (e) {
      const msg = e.response?.data?.error || 'El asistente no está disponible en este momento';
      setMensajes(prev => [...prev, { rol: 'asistente', texto: msg, error: true }]);
      toast(msg, { type: 'error' });
    } finally {
      setEnviando(false);
    }
  };

  const onKeyDown = e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      enviar();
    }
  };

  return (
    <>
      <button
        onClick={() => setOpen(o => !o)}
        aria-label={open ? 'Cerrar asistente de repuestos' : 'Abrir asistente de repuestos'}
        style={{
          position: 'fixed', bottom: 24, right: 24, zIndex: 1000,
          width: 52, height: 52, borderRadius: '50%', border: 'none',
          background: 'var(--accent)', color: '#1a1305',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          boxShadow: 'var(--shadow)', cursor: 'pointer',
        }}
      >
        {open ? <X size={22} /> : <MessageCircle size={22} />}
      </button>

      {open && (
        <div style={{
          position: 'fixed', bottom: 88, right: 24, zIndex: 999,
          width: 370, maxWidth: 'calc(100vw - 32px)',
          height: 500, maxHeight: 'calc(100vh - 120px)',
          background: 'var(--bg-card)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius-lg)', boxShadow: 'var(--shadow)',
          display: 'flex', flexDirection: 'column', overflow: 'hidden',
        }}>
          <div style={{
            padding: '14px 16px', borderBottom: '1px solid var(--border)',
            display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0,
          }}>
            <div style={{
              width: 32, height: 32, borderRadius: '50%', background: 'var(--accent-dim)',
              display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
            }}>
              <MessageCircle size={16} color="var(--accent)" />
            </div>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>
                Asistente de repuestos
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                Recomendación de sustitutos por NLP
              </div>
            </div>
          </div>

          <div
            ref={scrollRef}
            style={{ flex: 1, overflowY: 'auto', padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 12 }}
          >
            {mensajes.length === 0 && (
              <div style={{ margin: 'auto 0', textAlign: 'center', fontSize: 12.5, color: 'var(--text-muted)', lineHeight: 1.6 }}>
                Pregúntame por disponibilidad, precio, stock o compatibilidad — o pídeme un
                sustituto si un repuesto está agotado.
                <br /><br />
                <span style={{ fontStyle: 'italic' }}>
                  Ej: "No hay filtro de aceite para Toyota Hilux 2.7 gasolina 2024, ¿qué recomiendo?"
                </span>
              </div>
            )}
            {mensajes.map((m, i) => <MensajeBurbuja key={i} mensaje={m} />)}
            {enviando && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--text-muted)', fontSize: 12 }}>
                <Loader2 size={13} style={{ animation: 'asistenteSpin 0.8s linear infinite' }} /> Pensando…
              </div>
            )}
          </div>

          <div style={{ padding: 10, borderTop: '1px solid var(--border)', display: 'flex', gap: 8, flexShrink: 0 }}>
            <input
              ref={inputRef}
              className="form-control"
              placeholder="Escribe tu consulta…"
              value={texto}
              maxLength={MAX_CHARS}
              onChange={e => setTexto(e.target.value)}
              onKeyDown={onKeyDown}
              disabled={enviando}
              style={{ flex: 1 }}
            />
            <button
              className="btn btn-primary"
              onClick={enviar}
              disabled={enviando || !texto.trim()}
              style={{ padding: '0 12px' }}
              aria-label="Enviar consulta"
            >
              <Send size={15} />
            </button>
          </div>
        </div>
      )}

      <style>{`@keyframes asistenteSpin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
    </>
  );
}

function MensajeBurbuja({ mensaje }) {
  const esUsuario = mensaje.rol === 'usuario';
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: esUsuario ? 'flex-end' : 'flex-start', gap: 5 }}>
      {!esUsuario && mensaje.intencion && (
        <span style={{
          fontSize: 10, textTransform: 'uppercase', letterSpacing: 0.4, fontWeight: 600,
          color: 'var(--text-muted)', padding: '2px 8px', borderRadius: 20,
          background: 'var(--bg-hover)',
        }}>
          {INTENCION_LABEL[mensaje.intencion] || mensaje.intencion}
        </span>
      )}
      <div style={{
        maxWidth: '90%', padding: '8px 12px', borderRadius: 12,
        fontSize: 13, lineHeight: 1.5, whiteSpace: 'pre-wrap',
        background: esUsuario ? 'var(--accent)' : (mensaje.error ? 'var(--danger-dim)' : 'var(--bg-hover)'),
        color: esUsuario ? '#1a1305' : (mensaje.error ? 'var(--danger)' : 'var(--text-primary)'),
        borderBottomRightRadius: esUsuario ? 2 : 12,
        borderBottomLeftRadius: esUsuario ? 12 : 2,
      }}>
        {mensaje.texto}
      </div>
      {mensaje.sugerencias?.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, width: '100%' }}>
          {mensaje.sugerencias.map((s, i) => (
            <div key={s.id ?? i} style={{
              border: '1px solid var(--border)', borderRadius: 8, padding: '8px 10px',
              background: 'var(--bg-secondary)', fontSize: 12,
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{s.codigo}</span>
                {fmt(s.precio_venta) && <span style={{ color: 'var(--accent)', fontWeight: 600 }}>{fmt(s.precio_venta)}</span>}
              </div>
              <div style={{ color: 'var(--text-secondary)', marginTop: 2 }}>{s.nombre}</div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4, color: 'var(--text-muted)', fontSize: 11 }}>
                <span>{s.proveedor || s.categoria || ''}</span>
                {s.stock != null && <span>Stock: {s.stock}</span>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

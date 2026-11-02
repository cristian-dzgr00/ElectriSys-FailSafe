// frontend/src/components/ComplementosPanel.jsx
// "También suelen llevar": hasta 3 productos que, según las ventas reales, se
// compran junto a los del carrito (reglas de asociación del microservicio de
// NLP). Se usa en Nueva venta y Nueva cotización.
//
// Si no hay sugerencias, o el servicio no responde, no renderiza NADA: un
// panel vacío o un mensaje de error en plena venta solo estorba.

import { Plus, Sparkles } from 'lucide-react';
import { useComplementos } from '../hooks/useComplementos';
import { detalleAsociacion, textoSeLlevaJunto } from '../services/sugerenciasIa';

const fmt = n => new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 }).format(n ?? 0);

/**
 * @param items     líneas del carrito ({ repuesto_id, ... })
 * @param onAgregar recibe el producto ({ id, nombre, precio_venta, ... }), igual
 *                  que el onSeleccionar de BuscadorRepuesto
 */
export default function ComplementosPanel({ items, onAgregar }) {
  const ids = items.map(i => i.repuesto_id);
  const sugeridos = useComplementos(ids);

  if (sugeridos.length === 0) return null;

  return (
    <div
      className="card"
      style={{ padding: '10px 12px', marginBottom: 16, background: 'var(--bg-secondary)' }}
      aria-label="Productos que suelen llevarse junto a esta venta"
    >
      <div style={{
        display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8,
        fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)',
      }}>
        <Sparkles size={13} color="var(--accent)" /> También suelen llevar
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {sugeridos.map(c => {
          const frase = textoSeLlevaJunto(c);
          return (
            <div
              key={c.id}
              title={detalleAsociacion(c)}
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10,
                padding: '6px 8px', borderRadius: 6, border: '1px solid var(--border)',
              }}
            >
              <div style={{ minWidth: 0 }}>
                <div style={{
                  fontSize: 13, fontWeight: 600, color: 'var(--text-primary)',
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}>
                  {c.nombre}
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                  {fmt(c.precio_venta)} · Stock: {c.stock}
                  {frase ? ` · ${frase}` : ''}
                </div>
              </div>
              <button
                type="button"
                className="btn btn-ghost"
                style={{ padding: '4px 10px', fontSize: 12, flexShrink: 0 }}
                onClick={() => onAgregar(c)}
                aria-label={`Agregar ${c.nombre}`}
              >
                <Plus size={12} /> Agregar
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}

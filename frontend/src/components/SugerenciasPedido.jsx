// frontend/src/components/SugerenciasPedido.jsx
// Piezas de interfaz de la cantidad sugerida en "Nuevo pedido a proveedor".
// Los datos vienen del microservicio de NLP (punto de reorden sobre ventas
// reales); acá solo se muestran. Todo se oculta si el servicio no responde.

import { Check, Lightbulb, Plus } from 'lucide-react';
import {
  cantidadUsable, infoSenal, resumenSugerencia, sugerenciasDelProveedor,
} from '../services/sugerenciasIa';

/** Badge de la señal (reabastecer / rotación baja / normal) con el motivo en el tooltip. */
export function SenalBadge({ sugerencia }) {
  const info = infoSenal(sugerencia?.senal);
  const motivo = sugerencia?.motivo ? ` ${sugerencia.motivo}` : '';
  return (
    <span className={`badge ${info.clase}`} title={`${info.ayuda}${motivo}`} style={{ cursor: 'help' }}>
      {info.texto}
    </span>
  );
}

/**
 * Bajo el nombre de un producto del pedido: señal, el porqué en una línea
 * y el botón de un clic para usar la cantidad sugerida. No renderiza nada si
 * no hay sugerencia para ese producto.
 */
export function SugeridoDeItem({ sugerencia, cantidadActual, onUsar }) {
  if (!sugerencia) return null;
  const sugerida = cantidadUsable(sugerencia);
  const yaAplicada = sugerida != null && Number(cantidadActual) === sugerida;

  return (
    <div style={{ marginTop: 4, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
      <SenalBadge sugerencia={sugerencia} />
      <span style={{ fontSize: 11, color: 'var(--text-muted)' }} title={sugerencia.motivo || undefined}>
        {resumenSugerencia(sugerencia)}
      </span>
      {sugerida != null && (
        <button
          type="button"
          className="btn btn-ghost"
          style={{ padding: '2px 8px', fontSize: 11 }}
          disabled={yaAplicada}
          onClick={() => onUsar(sugerida)}
          title={sugerencia.motivo || 'Cantidad calculada con la demanda reciente'}
        >
          {yaAplicada ? <><Check size={11} /> Sugerida aplicada</> : <><Lightbulb size={11} /> Usar cantidad sugerida ({sugerida})</>}
        </button>
      )}
    </div>
  );
}

/**
 * Productos de ESTE proveedor que conviene reponer. `respuesta` es el cuerpo de
 * GET /pedidos/sugerencia; `onAplicar(item)` agrega el producto al pedido o
 * ajusta su cantidad a la sugerida.
 */
export function PanelSugerenciasProveedor({
  proveedorId, respuesta, cargando, disponible, itemsEnPedido, onAplicar,
}) {
  if (!proveedorId) return null;

  if (cargando) {
    return (
      <div className="card" style={{ padding: '10px 12px', marginBottom: 16, fontSize: 12, color: 'var(--text-muted)' }}>
        Calculando qué conviene pedir…
      </div>
    );
  }
  if (!disponible) return null;   // servicio de IA caído: el formulario sigue igual

  const sugeridos = sugerenciasDelProveedor(respuesta, proveedorId);
  const enPedido = s => itemsEnPedido.find(i => Number(i.repuesto_id) === Number(s.repuesto_id));
  const pendientes = sugeridos.filter(s => enPedido(s)?.cantidad !== s.cantidad);

  return (
    <div className="card" style={{ padding: '10px 12px', marginBottom: 16, background: 'var(--bg-secondary)' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)' }}>
          <Lightbulb size={13} color="var(--accent)" /> Sugerido para este proveedor
        </div>
        {pendientes.length > 1 && (
          <button
            type="button"
            className="btn btn-ghost"
            style={{ padding: '3px 10px', fontSize: 11 }}
            onClick={() => pendientes.forEach(onAplicar)}
          >
            <Plus size={11} /> Agregar todos ({pendientes.length})
          </button>
        )}
      </div>

      {sugeridos.length === 0 ? (
        <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          Según las ventas recientes, no hay productos de este proveedor que reponer.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 180, overflowY: 'auto' }}>
          {sugeridos.map(s => {
            const actual = enPedido(s);
            const aplicada = actual?.cantidad === s.cantidad;
            return (
              <div
                key={s.repuesto_id}
                title={s.motivo || undefined}
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
                    {s.nombre}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                    Stock {s.stock}
                    {s.en_transito > 0 ? ` · ${s.en_transito} en camino` : ''}
                    {s.punto_reorden != null ? ` · reorden en ${s.punto_reorden}` : ''}
                  </div>
                </div>
                <button
                  type="button"
                  className="btn btn-ghost"
                  style={{ padding: '4px 10px', fontSize: 12, flexShrink: 0 }}
                  disabled={aplicada}
                  onClick={() => onAplicar(s)}
                >
                  {aplicada
                    ? <><Check size={12} /> En el pedido</>
                    : <><Plus size={12} /> {actual ? `Usar ${s.cantidad} u.` : `Agregar ${s.cantidad} u.`}</>}
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

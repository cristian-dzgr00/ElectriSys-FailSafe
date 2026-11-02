// frontend/src/components/SugerenciaBusqueda.jsx
// "¿Quisiste decir «filtro de aceite»?" para las búsquedas de repuestos que no
// dieron resultados. La corrección la calcula el microservicio de NLP contra
// las palabras reales del catálogo (ver nlp-service/app/busqueda/corrector.py)
// y el backend la manda en `sugerencia_busqueda` solo si, con ella, la
// búsqueda sí encuentra algo.
//
// Es un botón y no un reemplazo automático: quien escribe decide. Si no hay
// sugerencia no renderiza nada.

import { CornerDownRight } from 'lucide-react';

/**
 * @param sugerencia { buscado, corregida, total } | null
 * @param textoActual lo que hay hoy en la caja; si ya no coincide con lo que se
 *                    buscó (el usuario siguió escribiendo) la sugerencia es vieja
 *                    y no se muestra, para no parpadear con datos caducos.
 * @param onAplicar  recibe el texto corregido para volver a buscar
 */
export default function SugerenciaBusqueda({ sugerencia, textoActual, onAplicar, style }) {
  if (!sugerencia?.corregida) return null;
  if (textoActual != null && sugerencia.buscado !== String(textoActual).trim()) return null;

  const n = Number(sugerencia.total) || 0;
  return (
    <div
      role="status"
      style={{ fontSize: 12, color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', ...style }}
    >
      <span>No hay resultados para «{sugerencia.buscado}».</span>
      <button
        type="button"
        onClick={() => onAplicar(sugerencia.corregida)}
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 4, padding: 0,
          background: 'none', border: 'none', cursor: 'pointer',
          color: 'var(--accent)', fontWeight: 600, fontSize: 12, textDecoration: 'underline',
        }}
      >
        <CornerDownRight size={12} /> ¿Quisiste decir «{sugerencia.corregida}»?
      </button>
      {n > 0 && <span style={{ color: 'var(--text-muted)' }}>({n} {n === 1 ? 'resultado' : 'resultados'})</span>}
    </div>
  );
}

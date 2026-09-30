// frontend/src/components/BuscadorRepuesto.jsx
// Lista de repuestos para agregar a una venta, con un botón de lupa que
// revela un campo de búsqueda (por nombre, proveedor o código) para
// filtrarla. Reemplaza al <select> que precargaba solo los primeros 15
// repuestos que devolvía GET /repuestos sin parámetros — con catálogos
// más grandes que eso, la mayoría ni aparecía en la lista.

import { useEffect, useRef, useState } from 'react';
import { Search, X } from 'lucide-react';
import { repuestosService } from '../services/ventasService';

const fmt = n => new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 }).format(n);

// campoPrecio: qué precio mostrar en la lista. Las ventas miran el precio
// de venta; los pedidos a proveedor, el de compra — mostrar el de venta al
// armar una orden de compra haría que se tipee el número equivocado.
export default function BuscadorRepuesto({ onSeleccionar, campoPrecio = 'precio_venta' }) {
  const [buscando, setBuscando]     = useState(false); // campo de texto visible
  const [texto, setTexto]           = useState('');
  const [productos, setProductos]   = useState([]);
  const [cargando, setCargando]     = useState(true);
  const inputRef = useRef(null);

  useEffect(() => {
    setCargando(true);
    const t = setTimeout(async () => {
      try {
        // Sin texto: catálogo completo (hasta el máximo que permite el
        // backend) para poder elegir a simple vista. Con texto: búsqueda
        // acotada por relevancia contra nombre/código/proveedor.
        const params = texto.trim() ? { q: texto, limit: 50 } : { limit: 100 };
        const r = await repuestosService.listar(params);
        setProductos(r.data.data ?? []);
      } finally {
        setCargando(false);
      }
    }, texto.trim() ? 300 : 0);
    return () => clearTimeout(t);
  }, [texto]);

  const abrirBusqueda = () => {
    setBuscando(true);
    setTimeout(() => inputRef.current?.focus(), 0);
  };

  const cerrarBusqueda = () => {
    setBuscando(false);
    setTexto('');
  };

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        {buscando ? (
          <div className="search-bar" style={{ flex: 1 }}>
            <Search size={14} className="search-icon" />
            <input
              ref={inputRef}
              className="form-control"
              style={{ width: '100%' }}
              placeholder="Buscar por nombre, proveedor o código…"
              value={texto}
              onChange={e => setTexto(e.target.value)}
            />
          </div>
        ) : (
          <span style={{ flex: 1, fontSize: 12, color: 'var(--text-muted)' }}>
            Elegí un producto de la lista, o buscá uno específico
          </span>
        )}
        <button
          type="button"
          className="btn-icon"
          onClick={buscando ? cerrarBusqueda : abrirBusqueda}
          title={buscando ? 'Cerrar búsqueda' : 'Buscar producto'}
        >
          {buscando ? <X size={14} /> : <Search size={14} />}
        </button>
      </div>

      <div style={{
        border: '1px solid var(--border)', borderRadius: 'var(--radius)',
        maxHeight: 220, overflowY: 'auto',
      }}>
        {cargando && (
          <div style={{ padding: '10px 12px', fontSize: 12, color: 'var(--text-muted)' }}>Cargando…</div>
        )}
        {!cargando && productos.length === 0 && (
          <div style={{ padding: '10px 12px', fontSize: 12, color: 'var(--text-muted)' }}>Sin resultados</div>
        )}
        {!cargando && productos.map(r => (
          <button
            key={r.id}
            type="button"
            onClick={() => onSeleccionar(r)}
            style={{
              display: 'block', width: '100%', textAlign: 'left', padding: '8px 12px',
              background: 'none', border: 'none', borderBottom: '1px solid var(--border)', cursor: 'pointer',
              color: 'var(--text-primary)',
            }}
            onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-hover)'; }}
            onMouseLeave={e => { e.currentTarget.style.background = 'none'; }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: 13 }}>
              <span style={{ fontWeight: 600 }}>{r.nombre}</span>
              <span style={{ color: 'var(--accent)', fontWeight: 600 }}>{fmt(r[campoPrecio])}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 2, fontSize: 11, color: 'var(--text-muted)' }}>
              <span>{r.codigo}{r.proveedor ? ` · ${r.proveedor}` : ''}</span>
              <span>Stock: {r.stock}</span>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

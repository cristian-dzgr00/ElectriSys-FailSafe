// frontend/src/services/sugerenciasIa.js
// Lógica pura (sin React ni red) de las sugerencias de IA de las pantallas de
// operación: complementos en ventas/cotizaciones y cantidad sugerida en
// pedidos. Está separada de los componentes para poder probarla sin navegador.

// ── "También suelen llevar" (reglas de asociación) ──────────────────────

export const MAX_COMPLEMENTOS = 3;

/**
 * Deja hasta `max` complementos mostrables: sin repetidos, sin lo que ya está
 * en el carrito y sin agotados (el backend ya filtra el stock, pero el
 * carrito cambia entre que se pide y se responde, y el stock puede haber
 * llegado en cero por una venta simultánea).
 *
 * @param {{data?: Array}|null|undefined} respuesta cuerpo de GET /ventas/complementos
 * @param {Array<number|string>} idsEnCarrito
 */
export function seleccionarComplementos(respuesta, idsEnCarrito, max = MAX_COMPLEMENTOS) {
  const lista = Array.isArray(respuesta?.data) ? respuesta.data : [];
  const enCarrito = new Set((idsEnCarrito ?? []).map(Number));
  const vistos = new Set();
  const salida = [];

  for (const c of lista) {
    const id = Number(c?.id);
    if (!Number.isFinite(id) || enCarrito.has(id) || vistos.has(id)) continue;
    if (!(Number(c.stock) > 0)) continue;
    vistos.add(id);
    salida.push(c);
    if (salida.length >= max) break;
  }
  return salida;
}

/** "Se lleva junto en 4 ventas", o null si no hay dato que respalde la frase. */
export function textoSeLlevaJunto(complemento) {
  const n = Math.round(Number(complemento?.veces_juntos) || 0);
  if (n <= 0) return null;
  return n === 1 ? 'Se lleva junto en 1 venta' : `Se lleva junto en ${n} ventas`;
}

/** Detalle técnico para el tooltip: confianza y lift de la regla. */
export function detalleAsociacion(complemento) {
  const partes = [];
  const confianza = Number(complemento?.confianza);
  if (confianza > 0) partes.push(`En ${Math.round(confianza * 100)}% de las ventas con el producto de arriba`);
  const lift = Number(complemento?.lift);
  if (lift > 0) partes.push(`lift ${lift.toFixed(1)}`);
  return partes.join(' · ');
}

// ── Cantidad sugerida en pedidos a proveedor ────────────────────────────

export const SENALES = {
  reabastecer:   { texto: 'Reabastecer',    clase: 'badge-danger',  ayuda: 'Al ritmo de venta reciente el stock se agota pronto.' },
  rotacion_baja: { texto: 'Rotación baja',  clase: 'badge-warning', ayuda: 'Hay inventario para mucho tiempo: pedir más inmoviliza dinero.' },
  normal:        { texto: 'Stock normal',   clase: 'badge-success', ayuda: 'El stock cubre el período de cobertura.' },
  sin_datos:     { texto: 'Sin historial',  clase: 'badge-neutral', ayuda: 'No hay ventas recientes para estimar la demanda.' },
};

export function infoSenal(senal) {
  return SENALES[senal] ?? SENALES.sin_datos;
}

/**
 * Indexa por repuesto_id la respuesta de GET /pedidos/sugerencia/items.
 * Devuelve {} si el servicio de IA no estaba disponible: así quien consume
 * nunca tiene que distinguir "sin datos" de "servicio caído" para dibujar.
 */
export function indexarSugerencias(respuesta) {
  if (!respuesta || respuesta.disponible === false || !Array.isArray(respuesta.data)) return {};
  const mapa = {};
  for (const s of respuesta.data) {
    if (s?.repuesto_id != null) mapa[s.repuesto_id] = s;
  }
  return mapa;
}

/** Cantidad a usar con el botón "usar sugerida", o null si no hay nada que sugerir. */
export function cantidadUsable(sugerencia) {
  if (!sugerencia?.necesita_reabastecer) return null;
  const n = Math.floor(Number(sugerencia.cantidad_sugerida));
  return Number.isFinite(n) && n > 0 ? n : null;
}

/** Línea corta con el porqué: stock actual, punto de reorden, demanda semanal. */
export function resumenSugerencia(sugerencia) {
  if (!sugerencia) return '';
  const partes = [];
  if (sugerencia.stock_actual != null) partes.push(`Stock ${Number(sugerencia.stock_actual)}`);
  if (Number(sugerencia.en_transito) > 0) partes.push(`${Number(sugerencia.en_transito)} en camino`);
  if (sugerencia.punto_reorden != null) partes.push(`reorden en ${Number(sugerencia.punto_reorden)}`);
  const demanda = Number(sugerencia.demanda_semanal_estimada);
  partes.push(demanda > 0 ? `~${demanda.toFixed(1)} u./semana` : 'sin ventas recientes');
  return partes.join(' · ');
}

/** Sugerencias del proveedor elegido, a partir de GET /pedidos/sugerencia (agrupada por proveedor). */
export function sugerenciasDelProveedor(respuesta, proveedorId) {
  if (!respuesta || respuesta.disponible === false || !Array.isArray(respuesta.data)) return [];
  const grupo = respuesta.data.find(g => String(g.proveedor_id) === String(proveedorId));
  return Array.isArray(grupo?.items) ? grupo.items : [];
}

/**
 * Aplica una cantidad a la lista de ítems del pedido: si el producto ya está
 * se REEMPLAZA su cantidad (no se suma: sumar dejaría pedir el doble al pulsar
 * dos veces); si no está, se agrega con esa cantidad.
 */
export function aplicarCantidad(items, { repuesto_id, nombre, precio_unit }, cantidad) {
  const cant = Math.max(1, Math.floor(Number(cantidad)) || 1);
  // Number(): según el driver, el id llega como número o como texto.
  const idx = items.findIndex(i => Number(i.repuesto_id) === Number(repuesto_id));
  if (idx >= 0) {
    const copia = [...items];
    copia[idx] = { ...copia[idx], cantidad: cant };
    return copia;
  }
  return [...items, { repuesto_id, nombre, cantidad: cant, precio_unit: Number(precio_unit) || 0 }];
}

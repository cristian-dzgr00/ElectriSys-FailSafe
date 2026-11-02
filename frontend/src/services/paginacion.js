// Trae TODAS las filas de un listado paginado del backend.
//
// Los listados (/ventas, /repuestos…) devuelven como máximo 100 filas por
// llamada aunque se pida más (`limit: 500` se recorta en silencio). Una pantalla
// que necesita el conjunto completo —por ejemplo Reportes con un rango de
// fechas— debe recorrer las páginas; si no, trabaja con las 100 más recientes y
// "no hay ventas" en cualquier fecha anterior.

/**
 * @param {(params: object) => Promise<{data: {data: any[], total?: number, limit?: number}}>} pedirPagina
 *        función que hace la llamada (p. ej. `p => ventasService.listar(p)`)
 * @param {object}  [opciones]
 * @param {object}  [opciones.filtros]    parámetros fijos de cada llamada (desde, hasta, estado…)
 * @param {number}  [opciones.limite=100] filas pedidas por página (el servidor puede recortarlas)
 * @param {number}  [opciones.maxPaginas=100] tope de seguridad contra un servidor que ignore `page`
 * @returns {Promise<any[]>} todas las filas, en el orden en que las entrega el servidor
 */
export async function traerTodasLasPaginas(pedirPagina, { filtros = {}, limite = 100, maxPaginas = 100 } = {}) {
  const acumuladas = [];
  for (let page = 1; page <= maxPaginas; page++) {
    const { data } = await pedirPagina({ ...filtros, page, limit: limite });
    const filas = Array.isArray(data?.data) ? data.data : [];
    acumuladas.push(...filas);
    const total = Number(data?.total);
    if (filas.length === 0 || (Number.isFinite(total) && acumuladas.length >= total)) break;
  }
  return acumuladas;
}

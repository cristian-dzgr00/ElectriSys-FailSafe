import { describe, expect, it, vi } from 'vitest';
import { traerTodasLasPaginas } from './paginacion';

// Simula una API paginada que responde como axios: { data: { data: [...], total } }.
const apiDe = (filas, tope = 100) => vi.fn(async ({ page, limit }) => {
  const l = Math.min(limit, tope);
  return { data: { data: filas.slice((page - 1) * l, page * l), total: filas.length, page, limit: l } };
});
const filas = n => Array.from({ length: n }, (_, i) => ({ id: i + 1 }));

describe('traerTodasLasPaginas', () => {
  it('une todas las páginas aunque el servidor recorte el límite pedido', async () => {
    const pedir = apiDe(filas(338));
    const todas = await traerTodasLasPaginas(pedir, { limite: 500 });
    expect(todas).toHaveLength(338);
    expect(todas[0].id).toBe(1);
    expect(todas[337].id).toBe(338);
    expect(pedir).toHaveBeenCalledTimes(4); // 100 + 100 + 100 + 38
  });

  it('con menos filas que una página hace una sola llamada', async () => {
    const pedir = apiDe(filas(7));
    expect(await traerTodasLasPaginas(pedir)).toHaveLength(7);
    expect(pedir).toHaveBeenCalledTimes(1);
  });

  it('sin filas devuelve una lista vacía', async () => {
    expect(await traerTodasLasPaginas(apiDe([]))).toEqual([]);
  });

  it('pasa los filtros en cada página', async () => {
    const pedir = apiDe(filas(150));
    await traerTodasLasPaginas(pedir, { filtros: { desde: '2026-08-01', hasta: '2026-08-31' } });
    for (const [args] of pedir.mock.calls) {
      expect(args).toMatchObject({ desde: '2026-08-01', hasta: '2026-08-31' });
    }
    expect(pedir.mock.calls.map(([a]) => a.page)).toEqual([1, 2]);
  });

  it('no entra en un bucle infinito si el servidor ignora la página', async () => {
    const siempreLoMismo = vi.fn(async () => ({ data: { data: filas(100), total: 100000 } }));
    const todas = await traerTodasLasPaginas(siempreLoMismo, { maxPaginas: 5 });
    expect(siempreLoMismo).toHaveBeenCalledTimes(5);
    expect(todas).toHaveLength(500);
  });

  it('propaga el error de una página en vez de devolver datos incompletos', async () => {
    const pedir = vi.fn()
      .mockResolvedValueOnce({ data: { data: filas(100), total: 250 } })
      .mockRejectedValueOnce(new Error('503'));
    await expect(traerTodasLasPaginas(pedir)).rejects.toThrow('503');
  });
});

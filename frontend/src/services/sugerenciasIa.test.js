import { describe, expect, it } from 'vitest';
import {
  aplicarCantidad, cantidadUsable, detalleAsociacion, indexarSugerencias, infoSenal,
  resumenSugerencia, seleccionarComplementos, sugerenciasDelProveedor, textoSeLlevaJunto,
} from './sugerenciasIa';

const comp = (id, extra = {}) => ({ id, nombre: `P${id}`, stock: 5, precio_venta: 1000, veces_juntos: 3, ...extra });

describe('seleccionarComplementos', () => {
  it('devuelve como máximo 3', () => {
    const r = seleccionarComplementos({ data: [1, 2, 3, 4, 5].map(i => comp(i)) }, []);
    expect(r.map(c => c.id)).toEqual([1, 2, 3]);
  });

  it('excluye lo que ya está en el carrito (ids numéricos o texto)', () => {
    const r = seleccionarComplementos({ data: [comp(1), comp(2), comp(3)] }, [1, '3']);
    expect(r.map(c => c.id)).toEqual([2]);
  });

  it('excluye agotados y sin stock informado', () => {
    const r = seleccionarComplementos({ data: [comp(1, { stock: 0 }), comp(2, { stock: undefined }), comp(3)] }, []);
    expect(r.map(c => c.id)).toEqual([3]);
  });

  it('descarta repetidos y filas rotas', () => {
    const r = seleccionarComplementos({ data: [comp(1), comp(1), null, { nombre: 'sin id', stock: 3 }, comp(2)] }, []);
    expect(r.map(c => c.id)).toEqual([1, 2]);
  });

  it.each([undefined, null, {}, { data: null }, { data: 'x' }, { data: [] }])(
    'respuesta vacía o inválida (%j) no rompe y no muestra nada',
    respuesta => {
      expect(seleccionarComplementos(respuesta, [1])).toEqual([]);
    },
  );

  it('con el carrito indefinido tampoco rompe', () => {
    expect(seleccionarComplementos({ data: [comp(1)] }, undefined)).toHaveLength(1);
  });
});

describe('textoSeLlevaJunto / detalleAsociacion', () => {
  it('pluraliza', () => {
    expect(textoSeLlevaJunto({ veces_juntos: 1 })).toBe('Se lleva junto en 1 venta');
    expect(textoSeLlevaJunto({ veces_juntos: 7 })).toBe('Se lleva junto en 7 ventas');
  });

  it('no inventa la frase sin dato', () => {
    expect(textoSeLlevaJunto({})).toBeNull();
    expect(textoSeLlevaJunto({ veces_juntos: 0 })).toBeNull();
    expect(textoSeLlevaJunto(null)).toBeNull();
  });

  it('arma el detalle con confianza y lift', () => {
    expect(detalleAsociacion({ confianza: 0.62, lift: 2.345 })).toBe('En 62% de las ventas con el producto de arriba · lift 2.3');
    expect(detalleAsociacion({})).toBe('');
  });
});

describe('señales y cantidad sugerida', () => {
  const sug = {
    repuesto_id: 7, senal: 'reabastecer', necesita_reabastecer: true, cantidad_sugerida: 12,
    stock_actual: 3, en_transito: 0, punto_reorden: 9.5, demanda_semanal_estimada: 4.25,
  };

  it('traduce cada señal y cae a "sin historial" con una desconocida', () => {
    expect(infoSenal('reabastecer').clase).toBe('badge-danger');
    expect(infoSenal('rotacion_baja').clase).toBe('badge-warning');
    expect(infoSenal('normal').clase).toBe('badge-success');
    expect(infoSenal('inventada').texto).toBe('Sin historial');
    expect(infoSenal(undefined).texto).toBe('Sin historial');
  });

  it('indexa por id', () => {
    const mapa = indexarSugerencias({ disponible: true, data: [sug, { repuesto_id: 8, senal: 'normal' }] });
    expect(Object.keys(mapa)).toEqual(['7', '8']);
    expect(mapa[7].cantidad_sugerida).toBe(12);
  });

  it('con el servicio caído (disponible:false) o respuesta rota no hay sugerencias', () => {
    expect(indexarSugerencias({ disponible: false, data: [sug] })).toEqual({});
    expect(indexarSugerencias(null)).toEqual({});
    expect(indexarSugerencias({ data: 'x' })).toEqual({});
  });

  it('cantidadUsable solo existe si hace falta reabastecer y la cantidad es positiva', () => {
    expect(cantidadUsable(sug)).toBe(12);
    expect(cantidadUsable({ ...sug, necesita_reabastecer: false })).toBeNull();
    expect(cantidadUsable({ ...sug, cantidad_sugerida: 0 })).toBeNull();
    expect(cantidadUsable({ ...sug, cantidad_sugerida: 'abc' })).toBeNull();
    expect(cantidadUsable({ ...sug, cantidad_sugerida: 7.9 })).toBe(7);
    expect(cantidadUsable(undefined)).toBeNull();
  });

  it('resume el porqué con stock, reorden y demanda', () => {
    expect(resumenSugerencia(sug)).toBe('Stock 3 · reorden en 9.5 · ~4.3 u./semana');
    expect(resumenSugerencia({ stock_actual: 0, en_transito: 5, demanda_semanal_estimada: 0 }))
      .toBe('Stock 0 · 5 en camino · sin ventas recientes');
    expect(resumenSugerencia(null)).toBe('');
  });
});

describe('sugerenciasDelProveedor', () => {
  const resp = {
    disponible: true,
    data: [
      { proveedor_id: 1, items: [{ repuesto_id: 10 }, { repuesto_id: 11 }] },
      { proveedor_id: 2, items: [{ repuesto_id: 20 }] },
    ],
  };

  it('filtra por proveedor (id numérico o texto del <select>)', () => {
    expect(sugerenciasDelProveedor(resp, '1')).toHaveLength(2);
    expect(sugerenciasDelProveedor(resp, 2)).toHaveLength(1);
  });

  it('proveedor sin sugerencias, vacío o servicio caído', () => {
    expect(sugerenciasDelProveedor(resp, 99)).toEqual([]);
    expect(sugerenciasDelProveedor(resp, '')).toEqual([]);
    expect(sugerenciasDelProveedor({ ...resp, disponible: false }, 1)).toEqual([]);
    expect(sugerenciasDelProveedor(null, 1)).toEqual([]);
  });
});

describe('aplicarCantidad', () => {
  const base = [{ repuesto_id: 1, nombre: 'A', cantidad: 2, precio_unit: 100 }];

  it('reemplaza la cantidad de un ítem existente (no la suma)', () => {
    const r = aplicarCantidad(base, { repuesto_id: 1, nombre: 'A', precio_unit: 100 }, 12);
    expect(r).toEqual([{ repuesto_id: 1, nombre: 'A', cantidad: 12, precio_unit: 100 }]);
    expect(base[0].cantidad).toBe(2);            // no muta el original
    const dos = aplicarCantidad(r, { repuesto_id: 1, nombre: 'A', precio_unit: 100 }, 12);
    expect(dos[0].cantidad).toBe(12);            // idempotente
  });

  it('agrega el ítem nuevo con la cantidad sugerida', () => {
    const r = aplicarCantidad(base, { repuesto_id: 2, nombre: 'B', precio_unit: '250' }, 5);
    expect(r[1]).toEqual({ repuesto_id: 2, nombre: 'B', cantidad: 5, precio_unit: 250 });
  });

  it('nunca deja una cantidad menor que 1', () => {
    expect(aplicarCantidad([], { repuesto_id: 3, nombre: 'C', precio_unit: 1 }, 0)[0].cantidad).toBe(1);
    expect(aplicarCantidad([], { repuesto_id: 3, nombre: 'C', precio_unit: 1 }, -4)[0].cantidad).toBe(1);
    expect(aplicarCantidad([], { repuesto_id: 3, nombre: 'C', precio_unit: 1 }, 'x')[0].cantidad).toBe(1);
  });
});

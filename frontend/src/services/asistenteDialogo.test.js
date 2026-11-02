import { describe, expect, it } from 'vitest';
import { agruparSugerencias, contextoPendienteDe, placeholderDe } from './asistenteDialogo';

describe('contextoPendienteDe', () => {
  it('es null cuando la respuesta ya fue completa', () => {
    expect(contextoPendienteDe({ esperando_datos: false, entidades: { marca: 'Toyota' } })).toBeNull();
    expect(contextoPendienteDe(undefined)).toBeNull();
    expect(contextoPendienteDe({})).toBeNull();
  });

  it('reenvía las entidades y la intención pendiente', () => {
    const ctx = contextoPendienteDe({
      esperando_datos: true,
      entidades: { categoria: 'Filtros', marca: null },
      intencion_pendiente: 'buscar_repuesto',
    });
    expect(ctx).toEqual({
      entidades: { categoria: 'Filtros', marca: null, _intencion_pendiente: 'buscar_repuesto' },
    });
  });

  it('con un microservicio viejo (sin intención pendiente) sigue funcionando', () => {
    const ctx = contextoPendienteDe({ esperando_datos: true, entidades: { categoria: 'Filtros' } });
    expect(ctx).toEqual({ entidades: { categoria: 'Filtros' } });
  });

  it('no muta la respuesta original', () => {
    const data = { esperando_datos: true, entidades: { a: 1 }, intencion_pendiente: 'buscar_repuesto' };
    contextoPendienteDe(data);
    expect(data.entidades).toEqual({ a: 1 });
  });

  it('tolera esperando_datos sin entidades', () => {
    expect(contextoPendienteDe({ esperando_datos: true })).toEqual({ entidades: {} });
  });
});

describe('agruparSugerencias', () => {
  it('separa confirmadas de no confirmadas', () => {
    const r = agruparSugerencias([
      { id: 1, compatibilidad_confirmada: true },
      { id: 2, compatibilidad_confirmada: false },
      { id: 3 },
    ]);
    expect(r.confirmadas.map(s => s.id)).toEqual([1, 3]);
    expect(r.noConfirmadas.map(s => s.id)).toEqual([2]);
  });

  it.each([undefined, null, 'x', {}])('entrada inválida (%j) da listas vacías', entrada => {
    expect(agruparSugerencias(entrada)).toEqual({ confirmadas: [], noConfirmadas: [] });
  });
});

describe('placeholderDe', () => {
  it('es el normal sin pregunta pendiente', () => {
    expect(placeholderDe(null, [])).toBe('Escribe tu consulta…');
  });

  it('pide solo lo que falta', () => {
    const ctx = { entidades: {} };
    expect(placeholderDe(ctx, ['modelo'])).toBe('Responde con el modelo del vehículo…');
    expect(placeholderDe(ctx, ['marca'])).toBe('Responde con la marca del vehículo…');
    expect(placeholderDe(ctx, ['marca', 'modelo'])).toBe('Responde con la marca y el modelo…');
    expect(placeholderDe(ctx, undefined)).toBe('Responde con la marca y el modelo…');
  });
});

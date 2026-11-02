import { describe, expect, it } from 'vitest';
import { detectarDatosPersonales, mensajeDatosPersonales } from './datosPersonales';

describe('detectarDatosPersonales', () => {
  it.each([
    'llamar al 3001234567 por el filtro',
    'cliente 300 123 4567 pide pastillas',
    'whatsapp +57 300-123-4567 ok',
    'cedula 1.234.567.890 del cliente',
    'cc 12345678',
    'tel 5551234',
  ])('detecta un número parecido a teléfono o cédula: %s', texto => {
    const r = detectarDatosPersonales(texto);
    expect(r.numero).toBe(true);
    expect(r.hay).toBe(true);
  });

  it.each([
    'mandar a juan.perez@correo.com gracias',
    'ana_r+pos@mail.empresa.co.uk',
  ])('detecta un correo: %s', texto => {
    const r = detectarDatosPersonales(texto);
    expect(r.correo).toBe(true);
    expect(r.hay).toBe(true);
  });

  it.each([
    'No hay filtro de aceite para Toyota Hilux 2.7 gasolina 2024, ¿qué recomiendo?',
    'cuantas unidades hay del filtro 90915-YZZD4',
    'precio del M1-102',
    'codigo 123456',
    'pastillas corolla 1.8 2015 2019',
    'hilux 2015 2019',
    'hilux 2015-2022',
    'quiero 20 unidades a 35000',
    '',
  ])('no avisa en una consulta normal: %s', texto => {
    expect(detectarDatosPersonales(texto).hay).toBe(false);
  });

  it('tolera entradas que no son texto', () => {
    expect(detectarDatosPersonales(undefined).hay).toBe(false);
    expect(detectarDatosPersonales(null).hay).toBe(false);
    expect(detectarDatosPersonales(12345678).numero).toBe(true);
  });

  it('no se cuelga con un texto larguísimo', () => {
    const largo = 'filtro de aceite 3001234567 '.repeat(5000);
    const inicio = Date.now();
    expect(detectarDatosPersonales(largo).numero).toBe(true);
    expect(Date.now() - inicio).toBeLessThan(2000);
  });
});

describe('mensajeDatosPersonales', () => {
  it('es null cuando no hay nada', () => {
    expect(mensajeDatosPersonales(detectarDatosPersonales('filtro de aceite'))).toBeNull();
    expect(mensajeDatosPersonales(undefined)).toBeNull();
  });

  it('nombra lo que se detectó', () => {
    expect(mensajeDatosPersonales(detectarDatosPersonales('a@b.co'))).toContain('correo');
    expect(mensajeDatosPersonales(detectarDatosPersonales('3001234567'))).toContain('teléfono o cédula');
    expect(mensajeDatosPersonales(detectarDatosPersonales('a@b.co 3001234567'))).toContain('un correo y un número');
  });
});

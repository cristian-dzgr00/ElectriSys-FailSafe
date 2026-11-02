// Pruebas de render (react-dom/server, sin navegador) de las piezas de
// sugerencias. No ejercitan efectos ni clics —eso lo cubren las pruebas de la
// lógica pura en src/services— sino que lo pintado sea el esperado y que los
// estados vacíos / servicio caído no rompan ni dibujen nada de más.

import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import SugerenciaBusqueda from './SugerenciaBusqueda';
import { PanelSugerenciasProveedor, SenalBadge, SugeridoDeItem } from './SugerenciasPedido';

const sugerencia = {
  repuesto_id: 7, senal: 'reabastecer', necesita_reabastecer: true, cantidad_sugerida: 12,
  stock_actual: 3, en_transito: 0, punto_reorden: 9.5, demanda_semanal_estimada: 4.25,
  motivo: 'Se venden ~4.3 u./semana y quedan 3.',
};

describe('SugerenciaBusqueda', () => {
  const sug = { buscado: 'filtro acite', corregida: 'filtro aceite', total: 4 };

  it('ofrece la corrección como botón', () => {
    const html = renderToStaticMarkup(<SugerenciaBusqueda sugerencia={sug} textoActual="filtro acite" onAplicar={() => {}} />);
    expect(html).toContain('¿Quisiste decir «filtro aceite»?');
    expect(html).toContain('<button');
    expect(html).toContain('(4 resultados)');
  });

  it('no dibuja nada sin sugerencia', () => {
    expect(renderToStaticMarkup(<SugerenciaBusqueda sugerencia={null} onAplicar={() => {}} />)).toBe('');
    expect(renderToStaticMarkup(<SugerenciaBusqueda sugerencia={{ corregida: '' }} onAplicar={() => {}} />)).toBe('');
  });

  it('oculta una sugerencia vieja si el usuario ya siguió escribiendo', () => {
    const html = renderToStaticMarkup(<SugerenciaBusqueda sugerencia={sug} textoActual="filtro acite de" onAplicar={() => {}} />);
    expect(html).toBe('');
  });

  it('singulariza un único resultado', () => {
    const html = renderToStaticMarkup(
      <SugerenciaBusqueda sugerencia={{ ...sug, total: 1 }} onAplicar={() => {}} />,
    );
    expect(html).toContain('(1 resultado)');
  });
});

describe('SenalBadge / SugeridoDeItem', () => {
  it('pinta la señal con su clase y el motivo en el tooltip', () => {
    const html = renderToStaticMarkup(<SenalBadge sugerencia={sugerencia} />);
    expect(html).toContain('badge-danger');
    expect(html).toContain('Reabastecer');
    expect(html).toContain('title="');
    expect(html).toContain('quedan 3');
  });

  it('ofrece usar la cantidad sugerida y explica el porqué', () => {
    const html = renderToStaticMarkup(<SugeridoDeItem sugerencia={sugerencia} cantidadActual={1} onUsar={() => {}} />);
    expect(html).toContain('Usar cantidad sugerida (12)');
    expect(html).toContain('Stock 3');
    expect(html).toContain('~4.3 u./semana');
  });

  it('cuando la cantidad ya es la sugerida lo indica y deshabilita el botón', () => {
    const html = renderToStaticMarkup(<SugeridoDeItem sugerencia={sugerencia} cantidadActual={12} onUsar={() => {}} />);
    expect(html).toContain('Sugerida aplicada');
    expect(html).toContain('disabled');
  });

  it('un producto con stock normal muestra la señal pero ningún botón', () => {
    const normal = { ...sugerencia, senal: 'normal', necesita_reabastecer: false, cantidad_sugerida: 0 };
    const html = renderToStaticMarkup(<SugeridoDeItem sugerencia={normal} cantidadActual={1} onUsar={() => {}} />);
    expect(html).toContain('badge-success');
    expect(html).not.toContain('<button');
  });

  it('sin sugerencia (servicio caído) no dibuja nada', () => {
    expect(renderToStaticMarkup(<SugeridoDeItem sugerencia={undefined} cantidadActual={1} onUsar={() => {}} />)).toBe('');
  });
});

describe('PanelSugerenciasProveedor', () => {
  const respuesta = {
    disponible: true,
    data: [{
      proveedor_id: 1,
      items: [
        { repuesto_id: 7, nombre: 'Pastilla delantera', stock: 3, en_transito: 0, punto_reorden: 9.5, cantidad: 12, precio_unit: 5000, motivo: 'x' },
        { repuesto_id: 8, nombre: 'Disco de freno', stock: 1, en_transito: 4, punto_reorden: 6, cantidad: 6, precio_unit: 9000, motivo: 'y' },
      ],
    }],
  };
  const base = { proveedorId: '1', respuesta, cargando: false, disponible: true, itemsEnPedido: [], onAplicar: () => {} };

  it('lista los productos del proveedor con su cantidad sugerida', () => {
    const html = renderToStaticMarkup(<PanelSugerenciasProveedor {...base} />);
    expect(html).toContain('Sugerido para este proveedor');
    expect(html).toContain('Agregar 12 u.');
    expect(html).toContain('Agregar 6 u.');
    expect(html).toContain('Agregar todos (2)');
    expect(html).toContain('4 en camino');
  });

  it('si el producto ya está en el pedido ofrece ajustar la cantidad', () => {
    const html = renderToStaticMarkup(
      <PanelSugerenciasProveedor {...base} itemsEnPedido={[{ repuesto_id: '7', cantidad: 1 }, { repuesto_id: 8, cantidad: 6 }]} />,
    );
    expect(html).toContain('Usar 12 u.');
    expect(html).toContain('En el pedido');
    expect(html).not.toContain('Agregar todos');
  });

  it('sin proveedor elegido no dibuja nada', () => {
    expect(renderToStaticMarkup(<PanelSugerenciasProveedor {...base} proveedorId="" />)).toBe('');
  });

  it('con el servicio de IA caído no dibuja nada (el formulario sigue igual)', () => {
    expect(renderToStaticMarkup(<PanelSugerenciasProveedor {...base} disponible={false} />)).toBe('');
  });

  it('mientras calcula avisa; sin pendientes lo dice', () => {
    expect(renderToStaticMarkup(<PanelSugerenciasProveedor {...base} cargando />)).toContain('Calculando');
    const vacio = renderToStaticMarkup(<PanelSugerenciasProveedor {...base} proveedorId="99" />);
    expect(vacio).toContain('no hay productos de este proveedor que reponer');
  });
});

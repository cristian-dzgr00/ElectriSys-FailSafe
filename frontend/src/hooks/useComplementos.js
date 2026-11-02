// frontend/src/hooks/useComplementos.js
// "También suelen llevar": pide al backend los productos que se venden junto
// a los del carrito y devuelve hasta 3 listos para mostrar.
//
// Decisiones para que se sienta como un extra y no como una carga:
//  - Debounce: agregar tres productos seguidos hace UNA llamada, no tres.
//  - Se conserva la respuesta anterior mientras llega la nueva (sin parpadeo),
//    y lo que ya está en el carrito se descarta al instante en cliente.
//  - Cualquier error se traga: la venta no puede depender de una sugerencia.

import { useEffect, useMemo, useState } from 'react';
import { ventasService } from '../services/ventasService';
import { seleccionarComplementos } from '../services/sugerenciasIa';

const ESPERA_MS = 450;

export function useComplementos(idsEnCarrito, { activo = true, esperaMs = ESPERA_MS } = {}) {
  const [respuesta, setRespuesta] = useState(null);

  // Clave estable: ordenada y sin repetidos, para que cambiar solo la
  // cantidad de una línea (mismos productos) no dispare otra llamada.
  const clave = useMemo(() => {
    const unicos = [...new Set((idsEnCarrito ?? []).map(Number).filter(Number.isFinite))];
    return unicos.sort((a, b) => a - b).join(',');
  }, [idsEnCarrito]);

  useEffect(() => {
    if (!activo || !clave) {
      setRespuesta(null);
      return undefined;
    }
    let vigente = true;
    const temporizador = setTimeout(async () => {
      try {
        const r = await ventasService.complementos(clave.split(','));
        if (vigente) setRespuesta(r.data);
      } catch {
        if (vigente) setRespuesta(null);
      }
    }, esperaMs);
    return () => {
      vigente = false;          // una respuesta tardía de un carrito viejo se ignora
      clearTimeout(temporizador);
    };
  }, [clave, activo, esperaMs]);

  return useMemo(
    () => seleccionarComplementos(respuesta, idsEnCarrito),
    [respuesta, idsEnCarrito],
  );
}

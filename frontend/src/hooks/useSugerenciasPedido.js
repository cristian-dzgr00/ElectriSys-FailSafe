// frontend/src/hooks/useSugerenciasPedido.js
// Datos de IA para el formulario "Nuevo pedido a proveedor". Ambos hooks
// degradan igual: si el microservicio no contesta (o el backend responde
// disponible:false) devuelven vacío y el formulario funciona sin sugerencias.

import { useEffect, useMemo, useState } from 'react';
import { pedidosService } from '../services/pedidosService';
import { indexarSugerencias } from '../services/sugerenciasIa';

const ESPERA_MS = 350;

/**
 * Señal y cantidad sugerida de los productos que ya están en el pedido.
 * Devuelve { porId, cargando, disponible }.
 */
export function useSugerenciasDeItems(idsEnPedido, { activo = true, esperaMs = ESPERA_MS } = {}) {
  const [respuesta, setRespuesta] = useState(null);
  const [cargando, setCargando] = useState(false);

  const clave = useMemo(() => {
    const unicos = [...new Set((idsEnPedido ?? []).map(Number).filter(Number.isFinite))];
    return unicos.sort((a, b) => a - b).join(',');
  }, [idsEnPedido]);

  useEffect(() => {
    if (!activo || !clave) {
      setRespuesta(null);
      setCargando(false);
      return undefined;
    }
    let vigente = true;
    setCargando(true);
    const temporizador = setTimeout(async () => {
      try {
        const r = await pedidosService.sugerenciaItems(clave.split(','));
        if (vigente) setRespuesta(r.data);
      } catch {
        if (vigente) setRespuesta(null);
      } finally {
        if (vigente) setCargando(false);
      }
    }, esperaMs);
    return () => {
      vigente = false;
      clearTimeout(temporizador);
    };
  }, [clave, activo, esperaMs]);

  const porId = useMemo(() => indexarSugerencias(respuesta), [respuesta]);
  return { porId, cargando, disponible: respuesta ? respuesta.disponible !== false : true };
}

/**
 * Sugerencias de reabastecimiento agrupadas por proveedor; se piden una sola
 * vez cada vez que se abre el formulario (es un cálculo sobre todo el
 * inventario, no algo para repetir con cada tecla).
 * Devuelve { respuesta, cargando, disponible }.
 */
export function useSugerenciasPorProveedor(activo) {
  const [respuesta, setRespuesta] = useState(null);
  const [cargando, setCargando] = useState(false);
  const [fallo, setFallo] = useState(false);

  useEffect(() => {
    if (!activo) return undefined;
    let vigente = true;
    setCargando(true);
    setFallo(false);
    setRespuesta(null);
    pedidosService.sugerencias()
      .then(r => { if (vigente) setRespuesta(r.data); })
      .catch(() => { if (vigente) setFallo(true); })
      .finally(() => { if (vigente) setCargando(false); });
    return () => { vigente = false; };
  }, [activo]);

  return {
    respuesta,
    cargando,
    disponible: !fallo && (respuesta ? respuesta.disponible !== false : true),
  };
}

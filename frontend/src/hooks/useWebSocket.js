// frontend/src/hooks/useWebSocket.js
// Hook para conectarse al servidor WebSocket de ElectriSys.
// Reconecta automáticamente con backoff exponencial.

import { useEffect, useRef, useCallback, useState } from 'react';

const MAX_RETRIES     = 5;
const BASE_RETRY_MS   = 1_000;

/**
 * URL del WebSocket derivada del host que sirve la página.
 *
 * Antes era un literal 'ws://localhost:8080': el navegador de cada usuario
 * intentaba conectarse a SU PROPIA máquina, así que las notificaciones solo
 * funcionaban en la PC de desarrollo. Usando location.host se conecta al
 * mismo servidor que sirvió la app, a través del proxy /ws de nginx
 * (ver nginx.conf) — y wss:// automáticamente si la página va por HTTPS.
 */
function resolverWsUrl() {
  if (import.meta.env.VITE_WS_URL) return import.meta.env.VITE_WS_URL;
  const protocolo = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocolo}//${window.location.host}/ws`;
}

/**
 * @param {(event: object) => void} onMessage  callback cuando llega un evento
 * @returns {{ connected: boolean, error: string|null }}
 */
export function useWebSocket(onMessage) {
  const wsRef         = useRef(null);
  const retriesRef    = useRef(0);
  const timeoutRef    = useRef(null);
  const [connected, setConnected] = useState(false);
  const [error, setError]         = useState(null);

  const getToken = () => localStorage.getItem('es_token');

  const connect = useCallback(() => {
    const token = getToken();
    if (!token) return;

    // El token viaja como subprotocolo, NO en la query string: nginx
    // registra la URL completa en su access log ($request), y un JWT ahí
    // queda como credencial en texto plano en disco.
    const ws = new WebSocket(resolverWsUrl(), ['bearer', token]);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      setError(null);
      retriesRef.current = 0;
      console.log('[ElectriSys WS] Conectado');
    };

    ws.onmessage = (evt) => {
      try {
        const event = JSON.parse(evt.data);
        onMessage(event);
      } catch {
        console.warn('[ElectriSys WS] Mensaje no parseable:', evt.data);
      }
    };

    ws.onclose = (evt) => {
      setConnected(false);
      if (evt.code === 4001 || evt.code === 4002) {
        // Token inválido — no reintentar
        setError('Sesión WebSocket inválida. Vuelve a iniciar sesión.');
        return;
      }
      // Reconexión con backoff exponencial
      if (retriesRef.current < MAX_RETRIES) {
        const delay = BASE_RETRY_MS * Math.pow(2, retriesRef.current);
        retriesRef.current++;
        console.log(`[ElectriSys WS] Reconectando en ${delay}ms (intento ${retriesRef.current})`);
        timeoutRef.current = setTimeout(connect, delay);
      } else {
        setError('No se pudo reconectar al servidor de notificaciones.');
      }
    };

    ws.onerror = () => {
      setError('Error de conexión WebSocket');
    };
  }, [onMessage]);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(timeoutRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { connected, error };
}

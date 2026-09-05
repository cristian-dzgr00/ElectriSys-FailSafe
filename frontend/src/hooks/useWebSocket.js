// frontend/src/hooks/useWebSocket.js
// Hook para conectarse al servidor WebSocket de ElectriSys.
// Reconecta automáticamente con backoff exponencial.

import { useEffect, useRef, useCallback, useState } from 'react';

const WS_URL = import.meta.env.VITE_WS_URL ?? 'ws://localhost:8080';
const MAX_RETRIES     = 5;
const BASE_RETRY_MS   = 1_000;

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

  const getToken = () => localStorage.getItem('token');

  const connect = useCallback(() => {
    const token = getToken();
    if (!token) return;

    const url = `${WS_URL}?token=${encodeURIComponent(token)}`;
    const ws  = new WebSocket(url);
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

import { useState, useCallback, useRef } from 'react';

/**
 * useToast — Hook para sistema de notificaciones con undo opcional.
 */
export function useToast() {
  const [toasts, setToasts] = useState([]);
  const undoFnsRef = useRef({});

  const show = useCallback((msg, { type = 'success', duration = 3500, undoFn = null } = {}) => {
    const id = Date.now() + Math.random();
    if (undoFn) undoFnsRef.current[id] = undoFn;

    setToasts(prev => [...prev, { id, msg, type, undoFn: !!undoFn }]);

    const timer = setTimeout(() => {
      remove(id);
    }, duration);

    return () => clearTimeout(timer);
  }, []);

  const remove = useCallback((id) => {
    setToasts(prev => prev.filter(t => t.id !== id));
    delete undoFnsRef.current[id];
  }, []);

  const undo = useCallback((id) => {
    const fn = undoFnsRef.current[id];
    if (fn) { fn(); remove(id); }
  }, [remove]);

  return { toasts, show, remove, undo };
}

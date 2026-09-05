import { createContext, useContext } from 'react';
import { useToast } from '../hooks/useToast';
import ToastContainer from '../components/ToastContainer';

const ToastContext = createContext(null);

export function ToastProvider({ children }) {
  const { toasts, show, remove, undo } = useToast();
  return (
    <ToastContext.Provider value={show}>
      {children}
      <ToastContainer toasts={toasts} onRemove={remove} onUndo={undo} />
    </ToastContext.Provider>
  );
}

/** Hook: const toast = useToastContext();  toast('Guardado', { type:'success' }) */
export const useToastContext = () => useContext(ToastContext);

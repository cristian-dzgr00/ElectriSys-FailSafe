// frontend/src/context/VpnContext.jsx
// Estado de la VPN para toda la app.
//
// Las listas de Usuarios, Respaldos y Auditoría se pueden ver sin VPN, pero
// cualquier acción que modifique algo exige estar dentro (VpnMiddleware).
// Este contexto consulta GET /api/vpn/estado una vez tras iniciar sesión y
// deja a las pantallas avisar con un modal antes de abrir un formulario.
// Si la consulta falla se asume vpn=false: es el caso seguro, el backend
// igual rechaza la acción con 403 VPN_REQUIRED.

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { useAuth } from './AuthContext';
import { vpnService } from '../services/vpnService';
import VpnRequiredModal from '../components/VpnRequiredModal';

const VpnContext = createContext({
  vpn: false,
  exigirVpn: () => true,
  manejarErrorVpn: async () => false,
});

export function VpnProvider({ children }) {
  const { user } = useAuth();
  const [vpn, setVpn] = useState(false);
  const [aviso, setAviso] = useState(false);

  // Una consulta por sesión: se repite solo si cambia el usuario.
  useEffect(() => {
    if (!user) { setVpn(false); return undefined; }
    let activo = true;
    vpnService.estado()
      .then(r => { if (activo) setVpn(r.data?.vpn === true); })
      .catch(() => { if (activo) setVpn(false); });
    return () => { activo = false; };
  }, [user?.id]);

  const cerrarAviso = useCallback(() => setAviso(false), []);

  /** true si puede continuar; si no, muestra el aviso y devuelve false. */
  const exigirVpn = useCallback(() => {
    if (vpn) return true;
    setAviso(true);
    return false;
  }, [vpn]);

  /**
   * Para el catch de una llamada a la API: si fue un 403 con code
   * VPN_REQUIRED (p. ej. el estado cambió desde la carga) muestra el mismo
   * aviso y devuelve true, para que el llamador no muestre un error genérico.
   */
  const manejarErrorVpn = useCallback(async err => {
    if (err?.response?.status !== 403) return false;
    let datos = err.response.data;
    // Con responseType 'blob' el cuerpo del error llega como Blob.
    if (typeof Blob !== 'undefined' && datos instanceof Blob) {
      try { datos = JSON.parse(await datos.text()); } catch { datos = null; }
    }
    if (datos?.code !== 'VPN_REQUIRED') return false;
    setVpn(false);
    setAviso(true);
    return true;
  }, []);

  const valor = useMemo(() => ({ vpn, exigirVpn, manejarErrorVpn }), [vpn, exigirVpn, manejarErrorVpn]);

  return (
    <VpnContext.Provider value={valor}>
      {children}
      {aviso && <VpnRequiredModal onClose={cerrarAviso} />}
    </VpnContext.Provider>
  );
}

/** const { vpn, exigirVpn, manejarErrorVpn } = useVpn(); */
export const useVpn = () => useContext(VpnContext);

import { createContext, useContext, useState } from 'react';
import api from '../services/api';

const AuthContext = createContext(null);

/**
 * Decodifica un segmento JWT (base64url) respetando UTF-8.
 *
 * atob() por sí solo devuelve una cadena de bytes interpretada como
 * Latin-1: "José Muñoz" se leía "JosÃ© MuÃ±oz" al restaurar la sesión.
 * Además el JWT usa base64url ('-' y '_' en vez de '+' y '/', sin
 * relleno), que atob() no acepta tal cual.
 */
function decodificarSegmento(segmento) {
  const base64 = segmento.replace(/-/g, '+').replace(/_/g, '/');
  const relleno = base64.length % 4 ? '='.repeat(4 - (base64.length % 4)) : '';
  const binaria = atob(base64 + relleno);
  const bytes = Uint8Array.from(binaria, caracter => caracter.charCodeAt(0));
  return new TextDecoder('utf-8').decode(bytes);
}

function decodeToken(token) {
  try {
    const payload = JSON.parse(decodificarSegmento(token.split('.')[1]));
    if (payload.exp > Date.now() / 1000) {
      return {
        id:     payload.sub,
        nombre: payload.nombre,
        email:  payload.email,
        rol:    payload.rol,
      };
    }
  } catch {}
  return null;
}

// Setear header ANTES de cualquier render
const _t = localStorage.getItem('es_token');
if (_t) api.defaults.headers.common['Authorization'] = `Bearer ${_t}`;

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    const t = localStorage.getItem('es_token');
    return t ? decodeToken(t) : null;
  });
  const [token, setToken] = useState(() => localStorage.getItem('es_token'));
  const loading = false;

  const login = async (email, password) => {
    const { data } = await api.post('/auth/login', { email, password });
    localStorage.setItem('es_token', data.token);
    api.defaults.headers.common['Authorization'] = `Bearer ${data.token}`;
    setToken(data.token);
    setUser(data.user);
    return data.user;
  };

  const logout = () => {
    localStorage.removeItem('es_token');
    delete api.defaults.headers.common['Authorization'];
    setToken(null);
    setUser(null);
  };

  const isAdmin = () => user?.rol === 'admin' || user?.rol === 'dueno';

  return (
    <AuthContext.Provider value={{ user, token, loading, login, logout, isAdmin }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
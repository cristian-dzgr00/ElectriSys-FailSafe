import { createContext, useContext, useState } from 'react';
import api from '../services/api';

const AuthContext = createContext(null);

function decodeToken(token) {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]));
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
import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
  timeout: 10000,
});

api.interceptors.request.use(config => {
  const token = localStorage.getItem('es_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  res => res,
  err => {
    // Si el token expiró, limpiar sesión y redirigir al login
    if (err.response?.status === 401) {
      localStorage.removeItem('es_token');
      localStorage.removeItem('es_user');
      window.location.href = '/login';
    }
    return Promise.reject(err);
  }
);

export default api;

import api from './api';

export const ventasService = {
  listar:     (params = {}) => api.get('/ventas',            { params }),
  buscar:     (id)          => api.get(`/ventas/${id}`),
  crear:      (data)        => api.post('/ventas',            data),
  anular:     (id)          => api.put(`/ventas/${id}/anular`),
  resumenHoy: ()            => api.get('/ventas/resumen/hoy'),
};

export const repuestosService = {
  listar:     (params = {}) => api.get('/repuestos',         { params }),
  buscar:     (id)          => api.get(`/repuestos/${id}`),
  crear:      (data)        => api.post('/repuestos',         data),
  actualizar: (id, data)    => api.put(`/repuestos/${id}`,   data),
  eliminar:   (id)          => api.delete(`/repuestos/${id}`),
  // Sugerencias del microservicio propio de NLP (TF-IDF + coseno) y señal
  // de reabastecimiento. Responde 200 aun si el microservicio está caído,
  // con disponible:false — ver backend/src/routes/repuestos.php.
  recomendaciones:       (id)        => api.get(`/repuestos/${id}/recomendaciones`),
  // Señales de reabastecimiento de TODA una página en una sola llamada
  // (el backend resuelve las N con una consulta agrupada).
  senalesDemanda:        (ids)      => api.get('/repuestos/demanda/senales', { params: { ids: ids.join(',') } }),
  listarCompatibilidad:  (id)        => api.get(`/repuestos/${id}/compatibilidad`),
  agregarCompatibilidad: (id, data)  => api.post(`/repuestos/${id}/compatibilidad`, data),
  quitarCompatibilidad:  (id, vehId) => api.delete(`/repuestos/${id}/compatibilidad/${vehId}`),
};

export const clientesService = {
  listar:     (params = {}) => api.get('/clientes',          { params }),
  buscar:     (id)          => api.get(`/clientes/${id}`),
  crear:      (data)        => api.post('/clientes',          data),
  actualizar: (id, data)    => api.put(`/clientes/${id}`,    data),
  eliminar:   (id)          => api.delete(`/clientes/${id}`),
};

export const usuariosService = {
  listar:     ()            => api.get('/usuarios'),
  crear:      (data)        => api.post('/usuarios',          data),
  actualizar: (id, data)    => api.put(`/usuarios/${id}`,    data),
  eliminar:   (id)          => api.delete(`/usuarios/${id}`),
};

export const cotizacionesService = {
  listar:        (params = {}) => api.get('/cotizaciones',           { params }),
  buscar:        (id)          => api.get(`/cotizaciones/${id}`),
  crear:         (data)        => api.post('/cotizaciones',           data),
  cambiarEstado: (id, estado)  => api.put(`/cotizaciones/${id}/estado`, { estado }),
};

export const proveedoresService = {
  listar:     (params = {}) => api.get('/proveedores',       { params }),
  crear:      (data)        => api.post('/proveedores',       data),
  actualizar: (id, data)    => api.put(`/proveedores/${id}`, data),
  eliminar:   (id)          => api.delete(`/proveedores/${id}`),
};

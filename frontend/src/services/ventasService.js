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

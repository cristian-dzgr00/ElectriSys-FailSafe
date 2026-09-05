import api from './api';

export const vehiculosService = {
  listar:  (params = {}) => api.get('/vehiculos', { params }),
  marcas:  ()             => api.get('/vehiculos/marcas'),
  modelos: (marca)        => api.get('/vehiculos/modelos', { params: { marca } }),
  crear:   (data)         => api.post('/vehiculos', data),
};

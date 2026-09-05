import api from './api';

export const asistenteService = {
  consultar: (texto) => api.post('/asistente/consultar', { texto }),
};

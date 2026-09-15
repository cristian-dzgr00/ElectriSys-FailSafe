import api from './api';

export const asistenteService = {
  consultar: (texto, contextoPrevio) =>
    api.post('/asistente/consultar', contextoPrevio ? { texto, contexto_previo: contextoPrevio } : { texto }),
  enviarFeedback: (id, util) => api.patch(`/asistente/consultar/${id}/feedback`, { util }),
};

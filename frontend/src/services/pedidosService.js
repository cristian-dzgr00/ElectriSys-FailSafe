// frontend/src/services/pedidosService.js
// Pedidos a proveedor (órdenes de reabastecimiento).
// Mismo patrón que ventasService/repuestosService: el interceptor de
// api.js ya adjunta el JWT, acá solo se declaran las rutas.
//
// Todos estos endpoints exigen rol admin/dueno en el backend
// (RoleMiddleware en backend/src/routes/pedidos.php): si un vendedor
// llegara a llamarlos, recibe 403 aunque la UI le escondiera el menú.

import api from './api';

export const pedidosService = {
  listar:        (params = {}) => api.get('/pedidos', { params }),
  buscar:        (id)          => api.get(`/pedidos/${id}`),
  crear:         (data)        => api.post('/pedidos', data),
  // PATCH y no PUT: solo cambia el estado, no reemplaza el pedido entero.
  cambiarEstado: (id, estado)  => api.patch(`/pedidos/${id}/estado`, { estado }),
  // DELETE cancela (cambio de estado), no borra la fila — igual que anular
  // una venta. El historial de compras nunca se pierde.
  cancelar:      (id)          => api.delete(`/pedidos/${id}`),
};

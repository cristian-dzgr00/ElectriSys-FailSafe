// frontend/src/services/vpnService.js
// Estado de la conexión VPN según el backend.
//
// GET /api/vpn/estado responde { vpn: true|false } con la misma decisión que
// VpnMiddleware (solo REMOTE_ADDR). Requiere JWT pero no VPN.

import api from './api';

export const vpnService = {
  estado: () => api.get('/vpn/estado', { timeout: 5000 }),
};

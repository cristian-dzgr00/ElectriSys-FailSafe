// frontend/src/services/backupsService.js
// Respaldos de la base (Oracle Data Pump).
//
// El listado solo necesita JWT. Crear un respaldo y exportar el CSV además
// exigen VPN (ver VpnMiddleware): fuera de la VPN responden 403 con
// code 'VPN_REQUIRED', que la vista traduce en el aviso de VPN.

import api from './api';

export const backupsService = {
  listar: () => api.get('/admin/backups'),

  // timeout propio de 60 s, muy por encima de los 10 s que api.js usa para
  // todo lo demás: DBMS_DATAPUMP.OPEN crea la master table del job y
  // START_JOB espera a que arranque, lo que en esta base tarda ~11 s. Con
  // el timeout por defecto, el navegador abortaba a los 10 s y mostraba
  // "no se pudo iniciar" mientras el respaldo se estaba haciendo igual —
  // el peor error posible: decirle al usuario que falló algo que funcionó.
  crear:  () => api.post('/admin/backups', null, { timeout: 60000 }),

  // Arma un .zip con un .csv por tabla de negocio (no el .dmp real, ver
  // Backups.jsx). responseType 'blob' porque la respuesta es binaria, y un
  // timeout mayor porque leer todas las tablas puede tardar más que una
  // consulta normal.
  exportarCsv: () => api.get('/admin/backups/exportar-csv', { responseType: 'blob', timeout: 60000 }),
};

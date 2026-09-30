// desktop/preload.js
// Puente entre la pantalla de error local y el proceso principal.
//
// Es lo ÚNICO que el renderer puede llamar: contextIsolation está activo y
// nodeIntegration desactivado, así que la web del POS no tiene acceso a
// Node ni al sistema de archivos. Si el servidor estuviera comprometido,
// lo máximo que podría hacer desde acá es cambiar su propia dirección.

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electrisys', {
  guardarServidor: (url) => ipcRenderer.invoke('electrisys:guardar-servidor', url),
  reintentar:      ()    => ipcRenderer.invoke('electrisys:reintentar'),
});

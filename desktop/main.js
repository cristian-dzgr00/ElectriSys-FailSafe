// desktop/main.js
// Proceso principal de la aplicación de escritorio de ElectriSys POS.
//
// La app NO empaqueta el frontend: es un cliente que se conecta al servidor
// del POS, igual que lo haría un navegador. Esa decisión mantiene la
// arquitectura distribuida del proyecto —un backend, varias cajas— y evita
// el problema de tener que reinstalar el .exe en cada caja cada vez que
// cambia una pantalla. Lo que aporta frente a abrir Chrome es el arranque
// directo a pantalla completa sin barra de direcciones, un icono propio en
// la barra de tareas, y que el cajero no pueda navegar a otro sitio.
//
// La URL del servidor se guarda en el perfil del usuario (userData), así que
// cada caja puede apuntar a un servidor distinto sin recompilar.

const { app, BrowserWindow, Menu, dialog, shell, ipcMain } = require('electron');
const path = require('node:path');
const fs = require('node:fs');

// Servidor por defecto: el nginx del docker compose en la misma máquina.
// En producción se cambia desde el menú a https://<dominio>.
const URL_POR_DEFECTO = 'http://localhost';

const rutaConfig = () => path.join(app.getPath('userData'), 'config.json');

function leerConfig() {
  try {
    return JSON.parse(fs.readFileSync(rutaConfig(), 'utf8'));
  } catch {
    // Primera ejecución, archivo corrupto o borrado: se arranca con el
    // valor por defecto en vez de fallar. Nunca debe impedir abrir la caja.
    return { servidor: URL_POR_DEFECTO };
  }
}

function guardarConfig(config) {
  try {
    fs.mkdirSync(app.getPath('userData'), { recursive: true });
    fs.writeFileSync(rutaConfig(), JSON.stringify(config, null, 2), 'utf8');
    return true;
  } catch (e) {
    console.error('[ElectriSys] No se pudo guardar la configuración:', e.message);
    return false;
  }
}

/** Solo http/https y sin credenciales embebidas en la URL. */
function urlValida(texto) {
  try {
    const u = new URL(texto);
    return (u.protocol === 'http:' || u.protocol === 'https:') && !u.username && !u.password;
  } catch {
    return false;
  }
}

let ventana = null;
// Chromium emite did-fail-load una vez por reintento, así que un servidor
// caído lo dispara varias veces seguidas. Sin esta bandera, la pantalla de
// error se recarga sola tres veces y parpadea justo cuando el cajero está
// intentando leer qué pasó.
let mostrandoError = false;

function cargarServidor() {
  const { servidor } = leerConfig();
  mostrandoError = false;
  ventana.loadURL(servidor).catch(() => { /* lo maneja did-fail-load */ });
}

function crearVentana() {
  ventana = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 1024,
    minHeight: 700,
    show: false,                 // se muestra al estar lista, sin parpadeo blanco
    backgroundColor: '#121212',  // el mismo --bg-primary de la app
    icon: path.join(__dirname, 'assets', 'icon.png'),
    title: 'ElectriSys POS',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      // El renderer carga una web remota: aislarlo del sistema es
      // obligatorio, no opcional.
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  ventana.once('ready-to-show', () => ventana.show());

  // Diagnóstico: sin esto, un error de JavaScript del POS deja la ventana en
  // negro y no queda rastro en ningún lado — el operador solo ve una caja
  // vacía. Los errores del renderer se vuelcan a la consola del proceso
  // principal, que es lo que se ve al lanzar la app desde una terminal.
  ventana.webContents.on('console-message', (_e, nivel, mensaje, linea, fuente) => {
    if (nivel >= 2) console.error(`[renderer] ${mensaje}  (${fuente}:${linea})`);
  });
  ventana.webContents.on('render-process-gone', (_e, detalles) => {
    console.error('[renderer] el proceso de la vista murió:', detalles.reason);
  });

  // Si el servidor no responde, en vez de la pantalla de error de Chromium
  // se muestra una propia que explica qué pasa y deja cambiar la dirección.
  ventana.webContents.on('did-fail-load', (_e, codigo, descripcion, urlFallida) => {
    // -3 es ERR_ABORTED: lo dispara una navegación cancelada (por ejemplo al
    // recargar rápido), no es una caída del servidor.
    if (codigo === -3) return;
    if (mostrandoError) return;
    mostrandoError = true;
    console.error(`[ElectriSys] Fallo al cargar ${urlFallida}: ${descripcion} (${codigo})`);
    ventana.loadFile(path.join(__dirname, 'error.html'), {
      query: { servidor: leerConfig().servidor, motivo: descripcion },
    });
  });

  // Cualquier enlace externo se abre en el navegador del sistema: la ventana
  // de la caja se queda en el POS y no se puede usar para navegar.
  ventana.webContents.setWindowOpenHandler(({ url }) => {
    if (urlValida(url)) shell.openExternal(url);
    return { action: 'deny' };
  });

  cargarServidor();
}

async function pedirServidor() {
  const actual = leerConfig().servidor;
  const { response } = await dialog.showMessageBox(ventana, {
    type: 'question',
    title: 'Servidor del POS',
    message: 'Dirección del servidor',
    detail: `Actualmente: ${actual}\n\n` +
            'Para cambiarla, editá el archivo de configuración y reiniciá la aplicación:\n' +
            rutaConfig(),
    buttons: ['Cerrar', 'Abrir la carpeta de configuración', 'Reintentar conexión'],
    defaultId: 0,
    cancelId: 0,
  });

  if (response === 1) {
    guardarConfig(leerConfig());        // garantiza que el archivo exista
    shell.showItemInFolder(rutaConfig());
  } else if (response === 2) {
    cargarServidor();
  }
}

function construirMenu() {
  return Menu.buildFromTemplate([
    {
      label: 'Archivo',
      submenu: [
        { label: 'Servidor…', click: pedirServidor },
        { label: 'Reconectar', accelerator: 'F5', click: cargarServidor },
        // Recarga descartando la caché. Hace falta cuando se despliega una
        // versión nueva del POS y la caja sigue mostrando la anterior: sin
        // esto, la única salida era esperar a que la caché expirara sola.
        {
          label: 'Recargar sin caché',
          accelerator: 'CommandOrControl+Shift+R',
          click: () => ventana?.webContents.reloadIgnoringCache(),
        },
        { type: 'separator' },
        { label: 'Salir', accelerator: 'Alt+F4', role: 'quit' },
      ],
    },
    {
      label: 'Ver',
      submenu: [
        { label: 'Pantalla completa', accelerator: 'F11', role: 'togglefullscreen' },
        { type: 'separator' },
        { label: 'Acercar',  accelerator: 'CommandOrControl+Plus',  role: 'zoomIn' },
        { label: 'Alejar',   accelerator: 'CommandOrControl+-',     role: 'zoomOut' },
        { label: 'Tamaño normal', accelerator: 'CommandOrControl+0', role: 'resetZoom' },
        { type: 'separator' },
        // Útil en la sustentación para mostrar los eventos del WebSocket.
        { label: 'Herramientas de desarrollo', accelerator: 'F12', role: 'toggleDevTools' },
      ],
    },
    {
      label: 'Ayuda',
      submenu: [
        {
          label: 'Acerca de ElectriSys POS',
          click: () => dialog.showMessageBox(ventana, {
            type: 'info',
            title: 'ElectriSys POS',
            message: `ElectriSys POS ${app.getVersion()}`,
            detail: `Servidor: ${leerConfig().servidor}\n` +
                    `Configuración: ${rutaConfig()}\n\n` +
                    'Punto de venta de Electritorres.',
          }),
        },
      ],
    },
  ]);
}

// Una sola instancia: dos ventanas de la misma caja apuntando al mismo
// servidor solo genera confusión sobre cuál tiene la venta en curso.
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (ventana) {
      if (ventana.isMinimized()) ventana.restore();
      ventana.focus();
    }
  });

  app.whenReady().then(() => {
    Menu.setApplicationMenu(construirMenu());
    crearVentana();

    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) crearVentana();
    });
  });

  app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit();
  });

  // Peticiones de la pantalla de error (error.html vía preload).
  ipcMain.handle('electrisys:guardar-servidor', (_e, url) => {
    if (!urlValida(url)) return { ok: false, error: 'La dirección debe empezar por http:// o https://' };
    if (!guardarConfig({ servidor: url })) return { ok: false, error: 'No se pudo guardar la configuración.' };
    cargarServidor();
    return { ok: true };
  });

  ipcMain.handle('electrisys:reintentar', () => { cargarServidor(); });
}
